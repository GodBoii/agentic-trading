"""Pure bounded candidate generation, validation selection and forecast metrics."""

from dataclasses import dataclass, asdict
import math
from collections.abc import Iterable

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    horizon: int
    family: str
    threshold_bps: float
    lookback: int | None = None


def candidates(horizon: int, spec: dict) -> list[Candidate]:
    if horizon not in spec["horizons_minutes"]:
        raise ValueError("horizon outside frozen grid")
    rules = [Candidate(f"h{horizon}_momentum_l{lookback}_t{threshold:g}", horizon,
                       "momentum", threshold, lookback)
             for lookback in spec["momentum_lookbacks_minutes"]
             for threshold in spec["momentum_entry_thresholds_bps"]]
    models = [Candidate(f"h{horizon}_{family}_t{threshold:g}", horizon, family, threshold)
              for family in ("ridge", "boosting") for threshold in spec["learned_entry_thresholds_bps"]]
    return rules + models


def directions(forecast: np.ndarray, threshold_bps: float) -> np.ndarray:
    forecast = np.asarray(forecast, dtype=float)
    if forecast.ndim != 1 or not np.isfinite(forecast).all() or not math.isfinite(threshold_bps) or threshold_bps <= 0:
        raise ValueError("finite one-dimensional forecasts and positive threshold required")
    return np.where(np.abs(forecast) >= threshold_bps, np.sign(forecast), 0).astype(int)


def select_validation(rows: Iterable[dict], minimum_trades: int) -> dict:
    """Zero-PnL no-trade comparator always qualifies; never access test columns."""
    if minimum_trades < 1:
        raise ValueError("minimum trades must be positive")
    eligible = [{"candidate_id": "no_trade", "net_pnl": 0.0, "trades": 0,
                 "abstain": True}]
    for row in rows:
        value, trades = float(row["net_pnl"]), int(row["trades"])
        if not math.isfinite(value) or trades < 0:
            raise ValueError("invalid validation result")
        if trades >= minimum_trades:
            eligible.append({"candidate_id": row["candidate_id"], "net_pnl": value,
                             "trades": trades, "abstain": False})
    # A zero-PnL active result cannot beat the no-trade comparator.
    return min(eligible, key=lambda row: (-row["net_pnl"], not row["abstain"], row["candidate_id"]))


def forecast_metrics(outcome: np.ndarray, prediction: np.ndarray, train_mean: float) -> dict:
    outcome, prediction = np.asarray(outcome, dtype=float), np.asarray(prediction, dtype=float)
    if (outcome.ndim != 1 or outcome.shape != prediction.shape or not len(outcome)
            or not np.isfinite(outcome).all() or not np.isfinite(prediction).all()
            or not math.isfinite(train_mean)):
        raise ValueError("finite aligned forecast cohort required")
    mse = float(np.mean((outcome - prediction) ** 2))
    baseline = float(np.mean((outcome - train_mean) ** 2))
    nonzero = outcome != 0
    return {"rows": len(outcome), "rmse_bps": math.sqrt(mse),
            "mae_bps": float(np.mean(np.abs(outcome - prediction))),
            "r2_vs_train_mean": 1 - mse / baseline if baseline > 0 else None,
            "direction_accuracy": float(np.mean(np.sign(outcome[nonzero]) ==
                                                np.sign(prediction[nonzero]))) if nonzero.any() else None,
            "direction_rows": int(nonzero.sum())}


def chronological_parts(frame: pd.DataFrame, spec: dict, horizon: int) -> dict[str, pd.DataFrame]:
    """Keep whole dates together and purge rows whose labels leave their phase."""
    exit_column = f"exit_us_{horizon}"
    required = {"date", "decision_us", "entry_us", exit_column}
    if not required.issubset(frame.columns):
        raise ValueError("shared dataset must expose date and interval timestamps")
    if not (frame.decision_us < frame.entry_us).all() or not (frame.entry_us < frame[exit_column]).all():
        raise ValueError("feature/entry/exit chronology is invalid")
    dates = frame.date.astype(str)
    entry_dates = pd.to_datetime(frame.entry_us, unit="us", utc=True).dt.tz_convert("Asia/Kolkata").dt.strftime("%Y-%m-%d")
    exit_dates = pd.to_datetime(frame[exit_column], unit="us", utc=True).dt.tz_convert("Asia/Kolkata").dt.strftime("%Y-%m-%d")
    parts = {}
    for name in ("training", "validation", "test"):
        first, last = spec[f"{name}_dates"]
        mask = dates.between(first, last) & entry_dates.between(first, last) & exit_dates.between(first, last)
        parts[name] = frame.loc[mask].copy()
    for left, right in (("training", "validation"), ("validation", "test")):
        a, b = parts[left], parts[right]
        if not a.empty and not b.empty and (a[exit_column].max() >= b.decision_us.min()
                                           or not set(a.date).isdisjoint(set(b.date))):
            raise ValueError("date groups or label intervals overlap phases")
    return parts


def candidate_record(candidate: Candidate) -> dict:
    return asdict(candidate)
