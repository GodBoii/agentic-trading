from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, time as dt_time, timedelta
from threading import Lock
import math
import pandas as pd
import time
from typing import Any, Dict, List, Optional, Tuple

from pipeline.config import PipelineConfig
from pipeline.services.dhan_service import DhanService
from pipeline.services.market_time_service import MarketTimeService
from pipeline.services.storage_service import StorageService


class Stage2MomentumIgnition:
    """
    Fast intraday momentum ignition stage.
    Uses Stage 1 survivors + intraday minute history to detect:
    - time-of-day RVOL
    - price vs VWAP
    - opening-range breakout
    - volume acceleration
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

    def _summarize_numeric_series(self, values: List[float]) -> Dict[str, Any]:
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

        def percentile(pct: float) -> float:
            index = int(round((count - 1) * pct))
            return ordered[index]

        return {
            "count": count,
            "min": round(ordered[0], 4),
            "median": round(percentile(0.50), 4),
            "p90": round(percentile(0.90), 4),
            "max": round(ordered[-1], 4),
            "avg": round(sum(ordered) / count, 4),
        }

    def _build_filters_summary(self) -> Dict[str, Any]:
        return {
            "history_days": self.config.stage2_history_days,
            "min_time_of_day_rvol": self.config.stage2_min_rvol,
            "min_price_vs_vwap_percent": self.config.stage2_min_price_vs_vwap_percent,
            "min_volume_acceleration_ratio": self.config.stage2_min_volume_acceleration_ratio,
            "volume_acceleration_window_minutes": self.config.stage2_volume_acceleration_window_minutes,
            "volume_acceleration_denominator_floor_fraction": (
                self.config.stage2_volume_acceleration_denominator_floor_fraction
            ),
            "volume_acceleration_max_ratio": self.config.stage2_volume_acceleration_max_ratio,
            "opening_range_minutes": self.config.stage2_opening_range_minutes,
            "min_breakout_percent": self.config.stage2_min_breakout_percent,
        }

    def _save_payload(self, payload: Dict[str, Any]) -> None:
        StorageService.save_snapshot(self.config.stage2_latest_path, payload)
        StorageService.save_snapshot(
            self.config.stage2_daily_path(self.market_time.market_date_str()),
            payload,
        )

    def _payload_market_date(self, payload: Optional[Dict[str, Any]]) -> Optional[str]:
        if not payload:
            return None
        summary_market_date = payload.get("summary", {}).get("market_date")
        if summary_market_date:
            return str(summary_market_date)
        return StorageService.snapshot_market_date(payload, self.config.market_timezone)

    def _load_stage1_universe(self) -> List[Dict[str, Any]]:
        market_date = self.market_time.market_date_str()
        payload = StorageService.load_snapshot(self.config.stage1_daily_path(market_date))

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
                f"Stage 1 snapshot not found for {market_date}. Run Stage 1 before Stage 2."
            )

        return payload.get("stocks", [])

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

    def _today_market_frame(self, frame: pd.DataFrame) -> pd.DataFrame:
        if frame.empty:
            return frame

        local_ts = (
            frame["timestamp"]
            .dt.tz_localize("UTC")
            .dt.tz_convert(self.market_time.tz)
        )
        local_frame = frame.copy()
        local_frame["market_timestamp"] = local_ts
        local_frame["market_date"] = local_ts.dt.date
        today = self.market_time.now().date()
        return local_frame[local_frame["market_date"] == today].sort_values("market_timestamp")

    def _compute_intraday_vwap(self, today_frame: pd.DataFrame) -> Optional[float]:
        if today_frame.empty or "volume" not in today_frame.columns:
            return None

        volume = pd.to_numeric(today_frame["volume"], errors="coerce").fillna(0.0)
        if math.isclose(float(volume.sum()), 0.0):
            return None

        typical_price = (
            pd.to_numeric(today_frame["high"], errors="coerce").fillna(0.0)
            + pd.to_numeric(today_frame["low"], errors="coerce").fillna(0.0)
            + pd.to_numeric(today_frame["close"], errors="coerce").fillna(0.0)
        ) / 3.0

        vwap = (typical_price * volume).sum() / volume.sum()
        return float(vwap) if pd.notna(vwap) else None

    def _compute_opening_range(self, today_frame: pd.DataFrame) -> Tuple[Optional[float], Optional[float], bool]:
        if today_frame.empty or "market_timestamp" not in today_frame.columns:
            return None, None, False

        open_dt = datetime.combine(
            self.market_time.now().date(),
            dt_time(self.config.market_open_hour, self.config.market_open_minute),
            tzinfo=self.market_time.tz,
        )
        range_end = open_dt + timedelta(minutes=self.config.stage2_opening_range_minutes)
        opening_slice = today_frame[
            (today_frame["market_timestamp"] >= open_dt)
            & (today_frame["market_timestamp"] < range_end)
        ]

        expected_bars = self.config.stage2_opening_range_minutes
        is_complete = len(opening_slice) >= max(3, expected_bars // 2)
        if opening_slice.empty:
            return None, None, False

        opening_high = float(pd.to_numeric(opening_slice["high"], errors="coerce").max())
        opening_low = float(pd.to_numeric(opening_slice["low"], errors="coerce").min())
        return opening_high, opening_low, is_complete

    def _compute_volume_acceleration_ratio(self, today_frame: pd.DataFrame) -> Optional[float]:
        window = self.config.stage2_volume_acceleration_window_minutes
        if today_frame.empty or len(today_frame) < window * 2:
            return None

        volume_series = pd.to_numeric(today_frame["volume"], errors="coerce").fillna(0.0)
        recent = float(volume_series.tail(window).sum())
        previous = float(volume_series.iloc[-(window * 2):-window].sum())
        if recent <= 0:
            return None

        positive_minutes = volume_series[volume_series > 0]
        per_minute_baseline = float(positive_minutes.median()) if not positive_minutes.empty else 0.0
        denominator_floor = max(
            1.0,
            per_minute_baseline
            * window
            * self.config.stage2_volume_acceleration_denominator_floor_fraction,
        )
        adjusted_previous = max(previous, denominator_floor)
        ratio = recent / adjusted_previous
        return min(ratio, self.config.stage2_volume_acceleration_max_ratio)

    def _build_stage_funnel_counts(
        self,
        total: int,
        records: List[Dict[str, Any]],
        failed_fetch: int,
    ) -> Dict[str, int]:
        reasons = Counter(
            str(record.get("stage2_reason"))
            for record in records
            if record.get("stage2_reason")
        )
        after_rvol = total - failed_fetch - (
            reasons.get("time_of_day_rvol_unavailable", 0) + reasons.get("time_of_day_rvol", 0)
        )
        after_vwap = after_rvol - (
            reasons.get("vwap_unavailable", 0) + reasons.get("below_vwap", 0)
        )
        after_opening_range = after_vwap - (
            reasons.get("opening_range_incomplete", 0) + reasons.get("opening_range_breakout", 0)
        )
        after_volume_acceleration = after_opening_range - (
            reasons.get("volume_acceleration_unavailable", 0) + reasons.get("volume_acceleration", 0)
        )

        return {
            "input_stage1_count": total,
            "after_fetch": total - failed_fetch,
            "after_rvol": max(0, after_rvol),
            "after_vwap": max(0, after_vwap),
            "after_opening_range": max(0, after_opening_range),
            "after_volume_acceleration": max(0, after_volume_acceleration),
            "passed": max(0, after_volume_acceleration),
        }

    def _near_miss_gap(self, record: Dict[str, Any]) -> Optional[float]:
        reason = record.get("stage2_reason")
        if reason == "time_of_day_rvol" and record.get("time_of_day_rvol") is not None:
            return max(0.0, self.config.stage2_min_rvol - float(record["time_of_day_rvol"]))
        if reason == "below_vwap" and record.get("price_vs_vwap_percent") is not None:
            return max(
                0.0,
                self.config.stage2_min_price_vs_vwap_percent - float(record["price_vs_vwap_percent"]),
            )
        if reason == "opening_range_breakout" and record.get("opening_range_breakout_percent") is not None:
            return max(
                0.0,
                self.config.stage2_min_breakout_percent - float(record["opening_range_breakout_percent"]),
            )
        if reason == "volume_acceleration" and record.get("volume_acceleration_ratio") is not None:
            return max(
                0.0,
                self.config.stage2_min_volume_acceleration_ratio - float(record["volume_acceleration_ratio"]),
            )
        return None

    def _build_near_misses(self, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        near_misses: List[Tuple[float, Dict[str, Any]]] = []
        for record in records:
            if record.get("stage2_reason") in {
                "time_of_day_rvol",
                "below_vwap",
                "opening_range_breakout",
                "volume_acceleration",
            }:
                gap = self._near_miss_gap(record)
                if gap is None:
                    continue
                near_misses.append((gap, record))

        near_misses.sort(key=lambda item: (item[0], -(float(item[1].get("time_of_day_rvol") or 0.0))))
        result: List[Dict[str, Any]] = []
        for gap, record in near_misses[: self.config.stage2_near_miss_limit]:
            result.append(
                {
                    "security_id": record.get("security_id"),
                    "display_name": record.get("display_name"),
                    "symbol": record.get("symbol"),
                    "stage2_reason": record.get("stage2_reason"),
                    "miss_gap": round(gap, 4),
                    "time_of_day_rvol": record.get("time_of_day_rvol"),
                    "price_vs_vwap_percent": record.get("price_vs_vwap_percent"),
                    "opening_range_breakout_percent": record.get("opening_range_breakout_percent"),
                    "volume_acceleration_ratio": record.get("volume_acceleration_ratio"),
                }
            )
        return result

    def _score_record(self, record: Dict[str, Any]) -> float:
        rvol = float(record.get("time_of_day_rvol") or 0.0)
        price_vs_vwap = max(0.0, float(record.get("price_vs_vwap_percent") or 0.0))
        breakout = max(0.0, float(record.get("opening_range_breakout_percent") or 0.0))
        volume_accel = max(0.0, float(record.get("volume_acceleration_ratio") or 0.0) - 1.0)

        score = (
            min(rvol, 5.0) * 40.0
            + min(price_vs_vwap, 5.0) * 20.0
            + min(breakout, 5.0) * 15.0
            + min(volume_accel, 3.0) * 25.0
        )
        return round(score, 2)

    def _process_stock(
        self,
        stock: Dict[str, Any],
        idx: int,
        total: int,
    ) -> Tuple[Optional[Dict[str, Any]], bool]:
        security_id = int(stock["security_id"])
        print(f"Stage 2 processing {stock.get('symbol') or security_id} ({security_id})...")

        intraday_resp = self.dhan.fetch_intraday_history(
            security_id,
            days=self.config.stage2_history_days,
            interval=1,
            exchange_segment="BSE_EQ",
            instrument_candidates=[stock.get("instrument"), "EQUITY"],
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

        today_frame = self._today_market_frame(intraday_frame)
        if today_frame.empty:
            self._record_fetch_failure("intraday_today_empty")
            print(f"Stage 2 skip {security_id}: no intraday candles for current market date")
            self._log_progress(total)
            return None, False

        latest_price = float(pd.to_numeric(today_frame["close"], errors="coerce").iloc[-1])
        rvol = self.dhan.compute_time_of_day_rvol(intraday_frame)
        vwap = self._compute_intraday_vwap(today_frame)
        opening_high, opening_low, opening_range_complete = self._compute_opening_range(today_frame)
        volume_acceleration_ratio = self._compute_volume_acceleration_ratio(today_frame)
        accel_window = self.config.stage2_volume_acceleration_window_minutes
        volume_series = pd.to_numeric(today_frame["volume"], errors="coerce").fillna(0.0)
        recent_volume_window = float(volume_series.tail(accel_window).sum()) if not volume_series.empty else None
        previous_volume_window = (
            float(volume_series.iloc[-(accel_window * 2):-accel_window].sum())
            if len(volume_series) >= accel_window * 2
            else None
        )

        price_vs_vwap_percent = None
        if vwap and vwap > 0:
            price_vs_vwap_percent = ((latest_price - vwap) / vwap) * 100.0

        opening_range_breakout_percent = None
        if opening_high and opening_high > 0:
            opening_range_breakout_percent = ((latest_price - opening_high) / opening_high) * 100.0

        record = {
            "security_id": security_id,
            "symbol": stock.get("symbol"),
            "display_name": stock.get("display_name"),
            "instrument": stock.get("instrument"),
            "isin": stock.get("isin"),
            "series": stock.get("series"),
            "price": latest_price,
            "adv_20_cr": stock.get("adv_20_cr"),
            "atr_percent": stock.get("atr_percent"),
            "time_of_day_rvol": round(rvol, 3) if rvol is not None else None,
            "intraday_vwap": round(vwap, 4) if vwap is not None else None,
            "price_vs_vwap_percent": (
                round(price_vs_vwap_percent, 4) if price_vs_vwap_percent is not None else None
            ),
            "is_above_vwap": bool(price_vs_vwap_percent is not None and price_vs_vwap_percent > 0),
            "opening_range_high": round(opening_high, 4) if opening_high is not None else None,
            "opening_range_low": round(opening_low, 4) if opening_low is not None else None,
            "opening_range_complete": opening_range_complete,
            "opening_range_breakout_percent": (
                round(opening_range_breakout_percent, 4)
                if opening_range_breakout_percent is not None
                else None
            ),
            "is_opening_range_breakout": bool(
                opening_range_breakout_percent is not None
                and opening_range_breakout_percent >= self.config.stage2_min_breakout_percent
            ),
            "volume_acceleration_ratio": (
                round(volume_acceleration_ratio, 4) if volume_acceleration_ratio is not None else None
            ),
            "recent_volume_window": round(recent_volume_window, 2) if recent_volume_window is not None else None,
            "previous_volume_window": (
                round(previous_volume_window, 2) if previous_volume_window is not None else None
            ),
            "stage2_reason": None,
            "stage2_score": None,
            "generated_at": datetime.now().isoformat(),
        }

        passed = True
        if rvol is None:
            record["stage2_reason"] = "time_of_day_rvol_unavailable"
            passed = False
        elif rvol < self.config.stage2_min_rvol:
            record["stage2_reason"] = "time_of_day_rvol"
            passed = False
        elif vwap is None:
            record["stage2_reason"] = "vwap_unavailable"
            passed = False
        elif price_vs_vwap_percent is None or price_vs_vwap_percent < self.config.stage2_min_price_vs_vwap_percent:
            record["stage2_reason"] = "below_vwap"
            passed = False
        elif not opening_range_complete:
            record["stage2_reason"] = "opening_range_incomplete"
            passed = False
        elif (
            opening_range_breakout_percent is None
            or opening_range_breakout_percent < self.config.stage2_min_breakout_percent
        ):
            record["stage2_reason"] = "opening_range_breakout"
            passed = False
        elif volume_acceleration_ratio is None:
            record["stage2_reason"] = "volume_acceleration_unavailable"
            passed = False
        elif volume_acceleration_ratio < self.config.stage2_min_volume_acceleration_ratio:
            record["stage2_reason"] = "volume_acceleration"
            passed = False

        if passed:
            record["stage2_score"] = self._score_record(record)
        elif record["stage2_reason"]:
            self._record_filter_reason(record["stage2_reason"])

        status_text = "PASS" if passed else f"FILTERED ({record['stage2_reason']})"
        print(
            f"Stage 2 result {security_id}: {status_text} | "
            f"rvol={record['time_of_day_rvol']} "
            f"vwap_delta={record['price_vs_vwap_percent']} "
            f"orb={record['opening_range_breakout_percent']} "
            f"vol_accel={record['volume_acceleration_ratio']}"
        )
        self._log_progress(total)
        return record, passed

    def run(self, max_stocks: Optional[int] = None, workers: Optional[int] = None) -> Dict[str, Any]:
        print("=" * 60)
        print("STAGE 2 - MOMENTUM IGNITION SCAN")
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
        print("  2. Fetch intraday minute history for each stock in parallel")
        print("  3. Compute RVOL, VWAP, opening-range breakout, and volume acceleration")
        print("  4. Filter for active momentum ignition candidates")
        print("  5. Rank passed stocks by momentum score")

        stage1_stocks = self._load_stage1_universe()
        if max_stocks:
            stage1_stocks = stage1_stocks[:max_stocks]
            print(f"TEST MODE: limiting Stage 2 to first {max_stocks} Stage 1 stocks")

        print(f"Loaded {len(stage1_stocks)} Stage 1 survivor(s) for Stage 2")
        print(
            "Stage 2 thresholds: "
            f"rvol>={self.config.stage2_min_rvol}, "
            f"price_vs_vwap>={self.config.stage2_min_price_vs_vwap_percent}%, "
            f"orb>={self.config.stage2_min_breakout_percent}%, "
            f"vol_accel>={self.config.stage2_min_volume_acceleration_ratio}"
        )

        if not stage1_stocks:
            payload = StorageService.build_payload(
                "stage2_momentum_ignition",
                {
                    "market_date": self.market_time.market_date_str(),
                    "input_stage1_count": 0,
                    "data_retrieved": 0,
                    "failed_fetch": 0,
                    "stage2_passed": 0,
                    "status": "no_stage1_stocks",
                    "stage2_filters": self._build_filters_summary(),
                },
                "stocks",
                [],
            )
            self._save_payload(payload)
            print("Stage 2 skipped because Stage 1 produced zero survivors.")
            return payload

        total = len(stage1_stocks)
        print(
            f"Stage 2 ignition scan starting for {total} stock(s) "
            f"with {workers} worker(s) and shared rate limit {self.config.historical_rate_limit_per_sec}/sec"
        )

        all_records: List[Dict[str, Any]] = []
        passed_records: List[Dict[str, Any]] = []
        failed_count = 0

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(self._process_stock, stock, idx, total): stock
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

        passed_records.sort(key=lambda row: -float(row.get("stage2_score") or 0.0))
        stage_funnel = self._build_stage_funnel_counts(total, all_records, failed_count)
        score_distribution = self._summarize_numeric_series(
            [float(row.get("stage2_score") or 0.0) for row in passed_records]
        )
        near_misses = self._build_near_misses(all_records)

        summary = {
            "market_date": self.market_time.market_date_str(),
            "input_stage1_count": total,
            "data_retrieved": len(all_records),
            "failed_fetch": failed_count,
            "stage2_passed": len(passed_records),
            "status": "completed",
            "stage2_filters": self._build_filters_summary(),
            "stage_funnel_counts": stage_funnel,
            "score_distribution": score_distribution,
            "near_misses": near_misses,
            "filter_reason_counts": dict(self.filter_reasons),
            "fetch_failure_reason_counts": dict(self.fetch_failure_reasons),
        }

        payload = StorageService.build_payload(
            "stage2_momentum_ignition",
            summary,
            "stocks",
            passed_records,
        )
        self._save_payload(payload)

        daily_path = self.config.stage2_daily_path(self.market_time.market_date_str())
        print("\nStage 2 complete")
        print(f"Passed Stage 2: {len(passed_records)}")
        print(f"Stage 2 records evaluated: {len(all_records)}")
        print(f"Stage 2 records skipped / fetch failed: {failed_count}")
        print(f"Saved official daily snapshot: {daily_path.name}")
        print(f"Saved latest snapshot: {self.config.stage2_latest_path.name}")

        print("\nStage 2 Funnel:")
        print("-" * 60)
        print(f"Input Stage 1 count: {stage_funnel['input_stage1_count']}")
        print(f"After fetch: {stage_funnel['after_fetch']}")
        print(f"After RVOL: {stage_funnel['after_rvol']}")
        print(f"After VWAP: {stage_funnel['after_vwap']}")
        print(f"After Opening Range: {stage_funnel['after_opening_range']}")
        print(f"After Volume Acceleration: {stage_funnel['after_volume_acceleration']}")

        if score_distribution["count"] > 0:
            print("\nStage 2 Score Distribution:")
            print("-" * 60)
            print(
                f"count={score_distribution['count']} "
                f"min={score_distribution['min']} "
                f"median={score_distribution['median']} "
                f"p90={score_distribution['p90']} "
                f"max={score_distribution['max']} "
                f"avg={score_distribution['avg']}"
            )

        if passed_records:
            print("\nTop Stage 2 Momentum Candidates:")
            print("-" * 60)
            for idx, record in enumerate(passed_records[:10], 1):
                print(
                    f"{idx}. {record.get('display_name') or record.get('symbol')} "
                    f"score={record.get('stage2_score')} "
                    f"rvol={record.get('time_of_day_rvol')} "
                    f"vwap_delta={record.get('price_vs_vwap_percent')} "
                    f"orb={record.get('opening_range_breakout_percent')} "
                    f"vol_accel={record.get('volume_acceleration_ratio')}"
                )

        if self.filter_reasons:
            print("\nTop Stage 2 Filter Reasons:")
            print("-" * 60)
            for reason, count in self.filter_reasons.most_common(5):
                print(f"{count} -> {reason}")

        if near_misses:
            print("\nTop Stage 2 Near Misses:")
            print("-" * 60)
            for idx, record in enumerate(near_misses[:5], 1):
                print(
                    f"{idx}. {record.get('display_name') or record.get('symbol')} "
                    f"reason={record.get('stage2_reason')} "
                    f"gap={record.get('miss_gap')} "
                    f"rvol={record.get('time_of_day_rvol')} "
                    f"vwap_delta={record.get('price_vs_vwap_percent')} "
                    f"orb={record.get('opening_range_breakout_percent')} "
                    f"vol_accel={record.get('volume_acceleration_ratio')}"
                )

        if self.fetch_failure_reasons:
            print("\nTop Stage 2 Fetch Failures:")
            print("-" * 60)
            for reason, count in self.fetch_failure_reasons.most_common(5):
                print(f"{count} -> {reason}")

        return payload
