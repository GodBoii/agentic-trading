"""Completed midpoint bars. No forward filling or trade-volume inference."""

from collections import deque
from dataclasses import dataclass

from research.intraday_lab.domain import PolicyConfig, Tick


@dataclass(frozen=True, slots=True)
class Bar:
    minute: int
    open: float
    high: float
    low: float
    close: float
    vwap: float | None
    observations: int
    first_us: int
    last_us: int


class CompletedBars:
    """Release a bar only after a later minute arrives; reject incomplete edges."""

    def __init__(self, config: PolicyConfig, capacity: int = 64):
        self.config = config
        self.capacity = capacity
        self.current: dict[int, Bar] = {}
        self.history: dict[int, deque[Bar]] = {}
        self.last_us: dict[int, int] = {}

    def update(self, tick: Tick) -> tuple[Bar | None, str]:
        sid = tick.security_id
        previous_us = self.last_us.get(sid)
        if previous_us is not None and tick.at_us <= previous_us:
            raise ValueError("each instrument's observations must advance strictly")
        self.last_us[sid] = tick.at_us
        history = self.history.setdefault(sid, deque(maxlen=self.capacity))
        if not tick.usable(self.config.maximum_trade_age_seconds,
                           receipt_proxy=self.config.freshness_mode == "receipt_proxy"):
            self.current.pop(sid, None)
            history.clear()
            return None, "unusable_observation"
        if previous_us is not None and tick.at_us - previous_us > self.config.maximum_gap_seconds * 1_000_000:
            self.current.pop(sid, None)
            history.clear()
        minute = tick.at_us // 60_000_000
        current = self.current.get(sid)
        price = tick.midpoint
        fresh = Bar(minute, price, price, price, price, tick.vwap, 1, tick.at_us, tick.at_us)
        if current is None:
            self.current[sid] = fresh
            return None, "warming_bar"
        if current.minute == minute:
            self.current[sid] = Bar(minute, current.open, max(current.high, price), min(current.low, price),
                                    price, tick.vwap, current.observations + 1, current.first_us, tick.at_us)
            return None, "between_evaluations"
        self.current[sid] = fresh
        # A minute must cover its edges and contain enough actual observations.
        start_offset = current.first_us - current.minute * 60_000_000
        end_offset = current.last_us - current.minute * 60_000_000
        if minute != current.minute + 1 or start_offset > 10_000_000 or end_offset < 50_000_000 or current.observations < 10:
            history.clear()
            return None, "incomplete_bar"
        history.append(current)
        return current, "completed_bar"
