from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from threading import Lock
import time
from typing import Any, Dict, List, Optional, Tuple

from pipeline.config import PipelineConfig
from pipeline.services.dhan_service import DhanService
from pipeline.services.storage_service import StorageService
from pipeline.services.surveillance_service import SurveillanceService
from pipeline.services.universe_service import UniverseService


class Stage1Sanitation:
    """
    Pre-market only.
    No live quote or live depth usage.
    Uses static universe metadata + historical daily data.
    """

    def __init__(self, config: Optional[PipelineConfig] = None):
        self.config = config or PipelineConfig()
        self.dhan = DhanService(self.config)
        self.universe_service = UniverseService(self.config)
        self.surveillance_service = SurveillanceService(self.config)
        self.lock = Lock()
        self.progress = 0
        self.last_reported_decile = 0
        self.last_heartbeat_ts = 0.0
        self.gsm_ids = set()
        self.asm_ids = set()

    def _log_progress(self, total: int) -> None:
        with self.lock:
            self.progress += 1
            completed_pct = int((self.progress / total) * 100) if total else 100
            decile = min(10, completed_pct // 10)
            now = time.time()
            if now - self.last_heartbeat_ts >= 30:
                self.last_heartbeat_ts = now
                print(f"Still fetching... {self.progress}/{total} processed")
            if decile > self.last_reported_decile:
                self.last_reported_decile = decile
                print(f"{decile * 10}% done fetching... ({self.progress}/{total})")

    def _process_stock(self, stock: Dict[str, Any], idx: int, total: int) -> Tuple[Optional[Dict[str, Any]], bool]:
        security_id = int(stock["security_id"])

        if security_id in self.gsm_ids or security_id in self.asm_ids:
            self._log_progress(total)
            return None, False

        resp = self.dhan.fetch_daily_history(security_id, days=30)
        if not resp or str(resp.get("status", "")).lower() != "success":
            self._log_progress(total)
            return None, False

        frame = self.dhan.daily_response_to_df(resp)
        if frame.empty or len(frame) < 20:
            self._log_progress(total)
            return None, False

        last_close = float(frame["close"].iloc[-1])
        adv_10_cr = float((frame["close"].tail(10) * frame["volume"].tail(10)).mean() / 10000000)
        adv_20_cr = float((frame["close"].tail(20) * frame["volume"].tail(20)).mean() / 10000000)
        atr_percent = self.dhan.compute_atr_percent(frame, period=14)

        record = {
            "security_id": security_id,
            "symbol": stock.get("symbol"),
            "display_name": stock.get("display_name"),
            "isin": stock.get("isin"),
            "series": stock.get("series"),
            "price": round(last_close, 2),
            "adv_10_cr": round(adv_10_cr, 2),
            "adv_20_cr": round(adv_20_cr, 2),
            "atr_percent": round(atr_percent, 2),
            "last_close_date": frame["timestamp"].iloc[-1].date().isoformat(),
            "asm_gsm_flag": stock.get("asm_gsm_flag"),
            "prefilter_reason": None,
            "generated_at": datetime.now().isoformat(),
        }

        passed = (
            self.config.stage1_min_price <= last_close <= self.config.stage1_max_price
            and adv_20_cr >= self.config.stage1_min_adv_cr
            and atr_percent >= self.config.stage1_min_atr_percent
        )

        if not passed:
            if last_close < self.config.stage1_min_price or last_close > self.config.stage1_max_price:
                record["prefilter_reason"] = "price_range"
            elif adv_20_cr < self.config.stage1_min_adv_cr:
                record["prefilter_reason"] = "adv_20"
            elif atr_percent < self.config.stage1_min_atr_percent:
                record["prefilter_reason"] = "atr_percent"

        self._log_progress(total)

        return record, passed

    def run(self, max_stocks: Optional[int] = None, workers: Optional[int] = None) -> Dict[str, Any]:
        print("=" * 60)
        print("STAGE 1 - UNIVERSE SANITATION (PRE-MARKET ONLY)")
        print("=" * 60)

        workers = workers or self.config.stage1_workers
        self.progress = 0
        self.last_reported_decile = 0
        self.last_heartbeat_ts = time.time()
        self.gsm_ids = self.surveillance_service.load_gsm_ids()
        self.asm_ids = self.surveillance_service.load_asm_ids()
        universe = self.universe_service.load_bse_common_equities()
        if max_stocks:
            universe = universe[:max_stocks]
            print(f"TEST MODE: limiting Stage 1 to first {max_stocks} stocks")

        total = len(universe)
        print(f"Loaded {total} common BSE equities for Stage 1")
        print(f"Filters: price {self.config.stage1_min_price}-{self.config.stage1_max_price}, ADV20 >= {self.config.stage1_min_adv_cr}Cr, ATR% >= {self.config.stage1_min_atr_percent}")
        estimated_minutes = total / max(1, self.config.historical_rate_limit_per_sec * 60)
        print(f"Rough lower-bound runtime estimate: ~{estimated_minutes:.1f} minutes plus network overhead")

        all_records: List[Dict[str, Any]] = []
        passed_records: List[Dict[str, Any]] = []
        failed_count = 0

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(self._process_stock, stock, idx, total): stock
                for idx, stock in enumerate(universe, 1)
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
                    print(f"Stage 1 task error: {exc}")

        passed_records.sort(key=lambda row: row["adv_20_cr"], reverse=True)
        summary = {
            "input_universe": total,
            "gsm_excluded": len(self.gsm_ids),
            "asm_excluded": len(self.asm_ids),
            "data_retrieved": len(all_records),
            "failed_fetch": failed_count,
            "stage1_passed": len(passed_records),
            "stage1_filters": {
                "min_price": self.config.stage1_min_price,
                "max_price": self.config.stage1_max_price,
                "min_adv_20_cr": self.config.stage1_min_adv_cr,
                "min_atr_percent": self.config.stage1_min_atr_percent,
            },
            "unsupported_today": [
                "corporate_actions_today",
                "recent_circuit_hit_last_5_sessions",
            ],
        }

        payload = StorageService.build_payload("stage1_sanitation", summary, "stocks", passed_records)
        StorageService.save_snapshot(self.config.stage1_latest_path, payload)

        timestamp_path = self.config.backend_dir / f"stage1_universe_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        StorageService.save_snapshot(timestamp_path, payload)

        print("\nStage 1 complete")
        print(f"Passed Stage 1: {len(passed_records)}")
        print(f"Saved latest snapshot: {self.config.stage1_latest_path.name}")
        return payload
