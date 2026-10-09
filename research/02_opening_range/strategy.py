"""Opening-range hypotheses using only received quotes available at decision time."""

from dataclasses import dataclass

from research.intraday_lab.domain import PolicyConfig, Side, Signal, Tick, session_second


@dataclass
class RangeState:
    first_us: int
    last_us: int
    observed_us: int
    high: float
    low: float
    open: float
    close: float
    valid: bool = True
    emitted: bool = False


class OpeningRangePolicy:
    def __init__(self, config: PolicyConfig, *, minutes: int = 15,
                 require_direction: bool = False, require_vwap: bool = False):
        if minutes not in {5, 15, 30}:
            raise ValueError("opening range must be 5, 15, or 30 minutes")
        self.config = config
        self.minutes = minutes
        self.require_direction = require_direction
        self.require_vwap = require_vwap
        self.states: dict[int, RangeState] = {}

    def on_tick(self, tick: Tick) -> tuple[Signal | None, str]:
        sec = session_second(tick.at_us)
        opening = 9 * 3600 + 15 * 60
        end = opening + self.minutes * 60
        state = self.states.get(tick.security_id)
        usable = tick.usable(self.config.maximum_trade_age_seconds,
                             receipt_proxy=self.config.freshness_mode == "receipt_proxy")
        if state is not None and tick.at_us <= state.observed_us:
            raise ValueError("per-instrument timestamps must increase")
        if state is None:
            # An incomplete opening tape cannot silently become a later rolling range.
            state = RangeState(tick.at_us, tick.at_us, tick.at_us, tick.midpoint, tick.midpoint,
                               tick.midpoint, tick.midpoint,
                               valid=opening <= sec <= opening + self.config.maximum_gap_seconds and usable)
            self.states[tick.security_id] = state
        elif sec < end:
            if tick.at_us - state.last_us > self.config.maximum_gap_seconds * 1_000_000 or not usable:
                state.valid = False
            state.last_us = tick.at_us
            if usable:
                state.high = max(state.high, tick.midpoint)
                state.low = min(state.low, tick.midpoint)
                state.close = tick.midpoint
        state.observed_us = tick.at_us
        if not state.valid:
            return None, "incomplete_opening_range"
        if sec < end:
            return None, "forming_opening_range"
        if session_second(state.last_us) < end - self.config.maximum_gap_seconds:
            state.valid = False
            return None, "incomplete_opening_range"
        if not usable:
            return None, "unusable_observation"
        if state.emitted:
            return None, "daily_signal_limit"
        if sec > 11 * 3600:
            return None, "opening_entry_cutoff"
        if tick.spread_bps > self.config.maximum_spread_bps:
            return None, "spread"
        high_break = (tick.midpoint / state.high - 1) * 10_000
        low_break = (state.low / tick.midpoint - 1) * 10_000
        buffer = self.config.confirmation_move_bps
        side = Side.LONG if high_break >= buffer else Side.SHORT if low_break >= buffer else None
        if side is None:
            return None, "inside_opening_range"
        if self.require_direction and side.sign * (state.close - state.open) <= 0:
            return None, "opening_direction"
        if self.require_vwap:
            if tick.vwap is None:
                return None, "vwap_unknown"
            if side.sign * (tick.midpoint - tick.vwap) <= 0:
                return None, "vwap_alignment"
        state.emitted = True
        move = (tick.midpoint / state.open - 1) * 10_000
        return Signal(tick.at_us, tick.security_id, side, tick.midpoint, move,
                      side.sign * max(high_break, low_break)), "signal"
