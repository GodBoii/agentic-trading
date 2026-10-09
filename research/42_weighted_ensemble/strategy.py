"""Chronologically stacked two-sided forecasts with simplex-constrained weights."""

from dataclasses import dataclass
from importlib import import_module
from itertools import combinations

import numpy as np

from research.intraday_lab.domain import PolicyConfig, Side, Signal, Tick

baseline = import_module("research.08_statistical_models.strategy")
CausalFeatures = baseline.CausalFeatures
executable_labels = baseline.executable_labels
FEATURE_NAMES = baseline.FEATURE_NAMES

GROUPS = ((0, 1), (2,), (3,), (4,))
SPECIALISTS = ("momentum", "vwap", "depth", "spread")
VARIANTS = SPECIALISTS + ("joint_ridge", "equal_average", "convex_average")
RIDGE = .01
SHRINKAGE = .1
MINIMUM_ROWS = 100


def matrix(value: np.ndarray, columns: int, name: str) -> np.ndarray:
    value = np.asarray(value, dtype=float)
    if value.ndim != 2 or value.shape[1] != columns or not np.isfinite(value).all():
        raise ValueError(f"{name} requires {columns} finite columns")
    return value


@dataclass(frozen=True)
class Ridge:
    columns: tuple[int, ...]
    mean: tuple[float, ...]
    scale: tuple[float, ...]
    coefficients: tuple[tuple[float, float], ...]

    def predict(self, x: np.ndarray) -> np.ndarray:
        x = matrix(x, len(FEATURE_NAMES), "features")
        design = np.column_stack([np.ones(len(x)),
                                  (x[:, self.columns] - self.mean) / self.scale])
        return design @ np.asarray(self.coefficients)


def fit_ridge(x: np.ndarray, y: np.ndarray, columns: tuple[int, ...]) -> Ridge:
    x = matrix(x, len(FEATURE_NAMES), "training features")
    y = matrix(y, 2, "training targets")
    if len(x) != len(y) or len(x) < MINIMUM_ROWS:
        raise ValueError("aligned training rows and at least 100 rows required")
    if not columns or len(set(columns)) != len(columns) or any(i not in range(len(FEATURE_NAMES)) for i in columns):
        raise ValueError("unique existing feature columns required")
    subset = x[:, columns]
    mean, scale = subset.mean(axis=0), subset.std(axis=0)
    scale[scale < 1e-8] = 1
    design = np.column_stack([np.ones(len(x)), (subset - mean) / scale])
    penalty = np.eye(design.shape[1]) * len(x) * RIDGE
    penalty[0, 0] = 0
    coefficients = np.linalg.solve(design.T @ design + penalty, design.T @ y)
    return Ridge(columns, tuple(mean), tuple(scale), tuple(tuple(row) for row in coefficients))


def convex_weights(predictions: np.ndarray, y: np.ndarray) -> tuple[float, ...]:
    """Solve a four-model simplex quadratic exactly by enumerating active faces."""
    predictions = np.asarray(predictions, dtype=float)
    y = matrix(y, 2, "weight targets")
    if (predictions.shape != (len(y), 4, 2) or len(y) < MINIMUM_ROWS
            or not np.isfinite(predictions).all()):
        raise ValueError("weight learning requires at least 100 aligned four-model predictions")
    design = predictions.transpose(0, 2, 1).reshape(-1, 4)
    target = y.reshape(-1)
    uniform = np.full(4, .25)
    gram = design.T @ design / len(design) + SHRINKAGE * np.eye(4)
    linear = design.T @ target / len(design) + SHRINKAGE * uniform
    best, best_loss = uniform, float("inf")
    for count in range(1, 5):
        for selected in combinations(range(4), count):
            indices = np.asarray(selected)
            block = gram[np.ix_(indices, indices)]
            ones = np.ones(count)
            unconstrained = np.linalg.solve(block, linear[indices])
            normal = np.linalg.solve(block, ones)
            solution = unconstrained - normal * ((ones @ unconstrained - 1) / (ones @ normal))
            if np.any(solution < -1e-9):
                continue
            weights = np.zeros(4)
            weights[indices] = np.maximum(solution, 0)
            weights /= weights.sum()
            loss = float(np.mean((design @ weights - target) ** 2)
                         + SHRINKAGE * np.sum((weights - uniform) ** 2))
            if loss < best_loss:
                best, best_loss = weights, loss
    return tuple(float(value) for value in best)


@dataclass(frozen=True)
class Ensemble:
    training_dates: tuple[str, ...]
    mode: str
    specialists: tuple[Ridge, ...]
    joint: Ridge
    weights: tuple[float, ...]
    constant_net: tuple[float, float]

    def __post_init__(self) -> None:
        if (len(self.training_dates) != 3 or tuple(sorted(set(self.training_dates))) != self.training_dates
                or self.mode not in {"recent_trade", "receipt_proxy"}
                or len(self.specialists) != 4 or len(self.weights) != 4
                or not np.isfinite(self.weights).all() or min(self.weights) < 0
                or abs(sum(self.weights) - 1) > 1e-8):
            raise ValueError("invalid training dates, mode or simplex weights")

    def predict(self, x: np.ndarray, variant: str) -> np.ndarray:
        if variant not in VARIANTS:
            raise ValueError("unknown ensemble comparison variant")
        if variant in SPECIALISTS:
            return self.specialists[SPECIALISTS.index(variant)].predict(x)
        if variant == "joint_ridge":
            return self.joint.predict(x)
        predictions = np.stack([model.predict(x) for model in self.specialists], axis=1)
        weights = self.weights if variant == "convex_average" else (.25,) * 4
        return np.einsum("nks,k->ns", predictions, weights)


def fit_ensemble(x: np.ndarray, y: np.ndarray, stack_x: np.ndarray,
                 stack_y: np.ndarray, dates: tuple[str, ...], mode: str) -> Ensemble | None:
    x, stack_x = matrix(x, 5, "base features"), matrix(stack_x, 5, "stack features")
    y, stack_y = matrix(y, 2, "base targets"), matrix(stack_y, 2, "stack targets")
    if len(x) != len(y) or len(stack_x) != len(stack_y):
        raise ValueError("feature and target rows must align")
    if len(x) < MINIMUM_ROWS or len(stack_x) < MINIMUM_ROWS:
        return None
    specialists = tuple(fit_ridge(x, y, group) for group in GROUPS)
    joint = fit_ridge(x, y, tuple(range(5)))
    predictions = np.stack([model.predict(stack_x) for model in specialists], axis=1)
    weights = convex_weights(predictions, stack_y)
    return Ensemble(dates, mode, specialists, joint, weights, tuple(y.mean(axis=0)))


class EnsemblePolicy:
    def __init__(self, config: PolicyConfig, model: Ensemble | None, training_dates: tuple[str, ...]):
        if config.name not in VARIANTS or model is not None and (
                config.freshness_mode != model.mode or training_dates != model.training_dates):
            raise ValueError("variant, training dates and model freshness must agree")
        self.config, self.model, self.training_dates = config, model, training_dates
        self.features = CausalFeatures(config)
        self.evaluation_start_us = (int(np.datetime64(training_dates[-1], "D").astype(int)) + 1) * 86_400_000_000 - 19_800_000_000

    def on_tick(self, tick: Tick) -> tuple[Signal | None, str]:
        if tick.at_us < self.evaluation_start_us:
            raise ValueError("evaluation must follow every training date")
        x, reason = self.features.update(tick)
        if x is None:
            return None, reason
        if self.model is None:
            return None, "insufficient_training"
        predictions = self.model.predict(x.reshape(1, -1), self.config.name)[0]
        side = int(np.argmax(predictions))
        if predictions[side] < 2:
            return None, "predicted_net_edge"
        return Signal(tick.at_us, tick.security_id, Side.LONG if side == 0 else Side.SHORT,
                      tick.midpoint, float(predictions[side]), float(predictions[0] - predictions[1])), "signal"
