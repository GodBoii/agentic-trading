"""Two density components fitted on development-only causal quote features."""

from collections import Counter
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from math import isfinite
from typing import Iterable, Mapping

import numpy as np

from research.intraday_lab.domain import PolicyConfig, Side, Signal, Tick
from .bars import CompletedBars

VARIANTS = ("mixture_trend_continuation", "mixture_low_efficiency_fade")
ITERATIONS = 30
SEED = 17
MINIMUM_ROWS = 200


def day_of(tick: Tick) -> str:
    return datetime.fromtimestamp(tick.at_us / 1_000_000 + 19_800, timezone.utc).date().isoformat()


class CausalFeatures:
    def __init__(self, config: PolicyConfig):
        self.bars = CompletedBars(config, capacity=6)

    def on_tick(self, tick: Tick) -> tuple[np.ndarray | None, float, str]:
        bar, reason = self.bars.update(tick)
        if bar is None:
            return None, 0.0, reason
        history = self.bars.history[tick.security_id]
        if len(history) < 6:
            return None, 0.0, "warming_features"
        closes = np.asarray([item.close for item in history], dtype=float)
        increments = np.diff(np.log(closes)) * 10_000
        total = float(increments.sum())
        path = float(np.abs(increments).sum())
        efficiency = abs(total) / path if path > 0 else 0.0
        values = np.asarray([total, float(np.std(increments)), efficiency])
        return values, float(increments[-1]), "feature"


@dataclass(frozen=True, slots=True)
class MixtureModel:
    training_dates: tuple[str, ...]
    mode: str
    offset: tuple[float, float, float]
    scale: tuple[float, float, float]
    weights: tuple[float, float]
    means: tuple[tuple[float, float, float], tuple[float, float, float]]
    variances: tuple[tuple[float, float, float], tuple[float, float, float]]
    trend_component: int

    def __post_init__(self) -> None:
        arrays = [np.asarray(value, dtype=float) for value in
                  (self.offset, self.scale, self.weights, self.means, self.variances)]
        if ([value.shape for value in arrays] != [(3,), (3,), (2,), (2, 3), (2, 3)]
                or not all(np.isfinite(value).all() for value in arrays)
                or np.any(arrays[1] <= 0) or np.any(arrays[2] <= 0)
                or abs(float(arrays[2].sum()) - 1) > 1e-8 or np.any(arrays[4] <= 0)
                or self.trend_component not in {0, 1}):
            raise ValueError("invalid mixture shape, normalization, weights or variance")

    def posterior(self, feature: np.ndarray) -> np.ndarray:
        feature = np.asarray(feature, dtype=float)
        if feature.shape != (3,) or not np.isfinite(feature).all():
            raise ValueError("posterior requires three finite causal features")
        z = (feature - np.asarray(self.offset)) / np.asarray(self.scale)
        means, variances = np.asarray(self.means), np.asarray(self.variances)
        terms = np.log(np.asarray(self.weights)) - .5 * np.sum(
            np.log(2 * np.pi * variances) + (z - means) ** 2 / variances, axis=1)
        shifted = np.exp(terms - terms.max())
        return shifted / shifted.sum()


def fit_features(values: np.ndarray, dates: tuple[str, ...], mode: str) -> tuple[MixtureModel | None, dict]:
    values = np.asarray(values, dtype=float)
    if len(dates) != 3 or dates != tuple(sorted(set(dates))) or mode not in {"recent_trade", "receipt_proxy"}:
        raise ValueError("three ordered training dates and a known mode required")
    if values.ndim != 2 or values.shape[1] != 3 or not np.isfinite(values).all():
        raise ValueError("training matrix must have three finite features per row")
    report = {"training_dates": list(dates), "mode": mode, "rows": len(values),
              "iterations": ITERATIONS, "seed": SEED, "minimum_rows": MINIMUM_ROWS,
              "variance_floor": .01, "status": "insufficient_training"}
    if len(values) < MINIMUM_ROWS:
        return None, report
    offset = values.mean(axis=0)
    scale = values.std(axis=0)
    if np.any(scale < 1e-6):
        report["status"] = "degenerate_training"
        return None, report
    z = (values - offset) / scale
    ordering = np.argsort(values[:, 2], kind="stable")
    generator = np.random.default_rng(SEED)
    initial = [generator.choice(ordering[:len(ordering) // 2]),
               generator.choice(ordering[len(ordering) // 2:])]
    means = z[initial].copy()
    variances = np.ones((2, 3))
    weights = np.asarray([.5, .5])
    likelihoods = []
    for _ in range(ITERATIONS):
        terms = np.log(weights)[None, :] - .5 * np.sum(
            np.log(2 * np.pi * variances)[None, :, :] + (z[:, None, :] - means) ** 2 / variances,
            axis=2)
        maxima = terms.max(axis=1, keepdims=True)
        numerator = np.exp(terms - maxima)
        likelihoods.append(float(np.sum(maxima[:, 0] + np.log(numerator.sum(axis=1)))))
        responsibility = numerator / numerator.sum(axis=1, keepdims=True)
        mass = responsibility.sum(axis=0)
        if np.any(mass < 1) or not np.isfinite(responsibility).all():
            report["status"] = "collapsed_component"
            return None, report
        weights = mass / len(z)
        means = responsibility.T @ z / mass[:, None]
        variances = np.maximum(np.sum(responsibility[:, :, None] * (z[:, None, :] - means) ** 2,
                                       axis=0) / mass[:, None], .01)
    trend_component = int(np.argmax(means[:, 2]))
    model = MixtureModel(dates, mode, tuple(offset.tolist()), tuple(scale.tolist()),
                         tuple(weights.tolist()), tuple(tuple(row) for row in means.tolist()),
                         tuple(tuple(row) for row in variances.tolist()), trend_component)
    report.update({"status": "fitted", "offset": list(model.offset), "scale": list(model.scale),
                   "weights": list(model.weights), "means": [list(row) for row in model.means],
                   "variances": [list(row) for row in model.variances],
                   "trend_component": trend_component, "training_loglikelihoods": likelihoods,
                   "physical_component_means": (means * scale + offset).tolist()})
    return model, report


def fit_model(sessions: Mapping[str, Iterable[Tick]], mode: str) -> tuple[MixtureModel | None, dict]:
    if len(sessions) != 3:
        raise ValueError("exactly three development sessions required")
    features = []
    rows_per_day = {}
    reasons = Counter()
    for day in sorted(sessions):
        collector = CausalFeatures(replace(PolicyConfig(), freshness_mode=mode))
        start = len(features)
        for tick in sessions[day]:
            if day_of(tick) != day:
                raise ValueError("training tick is outside declared date")
            feature, _, reason = collector.on_tick(tick)
            reasons[reason] += 1
            if feature is not None:
                features.append(feature)
        rows_per_day[day] = len(features) - start
    matrix = np.asarray(features, dtype=float).reshape(-1, 3)
    model, report = fit_features(matrix, tuple(sorted(sessions)), mode)
    if any(rows < 20 for rows in rows_per_day.values()):
        model = None
        report["status"] = "insufficient_training_day"
    report.update({"rows_per_day": rows_per_day, "feature_counts": dict(reasons)})
    return model, report


def model_from_report(report: dict) -> MixtureModel | None:
    if report["status"] != "fitted":
        return None
    return MixtureModel(tuple(report["training_dates"]), report["mode"],
                        tuple(report["offset"]), tuple(report["scale"]), tuple(report["weights"]),
                        tuple(tuple(row) for row in report["means"]),
                        tuple(tuple(row) for row in report["variances"]), int(report["trend_component"]))


class RegimePolicy:
    def __init__(self, config: PolicyConfig, model: MixtureModel | None, training_dates: tuple[str, ...]):
        if (config.name not in VARIANTS
                or model is not None and (model.mode != config.freshness_mode or model.training_dates != training_dates)):
            raise ValueError("unknown variant or mismatched fitted freshness")
        self.config, self.model, self.training_dates = config, model, training_dates
        self.features = CausalFeatures(config)

    def on_tick(self, tick: Tick) -> tuple[Signal | None, str]:
        if day_of(tick) <= self.training_dates[-1]:
            raise ValueError("evaluation must follow all frozen training dates")
        if self.model is None:
            return None, "insufficient_training"
        feature, turn, reason = self.features.on_tick(tick)
        if feature is None:
            return None, reason
        if tick.spread_bps > self.config.maximum_spread_bps:
            return None, "spread"
        probabilities = self.model.posterior(feature)
        trend = self.config.name == "mixture_trend_continuation"
        component = self.model.trend_component if trend else 1 - self.model.trend_component
        confidence = float(probabilities[component])
        if confidence < .8:
            return None, "regime_uncertain"
        move = float(feature[0])
        if not 15 <= abs(move) <= 100:
            return None, "move"
        side = Side.LONG if move > 0 else Side.SHORT
        if not trend:
            side = Side.SHORT if move > 0 else Side.LONG
        if side.sign * turn < 1:
            return None, "confirmation"
        return Signal(tick.at_us, tick.security_id, side, tick.midpoint, move, confidence), "signal"
