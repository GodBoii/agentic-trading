from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from .config import ResearchConfig

PRICE = ["ret_1_bps", "ret_5_bps", "rv_5_bps", "range_5_bps", "log_volume", "minutes_from_open"]
NEAR = ["imbalance_5", "imbalance_points_5", "imbalance_points_10", "imbalance_weighted"]
DEEP = ["imbalance_20", "imbalance_200", "imbalance_points_25", "imbalance_points_50"]
GROUPS = {"price": PRICE, "price_near_depth": PRICE + NEAR,
          "price_all_depth": PRICE + NEAR + DEEP,
          "price_depth_estimated_flow": PRICE + NEAR + DEEP + ["signed_volume_ratio", "oi_change_bps"]}


def metrics(actual: np.ndarray, forecast: np.ndarray) -> dict:
    finite = np.isfinite(actual) & np.isfinite(forecast)
    actual, forecast = actual[finite], forecast[finite]
    if not len(actual): return {"rows": 0}
    directional = np.abs(actual) > 0.1
    return {"rows": len(actual), "mae_bps": float(np.mean(np.abs(actual - forecast))),
            "rmse_bps": float(np.sqrt(np.mean((actual - forecast) ** 2))),
            "direction_accuracy": float(np.mean(np.sign(actual[directional]) == np.sign(forecast[directional])))
            if directional.any() and np.any(forecast != 0) else None,
            "mean_actual_bps": float(actual.mean()), "mean_forecast_bps": float(forecast.mean())}


def walk_forward(frame: pd.DataFrame, config: ResearchConfig) -> tuple[pd.DataFrame, dict]:
    columns = sorted({name for group in GROUPS.values() for name in group})
    missing = sorted(set(columns) - set(frame.columns))
    if missing: raise ValueError(f"Missing feature columns: {missing}")
    # Common, decision-time cohort makes each ablation comparable. Labels may be
    # missing on test rows, and those rows remain predictions and replay attempts.
    cohort = frame.loc[frame["feature_ready"] & np.isfinite(frame[columns]).all(axis=1)].copy()
    days = sorted(cohort["date"].unique()); forecasts = []; folds = []; skipped = []
    for day in days:
        training = cohort.loc[(cohort["date"] < day) & cohort["target_bps"].notna()]
        training_days = sorted(training["date"].unique())
        if len(training_days) < config.minimum_training_days or len(training) < config.minimum_training_rows:
            skipped.append({"date": day, "training_days": len(training_days), "training_rows": len(training)}); continue
        test = cohort.loc[cohort["date"] == day].copy()
        if not (training["label_at"] < test["decision_at"].min()).all():
            raise AssertionError("Training label reaches the test period")
        test["prediction_zero"] = 0.0
        test["prediction_momentum"] = test["ret_5_bps"]
        fold = {"date": day, "training_days": training_days, "training_rows": len(training),
                "prediction_rows": len(test), "scored_rows": int(test["target_bps"].notna().sum()), "models": {}}
        for name, features in GROUPS.items():
            model = make_pipeline(StandardScaler(), Ridge(alpha=config.ridge_alpha))
            model.fit(training[features], training["target_bps"])
            test[f"prediction_{name}"] = model.predict(test[features])
            fold["models"][name] = {"features": features,
                                    "scaled_coefficients": dict(zip(features, model[-1].coef_.tolist())),
                                    "metrics": metrics(test["target_bps"].to_numpy(), test[f"prediction_{name}"].to_numpy())}
        forecasts.append(test); folds.append(fold)
    if not forecasts:
        return pd.DataFrame(), {"status": "insufficient_training_history", "skipped": skipped, "cohort_rows": len(cohort)}
    predictions = pd.concat(forecasts, ignore_index=True)
    scored = predictions.dropna(subset=["target_bps"])
    summary = {"status": "exploratory", "config": config.to_dict(), "cohort_rows": len(cohort), "prediction_rows": len(predictions),
               "scored_rows": len(scored), "test_days": sorted(predictions["date"].unique()),
               "groups": GROUPS, "folds": folds, "skipped": skipped, "metrics": {}, "paired_day_comparisons": {}}
    for column in [name for name in predictions if name.startswith("prediction_")]:
        summary["metrics"][column.removeprefix("prediction_")] = metrics(scored["target_bps"].to_numpy(), scored[column].to_numpy())
    baseline_error = (scored["prediction_price"] - scored["target_bps"]) ** 2
    rng = np.random.default_rng(20260930)
    for name in GROUPS:
        if name == "price": continue
        difference = baseline_error - (scored[f"prediction_{name}"] - scored["target_bps"]) ** 2
        by_day = difference.groupby(scored["date"]).mean()
        if by_day.empty:
            continue
        boot = rng.choice(by_day.to_numpy(), size=(5000, len(by_day)), replace=True).mean(axis=1)
        summary["paired_day_comparisons"][name] = {
            "mean_daily_mse_improvement_bps_squared": float(by_day.mean()),
            "bootstrap_95_percent_interval": np.quantile(boot, [0.025, 0.975]).tolist(),
            "daily_improvement": {str(k): float(v) for k, v in by_day.items()},
            "interpretation": "Positive favours added features. Day bootstrap is descriptive with few dates; no multiple-testing correction."}
    return predictions, summary
