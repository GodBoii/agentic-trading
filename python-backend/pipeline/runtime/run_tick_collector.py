import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from io import StringIO
from contextlib import redirect_stdout
from typing import DefaultDict, Dict, List

from dhanhq import MarketFeed

from pipeline.config import PipelineConfig
from pipeline.services.dhan_service import DhanService
from pipeline.services.market_time_service import MarketTimeService
from pipeline.services.storage_service import StorageService


class TickCollector:
    def __init__(self, config: PipelineConfig):
        self.config = config
        self.dhan = DhanService(config)
        self.market_time = MarketTimeService(config)
        self.tick_windows: DefaultDict[int, deque] = defaultdict(deque)
        self.last_save = 0.0

    def load_stage1_instruments(self) -> List[tuple]:
        market_date = self.market_time.market_date_str()
        stage1_path = self.config.stage1_daily_path(market_date)
        payload = StorageService.load_snapshot(stage1_path)
        if not payload:
            raise FileNotFoundError(
                f"Stage 1 snapshot not found: {stage1_path}. Run Stage 1 before the tick collector."
            )
        stocks = payload.get("stocks", [])
        return [(MarketFeed.BSE, str(stock["security_id"]), MarketFeed.Ticker) for stock in stocks]

    def prune(self) -> None:
        cutoff = time.time() - 3600
        for security_id in list(self.tick_windows.keys()):
            window = self.tick_windows[security_id]
            while window and window[0] < cutoff:
                window.popleft()

    def save_stats(self) -> None:
        now = time.time()
        if now - self.last_save < self.config.tick_stats_save_interval_seconds:
            return

        self.prune()
        payload = {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "tick_stats": {
                str(security_id): {"ticks_last_hour": len(window)}
                for security_id, window in self.tick_windows.items()
            },
        }
        StorageService.save_snapshot(self.config.tick_stats_latest_path, payload)
        StorageService.save_snapshot(
            self.config.tick_stats_daily_path(self.market_time.market_date_str()),
            payload,
        )
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
        self.save_stats()

    def run(self) -> None:
        instruments = self.load_stage1_instruments()
        print(f"Starting tick collector for {len(instruments)} Stage 1 stocks")
        if not instruments:
            print("Tick collector is idle because Stage 1 has no survivors yet.")
            while True:
                self.save_stats()
                time.sleep(self.config.tick_stats_save_interval_seconds)

        while True:
            try:
                sink = StringIO()
                with redirect_stdout(sink):
                    feed = self.dhan.build_marketfeed(instruments)
                    feed.run_forever()
                while True:
                    packet = feed.get_data()
                    if isinstance(packet, dict):
                        self.record_packet(packet)
            except Exception as exc:
                print(f"Tick collector reconnecting after error: {exc}")
                time.sleep(2)


if __name__ == "__main__":
    TickCollector(PipelineConfig()).run()
