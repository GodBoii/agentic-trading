"""Frozen short-horizon reversal hypotheses; prices are quote midpoint samples."""

from dataclasses import replace
from math import log
from statistics import fmean, pstdev

from research.intraday_lab.domain import PolicyConfig, Side, Signal, Tick

from .bars import CompletedBars


VARIANTS = ("rolling_zscore_fade", "vwap_deviation_turn", "ou_admissible_fade")


def configuration(variant: str, freshness_mode: str = "recent_trade") -> PolicyConfig:
    if variant not in VARIANTS:
        raise ValueError(f"unknown mean-reversion variant: {variant}")
    return replace(PolicyConfig(), name=variant, freshness_mode=freshness_mode,
                   target_bps=30.0, stop_bps=20.0, horizon_seconds=600,
                   cooldown_seconds=600, require_cost_room=True)


def ar1_fit(values: list[float]) -> tuple[float, float, float] | None:
    """OLS x[t+1] = intercept + phi*x[t]; return phi, mean and half-life bars."""
    if len(values) < 3:
        return None
    x, y = values[:-1], values[1:]
    mx, my = fmean(x), fmean(y)
    variance = sum((v - mx) ** 2 for v in x)
    if variance <= 1e-20:
        return None
    phi = sum((a - mx) * (b - my) for a, b in zip(x, y, strict=True)) / variance
    if not 0 < phi < 1:
        return None
    equilibrium = (my - phi * mx) / (1 - phi)
    return phi, equilibrium, -log(2) / log(phi)


class ReversionPolicy:
    def __init__(self, config: PolicyConfig):
        if config.name not in VARIANTS:
            raise ValueError(f"unknown variant: {config.name}")
        self.config = config
        self.bars = CompletedBars(config)

    def on_tick(self, tick: Tick) -> tuple[Signal | None, str]:
        bar, reason = self.bars.update(tick)
        if bar is None:
            return None, reason
        if tick.spread_bps > self.config.maximum_spread_bps:
            return None, "spread"
        bars = list(self.bars.history[tick.security_id])
        if len(bars) < 21:
            return None, "warming_history"
        previous = bars[-2]
        prior = [b.close for b in bars[-21:-1]]
        center, sigma = fmean(prior), pstdev(prior)
        if self.config.name != "vwap_deviation_turn" and (sigma <= 0 or sigma / center * 10_000 < 2):
            return None, "zero_or_small_variance"
        deviation = (bar.close / center - 1) * 10_000
        zscore = (bar.close - center) / sigma if sigma > 0 else 0.0
        turn = (bar.close / previous.close - 1) * 10_000
        if self.config.name == "vwap_deviation_turn":
            if bar.vwap is None:
                return None, "vwap_unknown"
            deviation = (bar.close / bar.vwap - 1) * 10_000
            if not 25 <= abs(deviation) <= 120:
                return None, "vwap_deviation"
        elif self.config.name == "ou_admissible_fade":
            fit = ar1_fit(prior)
            if fit is None or not 2 <= fit[2] <= 15:
                return None, "ou_not_admissible"
            center = fit[1]
            if center <= 0 or abs(center / fmean(prior) - 1) * 10_000 > 100:
                return None, "ou_unstable_mean"
            deviation = (bar.close / center - 1) * 10_000
            zscore = (bar.close - center) / sigma
            if abs(zscore) < 2 or not 15 <= abs(deviation) <= 120:
                return None, "ou_deviation"
        elif abs(zscore) < 2 or not 15 <= abs(deviation) <= 120:
            return None, "zscore_deviation"
        side = Side.SHORT if deviation > 0 else Side.LONG
        if side.sign * turn < 1:
            return None, "no_reversal_confirmation"
        return Signal(tick.at_us, tick.security_id, side, tick.midpoint, deviation, turn), "signal"


def make_policy(variant: str, config: PolicyConfig) -> ReversionPolicy:
    if config.name != variant:
        raise ValueError("variant and execution configuration disagree")
    return ReversionPolicy(config)
