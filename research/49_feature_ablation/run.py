"""Freeze feature comparisons before reading test forecasts or outcomes."""

import importlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from research.common.data import file_hash

d = importlib.import_module("research.45_market_dataset.dataset")
a = importlib.import_module("research.45_market_dataset.account")
metric = importlib.import_module("research.44_daily_forecasts.methods").metrics
TRACK = Path(__file__).resolve().parent


def feature_groups(spec: dict) -> dict[str, list[str]]:
    price = spec["price"]
    volume = price + spec["volume_extra"]
    peers = volume + spec["peer_extra"]
    return {"price_vwap": price, "own_volume": volume, "peer_context": peers,
            "full_context": peers + spec["full_extra"]}


def freeze_ridge(model, features: list[str]) -> dict:
    scaler, ridge = model.steps[0][1], model.steps[1][1]
    return {"features": features, "mean": scaler.mean_.tolist(), "scale": scaler.scale_.tolist(),
            "coefficients": ridge.coef_.tolist(), "intercept": float(ridge.intercept_)}


def main() -> None:
    output = TRACK / "runs" / "initial-v1"
    if output.exists():
        raise ValueError("preserve existing versioned evidence")
    spec_path = TRACK / "specification.json"
    spec = json.loads(spec_path.read_text())
    output.mkdir(parents=True)
    d.write_json(output / "plan.json", {"specification": spec, "specification_sha256": file_hash(spec_path),
        "run_source_sha256": file_hash(Path(__file__)), "dataset_source_sha256": file_hash(Path(d.__file__)),
        "account_source_sha256": file_hash(Path(a.__file__)), "promotion_eligible": False})
    rows, _, manifest = d.load_dataset()
    d.write_json(output / "input-manifest.json", manifest)
    train = rows.loc[rows.date.between(*spec["training"])]
    validation = rows.loc[rows.date.between(*spec["validation"])]
    test = rows.loc[rows.date.between(*spec["evaluation"])]
    if not train.date.max() < validation.date.min() <= validation.date.max() < test.date.min():
        raise ValueError("overlapping phases")
    groups = feature_groups(spec)
    models, frozen = {}, {}
    for horizon in spec["horizons"]:
        target = f"target_gross_bps_{horizon}"
        for name, columns in groups.items():
            model = make_pipeline(StandardScaler(), Ridge(alpha=100))
            model.fit(train[columns], train[target])
            models[(horizon, name)] = model
            frozen[f"h{horizon}_{name}"] = freeze_ridge(model, columns)
    d.write_json(output / "models-freeze.json", frozen)
    forecasts, accounts = [], []
    for horizon in spec["horizons"]:
        target = f"target_gross_bps_{horizon}"
        for phase, subset in [("validation", validation), ("evaluation", test)]:
            prediction_rows = subset[["date", "security_id", "decision_us", target]].copy()
            predictions = {name: models[(horizon, name)].predict(subset[columns]) for name, columns in groups.items()}
            benchmark = np.full(len(subset), float(train[target].mean()))
            predictions["training_mean"] = benchmark
            for name, pred in predictions.items():
                prediction_rows[name] = pred
                forecasts.append({"horizon": horizon, "phase": phase, "model": name,
                    **metric(subset[target].to_numpy(), pred, benchmark)})
                for cost in spec["costs_per_leg_bps"]:
                    summary, trades, daily = a.account_replay(subset, pred, horizon,
                        threshold_net_bps=spec["admission_net_bps"], cost_per_leg_bps=cost)
                    accounts.append({"model": name, "phase": phase, **summary})
                    stem = f"{phase}-h{horizon}-{name}-cost{cost}"
                    trades.to_csv(output / f"trades-{stem}.csv", index=False)
                    daily.to_csv(output / f"daily-{stem}.csv", index=False)
            prediction_rows.to_parquet(output / f"predictions-{phase}-h{horizon}.parquet", index=False)
        print(json.dumps({"event": "ablation_completed", "horizon": horizon}), flush=True)
    d.write_json(output / "results.json", {"forecast_metrics": forecasts, "account_results": accounts,
        "models_sha256": file_hash(output / "models-freeze.json"), "promotion_eligible": False})


if __name__ == "__main__":
    main()
