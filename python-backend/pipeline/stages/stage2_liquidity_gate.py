from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
from threading import Lock
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from pipeline.config import PipelineConfig
from pipeline.services.dhan_service import DhanService
from pipeline.services.market_time_service import MarketTimeService
from pipeline.services.storage_service import StorageService


class Stage2LiquidityGate:
    """
    Live-market stage.
    Uses Stage 1 survivors + live quote data + rolling tick stats + intraday minute history.
    """

    def __init__(self, config: Optional[PipelineConfig] = None):
        self.config = config or PipelineConfig()
        self.dhan = DhanService(self.config)
        self.market_time = MarketTimeService(self.config)
        self.lock = Lock()
        self.progress = 0
        self.last_reported_decile = 0
        self.last_heartbeat_ts = 0.0
        self.filter_reasons: Counter[str] = Counter()
        self.fetch_failure_reasons: Counter[str] = Counter()

    def _build_stage2_filters_summary(self) -> Dict[str, Any]:
        return {
            "max_spread_percent": self.config.stage2_max_spread_percent,
            "min_ticks_last_10min": self.config.stage2_min_ticks_last_10min,
            "min_time_of_day_rvol": self.config.stage2_min_rvol,
            "min_tick_stats_coverage_ratio": self.config.stage2_min_tick_stats_coverage_ratio,
            "max_tick_stats_staleness_seconds": self.config.stage2_max_tick_stats_staleness_seconds,
            "min_tick_collector_warmup_seconds": self.config.stage2_min_tick_collector_warmup_seconds,
        }

    def _compute_universe_signature(self, security_ids: Set[int]) -> str:
        joined = ",".join(str(security_id) for security_id in sorted(security_ids))
        return hashlib.sha1(joined.encode("ascii")).hexdigest()[:16]

    def _save_payload(self, payload: Dict[str, Any]) -> None:
        StorageService.save_snapshot(self.config.stage2_latest_path, payload)
        daily_path = self.config.stage2_daily_path(self.market_time.market_date_str())
        StorageService.save_snapshot(daily_path, payload)

    def _log_gate_result(self, gate: str, ok: bool, detail: str) -> None:
        status = "PASS" if ok else "WAIT"
        print(f"Stage 2 gate [{gate}]: {status} | {detail}")

    def _summarize_numeric_series(self, values: List[int]) -> Dict[str, Any]:
        if not values:
            return {
                "count": 0,
                "min": None,
                "median": None,
                "p90": None,
                "max": None,
                "avg": None,
            }

        ordered = sorted(values)
        count = len(ordered)

        def percentile(pct: float) -> int:
            index = int(round((count - 1) * pct))
            return ordered[index]

        return {
            "count": count,
            "min": ordered[0],
            "median": percentile(0.50),
            "p90": percentile(0.90),
            "max": ordered[-1],
            "avg": round(sum(ordered) / count, 2),
        }

    def _summarize_tick_activity(self, tick_map: Dict[int, Dict[str, Any]]) -> Dict[str, Any]:
        series: Dict[str, List[int]] = {
            "ticks_last_10min": [],
            "ticks_last_30min": [],
            "ticks_last_60min": [],
            "ticks_today": [],
        }

        for item in tick_map.values():
            for key in series:
                try:
                    value = item.get(key)
                    if value is None:
                        continue
                    series[key].append(int(value))
                except Exception:
                    continue

        return {key: self._summarize_numeric_series(values) for key, values in series.items()}

    def _summarize_quote_map(self, quote_map: Dict[int, Dict[str, Any]]) -> Dict[str, int]:
        spread_available = 0
        spread_missing = 0
        last_price_available = 0

        for quote_item in quote_map.values():
            if self._compute_spread_percent(quote_item) is None:
                spread_missing += 1
            else:
                spread_available += 1

            if quote_item.get("last_price") is not None or quote_item.get("LTP") is not None:
                last_price_available += 1

        return {
            "quotes": len(quote_map),
            "spread_available": spread_available,
            "spread_missing": spread_missing,
            "last_price_available": last_price_available,
        }

    def _build_skip_payload(
        self,
        status: str,
        input_count: int,
        data_retrieved: int = 0,
        failed_fetch: int = 0,
        extra_summary: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        summary = {
            "input_stage1_count": input_count,
            "data_retrieved": data_retrieved,
            "failed_fetch": failed_fetch,
            "stage2_passed": 0,
            "status": status,
            "stage2_filters": self._build_stage2_filters_summary(),
            "requirements": {
                "tick_collector_required": True,
                "live_market_required": True,
            },
        }
        if extra_summary:
            summary.update(extra_summary)

        payload = StorageService.build_payload("stage2_liquidity_gate", summary, "stocks", [])
        self._save_payload(payload)
        return payload

    def _payload_market_date(self, payload: Optional[Dict[str, Any]]) -> Optional[str]:
        if not payload:
            return None
        summary_market_date = payload.get("summary", {}).get("market_date")
        if summary_market_date:
            return str(summary_market_date)
        return StorageService.snapshot_market_date(payload, self.config.market_timezone)

    def _load_stage1_universe(self) -> List[Dict[str, Any]]:
        market_date = self.market_time.market_date_str()
        stage1_path = self.config.stage1_daily_path(market_date)
        payload = StorageService.load_snapshot(stage1_path)

        if not payload:
            latest_payload = StorageService.load_snapshot(self.config.stage1_latest_path)
            if self._payload_market_date(latest_payload) == market_date:
                payload = latest_payload
                print(
                    f"Using latest Stage 1 snapshot for current market date {market_date} "
                    f"from {self.config.stage1_latest_path.name}"
                )

        if not payload:
            raise FileNotFoundError(
                f"Stage 1 snapshot not found: {stage1_path}. Run Stage 1 before Stage 2."
            )
        return payload.get("stocks", [])

    def _parse_generated_at_utc(self, payload: Optional[Dict[str, Any]]) -> Optional[datetime]:
        if not payload:
            return None
        generated_at = payload.get("generated_at_utc")
        if not generated_at:
            return None
        try:
            dt = datetime.fromisoformat(str(generated_at).replace("Z", "+00:00"))
        except ValueError:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    def _load_tick_stats(
        self,
        expected_security_ids: Optional[Set[int]] = None,
    ) -> Tuple[Dict[int, Dict[str, Any]], Dict[str, Any]]:
        market_date = self.market_time.market_date_str()
        payload = None
        source_name = None

        tick_stats_path = self.config.tick_stats_daily_path(market_date)
        daily_payload = StorageService.load_snapshot(tick_stats_path)
        if self._payload_market_date(daily_payload) == market_date:
            payload = daily_payload
            source_name = tick_stats_path.name

        if not payload:
            latest_payload = StorageService.load_snapshot(self.config.tick_stats_latest_path)
            if StorageService.snapshot_market_date(latest_payload, self.config.market_timezone) == market_date:
                payload = latest_payload
                source_name = self.config.tick_stats_latest_path.name

        if not payload:
            return {}, {
                "source": None,
                "age_seconds": None,
                "collector_uptime_seconds": None,
                "coverage_count": 0,
                "coverage_ratio": 0.0,
                "generated_at_utc": None,
                "collector_started_at_utc": None,
                "collector_universe_size": None,
                "collector_universe_signature": None,
            }

        stats = payload.get("tick_stats", {})
        parsed: Dict[int, Dict[str, Any]] = {}
        for raw_security_id, item in stats.items():
            try:
                parsed[int(raw_security_id)] = item
            except Exception:
                continue

        coverage_count = 0
        coverage_ratio = 0.0
        if expected_security_ids:
            coverage_count = len(expected_security_ids.intersection(parsed.keys()))
            coverage_ratio = coverage_count / len(expected_security_ids) if expected_security_ids else 0.0

        generated_at = self._parse_generated_at_utc(payload)
        collector_started_at = self._parse_generated_at_utc(
            {"generated_at_utc": payload.get("collector_started_at_utc")}
        )
        age_seconds = None
        if generated_at is not None:
            age_seconds = max(0.0, (datetime.now(timezone.utc) - generated_at).total_seconds())
        collector_uptime_seconds = None
        if collector_started_at is not None:
            collector_uptime_seconds = max(
                0.0,
                (datetime.now(timezone.utc) - collector_started_at).total_seconds(),
            )

        metadata = {
            "source": source_name,
            "age_seconds": round(age_seconds, 1) if age_seconds is not None else None,
            "collector_uptime_seconds": (
                round(collector_uptime_seconds, 1)
                if collector_uptime_seconds is not None
                else None
            ),
            "coverage_count": coverage_count,
            "coverage_ratio": round(coverage_ratio, 4),
            "generated_at_utc": generated_at.isoformat() if generated_at is not None else None,
            "collector_started_at_utc": (
                collector_started_at.isoformat() if collector_started_at is not None else None
            ),
            "collector_universe_size": payload.get("collector_universe_size"),
            "collector_universe_signature": payload.get("collector_universe_signature"),
            "history_source": self.config.tick_stats_history_daily_path(market_date).name,
        }
        return parsed, metadata

    def _chunk_ids(self, items: List[Dict[str, Any]], size: int) -> List[List[Dict[str, Any]]]:
        return [items[i:i + size] for i in range(0, len(items), size)]

    def _log_progress(self, total: int) -> None:
        with self.lock:
            self.progress += 1
            completed_pct = int((self.progress / total) * 100) if total else 100
            decile = min(10, completed_pct // 10)
            now = time.time()
            if now - self.last_heartbeat_ts >= 30:
                self.last_heartbeat_ts = now
                print(f"Stage 2 still running... {self.progress}/{total} processed")
            if decile > self.last_reported_decile:
                self.last_reported_decile = decile
                print(f"Stage 2 {decile * 10}% done... ({self.progress}/{total})")

    def _fetch_live_quotes(self, stocks: List[Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
        batches = self._chunk_ids(stocks, self.config.stage2_quote_batch_size)
        live_quotes: Dict[int, Dict[str, Any]] = {}
        print(f"Fetching Stage 2 live quote snapshots in {len(batches)} batch(es)...")

        for index, batch in enumerate(batches, 1):
            batch_ids = [int(stock["security_id"]) for stock in batch]
            quote_map = self.dhan.fetch_quote_batch(batch_ids)
            live_quotes.update(quote_map)
            print(f"  Quote batch {index}/{len(batches)} complete")

        return live_quotes

    def _first_price_from_levels(self, levels: Any, candidate_keys: List[str]) -> Optional[float]:
        if not isinstance(levels, list):
            return None

        for level in levels:
            if not isinstance(level, dict):
                continue
            for key in candidate_keys:
                raw_value = level.get(key)
                if raw_value in (None, "", 0, 0.0):
                    continue
                try:
                    value = float(raw_value)
                except Exception:
                    continue
                if value > 0:
                    return value
        return None

    def _first_price_from_quote(self, quote_item: Dict[str, Any], candidate_keys: List[str]) -> Optional[float]:
        for key in candidate_keys:
            raw_value = quote_item.get(key)
            if raw_value in (None, "", 0, 0.0):
                continue
            try:
                value = float(raw_value)
            except Exception:
                continue
            if value > 0:
                return value
        return None

    def _compute_spread_percent(self, quote_item: Dict[str, Any]) -> Optional[float]:
        bid_price = None
        ask_price = None
        depth = quote_item.get("depth") or quote_item.get("market_depth")

        if isinstance(depth, dict):
            bid_price = self._first_price_from_levels(
                depth.get("buy") or depth.get("bids") or [],
                ["price", "bid_price", "bidPrice", "best_bid_price"],
            )
            ask_price = self._first_price_from_levels(
                depth.get("sell") or depth.get("asks") or [],
                ["price", "ask_price", "askPrice", "best_ask_price"],
            )
        elif isinstance(depth, list):
            first_level = depth[0] if depth else {}
            if isinstance(first_level, dict):
                bid_price = self._first_price_from_quote(
                    first_level,
                    ["bid_price", "bidPrice", "best_bid_price", "price"],
                )
                ask_price = self._first_price_from_quote(
                    first_level,
                    ["ask_price", "askPrice", "best_ask_price", "price"],
                )

        if bid_price is None:
            bid_price = self._first_price_from_quote(
                quote_item,
                ["best_bid_price", "bid_price", "bidPrice"],
            )
        if ask_price is None:
            ask_price = self._first_price_from_quote(
                quote_item,
                ["best_ask_price", "ask_price", "askPrice"],
            )

        if bid_price is None or ask_price is None:
            return None

        mid = (bid_price + ask_price) / 2
        if mid <= 0:
            return None
        return ((ask_price - bid_price) / mid) * 100

    def _normalize_failure_reason(self, resp: Optional[Dict[str, Any]]) -> str:
        if not resp:
            return "empty_response"

        remarks = resp.get("remarks")
        if isinstance(remarks, dict):
            parts = [remarks.get("error_code"), remarks.get("error_type"), remarks.get("error_message")]
            text = " | ".join(str(part) for part in parts if part)
            if text:
                return text
        elif remarks:
            return str(remarks)
        return "unknown_failure"

    def _record_fetch_failure(self, reason: str) -> None:
        with self.lock:
            self.fetch_failure_reasons[reason] += 1

    def _record_filter_reason(self, reason: str) -> None:
        with self.lock:
            self.filter_reasons[reason] += 1

    def _process_stock(
        self,
        stock: Dict[str, Any],
        quote_map: Dict[int, Dict[str, Any]],
        tick_map: Dict[int, Dict[str, Any]],
        idx: int,
        total: int,
    ) -> Tuple[Optional[Dict[str, Any]], bool]:
        security_id = int(stock["security_id"])
        print(f"Stage 2 processing {stock.get('symbol') or security_id} ({security_id})...")
        quote_item = quote_map.get(security_id)
        if not quote_item:
            self._record_fetch_failure("quote_missing")
            print(f"Stage 2 skip {security_id}: no live quote found")
            self._log_progress(total)
            return None, False

        spread_percent = self._compute_spread_percent(quote_item)
        last_price = quote_item.get("last_price") or quote_item.get("LTP")
        volume = quote_item.get("volume")
        intraday_value_cr = None
        if last_price is not None and volume is not None:
            intraday_value_cr = (float(last_price) * float(volume)) / 10000000

        intraday_resp = self.dhan.fetch_intraday_history(
            security_id,
            days=5,
            interval=1,
            exchange_segment="BSE_EQ",
            instrument_candidates=[
                stock.get("instrument"),
                "EQUITY",
            ],
        )
        if not intraday_resp or str(intraday_resp.get("status", "")).lower() != "success":
            reason = self._normalize_failure_reason(intraday_resp)
            self._record_fetch_failure(f"intraday_history_failed::{reason}")
            print(f"Stage 2 skip {security_id}: intraday history fetch failed")
            self._log_progress(total)
            return None, False

        intraday_frame = self.dhan.intraday_response_to_df(intraday_resp)
        if intraday_frame.empty:
            self._record_fetch_failure("intraday_history_empty")
            print(f"Stage 2 skip {security_id}: intraday history frame empty")
            self._log_progress(total)
            return None, False

        rvol = self.dhan.compute_time_of_day_rvol(intraday_frame)
        tick_info = tick_map.get(security_id, {})
        ticks_last_10min = tick_info.get("ticks_last_10min")
        ticks_last_30min = tick_info.get("ticks_last_30min")
        ticks_last_60min = tick_info.get("ticks_last_60min")
        ticks_today = tick_info.get("ticks_today")

        record = {
            "security_id": security_id,
            "symbol": stock.get("symbol"),
            "display_name": stock.get("display_name"),
            "price": float(last_price) if last_price is not None else stock.get("price"),
            "adv_20_cr": stock.get("adv_20_cr"),
            "atr_percent": stock.get("atr_percent"),
            "spread_percent": round(spread_percent, 4) if spread_percent is not None else None,
            "ticks_last_10min": ticks_last_10min,
            "ticks_last_30min": ticks_last_30min,
            "ticks_last_60min": ticks_last_60min,
            "ticks_today": ticks_today,
            "time_of_day_rvol": round(rvol, 3) if rvol is not None else None,
            "intraday_value_cr": round(intraday_value_cr, 2) if intraday_value_cr is not None else None,
            "stage2_reason": None,
            "generated_at": datetime.now().isoformat(),
        }

        passed = True
        if spread_percent is None:
            record["stage2_reason"] = "spread_unavailable"
            passed = False
        elif spread_percent > self.config.stage2_max_spread_percent:
            record["stage2_reason"] = "spread"
            passed = False
        elif ticks_last_10min is None:
            record["stage2_reason"] = "tick_rate_unavailable"
            passed = False
        elif int(ticks_last_10min) < self.config.stage2_min_ticks_last_10min:
            record["stage2_reason"] = "tick_rate"
            passed = False
        elif rvol is None:
            record["stage2_reason"] = "time_of_day_rvol_unavailable"
            passed = False
        elif rvol < self.config.stage2_min_rvol:
            record["stage2_reason"] = "time_of_day_rvol"
            passed = False

        if not passed and record["stage2_reason"]:
            self._record_filter_reason(record["stage2_reason"])

        status_text = "PASS" if passed else f"FILTERED ({record['stage2_reason']})"
        print(
            f"Stage 2 result {security_id}: {status_text} | "
            f"spread={record['spread_percent']} "
            f"ticks10={ticks_last_10min} "
            f"ticks30={ticks_last_30min} "
            f"ticks60={ticks_last_60min} "
            f"rvol={record['time_of_day_rvol']}"
        )
        self._log_progress(total)

        return record, passed

    def run(self, max_stocks: Optional[int] = None, workers: Optional[int] = None) -> Dict[str, Any]:
        print("=" * 60)
        print("STAGE 2 - HARD LIQUIDITY GATE (LIVE MARKET)")
        print("=" * 60)
        print(f"Current market time: {self.market_time.market_status_text()}")

        workers = workers or self.config.stage2_workers
        self.progress = 0
        self.last_reported_decile = 0
        self.last_heartbeat_ts = time.time()
        self.filter_reasons = Counter()
        self.fetch_failure_reasons = Counter()
        print("Stage 2 execution plan:")
        print("  1. Load Stage 1 survivors for current market date")
        print("  2. Validate tick stats freshness, warmup, coverage, and universe sync")
        print("  3. Fetch live quote snapshots and inspect spread availability")
        print("  4. Fetch intraday minute history for each stock")
        print("  5. Apply spread, tick-rate, and RVOL filters")

        stage1_stocks = self._load_stage1_universe()
        if max_stocks:
            stage1_stocks = stage1_stocks[:max_stocks]
            print(f"TEST MODE: limiting Stage 2 to first {max_stocks} Stage 1 stocks")
        print(f"Loaded {len(stage1_stocks)} Stage 1 survivor(s) for Stage 2")
        print(
            "Stage 2 thresholds: "
            f"spread<={self.config.stage2_max_spread_percent}%, "
            f"ticks/10min>={self.config.stage2_min_ticks_last_10min}, "
            f"rvol>={self.config.stage2_min_rvol}"
        )

        if not stage1_stocks:
            payload = self._build_skip_payload("no_stage1_stocks", 0)
            print("Stage 2 skipped because Stage 1 produced zero survivors.")
            return payload

        expected_security_ids = {int(stock["security_id"]) for stock in stage1_stocks}
        expected_universe_signature = self._compute_universe_signature(expected_security_ids)
        tick_map, tick_meta = self._load_tick_stats(expected_security_ids)
        print(
            f"Loaded tick stats for {len(tick_map)} security id(s) "
            f"from {tick_meta.get('source') or 'none'} "
            f"(coverage={tick_meta.get('coverage_count')}/{len(expected_security_ids)}, "
            f"age={tick_meta.get('age_seconds')}s, "
            f"collector_uptime={tick_meta.get('collector_uptime_seconds')}s)"
        )
        tick_activity = self._summarize_tick_activity(tick_map)
        print(
            "Stage 2 tick activity snapshot [10m]: "
            f"count={tick_activity['ticks_last_10min']['count']}, "
            f"min={tick_activity['ticks_last_10min']['min']}, "
            f"median={tick_activity['ticks_last_10min']['median']}, "
            f"p90={tick_activity['ticks_last_10min']['p90']}, "
            f"max={tick_activity['ticks_last_10min']['max']}, "
            f"avg={tick_activity['ticks_last_10min']['avg']}"
        )
        print(
            "Stage 2 tick activity snapshot [60m/day]: "
            f"ticks60_median={tick_activity['ticks_last_60min']['median']}, "
            f"ticks60_p90={tick_activity['ticks_last_60min']['p90']}, "
            f"ticks60_max={tick_activity['ticks_last_60min']['max']}, "
            f"today_median={tick_activity['ticks_today']['median']}, "
            f"today_p90={tick_activity['ticks_today']['p90']}, "
            f"today_max={tick_activity['ticks_today']['max']}"
        )
        if not tick_map:
            self._log_gate_result("tick_stats_present", False, "tick stats file not available yet")
            payload = self._build_skip_payload(
                "waiting_for_tick_stats",
                len(stage1_stocks),
                extra_summary={"tick_stats": tick_meta},
            )
            print("Stage 2 skipped because tick stats are not available yet.")
            return payload
        self._log_gate_result("tick_stats_present", True, "tick stats file loaded")

        if (
            tick_meta.get("age_seconds") is not None
            and tick_meta["age_seconds"] > self.config.stage2_max_tick_stats_staleness_seconds
        ):
            self._log_gate_result(
                "tick_stats_freshness",
                False,
                f"age={tick_meta['age_seconds']}s exceeds limit {self.config.stage2_max_tick_stats_staleness_seconds}s",
            )
            payload = self._build_skip_payload(
                "waiting_for_fresh_tick_stats",
                len(stage1_stocks),
                extra_summary={"tick_stats": tick_meta},
            )
            print("Stage 2 skipped because tick stats are stale.")
            return payload
        self._log_gate_result(
            "tick_stats_freshness",
            True,
            f"age={tick_meta.get('age_seconds')}s within limit",
        )

        if (
            tick_meta.get("collector_uptime_seconds") is not None
            and tick_meta["collector_uptime_seconds"] < self.config.stage2_min_tick_collector_warmup_seconds
        ):
            self._log_gate_result(
                "tick_collector_warmup",
                False,
                f"uptime={tick_meta['collector_uptime_seconds']}s below minimum {self.config.stage2_min_tick_collector_warmup_seconds}s",
            )
            payload = self._build_skip_payload(
                "waiting_for_tick_stats_warmup",
                len(stage1_stocks),
                extra_summary={"tick_stats": tick_meta},
            )
            print("Stage 2 skipped because the tick collector is still warming up.")
            return payload
        self._log_gate_result(
            "tick_collector_warmup",
            True,
            f"uptime={tick_meta.get('collector_uptime_seconds')}s",
        )

        if tick_meta.get("coverage_ratio", 0.0) < self.config.stage2_min_tick_stats_coverage_ratio:
            self._log_gate_result(
                "tick_stats_coverage",
                False,
                f"coverage={tick_meta.get('coverage_ratio')} below minimum {self.config.stage2_min_tick_stats_coverage_ratio}",
            )
            payload = self._build_skip_payload(
                "waiting_for_tick_stats_coverage",
                len(stage1_stocks),
                extra_summary={"tick_stats": tick_meta},
            )
            print("Stage 2 skipped because tick stats coverage is too low.")
            return payload
        self._log_gate_result(
            "tick_stats_coverage",
            True,
            f"coverage={tick_meta.get('coverage_ratio')}",
        )

        collector_signature = tick_meta.get("collector_universe_signature")
        if collector_signature and collector_signature != expected_universe_signature:
            self._log_gate_result(
                "tick_stats_universe_sync",
                False,
                f"collector_signature={collector_signature}, expected_signature={expected_universe_signature}",
            )
            payload = self._build_skip_payload(
                "waiting_for_tick_stats_universe_sync",
                len(stage1_stocks),
                extra_summary={"tick_stats": tick_meta},
            )
            print("Stage 2 skipped because tick stats still belong to a different Stage 1 universe.")
            return payload
        self._log_gate_result(
            "tick_stats_universe_sync",
            True,
            f"signature={collector_signature or expected_universe_signature}",
        )

        quote_map = self._fetch_live_quotes(stage1_stocks)
        print(f"Loaded live quote snapshots for {len(quote_map)} security id(s)")
        if not quote_map:
            self._log_gate_result("quote_snapshot", False, "no quote data returned")
            payload = self._build_skip_payload(
                "quote_fetch_failed",
                len(stage1_stocks),
                failed_fetch=len(stage1_stocks),
            )
            print("Stage 2 skipped because live quote data could not be fetched.")
            return payload
        self._log_gate_result("quote_snapshot", True, f"quotes_loaded={len(quote_map)}")
        quote_summary = self._summarize_quote_map(quote_map)
        print(
            "Stage 2 quote snapshot summary: "
            f"quotes={quote_summary['quotes']}, "
            f"ltp_available={quote_summary['last_price_available']}, "
            f"spread_available={quote_summary['spread_available']}, "
            f"spread_missing={quote_summary['spread_missing']}"
        )

        total = len(stage1_stocks)
        print(
            f"Stage 2 historical refinement starting for {total} stock(s) "
            f"with {workers} worker(s) and shared rate limit {self.config.historical_rate_limit_per_sec}/sec"
        )
        print(
            "Stage 2 live processing starting: "
            "each stock will fetch intraday history, compute RVOL, and emit PASS/FILTERED/SKIP"
        )
        all_records: List[Dict[str, Any]] = []
        passed_records: List[Dict[str, Any]] = []
        failed_count = 0

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(self._process_stock, stock, quote_map, tick_map, idx, total): stock
                for idx, stock in enumerate(stage1_stocks, 1)
            }
            for future in as_completed(futures):
                try:
                    record, passed = future.result()
                    if record:
                        all_records.append(record)
                        if passed:
                            passed_records.append(record)
                    else:
                        failed_count += 1
                except Exception as exc:
                    failed_count += 1
                    self._record_fetch_failure(f"task_error::{type(exc).__name__}")
                    print(f"Stage 2 task error: {exc}")

        passed_records.sort(
            key=lambda row: (
                row.get("spread_percent") is None,
                row.get("spread_percent", 999),
                -float(row.get("time_of_day_rvol") or 0),
            )
        )

        summary = {
            "input_stage1_count": total,
            "data_retrieved": len(all_records),
            "failed_fetch": failed_count,
            "stage2_passed": len(passed_records),
            "status": "completed",
            "stage2_filters": self._build_stage2_filters_summary(),
            "tick_stats": tick_meta,
            "tick_activity_summary": tick_activity,
            "filter_reason_counts": dict(self.filter_reasons),
            "fetch_failure_reason_counts": dict(self.fetch_failure_reasons),
            "requirements": {
                "tick_collector_required": True,
                "live_market_required": True,
            },
        }

        payload = StorageService.build_payload("stage2_liquidity_gate", summary, "stocks", passed_records)
        self._save_payload(payload)

        daily_path = self.config.stage2_daily_path(self.market_time.market_date_str())
        print("\nStage 2 complete")
        print(f"Passed Stage 2: {len(passed_records)}")
        print(f"Stage 2 records evaluated: {len(all_records)}")
        print(f"Stage 2 records skipped / fetch failed: {failed_count}")
        print(f"Saved official daily snapshot: {daily_path.name}")
        print(f"Saved latest snapshot: {self.config.stage2_latest_path.name}")

        if self.filter_reasons:
            print("\nTop Stage 2 Filter Reasons:")
            print("-" * 60)
            for reason, count in self.filter_reasons.most_common(5):
                print(f"{count} -> {reason}")

        if self.fetch_failure_reasons:
            print("\nTop Stage 2 Fetch Failures:")
            print("-" * 60)
            for reason, count in self.fetch_failure_reasons.most_common(5):
                print(f"{count} -> {reason}")

        return payload
