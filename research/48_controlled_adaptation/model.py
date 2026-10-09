"""Immutable weighted ridge forecasts and causal monthly training windows."""

from dataclasses import dataclass
from hashlib import sha256
import json
import numpy as np
import pandas as pd

METHODS = ("static_ridge", "expanding_monthly", "rolling_12month_monthly", "recency_90date_monthly")


@dataclass(frozen=True)
class RidgeModel:
    mean: np.ndarray
    scale: np.ndarray
    coefficients: np.ndarray
    intercept: float
    training_rows: int
    last_label_end: str
    method: str

    def predict(self, features: np.ndarray) -> np.ndarray:
        values = np.asarray(features, dtype=float)
        if values.ndim != 2 or values.shape[1] != len(self.mean) or not np.isfinite(values).all():
            raise ValueError("finite matrix with fitted feature dimensions required")
        return ((values - self.mean) / self.scale) @ self.coefficients + self.intercept

    def payload(self) -> dict:
        return {"mean": self.mean.tolist(), "scale": self.scale.tolist(),
                "coefficients": self.coefficients.tolist(), "intercept": self.intercept,
                "training_rows": self.training_rows, "last_label_end": self.last_label_end,
                "method": self.method}

    @property
    def digest(self) -> str:
        return sha256(json.dumps(self.payload(), sort_keys=True, allow_nan=False).encode()).hexdigest()


def fit_ridge(
    x: np.ndarray, y: np.ndarray, weights: np.ndarray, *, method: str,
    last_label_end: str, alpha: float = 1.0
) -> RidgeModel:
    x, y, weights = np.asarray(x, float), np.asarray(y, float), np.asarray(weights, float)
    if x.ndim != 2 or len(x) == 0 or y.shape != (len(x),) or weights.shape != (len(x),):
        raise ValueError("nonempty training matrix and matching vectors required")
    if not np.isfinite(x).all() or not np.isfinite(y).all() or not np.isfinite(weights).all():
        raise ValueError("finite training inputs required")
    if (weights <= 0).any() or alpha <= 0:
        raise ValueError("positive weights and ridge penalty required")
    # Weight normalization prevents changing regularization just by changing total weight.
    weights = weights / weights.mean()
    mean = np.average(x, axis=0, weights=weights)
    scale = np.sqrt(np.average((x - mean) ** 2, axis=0, weights=weights))
    scale = np.where(scale > 1e-12, scale, 1.0)
    normalized = (x - mean) / scale
    intercept = float(np.average(y, weights=weights))
    gram = normalized.T @ (normalized * weights[:, None])
    coefficients = np.linalg.solve(gram + alpha * np.eye(x.shape[1]), normalized.T @ (weights * (y - intercept)))
    for array in (mean, scale, coefficients):
        array.setflags(write=False)
    return RidgeModel(mean, scale, coefficients, intercept, len(x), last_label_end, method)


def training_mask(frame: pd.DataFrame, cutoff: str, method: str) -> np.ndarray:
    """Require matured labels, not merely historical observation timestamps."""
    if method not in METHODS:
        raise ValueError("unknown adaptation method")
    boundary = pd.Timestamp(cutoff)
    dates = pd.to_datetime(frame.date)
    label_end = pd.to_datetime(frame.label_end, utc=True)
    utc_boundary = boundary.tz_localize("Asia/Kolkata").tz_convert("UTC")
    mask = (dates >= pd.Timestamp("2022-01-01")) & (dates < boundary) & (label_end < utc_boundary)
    if method == "static_ridge":
        mask &= dates < pd.Timestamp("2024-01-01")
    elif method == "rolling_12month_monthly":
        mask &= dates >= boundary - pd.DateOffset(months=12)
    return mask.to_numpy()


def incumbent_validation_is_unseen(model: RidgeModel, validation_start: str) -> bool:
    boundary = pd.Timestamp(validation_start).tz_localize("Asia/Kolkata").tz_convert("UTC")
    return pd.Timestamp(model.last_label_end) < boundary


def recency_weights(dates: pd.Series, half_life: int = 90) -> np.ndarray:
    if half_life <= 0 or len(dates) == 0:
        raise ValueError("nonempty dates and positive half-life required")
    ordered = sorted(dates.unique())
    age = {date: len(ordered) - 1 - index for index, date in enumerate(ordered)}
    return np.array([2 ** (-age[date] / half_life) for date in dates], dtype=float)


def fit_method(frame: pd.DataFrame, features: list[str], cutoff: str, method: str) -> RidgeModel:
    available = frame.loc[training_mask(frame, cutoff, method)]
    if len(available) < 100:
        raise ValueError(f"insufficient matured rows for {method} at {cutoff}")
    weights = recency_weights(available.date) if method == "recency_90date_monthly" else np.ones(len(available))
    return fit_ridge(available[features].to_numpy(), available.target.to_numpy(), weights,
                     method=method, last_label_end=str(available.label_end.max()))


def select_challenger(
    scores: dict[str, dict[str, float]], incumbent: str, *, improvement: float = 0.01
) -> tuple[str, str]:
    if incumbent not in scores or not 0 < improvement < 1:
        raise ValueError("scored incumbent and valid improvement threshold required")
    reference = scores[incumbent]
    qualifying = [method for method in METHODS if method != incumbent and method in scores
                  and scores[method]["mae"] <= reference["mae"] * (1 - improvement)
                  and scores[method]["net_utility"] >= max(0.0, reference["net_utility"])]
    if not qualifying:
        return incumbent, "retain_no_qualified_challenger"
    selected = min(qualifying, key=lambda method: (scores[method]["mae"], METHODS.index(method)))
    return selected, "switch_mae_and_cost_gate"
