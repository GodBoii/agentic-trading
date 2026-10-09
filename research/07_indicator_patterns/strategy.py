"""Independent indicator/pattern hypotheses on completed quote bars."""

from dataclasses import replace
from statistics import fmean, pstdev

from research.intraday_lab.domain import PolicyConfig, Side, Signal, Tick

from .bars import CompletedBars
VARIANTS = ("rsi_recross", "bollinger_breakout", "wick_rejection")


def configuration(variant: str, freshness_mode: str = "recent_trade") -> PolicyConfig:
    if variant not in VARIANTS:
        raise ValueError(f"unknown indicator variant: {variant}")
    return replace(PolicyConfig(), name=variant, freshness_mode=freshness_mode,
                   target_bps=30.0, stop_bps=20.0, horizon_seconds=600,
                   cooldown_seconds=600, require_cost_room=True)


class WilderRSI:
    def __init__(self, period: int = 14):
        if period < 2:
            raise ValueError("RSI period must exceed one")
        self.period = period
        self.previous: float | None = None
        self.gains: list[float] = []
        self.losses: list[float] = []
        self.average_gain: float | None = None
        self.average_loss: float | None = None

    def update(self, close: float) -> float | None:
        if self.previous is None:
            self.previous = close
            return None
        change = close - self.previous
        self.previous = close
        gain, loss = max(change, 0), max(-change, 0)
        if self.average_gain is None:
            self.gains.append(gain)
            self.losses.append(loss)
            if len(self.gains) < self.period:
                return None
            self.average_gain, self.average_loss = fmean(self.gains), fmean(self.losses)
        else:
            self.average_gain = ((self.period - 1) * self.average_gain + gain) / self.period
            self.average_loss = ((self.period - 1) * self.average_loss + loss) / self.period
        total = self.average_gain + self.average_loss
        # Neutral flat-price convention, documented rather than library-dependent.
        return 100 * self.average_gain / total if total else 50.0


class IndicatorPolicy:
    def __init__(self, config: PolicyConfig):
        if config.name not in VARIANTS:
            raise ValueError(f"unknown variant: {config.name}")
        self.config = config
        self.bars = CompletedBars(config)
        self.rsi: dict[int, WilderRSI] = {}
        self.previous_rsi: dict[int, float] = {}

    def on_tick(self, tick: Tick) -> tuple[Signal | None, str]:
        bar, reason = self.bars.update(tick)
        sid = tick.security_id
        if bar is None:
            if reason in {"unusable_observation", "warming_bar", "incomplete_bar"}:
                self.rsi.pop(sid, None)
                self.previous_rsi.pop(sid, None)
            return None, reason
        bars = list(self.bars.history[sid])
        old_rsi = self.previous_rsi.get(sid)
        rsi = self.rsi.setdefault(sid, WilderRSI()).update(bar.close)
        if rsi is not None:
            self.previous_rsi[sid] = rsi
        if tick.spread_bps > self.config.maximum_spread_bps:
            return None, "spread"
        if len(bars) < 21:
            return None, "warming_history"
        side = None
        feature = 0.0
        confirmation = (bar.close / bars[-2].close - 1) * 10_000
        if self.config.name == "rsi_recross":
            if old_rsi is None or rsi is None:
                return None, "warming_rsi"
            feature = rsi
            if old_rsi < 30 <= rsi:
                side = Side.LONG
            elif old_rsi > 70 >= rsi:
                side = Side.SHORT
        elif self.config.name == "bollinger_breakout":
            prior = [b.close for b in bars[-21:-1]]
            center, sigma = fmean(prior), pstdev(prior)
            if sigma <= 0 or sigma / center * 10_000 < 2:
                return None, "zero_or_small_variance"
            feature = (bar.close - center) / sigma
            if bar.close > center + 2 * sigma and bars[-2].close <= center + 2 * sigma and confirmation >= 3:
                side = Side.LONG
            elif bar.close < center - 2 * sigma and bars[-2].close >= center - 2 * sigma and confirmation <= -3:
                side = Side.SHORT
        else:
            total = bar.high - bar.low
            if total <= 0 or total / bar.close * 10_000 < 10:
                return None, "small_bar_range"
            lower = min(bar.open, bar.close) - bar.low
            upper = bar.high - max(bar.open, bar.close)
            body = abs(bar.close - bar.open)
            feature = total / bar.close * 10_000
            prior = bars[-6:-1]
            if lower / total >= .60 and body / total <= .25 and bar.close >= bar.low + .75 * total and bar.low < min(b.low for b in prior):
                side = Side.LONG
            elif upper / total >= .60 and body / total <= .25 and bar.close <= bar.high - .75 * total and bar.high > max(b.high for b in prior):
                side = Side.SHORT
        if side is None:
            return None, "pattern_absent"
        return Signal(tick.at_us, sid, side, tick.midpoint, feature, confirmation), "signal"


def make_policy(variant: str, config: PolicyConfig) -> IndicatorPolicy:
    if config.name != variant:
        raise ValueError("variant and execution configuration disagree")
    return IndicatorPolicy(config)
