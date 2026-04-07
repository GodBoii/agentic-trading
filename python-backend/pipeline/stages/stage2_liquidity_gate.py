from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from threading import Lock
import time
from typing import Any, Dict, List, Optional, Tuple

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

    def _load_stage1_universe(self) -> List[Dict[str, Any]]:
        market_date = self.market_time.market_date_str()
        stage1_path = self.config.stage1_daily_path(market_date)
        payload = StorageService.load_snapshot(stage1_path)
        if not payload:
            raise FileNotFoundError(
                f"Stage 1 snapshot not found: {stage1_path}. Run Stage 1 before Stage 2."
            )
        return payload.get("stocks", [])

    def _load_tick_stats(self) -> Dict[int, Dict[str, Any]]:
        payload = StorageService.load_snapshot(self.config.tick_stats_latest_path)
        if not payload:
            print("Tick stats file not found. Stage 2 tick-rate gate will fail until the live tick collector is running.")
            return {}
        stats = payload.get("tick_stats", {})
        parsed: Dict[int, Dict[str, Any]] = {}
        for raw_security_id, item in stats.items():
            try:
                parsed[int(raw_security_id)] = item
            except Exception:
                continue
        return parsed

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

    def _compute_spread_percent(self, quote_item: Dict[str, Any]) -> Optional[float]:
        depth = quote_item.get("depth") or quote_item.get("market_depth")
        if not isinstance(depth, list) or not depth:
            return None

        first_level = depth[0]
        bid_price = first_level.get("bid_price") or first_level.get("bidPrice") or first_level.get("best_bid_price")
        ask_price = first_level.get("ask_price") or first_level.get("askPrice") or first_level.get("best_ask_price")
        if bid_price is None or ask_price is None:
            return None

        bid_price = float(bid_price)
        ask_price = float(ask_price)
        mid = (bid_price + ask_price) / 2
        if mid <= 0:
            return None
        return ((ask_price - bid_price) / mid) * 100

    def _process_stock(
        self,
        stock: Dict[str, Any],
        quote_map: Dict[int, Dict[str, Any]],
        tick_map: Dict[int, Dict[str, Any]],
        idx: int,
        total: int,
    ) -> Tuple[Optional[Dict[str, Any]], bool]:
        security_id = int(stock["security_id"])
        quote_item = quote_map.get(security_id)
        if not quote_item:
            return None, False

        spread_percent = self._compute_spread_percent(quote_item)
        last_price = quote_item.get("last_price") or quote_item.get("LTP")
        volume = quote_item.get("volume")
        intraday_value_cr = None
        if last_price is not None and volume is not None:
            intraday_value_cr = (float(last_price) * float(volume)) / 10000000

        intraday_resp = self.dhan.fetch_intraday_history(security_id, days=5, interval=1)
        if not intraday_resp or str(intraday_resp.get("status", "")).lower() != "success":
            return None, False
        intraday_frame = self.dhan.intraday_response_to_df(intraday_resp)
        rvol = self.dhan.compute_time_of_day_rvol(intraday_frame)

        tick_info = tick_map.get(security_id, {})
        ticks_last_hour = tick_info.get("ticks_last_hour")

        record = {
            "security_id": security_id,
            "symbol": stock.get("symbol"),
            "display_name": stock.get("display_name"),
            "price": float(last_price) if last_price is not None else stock.get("price"),
            "adv_20_cr": stock.get("adv_20_cr"),
            "atr_percent": stock.get("atr_percent"),
            "spread_percent": round(spread_percent, 4) if spread_percent is not None else None,
            "ticks_last_hour": ticks_last_hour,
            "time_of_day_rvol": round(rvol, 3) if rvol is not None else None,
            "intraday_value_cr": round(intraday_value_cr, 2) if intraday_value_cr is not None else None,
            "stage2_reason": None,
            "generated_at": datetime.now().isoformat(),
        }

        passed = True
        if spread_percent is None or spread_percent > self.config.stage2_max_spread_percent:
            record["stage2_reason"] = "spread"
            passed = False
        elif ticks_last_hour is None or int(ticks_last_hour) < self.config.stage2_min_ticks_per_hour:
            record["stage2_reason"] = "tick_rate"
            passed = False
        elif rvol is None or rvol < self.config.stage2_min_rvol:
            record["stage2_reason"] = "time_of_day_rvol"
            passed = False

        self._log_progress(total)

        return record, passed

    def run(self, max_stocks: Optional[int] = None, workers: Optional[int] = None) -> Dict[str, Any]:
        print("=" * 60)
        print("STAGE 2 - HARD LIQUIDITY GATE (LIVE MARKET)")
        print("=" * 60)

        workers = workers or self.config.stage2_workers
        self.progress = 0
        self.last_reported_decile = 0
        self.last_heartbeat_ts = time.time()
        stage1_stocks = self._load_stage1_universe()
        if max_stocks:
            stage1_stocks = stage1_stocks[:max_stocks]
            print(f"TEST MODE: limiting Stage 2 to first {max_stocks} Stage 1 stocks")

        tick_map = self._load_tick_stats()
        if not tick_map:
            summary = {
                "input_stage1_count": len(stage1_stocks),
                "data_retrieved": 0,
                "failed_fetch": 0,
                "stage2_passed": 0,
                "status": "waiting_for_tick_stats",
                "stage2_filters": {
                    "max_spread_percent": self.config.stage2_max_spread_percent,
                    "min_ticks_per_hour": self.config.stage2_min_ticks_per_hour,
                    "min_time_of_day_rvol": self.config.stage2_min_rvol,
                },
            }
            payload = StorageService.build_payload("stage2_liquidity_gate", summary, "stocks", [])
            StorageService.save_snapshot(self.config.stage2_latest_path, payload)
            StorageService.save_snapshot(self.config.stage2_daily_path(self.market_time.market_date_str()), payload)
            print("Stage 2 skipped because tick stats are not available yet.")
            return payload
        quote_map = self._fetch_live_quotes(stage1_stocks)
        if not quote_map:
            summary = {
                "input_stage1_count": len(stage1_stocks),
                "data_retrieved": 0,
                "failed_fetch": len(stage1_stocks),
                "stage2_passed": 0,
                "status": "quote_fetch_failed",
                "stage2_filters": {
                    "max_spread_percent": self.config.stage2_max_spread_percent,
                    "min_ticks_per_hour": self.config.stage2_min_ticks_per_hour,
                    "min_time_of_day_rvol": self.config.stage2_min_rvol,
                },
            }
            payload = StorageService.build_payload("stage2_liquidity_gate", summary, "stocks", [])
            StorageService.save_snapshot(self.config.stage2_latest_path, payload)
            StorageService.save_snapshot(self.config.stage2_daily_path(self.market_time.market_date_str()), payload)
            print("Stage 2 skipped because live quote data could not be fetched.")
            return payload

        total = len(stage1_stocks)
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
            "stage2_filters": {
                "max_spread_percent": self.config.stage2_max_spread_percent,
                "min_ticks_per_hour": self.config.stage2_min_ticks_per_hour,
                "min_time_of_day_rvol": self.config.stage2_min_rvol,
            },
            "requirements": {
                "tick_collector_required": True,
                "live_market_required": True,
            },
        }

        payload = StorageService.build_payload("stage2_liquidity_gate", summary, "stocks", passed_records)
        StorageService.save_snapshot(self.config.stage2_latest_path, payload)
        daily_path = self.config.stage2_daily_path(self.market_time.market_date_str())
        StorageService.save_snapshot(daily_path, payload)

        print("\nStage 2 complete")
        print(f"Passed Stage 2: {len(passed_records)}")
        print(f"Saved official daily snapshot: {daily_path.name}")
        print(f"Saved latest snapshot: {self.config.stage2_latest_path.name}")
        return payload
