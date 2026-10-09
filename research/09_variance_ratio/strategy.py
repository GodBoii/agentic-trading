"""Variance-ratio descriptors on causal completed minute quotes, not p-values."""

from collections import deque
from math import log
from statistics import variance

from research.intraday_lab.domain import PolicyConfig, Side, Signal, Tick


def variance_ratio(returns: list[float], lag: int) -> float | None:
    if lag < 2 or len(returns) < 3 * lag:
        raise ValueError("need lag>=2 and at least three blocks of returns")
    one = variance(returns)
    if one <= 1e-18:
        return None
    blocks = [sum(returns[i:i + lag]) for i in range(len(returns) - lag + 1)]
    return variance(blocks) / (lag * one)


class VarianceRatioPolicy:
    def __init__(self, config: PolicyConfig, *, lag: int = 2, adaptive: bool = False):
        if lag not in {2, 5}:
            raise ValueError("only preregistered lags2 and5 permitted")
        self.config = config
        self.lag = lag
        self.adaptive = adaptive
        self.bars: dict[int, deque[tuple[int, float]]] = {}
        self.current: dict[int, tuple[int, float]] = {}
        self.latest: dict[int, int] = {}

    def on_tick(self, tick: Tick) -> tuple[Signal | None, str]:
        cfg = self.config
        sid = tick.security_id
        previous_at = self.latest.get(sid)
        self.latest[sid] = tick.at_us
        history = self.bars.setdefault(sid, deque(maxlen=31))
        if previous_at is not None and tick.at_us - previous_at > cfg.maximum_gap_seconds * 1_000_000:
            history.clear()
            self.current.pop(sid, None)
        if not tick.usable(cfg.maximum_trade_age_seconds, receipt_proxy=cfg.freshness_mode == "receipt_proxy"):
            history.clear()
            self.current.pop(sid, None)
            return None, "unusable"
        minute = tick.at_us // 60_000_000
        current = self.current.get(sid)
        self.current[sid] = (minute, tick.midpoint)
        if current is None or current[0] == minute:
            return None, "collecting_minute"
        if minute != current[0] + 1:
            history.clear()
            return None, "missing_minute"
        history.append(current)
        if len(history) < 31:
            return None, "history"
        if tick.spread_bps > cfg.maximum_spread_bps:
            return None, "spread"
        closes = [price for _, price in history]
        returns = [log(b / a) for a, b in zip(closes, closes[1:])]
        vr = variance_ratio(returns, self.lag)
        if vr is None:
            return None, "zero_variance"
        move = (closes[-1] / closes[-6] - 1) * 10_000
        if abs(move) < 10.0:
            return None, "move"
        direction = 1 if move > 0 else -1
        if vr > 1.25:
            pass
        elif self.adaptive and vr < .75:
            direction *= -1
        else:
            return None, "neutral_regime"
        return Signal(tick.at_us, sid, Side.LONG if direction > 0 else Side.SHORT,
                      tick.midpoint, move, vr), "signal"
