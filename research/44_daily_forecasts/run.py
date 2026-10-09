"""Freeze training-only models, evaluate later dates, retain every prediction."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import platform
import shutil

import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from research.common.data import file_hash
from .methods import FEATURES, MOMENTUM, REVERSAL, bar_trade, blend, inverse_error_weights, make_features, metrics


TRACK = Path(__file__).resolve().parent
ROOT = TRACK.parents[1]


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False), encoding="utf-8")


def phase(frame: pd.DataFrame, limits: list[str]) -> pd.DataFrame:
    return frame.loc[frame.target_date.between(*limits)].copy()


def run(run_name: str) -> Path:
    output = (TRACK / "runs" / run_name).resolve()
    if not output.is_relative_to(TRACK / "runs") or output.exists():
        raise ValueError("use a new run directory under this track")
    spec_path = TRACK / "specification.json"
    spec = json.loads(spec_path.read_text())
    output.mkdir(parents=True)
    # Preserve method and source before reading any outcomes.
    shutil.copyfile(spec_path, output / "specification.json")
    source_hashes = {}
    for source in [*TRACK.glob("*.py"), ROOT / "research/intraday_lab/costs.py"]:
        source_hashes[source.relative_to(ROOT).as_posix()] = file_hash(source)
        destination = output / "source" / source.relative_to(ROOT)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    manifest = {"experiment_kind": spec["experiment_kind"], "specification_sha256": file_hash(spec_path),
                "source_hashes": source_hashes, "runtime": {"python": platform.python_version(),
                "numpy": np.__version__, "pandas": pd.__version__, "sklearn": sklearn.__version__},
                "inputs": [], "promotion_eligible": False}
    frames = []
    for security_id in spec["security_ids"]:
        path = ROOT / f"context/stocks-data/NSE/{security_id}/daily.parquet"
        digest = file_hash(path)
        bars = pd.read_parquet(path)
        features = make_features(bars)
        features["security_id"] = security_id
        frames.append(features)
        manifest["inputs"].append({"path": path.relative_to(ROOT).as_posix(), "sha256": digest,
            "rows": len(bars), "first_date": features.feature_date.min(), "last_date": features.feature_date.max(),
            "invalid_rows": int(features.invalid_source_rows.iloc[0]),
            "history_resets": int(features.history_resets.iloc[0])})
        if file_hash(path) != digest:
            raise ValueError("source changed while reading")
    data = pd.concat(frames, ignore_index=True)
    finite = np.isfinite(data[[*FEATURES, "target_bps", "entry_reference", "exit_reference"]]).all(axis=1)
    data = data.loc[finite].sort_values(["target_date", "security_id"]).reset_index(drop=True)
    if not (data.feature_date < data.target_date).all():
        raise ValueError("feature dates must precede targets")
    train = phase(data, spec["training_target_dates"])
    calibration = phase(data, spec["weight_fit_target_dates"])
    evaluate = phase(data, spec["evaluation_target_dates"])
    if min(len(train), len(calibration), len(evaluate)) < 100:
        raise ValueError("insufficient data for declared chronological split")
    if not train.target_date.max() < calibration.target_date.min() <= calibration.target_date.max() < evaluate.target_date.min():
        raise ValueError("chronological splits overlap")
    manifest["cohort"] = {key: {"rows": len(part), "dates": part.target_date.nunique(),
        "start": part.target_date.min(), "end": part.target_date.max(),
        "large_overnight_gap_rows": int((part.next_overnight_gap_bps.abs() > 3500).sum())}
        for key, part in (("training", train), ("calibration", calibration), ("evaluation", evaluate))}
    write_json(output / "manifest.json", manifest)
    models = {"momentum_ridge": (make_pipeline(StandardScaler(), Ridge(alpha=spec["ridge_alpha"])), MOMENTUM),
              "reversal_ridge": (make_pipeline(StandardScaler(), Ridge(alpha=spec["ridge_alpha"])), REVERSAL),
              "full_ridge": (make_pipeline(StandardScaler(), Ridge(alpha=spec["ridge_alpha"])), FEATURES),
              "forest": (RandomForestRegressor(**spec["forest"]), FEATURES)}
    frozen = {"models": {}, "training_mean_bps": float(train.target_bps.mean()),
              "training_end": train.target_date.max(), "weight_fit_end": calibration.target_date.max()}
    calibration_forecasts = {}
    for name, (model, columns) in models.items():
        model.fit(train[list(columns)], train.target_bps)
        calibration_forecasts[name] = model.predict(calibration[list(columns)])
        if name != "forest":
            scaler, ridge = model.steps[0][1], model.steps[1][1]
            frozen["models"][name] = {"features": columns, "mean": scaler.mean_.tolist(),
                "scale": scaler.scale_.tolist(), "coefficients": ridge.coef_.tolist(), "intercept": float(ridge.intercept_)}
        else:
            # Forest state is fingerprinted and retained, without unsafe pickle loading.
            trees = [{"children_left": tree.tree_.children_left.tolist(),
                      "children_right": tree.tree_.children_right.tolist(),
                      "feature": tree.tree_.feature.tolist(), "threshold": tree.tree_.threshold.tolist(),
                      "value": tree.tree_.value.ravel().tolist()} for tree in model.estimators_]
            write_json(output / "forest.json", {"features": columns, "trees": trees})
            frozen["models"][name] = {"features": columns, "state_sha256": file_hash(output / "forest.json")}
    members = spec["ensemble_members"]
    weights = inverse_error_weights(np.column_stack([calibration_forecasts[m] for m in members]),
                                    calibration.target_bps.to_numpy())
    frozen["ensemble_members"] = members
    frozen["equal_weights"] = [1 / len(members)] * len(members)
    frozen["inverse_mse_weights"] = weights.tolist()
    # No evaluation predictions or outcomes were inspected during fitting.
    write_json(output / "model-freeze.json", frozen)
    forecasts = {name: model.predict(evaluate[list(columns)]) for name, (model, columns) in models.items()}
    stack = np.column_stack([forecasts[m] for m in members])
    forecasts["equal_ensemble"] = blend(stack, frozen["equal_weights"])
    forecasts["weighted_ensemble"] = blend(stack, weights)
    forecasts["training_mean"] = np.full(len(evaluate), frozen["training_mean_bps"])
    outcomes = evaluate.target_bps.to_numpy()
    summary = {"experiment_kind": spec["experiment_kind"], "manifest_sha256": file_hash(output / "manifest.json"),
               "model_freeze_sha256": file_hash(output / "model-freeze.json"), "promotion_eligible": False,
               "forecast_metrics": {name: metrics(outcomes, pred, forecasts["training_mean"])
                                    for name, pred in forecasts.items()}, "bar_price_diagnostics": []}
    predictions = evaluate[["security_id", "feature_date", "target_date", "target_bps",
                            "entry_reference", "exit_reference"]].copy()
    for name, forecast in forecasts.items():
        predictions[name] = forecast
    predictions.to_parquet(output / "predictions.parquet", index=False)
    trades = []
    for name, forecast in forecasts.items():
        signals = evaluate.copy()
        signals["forecast_bps"] = forecast
        signals["strength"] = np.abs(forecast)
        signals = signals.loc[signals.strength >= spec["diagnostic_entry_threshold_bps"]]
        signals = signals.sort_values(["target_date", "strength", "security_id"], ascending=[True, False, True])
        signals = signals.groupby("target_date", sort=False).head(spec["diagnostic_max_positions"])
        for cost in spec["diagnostic_extra_cost_per_leg_bps"]:
            selected = []
            for row in signals.itertuples():
                side = 1 if row.forecast_bps > 0 else -1
                trade = bar_trade(row.entry_reference, row.exit_reference, side,
                                  spec["diagnostic_notional_per_position"], cost)
                if trade is not None:
                    selected.append({"date": row.target_date, "security_id": row.security_id,
                                     "side": side, "model": name, "cost_per_leg_bps": cost, **trade})
            trades.extend(selected)
            summary["bar_price_diagnostics"].append({"model": name, "cost_per_leg_bps": cost,
                "trades": len(selected), "gross_pnl": sum(t["gross_pnl"] for t in selected),
                "fees": sum(t["fees"] for t in selected), "net_pnl": sum(t["net_pnl"] for t in selected),
                "days_with_positions": len({t["date"] for t in selected}), "live_fill_claim": False})
    pd.DataFrame(trades).to_csv(output / "bar-price-trades.csv", index=False)
    write_json(output / "results.json", summary)
    print(json.dumps({"run": str(output), "rows": len(evaluate), "weights": weights.tolist(),
                      "forecast_metrics": summary["forecast_metrics"]}, allow_nan=False))
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-name", default="initial-v1")
    run(parser.parse_args().run_name)
