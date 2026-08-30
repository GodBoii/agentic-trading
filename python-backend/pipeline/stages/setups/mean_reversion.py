from __future__ import annotations

from datetime import datetime, time as dt_time
from typing import List

from pipeline.stages.live_state import LiveStockState
from pipeline.stages.setups.base import SetupSignal, arm_or_trigger, reset_tracker


class MeanReversionDetector:
    def evaluate(self, state: LiveStockState, now: datetime) -> List[SetupSignal]:
        signals: List[SetupSignal] = []
        gap = self._gap_rejection(state, now)
        if gap is not None:
            signals.append(gap)
        vwap = self._vwap_reversion(state, now)
        if vwap is not None:
            signals.append(vwap)
        return signals

    def _gap_rejection(self, state: LiveStockState, now: datetime) -> SetupSignal | None:
        tracker = state.setup_state.setdefault("GAP_REJECTION", {})
        if (
            not (dt_time(9, 15) <= now.time() < dt_time(9, 35))
            or not state.session_open
            or state.previous_close <= 0
        ):
            reset_tracker(tracker)
            return None
        gap = (state.session_open - state.previous_close) / state.previous_close * 100.0
        minimum_gap = max(0.50, state.historical_atr_percent * 0.22)
        if abs(gap) > max(15.0, state.historical_atr_percent * 4.0):
            # An unexplained discontinuity this large is more likely an
            # unadjusted corporate action than an executable opening gap.
            reset_tracker(tracker)
            return None
        reversal = state.return_percent(30, now.timestamp())
        direction = "SHORT" if gap > 0 else "LONG"
        directional_reversal = reversal < -0.10 if direction == "SHORT" else reversal > 0.10
        qualified = (
            abs(gap) >= minimum_gap
            and directional_reversal
            and state.volume_percentile >= 65
            and state.volatility_percentile >= 65
        )
        if not qualified:
            reset_tracker(tracker)
            return None
        extreme = float(state.session_high if direction == "SHORT" else state.session_low)
        return arm_or_trigger(
            tracker,
            now=now,
            family="GAP_REJECTION",
            direction=direction,
            level=extreme,
            invalidation=extreme,
            reason="an abnormal opening gap failed to continue and short-term price velocity reversed",
            diagnostics={
                "price": state.latest_price,
                "gap_percent": round(gap, 4),
                "reversal_percent": round(reversal, 4),
                "volume_percentile": state.volume_percentile,
                "volatility_percentile": state.volatility_percentile,
                "activity_rank": state.activity_rank,
            },
            hold_seconds=5,
            expiry_seconds=45,
        )

    def _vwap_reversion(self, state: LiveStockState, now: datetime) -> SetupSignal | None:
        tracker = state.setup_state.setdefault("VWAP_REVERSION", {})
        if not state.session_vwap or now.time() < dt_time(9, 20) or now.time() >= dt_time(15, 0):
            reset_tracker(tracker)
            return None
        extension = (state.latest_price - state.session_vwap) / state.session_vwap * 100.0
        minimum_extension = max(0.60, state.historical_atr_percent * 0.35)
        reversal = state.return_percent(30, now.timestamp())
        direction = "SHORT" if extension > 0 else "LONG"
        directional_reversal = reversal < -0.10 if direction == "SHORT" else reversal > 0.10
        qualified = (
            abs(extension) >= minimum_extension
            and directional_reversal
            and state.volume_percentile >= 65
            and state.volatility_percentile >= 70
        )
        if not qualified:
            reset_tracker(tracker)
            return None
        extreme = float(state.session_high if direction == "SHORT" else state.session_low)
        return arm_or_trigger(
            tracker,
            now=now,
            family="VWAP_REVERSION",
            direction=direction,
            level=state.session_vwap,
            invalidation=extreme,
            reason="price was unusually extended from session VWAP and short-term velocity reversed",
            diagnostics={
                "price": state.latest_price,
                "vwap": state.session_vwap,
                "extension_percent": round(extension, 4),
                "reversal_percent": round(reversal, 4),
                "volume_percentile": state.volume_percentile,
                "volatility_percentile": state.volatility_percentile,
                "activity_rank": state.activity_rank,
            },
            hold_seconds=5,
            expiry_seconds=45,
        )
