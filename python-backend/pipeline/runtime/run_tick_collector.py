import hashlib
import time
from collections import defaultdict, deque
from contextlib import redirect_stdout
from datetime import datetime, timezone
from io import StringIO
from typing import DefaultDict, Dict, List, Optional, Tuple

from dhanhq import MarketFeed

from pipeline.config import PipelineConfig
from pipeline.services.dhan_service import DhanService
from pipeline.services.market_time_service import MarketTimeService
from pipeline.services.storage_service import StorageService


class Stage1UniverseChanged(RuntimeError):
    pass


class TickCollector:
    WINDOW_10_MIN_SECONDS = 10 * 60
    WINDOW_30_MIN_SECONDS = 30 * 60
    WINDOW_60_MIN_SECONDS = 60 * 60

    def __init__(self, config: PipelineConfig):
        self.config = config
        self.dhan = DhanService(config)
        self.market_time = MarketTimeService(config)
        self.tick_windows: DefaultDict[int, deque] = defaultdict(deque)
        self.tick_totals_today: DefaultDict[int, int] = defaultdict(int)
        self.last_save = 0.0
        self.last_history_save = 0.0
        self.last_refresh_check = 0.0
        self.current_market_date: Optional[str] = None
        self.current_security_ids: Tuple[int, ...] = tuple()
        self.current_instruments: List[tuple] = []
        self.collector_started_at = datetime.now(timezone.utc)

    def _payload_market_date(self, payload: Optional[Dict]) -> Optional[str]:
        if not payload:
            return None
        summary_market_date = payload.get("summary", {}).get("market_date")
        if summary_market_date:
            return str(summary_market_date)
        return StorageService.snapshot_market_date(payload, self.config.market_timezone)

    def _load_stage1_payload_for_current_date(self) -> Optional[Dict]:
        market_date = self.market_time.market_date_str()
        stage1_path = self.config.stage1_daily_path(market_date)
        payload = StorageService.load_snapshot(stage1_path)
        if payload:
            return payload

        latest_payload = StorageService.load_snapshot(self.config.stage1_latest_path)
        if self._payload_market_date(latest_payload) == market_date:
            return latest_payload
        return None

    def _build_instruments(self, payload: Dict) -> Tuple[Tuple[int, ...], List[tuple]]:
        stocks = payload.get("stocks", [])
        security_ids = tuple(sorted(int(stock["security_id"]) for stock in stocks))
        instruments = [
            (MarketFeed.BSE, str(stock["security_id"]), MarketFeed.Ticker)
            for stock in stocks
        ]
        return security_ids, instruments

    def _compute_universe_signature(self, security_ids: Tuple[int, ...]) -> str:
        joined = ",".join(str(security_id) for security_id in security_ids)
        return hashlib.sha1(joined.encode("ascii")).hexdigest()[:16]

    def _refresh_stage1_instruments(self, force: bool = False) -> List[tuple]:
        now = time.time()
        if (
            not force
            and self.current_instruments
            and now - self.last_refresh_check < self.config.tick_collector_refresh_check_interval_seconds
        ):
            return self.current_instruments

        self.last_refresh_check = now
        payload = self._load_stage1_payload_for_current_date()
        if not payload:
            if self.current_instruments:
                return self.current_instruments
            raise FileNotFoundError("Stage 1 snapshot not found for current market date.")

        market_date = self.market_time.market_date_str()
        security_ids, instruments = self._build_instruments(payload)

        if not self.current_instruments:
            self.current_market_date = market_date
            self.current_security_ids = security_ids
            self.current_instruments = instruments
            self.collector_started_at = datetime.now(timezone.utc)
            return instruments

        if market_date != self.current_market_date or security_ids != self.current_security_ids:
            self.current_market_date = market_date
            self.current_security_ids = security_ids
            self.current_instruments = instruments
            self.collector_started_at = datetime.now(timezone.utc)
            self.tick_windows.clear()
            self.tick_totals_today.clear()
            self.last_save = 0.0
            self.last_history_save = 0.0
            raise Stage1UniverseChanged(
                f"new Stage 1 universe detected for {market_date} with {len(instruments)} instrument(s)"
            )

        return self.current_instruments

    def prune(self) -> None:
        cutoff = time.time() - self.WINDOW_60_MIN_SECONDS
        for security_id in list(self.tick_windows.keys()):
            window = self.tick_windows[security_id]
            while window and window[0] < cutoff:
                window.popleft()

    def _build_tick_metrics(self) -> Dict[str, Dict[str, int]]:
        now = time.time()
        cutoff_10 = now - self.WINDOW_10_MIN_SECONDS
        cutoff_30 = now - self.WINDOW_30_MIN_SECONDS
        metrics: Dict[str, Dict[str, int]] = {}

        for security_id in self.current_security_ids:
            window = self.tick_windows.get(security_id, deque())
            ticks_last_10min = sum(1 for ts in window if ts >= cutoff_10)
            ticks_last_30min = sum(1 for ts in window if ts >= cutoff_30)
            ticks_last_60min = len(window)
            metrics[str(security_id)] = {
                "ticks_last_10min": ticks_last_10min,
                "ticks_last_30min": ticks_last_30min,
                "ticks_last_60min": ticks_last_60min,
                "ticks_today": int(self.tick_totals_today.get(security_id, 0)),
            }

        return metrics

    def _build_snapshot_payload(self) -> Dict:
        collector_uptime_seconds = max(
            0.0,
            (datetime.now(timezone.utc) - self.collector_started_at).total_seconds(),
        )
        return {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "collector_started_at_utc": self.collector_started_at.isoformat(),
            "collector_uptime_seconds": round(collector_uptime_seconds, 1),
            "collector_universe_size": len(self.current_security_ids),
            "collector_universe_signature": self._compute_universe_signature(self.current_security_ids),
            "tick_stats": self._build_tick_metrics(),
        }

    def _append_history_checkpoint(self, payload: Dict) -> None:
        now = time.time()
        if now - self.last_history_save < self.config.tick_stats_history_save_interval_seconds:
            return

        market_date = self.market_time.market_date_str()
        history_path = self.config.tick_stats_history_daily_path(market_date)
        history_payload = StorageService.load_snapshot(history_path) or {
            "stage": "tick_stats_history",
            "market_date": market_date,
            "collector_started_at_utc": payload.get("collector_started_at_utc"),
            "collector_universe_size": payload.get("collector_universe_size"),
            "collector_universe_signature": payload.get("collector_universe_signature"),
            "checkpoints": [],
        }

        history_payload["market_date"] = market_date
        history_payload["collector_started_at_utc"] = payload.get("collector_started_at_utc")
        history_payload["collector_universe_size"] = payload.get("collector_universe_size")
        history_payload["collector_universe_signature"] = payload.get("collector_universe_signature")
        history_payload["generated_at_utc"] = payload.get("generated_at_utc")
        history_payload.setdefault("checkpoints", []).append(
            {
                "generated_at_utc": payload.get("generated_at_utc"),
                "collector_uptime_seconds": payload.get("collector_uptime_seconds"),
                "tick_stats": payload.get("tick_stats", {}),
            }
        )

        StorageService.save_snapshot(self.config.tick_stats_history_latest_path, history_payload)
        StorageService.save_snapshot(history_path, history_payload)
        self.last_history_save = now

    def save_stats(self) -> None:
        now = time.time()
        if now - self.last_save < self.config.tick_stats_save_interval_seconds:
            return

        self.prune()
        payload = self._build_snapshot_payload()
        StorageService.save_snapshot(self.config.tick_stats_latest_path, payload)
        StorageService.save_snapshot(
            self.config.tick_stats_daily_path(self.market_time.market_date_str()),
            payload,
        )
        self._append_history_checkpoint(payload)
        self.last_save = now
        print(f"Saved tick stats for {len(payload['tick_stats'])} securities")

    def record_packet(self, packet: Dict) -> None:
        security_id = packet.get("security_id")
        if security_id is None:
            return
        try:
            security_id = int(security_id)
        except Exception:
            return

        self.tick_windows[security_id].append(time.time())
        self.tick_totals_today[security_id] += 1
        self.save_stats()

    def _close_feed(self, feed) -> None:
        if feed is None:
            return
        for method_name in ["close_connection", "disconnect"]:
            try:
                getattr(feed, method_name)()
                return
            except Exception:
                continue

    def run(self) -> None:
        while True:
            feed = None
            try:
                instruments = self._refresh_stage1_instruments(force=True)
                if not instruments:
                    print("Tick collector is idle because Stage 1 has no survivors yet.")
                    while True:
                        self._refresh_stage1_instruments(force=True)
                        self.save_stats()
                        time.sleep(self.config.tick_stats_save_interval_seconds)

                print(
                    f"Starting tick collector for {len(instruments)} Stage 1 stocks "
                    f"(market_date={self.current_market_date})"
                )
                sink = StringIO()
                with redirect_stdout(sink):
                    feed = self.dhan.build_marketfeed(instruments)
                    feed.run_forever()

                while True:
                    self._refresh_stage1_instruments()
                    packet = feed.get_data()
                    if isinstance(packet, dict):
                        self.record_packet(packet)
            except Stage1UniverseChanged as exc:
                self._close_feed(feed)
                print(f"Tick collector reloading after Stage 1 snapshot change: {exc}")
                time.sleep(1)
            except FileNotFoundError as exc:
                self._close_feed(feed)
                print(f"Tick collector waiting for Stage 1 snapshot: {exc}")
                time.sleep(self.config.tick_stats_save_interval_seconds)
            except Exception as exc:
                self._close_feed(feed)
                print(f"Tick collector reconnecting after error: {exc}")
                time.sleep(2)


if __name__ == "__main__":
    TickCollector(PipelineConfig()).run()
