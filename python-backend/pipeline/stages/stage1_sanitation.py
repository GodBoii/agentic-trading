from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter
from datetime import datetime
from threading import Lock
import time
from typing import Any, Dict, List, Optional, Tuple

from pipeline.config import PipelineConfig
from pipeline.services.dhan_service import DhanService
from pipeline.services.market_time_service import MarketTimeService
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
        self.market_time = MarketTimeService(self.config)
        self.universe_service = UniverseService(self.config)
        self.surveillance_service = SurveillanceService(self.config)
        self.lock = Lock()
        self.progress = 0
        self.last_reported_decile = 0
        self.last_heartbeat_ts = 0.0
        self.no_data_count = 0
        self.passed_count = 0
        self.sorted_out_count = 0
        self.rate_limited_count = 0
        self.insufficient_history_count = 0
        self.true_no_data_count = 0
        self.failure_reasons: Counter[str] = Counter()
        self.failure_samples_logged = 0
        self.gsm_ids = set()
        self.asm_ids = set()

    def _chunk_stocks(self, stocks: List[Dict[str, Any]], size: int) -> List[List[Dict[str, Any]]]:
        return [stocks[i:i + size] for i in range(0, len(stocks), size)]

    def _log_progress(self, total: int, outcome: str) -> None:
        with self.lock:
            self.progress += 1
            if outcome == "no_data":
                self.no_data_count += 1
            elif outcome == "passed":
                self.passed_count += 1
            elif outcome == "sorted_out":
                self.sorted_out_count += 1

            completed_pct = int((self.progress / total) * 100) if total else 100
            decile = min(10, completed_pct // 10)
            now = time.time()
            progress_tail = (
                f"(no data = {self.no_data_count}, "
                f"passed = {self.passed_count}, "
                f"sorted out = {self.sorted_out_count})"
            )
            if now - self.last_heartbeat_ts >= 30:
                self.last_heartbeat_ts = now
                print(f"Still fetching... {self.progress}/{total} processed {progress_tail}")
            if decile > self.last_reported_decile:
                self.last_reported_decile = decile
                print(f"{decile * 10}% done fetching... ({self.progress}/{total}) {progress_tail}")

    def _run_bulk_price_prefilter(self, universe: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
        candidates: List[Dict[str, Any]] = []
        summary = {
            "initial_universe": len(universe),
            "gsm_filtered": 0,
            "asm_filtered": 0,
            "missing_ohlc": 0,
            "price_filtered": 0,
            "historical_candidates": 0,
        }

        static_survivors: List[Dict[str, Any]] = []
        for stock in universe:
            security_id = int(stock["security_id"])
            if security_id in self.gsm_ids:
                summary["gsm_filtered"] += 1
                continue
            if security_id in self.asm_ids:
                summary["asm_filtered"] += 1
                continue
            static_survivors.append(stock)

        batches = self._chunk_stocks(static_survivors, self.config.stage2_quote_batch_size)
        print(
            f"Stage 1 fast prefilter: bulk OHLC snapshot for {len(static_survivors)} stocks "
            f"in {len(batches)} batch(es)..."
        )

        for index, batch in enumerate(batches, 1):
            batch_ids = [int(stock["security_id"]) for stock in batch]
            ohlc_map = self.dhan.fetch_ohlc_batch(batch_ids)
            for stock in batch:
                security_id = int(stock["security_id"])
                quote_item = ohlc_map.get(security_id)
                if not quote_item:
                    summary["missing_ohlc"] += 1
                    continue

                last_price = quote_item.get("last_price") or quote_item.get("LTP")
                if last_price is None:
                    summary["missing_ohlc"] += 1
                    continue

                try:
                    last_price = float(last_price)
                except Exception:
                    summary["missing_ohlc"] += 1
                    continue

                if not (self.config.stage1_min_price <= last_price <= self.config.stage1_max_price):
                    summary["price_filtered"] += 1
                    continue

                candidate = dict(stock)
                candidate["prefilter_price"] = round(last_price, 2)
                candidates.append(candidate)

            print(f"  Stage 1 OHLC batch {index}/{len(batches)} complete")

        summary["historical_candidates"] = len(candidates)
        return candidates, summary

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

        data = resp.get("data")
        if data:
            text = str(data)
            return text[:280] + "..." if len(text) > 280 else text
        return "unknown_failure"

    def _record_failure(
        self,
        security_id: int,
        resp: Optional[Dict[str, Any]],
        stock: Dict[str, Any],
        explicit_reason: Optional[str] = None,
    ) -> None:
        reason = explicit_reason or self._normalize_failure_reason(resp)
        with self.lock:
            self.failure_reasons[reason] += 1
            reason_lower = reason.lower()
            if reason.startswith("insufficient_history_points="):
                self.insufficient_history_count += 1
            elif "dh-904" in reason_lower or "rate_limit" in reason_lower or "too many requests" in reason_lower:
                self.rate_limited_count += 1
            else:
                self.true_no_data_count += 1
            if self.failure_samples_logged < 5:
                debug = resp.get("_debug", {}) if isinstance(resp, dict) else {}
                print(
                    f"Stage 1 failure sample {self.failure_samples_logged + 1}: "
                    f"security_id={security_id}, symbol={stock.get('symbol')}, "
                    f"exchange={debug.get('exchange_segment_used', 'BSE_EQ')}, "
                    f"instrument={debug.get('instrument_used', 'unknown')} | reason={reason}"
                )
                self.failure_samples_logged += 1

    def _process_stock(self, stock: Dict[str, Any], idx: int, total: int) -> Tuple[Optional[Dict[str, Any]], bool]:
        security_id = int(stock["security_id"])

        instrument_candidates = [
            stock.get("instrument"),
            "EQUITY",
        ]
        resp = self.dhan.fetch_daily_history(
            security_id,
            days=45,
            exchange_segment="BSE_EQ",
            instrument_candidates=instrument_candidates,
        )
        if not resp or str(resp.get("status", "")).lower() != "success":
            self._record_failure(security_id, resp, stock)
            self._log_progress(total, "no_data")
            return None, False

        frame = self.dhan.daily_response_to_df(resp)
        if frame.empty:
            self._record_failure(security_id, resp, stock)
            self._log_progress(total, "no_data")
            return None, False

        if len(frame) < 14:
            self._record_failure(
                security_id,
                resp,
                stock,
                explicit_reason=f"insufficient_history_points={len(frame)}",
            )
            self._log_progress(total, "sorted_out")
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
            "prefilter_price": stock.get("prefilter_price"),
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

        self._log_progress(total, "passed" if passed else "sorted_out")

        return record, passed

    def run(self, max_stocks: Optional[int] = None, workers: Optional[int] = None) -> Dict[str, Any]:
        started_at = time.time()
        print("=" * 60)
        print("STAGE 1 - UNIVERSE SANITATION (PRE-MARKET ONLY)")
        print("=" * 60)

        workers = workers or self.config.stage1_workers
        self.progress = 0
        self.last_reported_decile = 0
        self.last_heartbeat_ts = time.time()
        self.no_data_count = 0
        self.passed_count = 0
        self.sorted_out_count = 0
        self.rate_limited_count = 0
        self.insufficient_history_count = 0
        self.true_no_data_count = 0
        self.failure_reasons = Counter()
        self.failure_samples_logged = 0
        self.gsm_ids = self.surveillance_service.load_gsm_ids()
        self.asm_ids = self.surveillance_service.load_asm_ids()
        universe = self.universe_service.load_bse_common_equities()
        if max_stocks:
            universe = universe[:max_stocks]
            print(f"TEST MODE: limiting Stage 1 to first {max_stocks} stocks")

        total = len(universe)
        print(f"Loaded {total} common BSE equities for Stage 1")
        print(f"Filters: price {self.config.stage1_min_price}-{self.config.stage1_max_price}, ADV20 >= {self.config.stage1_min_adv_cr}Cr, ATR% >= {self.config.stage1_min_atr_percent}")
        credential_info = self.dhan.credentials_summary()
        print(
            "Dhan credential check: "
            f"client_id={credential_info['client_id_masked']}, "
            f"data_access_token={credential_info['has_data_access_token']}, "
            f"app_id={credential_info['has_app_id']}, "
            f"app_secret={credential_info['has_app_secret']}"
        )
        profile = self.dhan.fetch_user_profile()
        if profile.get("status") == "success" and isinstance(profile.get("data"), dict):
            profile_data = profile["data"]
            print(
                "Dhan profile: "
                f"dataPlan={profile_data.get('dataPlan')}, "
                f"dataValidity={profile_data.get('dataValidity')}, "
                f"tokenValidity={profile_data.get('tokenValidity')}, "
                f"activeSegment={profile_data.get('activeSegment')}"
            )
        else:
            print(f"Dhan profile check failed: {profile.get('remarks')}")
        print("Stage 1 execution plan:")
        print("  1. Static ASM/GSM removal")
        print("  2. Bulk OHLC prefilter by price range")
        print("  3. Historical daily fetch only for survivors")

        candidates, prefilter_summary = self._run_bulk_price_prefilter(universe)
        historical_total = len(candidates)
        estimated_minutes = historical_total / max(1, self.config.historical_rate_limit_per_sec * 60)
        print("\nStage 1 fast prefilter summary:")
        print(f"  - Initial universe: {prefilter_summary['initial_universe']}")
        print(f"  - GSM filtered: {prefilter_summary['gsm_filtered']}")
        print(f"  - ASM filtered: {prefilter_summary['asm_filtered']}")
        print(f"  - Missing OHLC: {prefilter_summary['missing_ohlc']}")
        print(f"  - Price filtered: {prefilter_summary['price_filtered']}")
        print(f"  - Remaining for historical scan: {historical_total}")
        print(f"Rough lower-bound runtime estimate for historical phase: ~{estimated_minutes:.1f} minutes plus network overhead")

        if not candidates:
            print("No Stage 1 candidates remained after bulk prefilter.")

        all_records: List[Dict[str, Any]] = []
        passed_records: List[Dict[str, Any]] = []
        failed_count = 0

        if candidates:
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = {
                    executor.submit(self._process_stock, stock, idx, historical_total): stock
                    for idx, stock in enumerate(candidates, 1)
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
            "market_date": self.market_time.market_date_str(),
            "output_file": "",
            "input_universe": total,
            "gsm_excluded": prefilter_summary["gsm_filtered"],
            "asm_excluded": prefilter_summary["asm_filtered"],
            "missing_ohlc": prefilter_summary["missing_ohlc"],
            "price_filtered": prefilter_summary["price_filtered"],
            "historical_candidates": historical_total,
            "data_retrieved": len(all_records),
            "failed_fetch": failed_count,
            "rate_limited_count": self.rate_limited_count,
            "insufficient_history_count": self.insufficient_history_count,
            "true_no_data_count": self.true_no_data_count,
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

        market_date = summary["market_date"]
        daily_path = self.config.stage1_daily_path(market_date)
        summary["output_file"] = daily_path.name
        payload["summary"] = summary
        StorageService.save_snapshot(daily_path, payload)

        elapsed_seconds = time.time() - started_at
        elapsed_minutes = elapsed_seconds / 60 if elapsed_seconds else 0.0
        pass_rate = (len(passed_records) / len(all_records) * 100) if all_records else 0.0
        speed = (historical_total / elapsed_seconds) if elapsed_seconds > 0 else 0.0

        print("\nStage 1 complete")
        print(f"Passed Stage 1: {len(passed_records)}")
        print(f"Saved official daily snapshot: {daily_path.name}")
        print(f"Saved latest snapshot: {self.config.stage1_latest_path.name}")
        print("\n" + "=" * 60)
        print("SCAN COMPLETE")
        print("=" * 60)
        print(f"Total Stocks Scanned: {historical_total}")
        print(f"Data Retrieved: {len(all_records)}")
        print(f"Failed to Fetch: {failed_count}")
        print(f"GSM Filtered Out: {prefilter_summary['gsm_filtered']}")
        print(f"ASM Filtered Out: {prefilter_summary['asm_filtered']}")
        print(f"Missing OHLC: {prefilter_summary['missing_ohlc']}")
        print(f"Price Filtered Out: {prefilter_summary['price_filtered']}")
        print(f"Passed All Filters: {len(passed_records)}")
        print(f"Rate Limited: {self.rate_limited_count}")
        print(f"Insufficient History: {self.insufficient_history_count}")
        print(f"True No Data / Fetch Failures: {self.true_no_data_count}")
        print(f"Pass Rate: {pass_rate:.1f}%")
        print(f"Time Taken: {elapsed_seconds:.1f} seconds ({elapsed_minutes:.1f} minutes)")
        print(f"Speed: {speed:.2f} stocks/second")
        print("=" * 60)

        if self.failure_reasons:
            print("\nTop Stage 1 Failure Reasons:")
            print("-" * 60)
            for reason, count in self.failure_reasons.most_common(5):
                print(f"{count} -> {reason}")

        if passed_records:
            print("\nTop 10 Most Liquid Stocks:")
            print("-" * 60)
            for index, row in enumerate(passed_records[:10], 1):
                name = (row.get("display_name") or row.get("symbol") or str(row.get("security_id")))[:25]
                print(
                    f"{index}. {name:<25} "
                    f"Rs {float(row.get('price') or 0):>7.2f}    "
                    f"{float(row.get('adv_20_cr') or 0):>7.2f}Cr  "
                    f"ATR: {float(row.get('atr_percent') or 0):.2f}%"
                )

        return payload
