"""Read-only Nifty return forecasts and finite-window regime diagnostics."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.mixture import GaussianMixture
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[2]
HORIZONS = (1, 5, 15)
AR_ALPHAS = (10, 100)


def variance_ratio(log_prices: np.ndarray, q: int = 5) -> float:
    """Descriptive overlapping variance ratio, without inferential correction."""
    values = np.asarray(log_prices, dtype=float)
    if q < 2 or len(values) < q+3 or not np.isfinite(values).all():
        return np.nan
    one = np.diff(values)
    denominator = q * np.var(one, ddof=1)
    return float(np.var(values[q:] - values[:-q], ddof=1)/denominator) if denominator > 0 else np.nan


def ou_like_fit(log_prices: np.ndarray) -> tuple[float, float, float]:
    """AR1 fit to log levels; stationarity is not inferred from its coefficient."""
    values = np.asarray(log_prices, dtype=float)
    if len(values) < 10 or not np.isfinite(values).all():
        return np.nan, np.nan, np.nan
    x, y = values[:-1], values[1:]
    centered_x, centered_y = x-x.mean(), y-y.mean()
    denominator = centered_x @ centered_x
    if denominator <= 0:
        return np.nan, np.nan, np.nan
    phi = float((centered_x @ centered_y)/denominator)
    intercept = float(y.mean()-phi*x.mean())
    half_life = float(-np.log(2)/np.log(phi)) if 0 < phi < 1 else np.nan
    return phi, intercept, half_life


def causal_features(frame: pd.DataFrame) -> pd.DataFrame:
    parts = []
    for _, group in frame.groupby(["date", "security_id", "segment"], sort=True):
        group = group.sort_values("decision_at").copy()
        valid = group["complete_minute"] & np.isfinite(group["close"]) & (group["close"] > 0)
        breaks = (~valid) | (~valid.shift(fill_value=False)) | group["decision_at"].diff().ne(pd.Timedelta(minutes=1))
        group["run"] = breaks.cumsum()
        for _, part in group[valid].groupby("run"):
            part = part.copy()
            logs = np.log(part["close"])
            ret = logs.diff()*10000
            for lag in range(5):
                part[f"lag_{lag}"] = ret.shift(lag)
            part["past_ret5"] = (logs-logs.shift(5))*10000
            part["past_var5"] = (ret**2).rolling(5, min_periods=5).mean()
            part["past_var60"] = (ret**2).rolling(60, min_periods=60).mean()
            part["log_var5"] = np.log(np.maximum(part["past_var5"], 1e-8))
            part["vr5_60"] = logs.rolling(61, min_periods=61).apply(variance_ratio, raw=True)
            estimates = [ou_like_fit(logs.iloc[i-60:i+1].to_numpy()) if i >= 60 else (np.nan, np.nan, np.nan)
                         for i in range(len(part))]
            part["ou_phi"] = [x[0] for x in estimates]
            part["ou_intercept"] = [x[1] for x in estimates]
            part["ou_half_life_minutes"] = [x[2] for x in estimates]
            for horizon in HORIZONS:
                part[f"target_{horizon}"] = (logs.shift(-horizon)-logs)*10000
                part[f"label_at_{horizon}"] = part["decision_at"].shift(-horizon)
                reversion = (part["ou_phi"] > 0) & (part["ou_phi"] < 1)
                # Stable expression for projected AR1 level change.
                change = ((1-part["ou_phi"]**horizon)/(1-part["ou_phi"])) * (part["ou_intercept"]-(1-part["ou_phi"])*logs)*10000
                part[f"ou_forecast_{horizon}"] = np.where(reversion, change, 0.0)
            parts.append(part)
    return pd.concat(parts, ignore_index=True)


def mixture_prediction(train: pd.DataFrame, test: pd.DataFrame, target: str,
                       components: int) -> tuple[np.ndarray, dict]:
    columns = ["log_var5", "past_ret5"]
    scaler = StandardScaler().fit(train[columns])
    x_train, x_test = scaler.transform(train[columns]), scaler.transform(test[columns])
    mixture = GaussianMixture(n_components=components, covariance_type="full", reg_covar=1e-4,
                              n_init=3, max_iter=500, random_state=20261001)
    mixture.fit(x_train)
    if not mixture.converged_:
        raise RuntimeError("Mixture did not converge; no forecast emitted")
    posterior = mixture.predict_proba(x_train)
    means = (posterior.T @ train[target].to_numpy()) / posterior.sum(axis=0)
    predictions = mixture.predict_proba(x_test) @ means
    diagnostics = {"training_scaler_mean": scaler.mean_.tolist(), "training_scaler_scale": scaler.scale_.tolist(),
                   "component_target_means_bps": means.tolist(), "component_weights": mixture.weights_.tolist(),
                   "iterations": mixture.n_iter_, "converged": mixture.converged_}
    return predictions, diagnostics


def walk_forward(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    features = [f"lag_{i}" for i in range(5)] + ["vr5_60", "log_var5", "past_ret5", "past_var60"]
    cohort = frame.dropna(subset=features).copy()
    outputs, report = [], {}
    for horizon in HORIZONS:
        target = f"target_{horizon}"
        pieces, folds = [], []
        for day in sorted(cohort["date"].unique()):
            train = cohort[(cohort["date"] < day) & cohort[target].notna()]
            test = cohort[(cohort["date"] == day)].copy()
            if train["date"].nunique() < 3 or len(train) < 100 or test.empty:
                continue
            assert (train[f"label_at_{horizon}"] < test["decision_at"].min()).all()
            test["pred_zero"] = 0.0
            test["pred_historical_mean"] = train[target].mean()
            test["pred_momentum5"] = test["past_ret5"]*horizon/5
            test["pred_reversal5"] = -test["past_ret5"]*horizon/5
            for low, high in ((.8, 1.2), (.9, 1.1)):
                sign = np.where(test["vr5_60"] < low, -1, np.where(test["vr5_60"] > high, 1, 0))
                test[f"pred_VR_{low}_{high}"] = sign*test["past_ret5"]*horizon/5
            for lags in (1, 5):
                columns = [f"lag_{i}" for i in range(lags)]
                for alpha in AR_ALPHAS:
                    model = make_pipeline(StandardScaler(), Ridge(alpha=alpha))
                    model.fit(train[columns], train[target])
                    test[f"pred_AR{lags}_{alpha}"] = model.predict(test[columns])
            regimes = {}
            for components in (2, 3):
                test[f"pred_GMM{components}"], regimes[str(components)] = mixture_prediction(train, test, target, components)
            # Diagnostic OU fit is limited to 3x trailing root variance over horizon.
            cap = 3*np.sqrt(test["past_var60"]*horizon)
            test["pred_OU60_capped"] = np.clip(test[f"ou_forecast_{horizon}"], -cap, cap)
            test["horizon"] = horizon
            test["actual_bps"] = test[target]
            pieces.append(test)
            folds.append({"date": day, "training_rows": len(train), "training_dates": sorted(train["date"].unique()),
                          "prediction_rows": len(test), "scored_rows": int(test[target].notna().sum()), "regimes": regimes})
        predictions = pd.concat(pieces, ignore_index=True)
        scored = predictions.dropna(subset=["actual_bps"])
        metrics = {}
        y = scored["actual_bps"].to_numpy()
        rng = np.random.default_rng(20261001)
        for name in [x for x in predictions if x.startswith("pred_")]:
            p = scored[name].to_numpy()
            difference = pd.Series(y*y - (y-p)**2, index=scored.index).groupby(scored["date"]).mean()
            boot = rng.choice(difference.to_numpy(), size=(3000, len(difference)), replace=True).mean(axis=1)
            moving = np.abs(y)>.1
            metrics[name] = {"rows": len(scored), "days": scored["date"].nunique(),
                             "rmse_bps": float(np.sqrt(np.mean((y-p)**2))), "mae_bps": float(np.abs(y-p).mean()),
                             "nonzero_prediction_rows": int((p!=0).sum()),
                             "direction_accuracy_on_nonflat_labels": float((np.sign(y[moving])==np.sign(p[moving])).mean()) if (p!=0).any() else None,
                             "equal_day_mse_improvement_vs_zero_bps2": float(difference.mean()),
                             "descriptive_day_bootstrap95": np.quantile(boot, [.025,.975]).tolist()}
        outputs.append(predictions[["date", "decision_at", "security_id", "horizon", "actual_bps", "vr5_60", "ou_phi", "ou_half_life_minutes"]+[x for x in predictions if x.startswith("pred_")]])
        report[str(horizon)] = {"prediction_rows": len(predictions), "scored_rows": len(scored), "metrics": metrics, "folds": folds}
    return pd.concat(outputs, ignore_index=True), report


def run(input_path: Path, output: Path) -> None:
    raw = pd.read_parquet(input_path)
    feature = causal_features(raw)
    predictions, experiments = walk_forward(feature)
    output.mkdir(parents=True, exist_ok=True)
    predictions.to_parquet(output / "predictions.parquet", index=False)
    diagnostic = feature.dropna(subset=["vr5_60", "ou_phi"])
    finite_half = diagnostic["ou_half_life_minutes"].dropna()
    result = {"date": "2026-10-02", "status": "exploratory_no_option_replay", "model_horizon_trials": 39,
              "experiments": experiments, "diagnostics": {"rows": len(diagnostic), "dates": diagnostic["date"].nunique(),
                  "fraction_phi_between_zero_one": float(((diagnostic["ou_phi"]>0)&(diagnostic["ou_phi"]<1)).mean()),
                  "conditional_half_life_quantiles_minutes": {str(q): float(v) for q,v in finite_half.quantile([.05,.5,.95]).items()},
                  "variance_ratio_quantiles": {str(q): float(v) for q,v in diagnostic["vr5_60"].quantile([.05,.5,.95]).items()}},
              "input_sha256": hashlib.sha256(input_path.read_bytes()).hexdigest(), "study_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (output / "results.json").write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
    lines = ["# All statistical regime results", "", "Positive MSE improvement favours the model. Intervals are descriptive and unadjusted for thirty-nine comparisons.", "",
             "| Horizon | Method | Rows | Days | RMSE bps | MAE bps | Equal-day MSE improvement | Interval |", "|---:|---|---:|---:|---:|---:|---:|---|"]
    for horizon, experiment in experiments.items():
        for name, value in experiment["metrics"].items():
            lo, hi = value["descriptive_day_bootstrap95"]
            lines.append(f"| {horizon} | {name} | {value['rows']} | {value['days']} | {value['rmse_bps']:.4f} | {value['mae_bps']:.4f} | {value['equal_day_mse_improvement_vs_zero_bps2']:.4f} | {lo:.4f} to {hi:.4f} |")
    (output / "numerical-results.md").write_text("\n".join(lines)+"\n", encoding="utf-8")
    print(json.dumps({"diagnostics": result["diagnostics"], "trial_count": 39,
                      "metrics": {h: x["metrics"] for h,x in experiments.items()}}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=ROOT / "research/01_depth_forecast_baseline/artifacts/features.parquet")
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parent / "artifacts")
    args = parser.parse_args()
    if not args.input.is_file():
        parser.error("Missing feature cache")
    run(args.input, args.output)
