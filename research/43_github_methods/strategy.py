"""Forward-only local-linear Kalman filtering and symmetric CUSUM sampling."""

from dataclasses import dataclass, field
from math import isfinite, log, sqrt

import numpy as np

from research.intraday_lab.domain import PolicyConfig, Side, Signal, Tick
from .bars import CompletedBars


VARIANTS = ("kalman_trend", "cusum_continuation", "kalman_cusum_agreement")
THRESHOLD_BPS = 15.0
WARMUP_BARS = 20
FORECAST_MINUTES = 5


@dataclass
class SymmetricCusum:
    """Same log-return/reset recursion as mlfinpy; return event direction too."""

    threshold: float = THRESHOLD_BPS
    positive: float = 0.0
    negative: float = 0.0

    def __post_init__(self) -> None:
        if not isfinite(self.threshold) or self.threshold <= 0:
            raise ValueError("CUSUM threshold must be finite and positive")

    def update(self, return_bps: float) -> int:
        if not isfinite(return_bps):
            raise ValueError("CUSUM needs a finite return")
        self.positive = max(0.0, self.positive + return_bps)
        self.negative = min(0.0, self.negative + return_bps)
        if self.negative < -self.threshold:
            self.negative = 0.0
            return -1
        if self.positive > self.threshold:
            self.positive = 0.0
            return 1
        return 0


@dataclass
class LocalLinearKalman:
    """Latent log-price level and slope in bps, one update per completed minute."""

    mean: np.ndarray = field(default_factory=lambda: np.zeros(2))
    covariance: np.ndarray = field(default_factory=lambda: np.diag([25.0, 4.0]))

    def update(self, observed_bps: float) -> tuple[float, float]:
        if not isfinite(observed_bps):
            raise ValueError("Kalman needs a finite observation")
        transition = np.asarray([[1.0, 1.0], [0.0, 1.0]])
        process = np.diag([0.25, 0.04])
        predicted = transition @ self.mean
        prior = transition @ self.covariance @ transition.T + process
        gain = prior[:, 0] / (prior[0, 0] + 9.0)
        self.mean = predicted + gain * (observed_bps - predicted[0])
        # Joseph form keeps the covariance symmetric and nonnegative numerically.
        residual = np.eye(2) - np.outer(gain, [1.0, 0.0])
        self.covariance = residual @ prior @ residual.T + np.outer(gain, gain) * 9.0
        return float(self.mean[1]), sqrt(max(0.0, float(self.covariance[1, 1])))


@dataclass
class InstrumentState:
    anchor: float
    previous: float
    minute: int
    count: int = 0
    kalman: LocalLinearKalman = field(default_factory=LocalLinearKalman)
    cusum: SymmetricCusum = field(default_factory=SymmetricCusum)


def decision(variant: str, slope: float, slope_sd: float, move_bps: float, event: int) -> int:
    """Return fixed entry direction; uncertainty is model uncertainty, not profit odds."""
    if variant not in VARIANTS:
        raise ValueError("unknown frozen variant")
    direction = 1 if slope > 0 else -1
    kalman_direction = direction if (
        abs(FORECAST_MINUTES * slope) >= 15.0 and slope_sd > 0
        and abs(slope) / slope_sd >= 2.0
        and 10.0 <= abs(move_bps) <= 100.0 and move_bps * direction > 0
    ) else 0
    if variant == "kalman_trend":
        return kalman_direction
    if variant == "cusum_continuation":
        return event
    return event if event != 0 and event == kalman_direction else 0


class GithubMethodsPolicy:
    def __init__(self, config: PolicyConfig):
        if config.name not in VARIANTS:
            raise ValueError("policy name must identify a frozen GitHub-method variant")
        self.config = config
        self.bars = CompletedBars(config, capacity=6)
        self.states: dict[int, InstrumentState] = {}

    def on_tick(self, tick: Tick) -> tuple[Signal | None, str]:
        sid = tick.security_id
        bar, reason = self.bars.update(tick)
        if bar is None:
            if reason in {"unusable_observation", "incomplete_bar"}:
                self.states.pop(sid, None)
            return None, reason
        state = self.states.get(sid)
        if state is None or bar.minute != state.minute + 1:
            state = InstrumentState(bar.close, bar.close, bar.minute - 1)
            self.states[sid] = state
        event = state.cusum.update(log(bar.close / state.previous) * 10_000)
        slope, slope_sd = state.kalman.update(log(bar.close / state.anchor) * 10_000)
        state.previous, state.minute = bar.close, bar.minute
        state.count += 1
        if state.count < WARMUP_BARS:
            return None, "warming_model"
        history = self.bars.history[sid]
        if len(history) < 6:
            return None, "warming_history"
        if tick.spread_bps > self.config.maximum_spread_bps:
            return None, "spread"
        move = log(history[-1].close / history[0].close) * 10_000
        direction = decision(self.config.name, slope, slope_sd, move, event)
        if direction == 0:
            return None, "no_frozen_signal"
        return Signal(tick.at_us, sid, Side.LONG if direction > 0 else Side.SHORT,
                      tick.midpoint, move, slope), "signal"
