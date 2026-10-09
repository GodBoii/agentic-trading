"""Paper-inspired entry rules under the existing fixed-exit comparison engine."""

from importlib import import_module
from math import isfinite

from research.intraday_lab.domain import PolicyConfig, Side, Signal, Tick

CompletedBars = import_module("research.10_vwap_pullback.bars").CompletedBars
VARIANTS = ("vwap_direction", "vwap_momentum_confirmed")


def directional_evidence(
    closes: list[float], vwap: float, *, confirmed: bool
) -> tuple[Side | None, float, float, str]:
    """Use only completed closes supplied by the caller, never future values."""
    if not closes or not all(isfinite(p) and p > 0 for p in closes):
        raise ValueError("positive finite completed closes required")
    if not isfinite(vwap) or vwap <= 0:
        raise ValueError("positive finite VWAP required")
    deviation = (closes[-1] / vwap - 1) * 10_000
    if deviation == 0:
        return None, deviation, 0.0, "at_vwap"
    side = Side.LONG if deviation > 0 else Side.SHORT
    if not confirmed:
        return side, deviation, 0.0, "signal"
    if len(closes) < 6:
        return None, deviation, 0.0, "warming_confirmation"
    recent = closes[-6:]
    movement = (recent[-1] / recent[0] - 1) * 10_000
    latest = (recent[-1] / recent[-2] - 1) * 10_000
    path = sum(abs(b - a) for a, b in zip(recent, recent[1:]))
    efficiency = abs(recent[-1] - recent[0]) / path if path else 0.0
    if side.sign * movement < 8.0 or side.sign * latest <= 0 or efficiency < 0.3:
        return None, deviation, movement, "confirmation_failed"
    return side, deviation, movement, "signal"


class VWAPDirectionPolicy:
    def __init__(self, config: PolicyConfig):
        if config.name not in VARIANTS:
            raise ValueError("unknown SSRN adaptation variant")
        self.config = config
        self.bars = CompletedBars(config, capacity=8)

    def on_tick(self, tick: Tick) -> tuple[Signal | None, str]:
        bar, reason = self.bars.update(tick)
        if bar is None:
            return None, reason
        if tick.spread_bps > self.config.maximum_spread_bps:
            return None, "spread"
        if bar.vwap is None:
            return None, "vwap_unknown"
        closes = [item.close for item in self.bars.history[tick.security_id]]
        side, deviation, movement, reason = directional_evidence(
            closes, bar.vwap, confirmed=self.config.name == "vwap_momentum_confirmed"
        )
        if side is None:
            return None, reason
        return Signal(tick.at_us, tick.security_id, side, tick.midpoint, deviation, movement), reason
