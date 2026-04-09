from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, time as dt_time, timedelta, timezone
import math
from statistics import pstdev
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from pipeline.config import PipelineConfig
from pipeline.services.dhan_service import DhanService
from pipeline.services.market_time_service import MarketTimeService
from pipeline.services.storage_service import StorageService


class MarketRegimeAnalyzer:
    """
    Standalone market-context lane.
    It consumes a liquid basket sourced from Stage 1, computes market-wide
    intraday structure diagnostics, classifies the current regime, and saves
    the result to JSON. It does not modify any other pipeline behavior.
    """

    def __init__(self, config: Optional[PipelineConfig] = None):
        self.config = config or PipelineConfig()
        self.dhan = DhanService(self.config)
        self.market_time = MarketTimeService(self.config)

    def _payload_market_date(self, payload: Optional[Dict[str, Any]]) -> Optional[str]:
        if not payload:
            return None
        summary_market_date = payload.get("summary", {}).get("market_date")
        if summary_market_date:
            return str(summary_market_date)
        return StorageService.snapshot_market_date(payload, self.config.market_timezone)

    def _load_stage1_payload(self) -> Optional[Dict[str, Any]]:
        market_date = self.market_time.market_date_str()
        daily_path = self.config.stage1_daily_path(market_date)
        payload = StorageService.load_snapshot(daily_path)
        if payload:
            return payload

        latest_payload = StorageService.load_snapshot(self.config.stage1_latest_path)
        if self._payload_market_date(latest_payload) == market_date:
            print(
                f"Using latest Stage 1 snapshot for current market date {market_date} "
                f"from {self.config.stage1_latest_path.name}"
            )
            return latest_payload
        return None

    def _load_stage2_payload(self) -> Optional[Dict[str, Any]]:
        market_date = self.market_time.market_date_str()
        daily_path = self.config.stage2_daily_path(market_date)
        payload = StorageService.load_snapshot(daily_path)
        if payload:
            return payload

        latest_payload = StorageService.load_snapshot(self.config.stage2_latest_path)
        if self._payload_market_date(latest_payload) == market_date:
            return latest_payload
        return None

    def _load_regime_basket(self) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        stage1_payload = self._load_stage1_payload()
        if not stage1_payload:
            return [], {
                "source": "stage1",
                "status": "waiting_for_stage1_snapshot",
                "market_date": self.market_time.market_date_str(),
            }

        stage1_stocks = list(stage1_payload.get("stocks", []))
        stage1_stocks.sort(key=lambda row: -float(row.get("adv_20_cr") or 0.0))
        basket = stage1_stocks[: self.config.regime_basket_size]

        return basket, {
            "source": "stage1",
            "status": "ready",
            "market_date": self.market_time.market_date_str(),
            "stage1_count": len(stage1_stocks),
            "basket_size": len(basket),
        }

    def _today_market_frame(self, frame: pd.DataFrame) -> pd.DataFrame:
        if frame.empty:
            return frame

        local_ts = frame["timestamp"].dt.tz_localize("UTC").dt.tz_convert(self.market_time.tz)
        local_frame = frame.copy()
        local_frame["market_timestamp"] = local_ts
        local_frame["market_date"] = local_ts.dt.date
        today = self.market_time.now().date()
        return local_frame[local_frame["market_date"] == today].sort_values("market_timestamp")

    def _compute_intraday_vwap(self, today_frame: pd.DataFrame) -> Optional[float]:
        if today_frame.empty or "volume" not in today_frame.columns:
            return None

        volume = pd.to_numeric(today_frame["volume"], errors="coerce").fillna(0.0)
        total_volume = float(volume.sum())
        if math.isclose(total_volume, 0.0):
            return None

        typical_price = (
            pd.to_numeric(today_frame["high"], errors="coerce").fillna(0.0)
            + pd.to_numeric(today_frame["low"], errors="coerce").fillna(0.0)
            + pd.to_numeric(today_frame["close"], errors="coerce").fillna(0.0)
        ) / 3.0
        vwap = (typical_price * volume).sum() / total_volume
        return float(vwap) if pd.notna(vwap) else None

    def _compute_opening_range(self, today_frame: pd.DataFrame) -> Tuple[Optional[float], Optional[float], bool]:
        if today_frame.empty or "market_timestamp" not in today_frame.columns:
            return None, None, False

        open_dt = datetime.combine(
            self.market_time.now().date(),
            dt_time(self.config.market_open_hour, self.config.market_open_minute),
            tzinfo=self.market_time.tz,
        )
        range_end = open_dt + timedelta(minutes=self.config.regime_opening_range_minutes)
        opening_slice = today_frame[
            (today_frame["market_timestamp"] >= open_dt)
            & (today_frame["market_timestamp"] < range_end)
        ]

        expected_bars = self.config.regime_opening_range_minutes
        is_complete = len(opening_slice) >= max(3, expected_bars // 2)
        if opening_slice.empty:
            return None, None, False

        opening_high = float(pd.to_numeric(opening_slice["high"], errors="coerce").max())
        opening_low = float(pd.to_numeric(opening_slice["low"], errors="coerce").min())
        return opening_high, opening_low, is_complete

    def _process_stock(self, stock: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        security_id = int(stock["security_id"])
        resp = self.dhan.fetch_intraday_history(
            security_id,
            days=self.config.regime_history_days,
            interval=1,
            exchange_segment="BSE_EQ",
            instrument_candidates=[stock.get("instrument"), "EQUITY"],
        )
        if not resp or str(resp.get("status", "")).lower() != "success":
            return None, "intraday_history_failed"

        frame = self.dhan.intraday_response_to_df(resp)
        if frame.empty:
            return None, "intraday_history_empty"

        today_frame = self._today_market_frame(frame)
        if len(today_frame) < 3:
            return None, "intraday_today_insufficient"

        latest_price = float(pd.to_numeric(today_frame["close"], errors="coerce").iloc[-1])
        session_open = float(pd.to_numeric(today_frame["open"], errors="coerce").iloc[0])
        session_high = float(pd.to_numeric(today_frame["high"], errors="coerce").max())
        session_low = float(pd.to_numeric(today_frame["low"], errors="coerce").min())
        vwap = self._compute_intraday_vwap(today_frame)
        opening_high, opening_low, opening_range_complete = self._compute_opening_range(today_frame)
        rvol = self.dhan.compute_time_of_day_rvol(frame)
        atr_percent = float(stock.get("atr_percent") or 0.0)

        price_vs_open_percent = None
        if session_open > 0:
            price_vs_open_percent = ((latest_price - session_open) / session_open) * 100.0

        price_vs_vwap_percent = None
        if vwap and vwap > 0:
            price_vs_vwap_percent = ((latest_price - vwap) / vwap) * 100.0

        opening_range_breakout_percent = None
        opening_range_breakdown_percent = None
        if opening_high and opening_high > 0:
            opening_range_breakout_percent = ((latest_price - opening_high) / opening_high) * 100.0
        if opening_low and opening_low > 0:
            opening_range_breakdown_percent = ((opening_low - latest_price) / opening_low) * 100.0

        move_vs_atr_ratio = None
        if atr_percent > 0 and price_vs_open_percent is not None:
            move_vs_atr_ratio = abs(price_vs_open_percent) / atr_percent

        adv_20_cr = float(stock.get("adv_20_cr") or 0.0)
        weight = max(1.0, adv_20_cr)

        return {
            "security_id": security_id,
            "symbol": stock.get("symbol"),
            "display_name": stock.get("display_name"),
            "weight": round(weight, 4),
            "adv_20_cr": round(adv_20_cr, 2),
            "atr_percent": round(atr_percent, 2),
            "time_of_day_rvol": round(rvol, 4) if rvol is not None else None,
            "session_open": round(session_open, 4),
            "session_high": round(session_high, 4),
            "session_low": round(session_low, 4),
            "latest_price": round(latest_price, 4),
            "intraday_vwap": round(vwap, 4) if vwap is not None else None,
            "price_vs_open_percent": round(price_vs_open_percent, 4) if price_vs_open_percent is not None else None,
            "price_vs_vwap_percent": round(price_vs_vwap_percent, 4) if price_vs_vwap_percent is not None else None,
            "opening_range_high": round(opening_high, 4) if opening_high is not None else None,
            "opening_range_low": round(opening_low, 4) if opening_low is not None else None,
            "opening_range_complete": opening_range_complete,
            "opening_range_breakout_percent": (
                round(opening_range_breakout_percent, 4)
                if opening_range_breakout_percent is not None
                else None
            ),
            "opening_range_breakdown_percent": (
                round(opening_range_breakdown_percent, 4)
                if opening_range_breakdown_percent is not None
                else None
            ),
            "is_above_open": bool(price_vs_open_percent is not None and price_vs_open_percent > 0),
            "is_above_vwap": bool(price_vs_vwap_percent is not None and price_vs_vwap_percent > 0),
            "is_opening_range_breakout": bool(
                opening_range_breakout_percent is not None and opening_range_breakout_percent > 0
            ),
            "is_opening_range_breakdown": bool(
                opening_range_breakdown_percent is not None and opening_range_breakdown_percent > 0
            ),
            "move_vs_atr_ratio": round(move_vs_atr_ratio, 4) if move_vs_atr_ratio is not None else None,
        }, None

    def _weighted_ratio(self, rows: List[Dict[str, Any]], key: str) -> float:
        total_weight = sum(float(row.get("weight") or 0.0) for row in rows)
        if total_weight <= 0:
            return 0.0
        positive_weight = sum(
            float(row.get("weight") or 0.0) for row in rows if bool(row.get(key))
        )
        return positive_weight / total_weight

    def _weighted_average(self, rows: List[Dict[str, Any]], key: str) -> Optional[float]:
        pairs: List[Tuple[float, float]] = []
        for row in rows:
            raw_value = row.get(key)
            if raw_value is None:
                continue
            try:
                value = float(raw_value)
                weight = float(row.get("weight") or 0.0)
            except Exception:
                continue
            pairs.append((value, weight))

        if not pairs:
            return None

        total_weight = sum(weight for _, weight in pairs)
        if total_weight <= 0:
            return None
        return sum(value * weight for value, weight in pairs) / total_weight

    def _average(self, rows: List[Dict[str, Any]], key: str, absolute: bool = False) -> Optional[float]:
        values: List[float] = []
        for row in rows:
            raw_value = row.get(key)
            if raw_value is None:
                continue
            try:
                value = float(raw_value)
            except Exception:
                continue
            values.append(abs(value) if absolute else value)
        if not values:
            return None
        return sum(values) / len(values)

    def _top_movers(
        self,
        rows: List[Dict[str, Any]],
        key: str,
        reverse: bool,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        filtered = [row for row in rows if row.get(key) is not None]
        filtered.sort(key=lambda row: float(row.get(key) or 0.0), reverse=reverse)
        result: List[Dict[str, Any]] = []
        for row in filtered[:limit]:
            result.append(
                {
                    "security_id": row.get("security_id"),
                    "display_name": row.get("display_name"),
                    key: row.get(key),
                }
            )
        return result

    def _minutes_since_market_open(self) -> int:
        now = self.market_time.now()
        market_open = now.replace(
            hour=self.config.market_open_hour,
            minute=self.config.market_open_minute,
            second=0,
            microsecond=0,
        )
        return max(0, int((now - market_open).total_seconds() // 60))

    def _confidence_score(
        self,
        sorted_scores: List[Tuple[str, float]],
        coverage_ratio: float,
        warmed_up: bool,
    ) -> float:
        if not sorted_scores:
            return 0.0

        top_score = sorted_scores[0][1]
        runner_up = sorted_scores[1][1] if len(sorted_scores) > 1 else 0.0
        margin = max(0.0, top_score - runner_up)
        confidence = min(100.0, (margin * 0.9) + (coverage_ratio * 35.0) + (20.0 if warmed_up else 0.0))
        return round(confidence, 2)

    def _build_reasoning_summary(
        self,
        regime_label: str,
        metrics: Dict[str, Optional[float]],
    ) -> str:
        weighted_move = metrics.get("weighted_price_vs_open_percent_avg")
        weighted_vwap = metrics.get("weighted_price_vs_vwap_percent_avg")
        above_open = metrics.get("above_open_ratio")
        above_vwap = metrics.get("above_vwap_ratio")
        breakout = metrics.get("breakout_ratio")
        breakdown = metrics.get("breakdown_ratio")
        avg_rvol = metrics.get("avg_rvol")

        if regime_label == "trend_up":
            return (
                "Broad liquid-basket participation is skewed upward with positive open-to-current drift, "
                "positive VWAP positioning, and stronger breakout participation than breakdown pressure."
            )
        if regime_label == "trend_down":
            return (
                "Broad liquid-basket participation is skewed downward with negative open-to-current drift, "
                "negative VWAP positioning, and stronger breakdown participation than upside continuation."
            )
        if regime_label == "event_risk":
            return (
                "Cross-sectional move size and RVOL are elevated versus normal intraday baselines, "
                "suggesting an unusually volatile or news-heavy session."
            )
        if regime_label == "mean_reversion":
            return (
                "The basket is rotating around the session anchor rather than persisting away from it, "
                "with limited net directional edge despite active participation."
            )
        if regime_label == "choppy":
            return (
                "Directional breadth is mixed and follow-through is weak, pointing to an indecisive session "
                "with limited structure persistence."
            )
        return (
            "Regime remains provisional while the opening session develops. "
            f"weighted_move={weighted_move}, weighted_vwap={weighted_vwap}, "
            f"above_open={above_open}, above_vwap={above_vwap}, "
            f"breakout={breakout}, breakdown={breakdown}, avg_rvol={avg_rvol}"
        )

    def _classify_regime(
        self,
        rows: List[Dict[str, Any]],
        stage2_payload: Optional[Dict[str, Any]],
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        coverage_ratio = len(rows) / max(1, self.config.regime_basket_size)
        minutes_since_open = self._minutes_since_market_open()
        warmed_up = minutes_since_open >= self.config.regime_min_minutes_after_open

        above_open_ratio = self._weighted_ratio(rows, "is_above_open")
        above_vwap_ratio = self._weighted_ratio(rows, "is_above_vwap")
        breakout_ratio = self._weighted_ratio(rows, "is_opening_range_breakout")
        breakdown_ratio = self._weighted_ratio(rows, "is_opening_range_breakdown")

        weighted_price_vs_open = self._weighted_average(rows, "price_vs_open_percent") or 0.0
        weighted_price_vs_vwap = self._weighted_average(rows, "price_vs_vwap_percent") or 0.0
        avg_abs_price_vs_open = self._average(rows, "price_vs_open_percent", absolute=True) or 0.0
        avg_abs_price_vs_vwap = self._average(rows, "price_vs_vwap_percent", absolute=True) or 0.0
        avg_rvol = self._average(rows, "time_of_day_rvol") or 0.0
        avg_move_vs_atr = self._average(rows, "move_vs_atr_ratio") or 0.0

        price_vs_open_values = [
            float(row["price_vs_open_percent"])
            for row in rows
            if row.get("price_vs_open_percent") is not None
        ]
        price_vs_vwap_values = [
            float(row["price_vs_vwap_percent"])
            for row in rows
            if row.get("price_vs_vwap_percent") is not None
        ]
        open_dispersion = pstdev(price_vs_open_values) if len(price_vs_open_values) >= 2 else 0.0
        vwap_dispersion = pstdev(price_vs_vwap_values) if len(price_vs_vwap_values) >= 2 else 0.0

        direction_balance = 1.0 - min(abs(above_open_ratio - 0.5) / 0.5, 1.0)
        vwap_balance = 1.0 - min(abs(above_vwap_ratio - 0.5) / 0.5, 1.0)
        breakout_imbalance = breakout_ratio - breakdown_ratio
        breakout_symmetry = min(breakout_ratio, breakdown_ratio) * 2.0

        trend_up_score = (
            min(max(above_open_ratio - 0.5, 0.0) / 0.5, 1.0) * 24.0
            + min(max(above_vwap_ratio - 0.5, 0.0) / 0.5, 1.0) * 24.0
            + min(max(weighted_price_vs_open, 0.0) / 1.25, 1.0) * 18.0
            + min(max(breakout_imbalance, 0.0) / 0.35, 1.0) * 18.0
            + min(max(avg_rvol - 1.0, 0.0) / 1.5, 1.0) * 16.0
        )
        trend_down_score = (
            min(max((1.0 - above_open_ratio) - 0.5, 0.0) / 0.5, 1.0) * 24.0
            + min(max((1.0 - above_vwap_ratio) - 0.5, 0.0) / 0.5, 1.0) * 24.0
            + min(max(-weighted_price_vs_open, 0.0) / 1.25, 1.0) * 18.0
            + min(max(-breakout_imbalance, 0.0) / 0.35, 1.0) * 18.0
            + min(max(avg_rvol - 1.0, 0.0) / 1.5, 1.0) * 16.0
        )
        mean_reversion_score = (
            (1.0 - min(abs(weighted_price_vs_vwap) / 0.6, 1.0)) * 26.0
            + (1.0 - min(abs(weighted_price_vs_open) / 0.8, 1.0)) * 18.0
            + breakout_symmetry * 18.0
            + direction_balance * 18.0
            + min(avg_rvol / 2.0, 1.0) * 12.0
            + (1.0 - min(abs(breakout_imbalance) / 0.25, 1.0)) * 8.0
        )
        choppy_score = (
            (1.0 - min(avg_abs_price_vs_open / 1.0, 1.0)) * 28.0
            + (1.0 - min(avg_rvol / 1.5, 1.0)) * 26.0
            + direction_balance * 20.0
            + vwap_balance * 14.0
            + (1.0 - min((breakout_ratio + breakdown_ratio) / 0.35, 1.0)) * 12.0
        )
        event_risk_score = (
            min(avg_move_vs_atr / 1.2, 1.0) * 36.0
            + min(avg_rvol / 2.5, 1.0) * 28.0
            + min(open_dispersion / 1.8, 1.0) * 20.0
            + min(avg_abs_price_vs_open / 1.75, 1.0) * 16.0
        )

        score_map = {
            "trend_up": round(trend_up_score, 2),
            "trend_down": round(trend_down_score, 2),
            "mean_reversion": round(mean_reversion_score, 2),
            "choppy": round(choppy_score, 2),
            "event_risk": round(event_risk_score, 2),
        }
        sorted_scores = sorted(score_map.items(), key=lambda item: item[1], reverse=True)
        regime_label = sorted_scores[0][0] if sorted_scores else "unclassified"
        confidence = self._confidence_score(sorted_scores, coverage_ratio, warmed_up)

        regime_status = "completed" if warmed_up else "warming_up"
        if not rows:
            regime_label = "unclassified"
            regime_status = "waiting_for_data"
            confidence = 0.0

        metrics = {
            "above_open_ratio": round(above_open_ratio, 4),
            "above_vwap_ratio": round(above_vwap_ratio, 4),
            "breakout_ratio": round(breakout_ratio, 4),
            "breakdown_ratio": round(breakdown_ratio, 4),
            "weighted_price_vs_open_percent_avg": round(weighted_price_vs_open, 4),
            "weighted_price_vs_vwap_percent_avg": round(weighted_price_vs_vwap, 4),
            "avg_abs_price_vs_open_percent": round(avg_abs_price_vs_open, 4),
            "avg_abs_price_vs_vwap_percent": round(avg_abs_price_vs_vwap, 4),
            "avg_rvol": round(avg_rvol, 4),
            "avg_move_vs_atr_ratio": round(avg_move_vs_atr, 4),
            "open_dispersion": round(open_dispersion, 4),
            "vwap_dispersion": round(vwap_dispersion, 4),
            "coverage_ratio": round(coverage_ratio, 4),
            "minutes_since_open": minutes_since_open,
        }

        stage2_context = {
            "available": bool(stage2_payload),
            "stage2_passed": int(stage2_payload.get("summary", {}).get("stage2_passed", 0))
            if stage2_payload
            else 0,
            "top_stage2_names": [
                row.get("display_name") or row.get("symbol")
                for row in (stage2_payload.get("stocks", [])[:5] if stage2_payload else [])
            ],
        }

        reasoning_summary = self._build_reasoning_summary(regime_label, metrics)
        regime = {
            "status": regime_status,
            "market_regime": regime_label,
            "confidence": confidence,
            "minutes_since_open": minutes_since_open,
            "is_actionable": warmed_up,
            "style_inference": regime_label,
            "score_map": score_map,
            "reasoning_summary": reasoning_summary,
            "metrics": metrics,
            "stage2_context": stage2_context,
        }
        diagnostics = {
            "top_scores": sorted_scores[:3],
            "top_gainers_from_open": self._top_movers(rows, "price_vs_open_percent", reverse=True),
            "top_losers_from_open": self._top_movers(rows, "price_vs_open_percent", reverse=False),
            "top_rvol": self._top_movers(rows, "time_of_day_rvol", reverse=True),
        }
        return regime, diagnostics

    def _save_payload(self, payload: Dict[str, Any]) -> None:
        StorageService.save_snapshot(self.config.regime_latest_path, payload)
        StorageService.save_snapshot(
            self.config.regime_daily_path(self.market_time.market_date_str()),
            payload,
        )

    def _build_waiting_payload(self, basket_meta: Dict[str, Any]) -> Dict[str, Any]:
        now_utc = datetime.now(timezone.utc).isoformat()
        summary = {
            "market_date": self.market_time.market_date_str(),
            "status": basket_meta.get("status", "waiting"),
            "basket_source": basket_meta.get("source"),
            "input_stage1_count": basket_meta.get("stage1_count", 0),
            "configured_basket_size": self.config.regime_basket_size,
            "analyzed_count": 0,
            "failed_fetch": 0,
            "review_interval_seconds": self.config.regime_loop_interval_seconds,
        }
        payload = {
            "stage": "market_regime",
            "generated_at_utc": now_utc,
            "summary": summary,
            "regime": {
                "status": basket_meta.get("status", "waiting"),
                "market_regime": "unclassified",
                "confidence": 0.0,
                "minutes_since_open": self._minutes_since_market_open(),
                "is_actionable": False,
                "style_inference": "unclassified",
                "score_map": {},
                "reasoning_summary": "Regime is waiting for Stage 1 liquidity basket data before analysis can begin.",
                "metrics": {},
                "stage2_context": {
                    "available": False,
                    "stage2_passed": 0,
                    "top_stage2_names": [],
                },
            },
            "diagnostics": {
                "top_scores": [],
                "top_gainers_from_open": [],
                "top_losers_from_open": [],
                "top_rvol": [],
            },
            "basket": [],
        }
        self._save_payload(payload)
        return payload

    def run(self) -> Dict[str, Any]:
        print("=" * 60)
        print("REGIME - MARKET CONTEXT ANALYZER")
        print("=" * 60)
        print(f"Current market time: {self.market_time.market_status_text()}")

        basket, basket_meta = self._load_regime_basket()
        if not basket:
            print("Regime is waiting for Stage 1 to produce the liquid basket.")
            return self._build_waiting_payload(basket_meta)

        print(
            f"Loaded regime basket: {len(basket)} stock(s) sourced from Stage 1 "
            f"(configured basket size={self.config.regime_basket_size})"
        )

        analyzed_rows: List[Dict[str, Any]] = []
        failure_counts: Dict[str, int] = {}

        with ThreadPoolExecutor(max_workers=self.config.regime_workers) as executor:
            futures = [executor.submit(self._process_stock, stock) for stock in basket]
            for future in as_completed(futures):
                row, failure_reason = future.result()
                if row:
                    analyzed_rows.append(row)
                elif failure_reason:
                    failure_counts[failure_reason] = failure_counts.get(failure_reason, 0) + 1

        analyzed_rows.sort(key=lambda row: -float(row.get("weight") or 0.0))
        stage2_payload = self._load_stage2_payload()
        regime, diagnostics = self._classify_regime(analyzed_rows, stage2_payload)

        summary = {
            "market_date": self.market_time.market_date_str(),
            "status": regime.get("status"),
            "basket_source": basket_meta.get("source"),
            "input_stage1_count": basket_meta.get("stage1_count", 0),
            "configured_basket_size": self.config.regime_basket_size,
            "analyzed_count": len(analyzed_rows),
            "failed_fetch": sum(failure_counts.values()),
            "failure_reason_counts": failure_counts,
            "review_interval_seconds": self.config.regime_loop_interval_seconds,
            "next_review_at": (
                self.market_time.now() + timedelta(seconds=self.config.regime_loop_interval_seconds)
            ).isoformat(),
        }

        payload = {
            "stage": "market_regime",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "summary": summary,
            "regime": regime,
            "diagnostics": diagnostics,
            "basket": analyzed_rows,
        }
        self._save_payload(payload)

        print("\nRegime analysis complete")
        print(f"Regime status: {regime.get('status')}")
        print(f"Market regime: {regime.get('market_regime')}")
        print(f"Confidence: {regime.get('confidence')}")
        print(f"Analyzed basket count: {len(analyzed_rows)}")
        print(f"Saved latest snapshot: {self.config.regime_latest_path.name}")
        print(f"Saved daily snapshot: {self.config.regime_daily_path(self.market_time.market_date_str()).name}")
        return payload
