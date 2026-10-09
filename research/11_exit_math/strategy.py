"""Analytical exit payoff checks. Actual entries reuse the frozen momentum policy."""

from dataclasses import dataclass
from math import isfinite


def _distances(target_bps: float, stop_bps: float, cost_bps: float) -> None:
    if (not all(isfinite(x) for x in (target_bps, stop_bps, cost_bps))
            or target_bps <= 0 or stop_bps <= 0 or cost_bps < 0):
        raise ValueError("positive finite target/stop and nonnegative finite costs required")


def break_even_probability(target_bps: float, stop_bps: float, cost_bps: float) -> float:
    """Two-outcome barrier payoff only. A value above one means even wins lose net."""
    _distances(target_bps, stop_bps, cost_bps)
    return (stop_bps + cost_bps) / (target_bps + stop_bps)


def expected_payoff_bps(win_probability: float, target_bps: float, stop_bps: float,
                        cost_bps: float) -> float:
    _distances(target_bps, stop_bps, cost_bps)
    if not isfinite(win_probability) or not 0 <= win_probability <= 1:
        raise ValueError("probability must be finite and in [0,1]")
    return win_probability * target_bps - (1-win_probability) * stop_bps - cost_bps


@dataclass(frozen=True)
class ExitSpec:
    target_bps: float
    stop_bps: float
    horizon_seconds: int

    def __post_init__(self) -> None:
        _distances(self.target_bps, self.stop_bps, 0)
        if not isinstance(self.horizon_seconds, int) or self.horizon_seconds <= 0:
            raise ValueError("horizon must be a positive integer number of seconds")

    def policy_overrides(self) -> dict:
        return {"target_bps": self.target_bps, "stop_bps": self.stop_bps,
                "horizon_seconds": self.horizon_seconds}
