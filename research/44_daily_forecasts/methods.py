"""Pure feature, ensemble, metric and idealized bar-price calculations."""

from collections.abc import Sequence
import math

import numpy as np
import pandas as pd

from research.intraday_lab.costs import round_trip_fees


FEATURES = ("return1", "return5", "return20", "ma_distance", "body",
            "range", "close_location", "volatility20", "volume_surprise")
MOMENTUM = ("return5", "return20", "ma_distance")
REVERSAL = ("return1", "body", "close_location", "volume_surprise")


def make_features(bars: pd.DataFrame) -> pd.DataFrame:
    """Attach t-only features to t+1 labels. Invalid rows never bridge history."""
    required = {"timestamp", "open", "high", "low", "close", "volume", "datetime_ist"}
    if not required.issubset(bars.columns):
        raise ValueError("daily input is missing required columns")
    frame = bars.copy().sort_values("timestamp").reset_index(drop=True)
    if frame.timestamp.duplicated().any():
        raise ValueError("duplicate daily timestamps")
    dates = pd.to_datetime(frame.datetime_ist.str[:10], errors="raise")
    epoch_dates = pd.to_datetime(frame.timestamp, unit="s", utc=True).dt.tz_convert(
        "Asia/Kolkata").dt.tz_localize(None).dt.normalize()
    if (dates != epoch_dates).any():
        raise ValueError("daily date disagrees with timestamp")
    values = frame[["open", "high", "low", "close", "volume"]].to_numpy(dtype=float)
    valid = (np.isfinite(values).all(axis=1) & (values[:, :4] > 0).all(axis=1)
             & (values[:, 4] >= 0) & (values[:, 1] >= values[:, :4].max(axis=1))
             & (values[:, 2] <= values[:, :4].min(axis=1)))
    frame.loc[~valid, ["open", "high", "low", "close", "volume"]] = np.nan
    close = frame.close
    history_break = (~pd.Series(valid)) | (dates.diff().dt.days > 7)
    # Unknown corporate actions are flagged separately; large historical jumps
    # reset feature history without selecting on the next session's return.
    history_break |= (close / close.shift(1) - 1).abs() > 0.35
    segments = history_break.cumsum()
    features = pd.DataFrame(index=frame.index, columns=FEATURES, dtype=float)
    for _, subset in frame.groupby(segments, sort=False):
        c = subset.close
        ret = c.pct_change(fill_method=None)
        width = subset.high - subset.low
        volume_mean = subset.volume.rolling(20, min_periods=20).mean()
        features.loc[subset.index, "return1"] = ret * 10000
        features.loc[subset.index, "return5"] = c.pct_change(5, fill_method=None) * 10000
        features.loc[subset.index, "return20"] = c.pct_change(20, fill_method=None) * 10000
        features.loc[subset.index, "ma_distance"] = (c / c.rolling(20).mean() - 1) * 10000
        features.loc[subset.index, "body"] = (c / subset.open - 1) * 10000
        features.loc[subset.index, "range"] = width / c * 10000
        features.loc[subset.index, "close_location"] = ((c - subset.low) / width.where(width > 0)).fillna(0.5)
        features.loc[subset.index, "volatility20"] = ret.rolling(20).std(ddof=0) * 10000
        features.loc[subset.index, "volume_surprise"] = subset.volume / volume_mean.where(volume_mean > 0)
    features["feature_date"] = dates.dt.strftime("%Y-%m-%d")
    features["target_date"] = dates.shift(-1).dt.strftime("%Y-%m-%d")
    features["target_bps"] = (frame.close.shift(-1) / frame.open.shift(-1) - 1) * 10000
    features["entry_reference"] = frame.open.shift(-1)
    features["exit_reference"] = frame.close.shift(-1)
    features["next_overnight_gap_bps"] = (frame.open.shift(-1) / close - 1) * 10000
    features["invalid_source_rows"] = int((~valid).sum())
    features["history_resets"] = int(history_break.sum())
    return features


def inverse_error_weights(predictions: np.ndarray, outcomes: np.ndarray) -> np.ndarray:
    """Calibrate a convex forecast average using disjoint historical outcomes."""
    if (predictions.ndim != 2 or predictions.shape[0] != len(outcomes)
            or predictions.shape[0] < 100 or predictions.shape[1] < 2
            or not np.isfinite(predictions).all() or not np.isfinite(outcomes).all()):
        raise ValueError("finite aligned calibration predictions with at least 100 rows required")
    mse = np.mean((predictions - outcomes[:, None]) ** 2, axis=0)
    inverse = 1 / np.maximum(mse, 1e-12)
    return inverse / inverse.sum()


def blend(predictions: np.ndarray, weights: Sequence[float]) -> np.ndarray:
    weights_array = np.asarray(weights, dtype=float)
    if (predictions.ndim != 2 or predictions.shape[1] != len(weights_array)
            or not np.isfinite(predictions).all() or not np.isfinite(weights_array).all()
            or (weights_array < 0).any() or not math.isclose(float(weights_array.sum()), 1.0)):
        raise ValueError("finite predictions and nonnegative sum-to-one weights required")
    return predictions @ weights_array


def metrics(outcomes: np.ndarray, forecast: np.ndarray, benchmark: np.ndarray) -> dict:
    if not len(outcomes) or not all(np.isfinite(v).all() for v in (outcomes, forecast, benchmark)):
        raise ValueError("finite nonempty forecast cohort required")
    if not (outcomes.shape == forecast.shape == benchmark.shape):
        raise ValueError("forecast metrics require identical cohorts")
    mse = float(np.mean((outcomes - forecast) ** 2))
    reference_mse = float(np.mean((outcomes - benchmark) ** 2))
    directional = outcomes != 0
    return {"rows": len(outcomes), "rmse_bps": math.sqrt(mse),
            "mae_bps": float(np.mean(np.abs(outcomes - forecast))),
            "r2_vs_training_mean": 1 - mse / reference_mse if reference_mse else None,
            "direction_accuracy": float(np.mean((forecast[directional] > 0) ==
                                                  (outcomes[directional] > 0))) if directional.any() else None,
            "direction_rows": int(directional.sum())}


def bar_trade(entry: float, exit_price: float, side: int, notional: float,
              cost_per_leg_bps: float) -> dict | None:
    """Reference-price sensitivity, never a claim of real fill capacity."""
    if (side not in {-1, 1} or not all(math.isfinite(x) for x in
            (entry, exit_price, notional, cost_per_leg_bps))
            or min(entry, exit_price, notional) <= 0 or not 0 <= cost_per_leg_bps < 10000):
        raise ValueError("valid prices, side, budget and execution sensitivity required")
    entry_fill = entry * (1 + side * cost_per_leg_bps / 10000)
    exit_fill = exit_price * (1 - side * cost_per_leg_bps / 10000)
    quantity = math.floor(notional / entry_fill)
    if quantity < 1:
        return None
    gross = side * (exit_fill - entry_fill) * quantity
    fees = round_trip_fees(entry_fill, exit_fill, quantity, long=side == 1)
    return {"quantity": quantity, "entry_fill": entry_fill, "exit_fill": exit_fill,
            "gross_pnl": gross, "fees": fees, "net_pnl": gross - fees}
