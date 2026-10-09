"""Causal completed-minute volatility and compression-breakout policies."""

from collections import deque
from dataclasses import dataclass, field
from statistics import fmean, pstdev

from research.intraday_lab.domain import PolicyConfig, Side, Signal, Tick


@dataclass
class State:
    minute: int
    last_us: int
    close: float
    closes: deque[float] = field(default_factory=lambda: deque(maxlen=20))
    widths: deque[float] = field(default_factory=lambda: deque(maxlen=125))
    armed: int = 0
    last_side: Side | None = None
    consecutive: int = 0


class CompressionPolicy:
    def __init__(self, config: PolicyConfig, *, method: str = "bollinger_relative",
                 width_bps: float = 15.0, confirmation_bars: int = 2):
        if method not in {"bollinger_relative", "bollinger_absolute", "range"}:
            raise ValueError("unknown compression method")
        if width_bps <= 0 or confirmation_bars not in {1, 2}:
            raise ValueError("positive width and one or two confirmation bars required")
        self.config = config
        self.method = method
        self.width_bps = width_bps
        self.confirmation_bars = confirmation_bars
        self.states: dict[int, State] = {}

    def on_tick(self, tick: Tick) -> tuple[Signal | None, str]:
        state = self.states.get(tick.security_id)
        if state is not None and tick.at_us <= state.last_us:
            raise ValueError("per-instrument timestamps must increase")
        if not tick.usable(self.config.maximum_trade_age_seconds,
                           receipt_proxy=self.config.freshness_mode == "receipt_proxy"):
            self.states.pop(tick.security_id, None)
            return None, "unusable_observation"
        minute = tick.at_us // 60_000_000
        if state is None or tick.at_us - state.last_us > self.config.maximum_gap_seconds * 1_000_000:
            self.states[tick.security_id] = State(minute, tick.at_us, tick.midpoint)
            return None, "warming_history"
        state.last_us = tick.at_us
        if minute == state.minute:
            state.close = tick.midpoint
            return None, "forming_minute"
        if minute != state.minute + 1:
            self.states[tick.security_id] = State(minute, tick.at_us, tick.midpoint)
            return None, "minute_gap"
        closed = state.close
        state.minute = minute
        state.close = tick.midpoint
        side = None
        move = 0.0
        if self.method == "range":
            if len(state.closes) >= 5:
                past = list(state.closes)[-5:]
                high, low = max(past), min(past)
                width = (high / low - 1) * 10_000
                buffer = self.config.confirmation_move_bps / 10_000
                if width <= self.width_bps:
                    if closed > high * (1 + buffer):
                        side = Side.LONG
                    elif closed < low * (1 - buffer):
                        side = Side.SHORT
                    move = (closed / fmean(past) - 1) * 10_000
            state.closes.append(closed)
        else:
            state.closes.append(closed)
            if len(state.closes) < 20:
                return None, "warming_bands"
            middle, sigma = fmean(state.closes), pstdev(state.closes)
            upper, lower = middle + 2 * sigma, middle - 2 * sigma
            width = 4 * sigma / middle * 10_000
            squeeze = (len(state.widths) == 125 and width <= min(state.widths)
                       if self.method == "bollinger_relative" else width <= self.width_bps)
            state.widths.append(width)
            if squeeze:
                state.armed = 10
            elif state.armed:
                state.armed -= 1
            if state.armed and sigma > 0:
                buffer = self.config.confirmation_move_bps / 10_000
                side = Side.LONG if closed > upper * (1 + buffer) else (
                    Side.SHORT if closed < lower * (1 - buffer) else None)
                move = (closed / middle - 1) * 10_000
        if side is None:
            state.consecutive = 0
            state.last_side = None
            return None, "no_confirmed_breakout"
        state.consecutive = state.consecutive + 1 if side == state.last_side else 1
        state.last_side = side
        if state.consecutive < self.confirmation_bars:
            return None, "confirming_breakout"
        if tick.spread_bps > self.config.maximum_spread_bps:
            return None, "spread"
        # Current receipt must still lie on the same side, rather than entering on a reversed close.
        if side.sign * (tick.midpoint / closed - 1) * 10_000 < -self.config.confirmation_move_bps:
            return None, "breakout_reversed_before_decision"
        state.armed = 0
        state.consecutive = 0
        return Signal(tick.at_us, tick.security_id, side, tick.midpoint, move,
                      side.sign * abs(move)), "signal"
