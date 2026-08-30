from __future__ import annotations

from datetime import datetime, time as dt_time
from typing import List

from pipeline.stages.live_state import LiveStockState
from pipeline.stages.setups.base import SetupSignal, arm_or_trigger, reset_tracker


class MomentumDetector:
    def evaluate(self, state: LiveStockState, now: datetime) -> List[SetupSignal]:
        signals: List[SetupSignal] = []
        opening = self._opening_drive(state, now)
        if opening is not None:
            signals.append(opening)
        breakout = self._opening_range_break(state, now)
        if breakout is not None:
            signals.append(breakout)
        ignition = self._volatility_ignition(state, now)
        if ignition is not None:
            signals.append(ignition)
        return signals

    def _opening_drive(self, state: LiveStockState, now: datetime) -> SetupSignal | None:
        tracker = state.setup_state.setdefault("OPENING_DRIVE", {})
        if not (dt_time(9, 15) <= now.time() < dt_time(9, 30)) or not state.first_packet_at:
            reset_tracker(tracker)
            return None
        try:
            observed = (now - datetime.fromisoformat(state.first_packet_at)).total_seconds()
        except ValueError:
            return None
        move = state.return_percent(30, now.timestamp())
        minimum_move = max(0.12, state.historical_atr_percent * 0.06)
        qualified = (
            observed >= 15
            and state.volume_percentile >= 75
            and state.volatility_percentile >= 70
            and state.relative_strength_percentile >= 60
            and state.trend_efficiency >= 0.58
            and abs(move) >= minimum_move
        )
        if not qualified:
            reset_tracker(tracker)
            return None
        direction = "LONG" if move > 0 else "SHORT"
        level = float(state.session_high if direction == "LONG" else state.session_low)
        invalidation = float(state.session_open or state.latest_price)
        return arm_or_trigger(
            tracker,
            now=now,
            family="OPENING_DRIVE",
            direction=direction,
            level=level,
            invalidation=invalidation,
            reason="opening participation, movement and path efficiency are jointly exceptional",
            diagnostics=self._diagnostics(state, move),
            hold_seconds=8,
            expiry_seconds=45,
        )

    def _opening_range_break(self, state: LiveStockState, now: datetime) -> SetupSignal | None:
        tracker = state.setup_state.setdefault("OPENING_RANGE_ACCEPTANCE", {})
        if not state.opening_range_complete or now.time() >= dt_time(15, 0):
            reset_tracker(tracker)
            return None
        buffer = state.latest_price * 0.0003
        direction = None
        level = 0.0
        if state.opening_range_high and state.latest_price > state.opening_range_high + buffer:
            direction, level = "LONG", state.opening_range_high
        elif state.opening_range_low and state.latest_price < state.opening_range_low - buffer:
            direction, level = "SHORT", state.opening_range_low
        move = state.return_percent(60, now.timestamp())
        qualified = (
            direction is not None
            and state.volume_percentile >= 70
            and state.volatility_percentile >= 65
            and state.relative_strength_percentile >= 50
            and state.trend_efficiency >= 0.50
            and ((direction == "LONG" and move > 0) or (direction == "SHORT" and move < 0))
        )
        if not qualified:
            reset_tracker(tracker)
            return None
        return arm_or_trigger(
            tracker,
            now=now,
            family="OPENING_RANGE_ACCEPTANCE",
            direction=direction,
            level=float(level),
            invalidation=float(level),
            reason="price accepted outside the completed opening range with active participation",
            diagnostics=self._diagnostics(state, move),
            hold_seconds=8,
            expiry_seconds=45,
        )

    def _volatility_ignition(self, state: LiveStockState, now: datetime) -> SetupSignal | None:
        tracker = state.setup_state.setdefault("VOLATILITY_IGNITION", {})
        move = state.return_percent(60, now.timestamp())
        acceleration = state.volume_acceleration or 0.0
        minimum_move = max(0.15, state.historical_atr_percent * 0.07)
        qualified = (
            now.time() < dt_time(15, 0)
            and state.volume_percentile >= 80
            and state.volatility_percentile >= 80
            and state.relative_strength_percentile >= 60
            and state.trend_efficiency >= 0.62
            and abs(move) >= minimum_move
            and acceleration >= 1.15
        )
        if not qualified:
            reset_tracker(tracker)
            return None
        direction = "LONG" if move > 0 else "SHORT"
        level = state.latest_price
        noise = max(state.latest_price * 0.002, state.historical_atr * 0.12)
        invalidation = level - noise if direction == "LONG" else level + noise
        return arm_or_trigger(
            tracker,
            now=now,
            family="VOLATILITY_IGNITION",
            direction=direction,
            level=level,
            invalidation=invalidation,
            reason="volume pace, realized volatility and directional efficiency accelerated together",
            diagnostics=self._diagnostics(state, move),
            hold_seconds=5,
            expiry_seconds=30,
        )

    @staticmethod
    def _diagnostics(state: LiveStockState, move: float) -> dict:
        return {
            "price": state.latest_price,
            "return_percent": round(move, 4),
            "volume_pace": state.volume_pace,
            "volume_acceleration": state.volume_acceleration,
            "volume_percentile": state.volume_percentile,
            "volatility_percentile": state.volatility_percentile,
            "trend_efficiency": state.trend_efficiency,
            "activity_rank": state.activity_rank,
            "market_return_5m_percent": state.market_return_5m_percent,
            "relative_strength_5m_percent": state.relative_strength_5m_percent,
            "relative_strength_percentile": state.relative_strength_percentile,
        }
