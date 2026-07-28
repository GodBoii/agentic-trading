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
            "live_quote_enrichment_enabled": self.config.stage2_live_quote_enrichment_enabled,
            "good_spread_percent": self.config.stage2_good_spread_percent,
            "acceptable_spread_percent": self.config.stage2_acceptable_spread_percent,
            "min_intraday_value_cr": self.config.stage2_min_intraday_value_cr,
        }

    def _save_payload(self, payload: Dict[str, Any]) -> None:
        status = str((payload.get("summary") or {}).get("status") or "").lower()
        market_date = self.market_time.market_date_str()
        if status == "completed":
            StorageService.save_snapshot(self.config.stage2_latest_path, payload)
            StorageService.save_snapshot(self.config.stage2_daily_path(market_date), payload)
            return
        StorageService.save_snapshot(self.config.stage2_degraded_path(market_date), payload)

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
        if not StorageService.is_stage_snapshot_usable(
            payload,
            self.config.stage1_max_fetch_failure_ratio,
        ):
            raise RuntimeError(
                f"Stage 1 snapshot for {market_date} is degraded or incomplete; "
                "Stage 2 will not consume it."
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

    def _chunk_stocks(self, stocks: List[Dict[str, Any]], size: int) -> List[List[Dict[str, Any]]]:
        return [stocks[i:i + size] for i in range(0, len(stocks), size)]

    def _fetch_live_quote_enrichment(self, stocks: List[Dict[str, Any]]) -> Tuple[Dict[int, Dict[str, Any]], Dict[str, Any]]:
        if not self.config.stage2_live_quote_enrichment_enabled:
            return {}, {"status": "disabled", "quotes": 0, "failed_batches": 0}

        batches = self._chunk_stocks(stocks, self.config.stage2_quote_batch_size)
        quotes: Dict[int, Dict[str, Any]] = {}
        failed_batches = 0
        print(f"Stage 2 live quote enrichment: fetching {len(batches)} batch(es)...")
        for index, batch in enumerate(batches, 1):
            batch_ids = [int(stock["security_id"]) for stock in batch]
            try:
                quote_map = self.dhan.fetch_quote_batch(batch_ids, exchange_segment="BSE_EQ")
            except Exception as exc:
                failed_batches += 1
                self._record_fetch_failure(f"quote_batch_failed::{type(exc).__name__}")
                print(f"  Stage 2 quote batch {index}/{len(batches)} failed: {exc}")
                continue
            quotes.update(quote_map)
            print(f"  Stage 2 quote batch {index}/{len(batches)} complete")

        return quotes, {
            "status": "completed",
            "quotes": len(quotes),
            "failed_batches": failed_batches,
            "batch_count": len(batches),
        }

    def _first_number(self, payload: Any, keys: Tuple[str, ...]) -> Optional[float]:
        if isinstance(payload, dict):
            for key in keys:
                value = payload.get(key)
                if value in (None, ""):
                    continue
                try:
                    number = float(value)
                except Exception:
                    continue
                if not math.isnan(number) and not math.isinf(number):
                    return number
            for value in payload.values():
                nested = self._first_number(value, keys)
                if nested is not None:
                    return nested
        elif isinstance(payload, list):
            for value in payload:
                nested = self._first_number(value, keys)
                if nested is not None:
                    return nested
        return None

    def _first_level_number(self, levels: Any, keys: Tuple[str, ...]) -> Optional[float]:
        if not isinstance(levels, list):
            return None
        for level in levels:
            if not isinstance(level, dict):
                continue
            value = self._first_number(level, keys)
            if value is not None and value > 0:
                return value
        return None

    def _build_quote_features(self, quote_item: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not quote_item:
            return {
                "quote_available": False,
                "live_price": None,
                "bid_price": None,
                "ask_price": None,
                "bid_quantity": None,
                "ask_quantity": None,
                "spread_percent": None,
                "live_volume": None,
                "live_intraday_value_cr": None,
                "open_interest": None,
                "quote_depth_levels": 0,
                "quote_raw_keys": [],
            }

        depth = quote_item.get("depth") or quote_item.get("market_depth") or {}
        buy_levels = []
        sell_levels = []
        if isinstance(depth, dict):
            buy_levels = depth.get("buy") or depth.get("bids") or []
            sell_levels = depth.get("sell") or depth.get("asks") or []
        elif isinstance(depth, list):
            buy_levels = depth
            sell_levels = depth

        bid_price = self._first_level_number(
            buy_levels,
            ("price", "bid_price", "bidPrice", "best_bid_price", "bestBidPrice"),
        ) or self._first_number(quote_item, ("best_bid_price", "bestBidPrice", "bid_price", "bidPrice", "bid"))
        ask_price = self._first_level_number(
            sell_levels,
            ("price", "ask_price", "askPrice", "best_ask_price", "bestAskPrice"),
        ) or self._first_number(quote_item, ("best_ask_price", "bestAskPrice", "ask_price", "askPrice", "ask"))
        bid_quantity = self._first_level_number(
            buy_levels,
            ("quantity", "qty", "bid_quantity", "bidQuantity", "bid_qty"),
        ) or self._first_number(quote_item, ("bid_quantity", "bidQuantity", "bid_qty"))
        ask_quantity = self._first_level_number(
            sell_levels,
            ("quantity", "qty", "ask_quantity", "askQuantity", "ask_qty"),
        ) or self._first_number(quote_item, ("ask_quantity", "askQuantity", "ask_qty"))
        live_price = self._first_number(
            quote_item,
            ("last_price", "lastPrice", "LTP", "ltp", "latest_traded_price"),
        )
        live_volume = self._first_number(quote_item, ("volume", "Volume", "total_volume"))
        open_interest = self._first_number(quote_item, ("open_interest", "openInterest", "oi", "OI"))

        spread_percent = None
        if bid_price is not None and ask_price is not None:
            mid = (bid_price + ask_price) / 2.0
            if mid > 0:
                spread_percent = ((ask_price - bid_price) / mid) * 100.0

        live_intraday_value_cr = None
        if live_price is not None and live_volume is not None:
            live_intraday_value_cr = (live_price * live_volume) / 10000000

        return {
            "quote_available": True,
            "live_price": round(live_price, 4) if live_price is not None else None,
            "bid_price": round(bid_price, 4) if bid_price is not None else None,
            "ask_price": round(ask_price, 4) if ask_price is not None else None,
            "bid_quantity": int(bid_quantity) if bid_quantity is not None else None,
            "ask_quantity": int(ask_quantity) if ask_quantity is not None else None,
            "spread_percent": round(spread_percent, 4) if spread_percent is not None else None,
            "live_volume": int(live_volume) if live_volume is not None else None,
            "live_intraday_value_cr": round(live_intraday_value_cr, 4) if live_intraday_value_cr is not None else None,
            "open_interest": int(open_interest) if open_interest is not None else None,
            "quote_depth_levels": max(len(buy_levels) if isinstance(buy_levels, list) else 0, len(sell_levels) if isinstance(sell_levels, list) else 0),
            "quote_raw_keys": sorted(str(key) for key in quote_item.keys())[:30],
        }

    def _score_live_liquidity(self, quote_features: Dict[str, Any], adv_20_cr: Any) -> Dict[str, Any]:
        score = 50.0
        reasons: List[str] = []

        spread = quote_features.get("spread_percent")
        if spread is None:
            reasons.append("spread_unavailable")
        elif spread <= self.config.stage2_good_spread_percent:
            score += 25.0
            reasons.append("tight_spread")
        elif spread <= self.config.stage2_acceptable_spread_percent:
            score += 10.0
            reasons.append("acceptable_spread")
        else:
            score -= min(35.0, (float(spread) - self.config.stage2_acceptable_spread_percent) * 80.0)
            reasons.append("wide_spread")

        intraday_value = quote_features.get("live_intraday_value_cr")
        if intraday_value is None:
            reasons.append("intraday_value_unavailable")
        elif float(intraday_value) >= self.config.stage2_min_intraday_value_cr:
            score += min(20.0, float(intraday_value) / max(self.config.stage2_min_intraday_value_cr, 0.01) * 4.0)
            reasons.append("live_value_ok")
        else:
            score -= 10.0
            reasons.append("low_live_value")

        try:
            adv = float(adv_20_cr or 0.0)
        except Exception:
            adv = 0.0
        if adv >= self.config.stage1_min_adv_cr * 2:
            score += 5.0
        elif adv < self.config.stage1_min_adv_cr:
            score -= 10.0

        if quote_features.get("bid_quantity") and quote_features.get("ask_quantity"):
            score += 5.0
            bid_qty = float(quote_features["bid_quantity"])
            ask_qty = float(quote_features["ask_quantity"])
            imbalance = (bid_qty - ask_qty) / (bid_qty + ask_qty) if bid_qty + ask_qty > 0 else None
        else:
            imbalance = None

        return {
            "score": round(max(0.0, min(score, 100.0)), 2),
            "reasons": reasons,
            "top_book_imbalance": round(imbalance, 4) if imbalance is not None else None,
        }

    def _score_data_quality(self, record: Dict[str, Any], quote_features: Dict[str, Any]) -> Dict[str, Any]:
        score = 100.0
        warnings: List[str] = []
        if record.get("time_of_day_rvol") is None:
            score -= 25.0
            warnings.append("rvol_unavailable")
        if record.get("intraday_vwap") is None:
            score -= 15.0
            warnings.append("vwap_unavailable")
        if record.get("volume_acceleration_ratio") is None:
            score -= 10.0
            warnings.append("volume_acceleration_unavailable")
        if not quote_features.get("quote_available"):
            score -= 20.0
            warnings.append("live_quote_unavailable")
        elif quote_features.get("spread_percent") is None:
            score -= 10.0
            warnings.append("spread_unavailable")
        return {"score": round(max(0.0, score), 2), "warnings": warnings}

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

    def _score_selection_record(self, record: Dict[str, Any]) -> float:
        base = float(record.get("stage2_score") or 0.0)
        liquidity = float((record.get("live_liquidity") or {}).get("score") or 50.0)
        data_quality = float((record.get("data_quality") or {}).get("score") or 80.0)
        # Keep momentum dominant, but prefer cleaner, more tradable candidates.
        score = base * 0.72 + liquidity * 0.20 + data_quality * 0.08
        return round(score, 2)

    def _process_stock(
        self,
        stock: Dict[str, Any],
        quote_map: Dict[int, Dict[str, Any]],
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
        quote_features = self._build_quote_features(quote_map.get(security_id))
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
            "avg_volume_20": stock.get("avg_volume_20"),
            "previous_session": stock.get("previous_session"),
            "static_tradability": stock.get("static_tradability"),
            "derivatives": stock.get("derivatives"),
            "live_quote": quote_features,
            "stage2_reason": None,
            "stage2_score": None,
            "selection_score": None,
            "live_liquidity": None,
            "data_quality": None,
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
            record["live_liquidity"] = self._score_live_liquidity(quote_features, record.get("adv_20_cr"))
            record["data_quality"] = self._score_data_quality(record, quote_features)
            record["selection_score"] = self._score_selection_record(record)
        elif record["stage2_reason"]:
            record["live_liquidity"] = self._score_live_liquidity(quote_features, record.get("adv_20_cr"))
            record["data_quality"] = self._score_data_quality(record, quote_features)
            self._record_filter_reason(record["stage2_reason"])

        status_text = "PASS" if passed else f"FILTERED ({record['stage2_reason']})"
        print(
            f"Stage 2 result {security_id}: {status_text} | "
            f"rvol={record['time_of_day_rvol']} "
            f"vwap_delta={record['price_vs_vwap_percent']} "
            f"orb={record['opening_range_breakout_percent']} "
            f"vol_accel={record['volume_acceleration_ratio']} "
            f"spread={quote_features.get('spread_percent')} "
            f"liq={record.get('live_liquidity', {}).get('score') if record.get('live_liquidity') else None}"
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
        print("  2. Fetch one batched live quote snapshot for cheap liquidity enrichment")
        print("  3. Fetch intraday minute history for each stock in parallel")
        print("  4. Compute RVOL, VWAP, opening-range breakout, volume acceleration, and liquidity scores")
        print("  5. Filter for active momentum ignition candidates")
        print("  6. Rank passed stocks by momentum plus liquidity/data-quality score")

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
                    "status": "blocked",
                    "degraded_reasons": ["no_stage1_stocks"],
                    "stage2_filters": self._build_filters_summary(),
                },
                "stocks",
                [],
            )
            self._save_payload(payload)
            print("Stage 2 skipped because Stage 1 produced zero survivors.")
            return payload

        total = len(stage1_stocks)
        quote_map, quote_summary = self._fetch_live_quote_enrichment(stage1_stocks)
        print(
            "Stage 2 quote enrichment summary: "
            f"status={quote_summary.get('status')}, "
            f"quotes={quote_summary.get('quotes')}, "
            f"failed_batches={quote_summary.get('failed_batches')}"
        )
        print(
            f"Stage 2 ignition scan starting for {total} stock(s) "
            f"with {workers} worker(s) and shared rate limit {self.config.historical_rate_limit_per_sec}/sec"
        )

        all_records: List[Dict[str, Any]] = []
        passed_records: List[Dict[str, Any]] = []
        failed_count = 0

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(self._process_stock, stock, quote_map, idx, total): stock
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
                -float(row.get("selection_score") or row.get("stage2_score") or 0.0),
                -float(row.get("stage2_score") or 0.0),
            )
        )
        stage_funnel = self._build_stage_funnel_counts(total, all_records, failed_count)
        score_distribution = self._summarize_numeric_series(
            [float(row.get("stage2_score") or 0.0) for row in passed_records]
        )
        near_misses = self._build_near_misses(all_records)
        fetch_failure_ratio = (failed_count / total) if total else 0.0
        quote_degraded = (
            self.config.stage2_live_quote_enrichment_enabled
            and int(quote_summary.get("failed_batches") or 0) > 0
        )
        is_degraded = (
            fetch_failure_ratio > self.config.stage2_max_fetch_failure_ratio
            or quote_degraded
        )
        stage_status = "degraded" if is_degraded else "completed"
        degraded_reasons: List[str] = []
        if fetch_failure_ratio > self.config.stage2_max_fetch_failure_ratio:
            degraded_reasons.append("intraday_fetch_failure_ratio")
        if quote_degraded:
            degraded_reasons.append("quote_enrichment_failure")

        summary = {
            "market_date": self.market_time.market_date_str(),
            "input_stage1_count": total,
            "data_retrieved": len(all_records),
            "failed_fetch": failed_count,
            "stage2_passed": len(passed_records),
            "status": stage_status,
            "fetch_failure_ratio": round(fetch_failure_ratio, 6),
            "max_fetch_failure_ratio": self.config.stage2_max_fetch_failure_ratio,
            "degraded_reasons": degraded_reasons,
            "stage2_filters": self._build_filters_summary(),
            "stage_funnel_counts": stage_funnel,
            "score_distribution": score_distribution,
            "near_misses": near_misses,
            "filter_reason_counts": dict(self.filter_reasons),
            "fetch_failure_reason_counts": dict(self.fetch_failure_reasons),
            "quote_enrichment": quote_summary,
        }

        payload = StorageService.build_payload(
            "stage2_momentum_ignition",
            summary,
            "stocks",
            passed_records,
        )
        self._save_payload(payload)

        daily_path = (
            self.config.stage2_degraded_path(self.market_time.market_date_str())
            if is_degraded
            else self.config.stage2_daily_path(self.market_time.market_date_str())
        )
        print(f"\nStage 2 {stage_status}")
        print(f"Passed Stage 2: {len(passed_records)}")
        print(f"Stage 2 records evaluated: {len(all_records)}")
        print(f"Stage 2 records skipped / fetch failed: {failed_count}")
        if is_degraded:
            print(f"Saved diagnostic degraded snapshot: {daily_path.name}")
            print("Official Stage 2 snapshots were not published.")
        else:
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
                    f"selection={record.get('selection_score')} "
                    f"rvol={record.get('time_of_day_rvol')} "
                    f"vwap_delta={record.get('price_vs_vwap_percent')} "
                    f"orb={record.get('opening_range_breakout_percent')} "
                    f"vol_accel={record.get('volume_acceleration_ratio')} "
                    f"spread={(record.get('live_quote') or {}).get('spread_percent')} "
                    f"liq={(record.get('live_liquidity') or {}).get('score')}"
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
