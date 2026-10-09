"""Frozen numerical baselines with causal features and future executable labels."""

from bisect import bisect_left
from collections import deque
from dataclasses import dataclass
from math import floor

import numpy as np

from research.intraday_lab.costs import round_trip_fees
from research.intraday_lab.domain import PolicyConfig, Signal, Side, Tick


FEATURE_NAMES = ("return_15s_bps", "return_60s_bps", "vwap_distance_bps",
                 "aggregate_depth_imbalance", "spread_bps")


class CausalFeatures:
    def __init__(self, config: PolicyConfig):
        self.config = config
        self.history: dict[int, deque[Tick]] = {}
        self.last_evaluation: dict[int, int] = {}

    def update(self, tick: Tick) -> tuple[np.ndarray | None, str]:
        history = self.history.setdefault(tick.security_id, deque())
        if not tick.usable(self.config.maximum_trade_age_seconds,
                           receipt_proxy=self.config.freshness_mode == "receipt_proxy"):
            history.clear()
            return None, "unusable_observation"
        if history and (tick.at_us <= history[-1].at_us or
                        tick.at_us - history[-1].at_us > self.config.maximum_gap_seconds * 1e6):
            history.clear()
        history.append(tick)
        cutoff = tick.at_us - 60_000_000
        while len(history) > 1 and history[1].at_us <= cutoff:
            history.popleft()
        if history[0].at_us > cutoff:
            return None, "warming_history"
        minute = tick.at_us // 60_000_000
        if self.last_evaluation.get(tick.security_id) == minute:
            return None, "between_evaluations"
        self.last_evaluation[tick.security_id] = minute
        if tick.vwap is None:
            return None, "vwap_unknown"
        if tick.spread_bps > self.config.maximum_spread_bps:
            return None, "spread"
        recent = next(item for item in reversed(history) if item.at_us <= tick.at_us - 15_000_000)
        depth = tick.bid_quantity_5 + tick.ask_quantity_5
        return np.array([(tick.midpoint / recent.midpoint - 1) * 10_000,
                         (tick.midpoint / history[0].midpoint - 1) * 10_000,
                         (tick.midpoint / tick.vwap - 1) * 10_000,
                         (tick.bid_quantity_5 - tick.ask_quantity_5) / depth,
                         tick.spread_bps]), "features"


def executable_labels(ticks: list[Tick], config: PolicyConfig,
                      horizon_seconds: int = 60) -> tuple[np.ndarray, np.ndarray, dict]:
    """Both labels use later observations, explicit costs, and continuous usable quotes.

    Label intervals stay inside a single caller-supplied session. One minute spacing
    does not remove all dependence between instruments, so rows are not IID trials.
    """
    by_id: dict[int, list[Tick]] = {}
    for tick in ticks:
        by_id.setdefault(tick.security_id, []).append(tick)
    xs, ys = [], []
    rejected = 0
    for observations in by_id.values():
        times = [t.at_us for t in observations]
        if any(a >= b for a, b in zip(times, times[1:])):
            raise ValueError("labels require strictly increasing per-instrument times")
        features = CausalFeatures(config)
        bad_prefix = [0]
        for index, t in enumerate(observations):
            bad = not t.usable(config.maximum_trade_age_seconds,
                               receipt_proxy=config.freshness_mode == "receipt_proxy")
            bad |= index > 0 and t.at_us - observations[index - 1].at_us > config.maximum_gap_seconds * 1e6
            bad_prefix.append(bad_prefix[-1] + int(bad))
        for index, decision in enumerate(observations):
            x, _ = features.update(decision)
            if x is None:
                continue
            entry_index = max(index + 1, bisect_left(times, decision.at_us + 250_000))
            if entry_index >= len(times):
                rejected += 1
                continue
            entry = observations[entry_index]
            exit_index = bisect_left(times, entry.at_us + horizon_seconds * 1_000_000)
            if (exit_index >= len(times) or entry.at_us - decision.at_us > 15_000_000
                    or observations[exit_index].at_us - entry.at_us > (horizon_seconds + 15) * 1_000_000
                    or bad_prefix[exit_index + 1] != bad_prefix[index]):
                rejected += 1
                continue
            exit_tick = observations[exit_index]
            values = []
            for long in (True, False):
                entry_price = entry.ask * 1.0001 if long else entry.bid * .9999
                exit_price = exit_tick.bid * .9999 if long else exit_tick.ask * 1.0001
                quantity = floor(100_000 / entry_price)
                if quantity < 1:
                    raise ValueError("label notional cannot purchase one share")
                pnl = (1 if long else -1) * (exit_price - entry_price) * quantity
                pnl -= round_trip_fees(entry_price, exit_price, quantity, long=long)
                values.append(pnl / (entry_price * quantity) * 10_000)
            xs.append(x)
            ys.append(values)
    return (np.asarray(xs).reshape(-1, len(FEATURE_NAMES)), np.asarray(ys).reshape(-1, 2),
            {"samples": len(xs), "rejected_future_intervals": rejected})


@dataclass(frozen=True)
class FrozenModel:
    mean: np.ndarray
    scale: np.ndarray
    ridge: np.ndarray
    logistic: np.ndarray
    training_rows: int

    def predictions(self, features: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        values = np.r_[1., (features - self.mean) / self.scale]
        net = values @ self.ridge
        probabilities = 1 / (1 + np.exp(-np.clip(values @ self.logistic, -40, 40)))
        return net, probabilities

    def payload(self) -> dict:
        return {"feature_names": list(FEATURE_NAMES), "mean": self.mean.tolist(),
                "scale": self.scale.tolist(), "ridge_coefficients": self.ridge.tolist(),
                "logistic_coefficients": self.logistic.tolist(), "training_rows": self.training_rows}


def fit_model(x: np.ndarray, y: np.ndarray) -> FrozenModel | None:
    if x.shape != (len(y), len(FEATURE_NAMES)) or y.shape != (len(x), 2):
        raise ValueError("feature and two-sided target shapes do not match")
    if not np.isfinite(x).all() or not np.isfinite(y).all():
        raise ValueError("training numbers must be finite")
    if len(x) < 100:
        return None
    mean, scale = x.mean(axis=0), x.std(axis=0)
    scale[scale < 1e-8] = 1
    design = np.column_stack([np.ones(len(x)), (x - mean) / scale])
    penalty = np.eye(design.shape[1]) * len(x) * .01
    penalty[0, 0] = 0
    ridge = np.linalg.solve(design.T @ design + penalty, design.T @ y)
    target = (y > 0).astype(float)
    weights = np.zeros_like(ridge)
    # Fixed, deterministic gradient descent with step bounded by logistic curvature.
    curvature = np.linalg.norm(design.T @ design / len(x), ord=2) / 4 + .01
    step = .9 / curvature
    for _ in range(400):
        prob = 1 / (1 + np.exp(-np.clip(design @ weights, -40, 40)))
        gradient = design.T @ (prob - target) / len(x)
        gradient[1:] += .01 * weights[1:]
        weights -= step * gradient
    for array in (mean, scale, ridge, weights):
        array.setflags(write=False)
    return FrozenModel(mean, scale, ridge, weights, len(x))


class StatisticalPolicy:
    def __init__(self, config: PolicyConfig, model: FrozenModel | None,
                 method: str = "ridge", minimum_net_bps: float = 2.0,
                 minimum_probability: float = .65):
        if method not in {"ridge", "logistic_plus_ridge"}:
            raise ValueError("unknown numerical hypothesis")
        if not np.isfinite(minimum_net_bps) or minimum_net_bps < 0 or not .5 < minimum_probability < 1:
            raise ValueError("invalid prediction gates")
        self.features = CausalFeatures(config)
        self.model = model
        self.method = method
        self.minimum_net_bps = minimum_net_bps
        self.minimum_probability = minimum_probability

    def on_tick(self, tick: Tick) -> tuple[Signal | None, str]:
        x, reason = self.features.update(tick)
        if x is None:
            return None, reason
        if self.model is None:
            return None, "insufficient_training_data"
        net, probability = self.model.predictions(x)
        index = int(np.argmax(net))
        if net[index] < self.minimum_net_bps:
            return None, "predicted_net_edge"
        if self.method == "logistic_plus_ridge" and probability[index] < self.minimum_probability:
            return None, "profit_probability"
        side = Side.LONG if index == 0 else Side.SHORT
        return Signal(tick.at_us, tick.security_id, side, tick.midpoint,
                      float(net[index]), float(probability[index])), "signal"
