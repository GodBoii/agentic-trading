"""Fit train-only models, select validation policies, freeze then evaluate test."""

from datetime import datetime, timezone
from hashlib import sha256
from importlib import import_module
import json
from pathlib import Path
import platform
import shutil

import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

from .methods import candidates, candidate_record, chronological_parts, forecast_metrics, select_validation


TRACK = Path(__file__).parent
ROOT = TRACK.resolve().parents[1]


def digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False), encoding="utf-8")


def frame_of(value) -> pd.DataFrame:
    return value if isinstance(value, pd.DataFrame) else pd.DataFrame(value)


def save_account(output: Path, stem: str, result: tuple) -> dict:
    summary, trades, daily = result
    write_json(output / f"account-{stem}.json", summary)
    frame_of(trades).to_csv(output / f"trades-{stem}.csv", index=False)
    frame_of(daily).to_csv(output / f"daily-{stem}.csv", index=False)
    return summary


def freeze_model(output: Path, horizon: int, family: str, model, features: list[str]) -> dict:
    if family == "ridge":
        scaler, ridge = model.steps[0][1], model.steps[1][1]
        state = {"features": features, "mean": scaler.mean_.tolist(), "scale": scaler.scale_.tolist(),
                 "coefficients": ridge.coef_.tolist(), "intercept": float(ridge.intercept_)}
        path = output / f"model-h{horizon}-ridge.json"
        write_json(path, state)
    else:
        path = output / f"model-h{horizon}-boosting.npz"
        arrays = {f"nodes_{i}": predictor[0].nodes for i, predictor in enumerate(model._predictors)}
        arrays["baseline"] = np.asarray(model._baseline_prediction)
        np.savez_compressed(path, **arrays)
        write_json(output / f"model-h{horizon}-boosting-meta.json", {
            "features": features, "trees": len(model._predictors),
            "state_format": "inert numpy structured node arrays; no pickle; sklearn private tree format",
            "missing_allowed": False, "categorical_features": False,
            "parameters": model.get_params()})
    return {"file": path.name, "sha256": digest(path)}


def main() -> None:
    dataset = import_module("research.45_market_dataset.dataset")
    account = import_module("research.45_market_dataset.account")
    spec_path = TRACK / "specification.json"
    spec = json.loads(spec_path.read_text())
    output = TRACK / "runs/initial-v1"
    if output.exists():
        raise ValueError("initial run exists; never overwrite research evidence")
    output.mkdir(parents=True)
    shutil.copyfile(spec_path, output / "specification.json")
    source_hashes = {}
    sources = list(TRACK.glob("*.py")) + list((ROOT / "research/45_market_dataset").glob("*.py"))
    sources += [ROOT / "research/intraday_lab/costs.py"]
    for source in sorted(sources):
        relative = source.relative_to(ROOT)
        target = output / "source" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
        source_hashes[relative.as_posix()] = digest(source)
    write_json(output / "plan.json", {"specification_sha256": digest(spec_path),
        "source_hashes": source_hashes, "created_utc": datetime.now(timezone.utc).isoformat(),
        "runtime": {"python": platform.python_version(), "sklearn": sklearn.__version__,
                    "numpy": np.__version__, "pandas": pd.__version__},
        "promotion_eligible": False})
    frame, _, manifest = dataset.load_dataset()
    features = list(dataset.FEATURES_CONTEXT)
    if not np.isfinite(frame[features].to_numpy(dtype=float)).all():
        raise ValueError("shared finite feature cohort required")
    write_json(output / "dataset-manifest.json", manifest)
    fitted, selections, trials, forecast_reports, cohort, controls = {}, [], [], [], {}, []
    for horizon in spec["horizons_minutes"]:
        parts = chronological_parts(frame, spec, horizon)
        train, validation = parts["training"], parts["validation"]
        if min(len(train), len(validation), len(parts["test"])) < 100:
            raise ValueError("declared chronological phases require at least 100 rows")
        cohort[str(horizon)] = {phase: {"rows": len(rows), "dates": rows.date.nunique(),
                                       "first_date": str(rows.date.min()), "last_date": str(rows.date.max())}
                                for phase, rows in parts.items()}
        target = f"target_gross_bps_{horizon}"
        mean = float(train[target].mean())
        models = {"ridge": make_pipeline(StandardScaler(), Ridge(alpha=spec["ridge_alpha"])),
                  "boosting": HistGradientBoostingRegressor(**spec["boosting"])}
        predictions = {f"momentum_l{lookback}": validation[f"ret{lookback}"].to_numpy()
                       for lookback in spec["momentum_lookbacks_minutes"]}
        for family, model in models.items():
            with threadpool_limits(limits=2):
                model.fit(train[features], train[target])
                predictions[family] = model.predict(validation[features])
            fitted[(horizon, family)] = model
            state = freeze_model(output, horizon, family, model, features)
            forecast_reports.append({"horizon": horizon, "family": family, "phase": "validation",
                "train_mean_bps": mean, "frozen_model": state,
                **forecast_metrics(validation[target].to_numpy(), predictions[family], mean)})
        saved = validation.copy()
        for name, values in predictions.items():
            saved[f"prediction_{name}"] = values
        saved.to_parquet(output / f"predictions-validation-h{horizon}.parquet", index=False)
        grid = candidates(horizon, spec)
        control = save_account(output, f"validation-h{horizon}-no-trade-cost2",
            account.account_replay(validation, np.zeros(len(validation)), horizon,
                                   threshold_net_bps=10.0, cost_per_leg_bps=2.0))
        if control["trades"] != 0 or control["net_pnl"] != 0:
            raise ValueError("shared account no-trade comparator is invalid")
        horizon_trials = []
        for candidate in grid:
            column = f"momentum_l{candidate.lookback}" if candidate.family == "momentum" else candidate.family
            summary = save_account(output, f"validation-{candidate.candidate_id}-cost2",
                account.account_replay(validation, predictions[column], horizon,
                                       threshold_net_bps=candidate.threshold_bps, cost_per_leg_bps=2.0))
            row = {**candidate_record(candidate), "phase": "validation", "cost_per_leg_bps": 2,
                   **summary}
            trials.append(row)
            horizon_trials.append(row)
        for family in ("momentum", "ridge", "boosting"):
            controls.append({"horizon": horizon, "family": family, "candidate_id": "no_trade", **control})
            selection = select_validation([row for row in horizon_trials if row["family"] == family],
                                          spec["minimum_validation_trades"])
            if not selection["abstain"]:
                selected = next(c for c in grid if c.candidate_id == selection["candidate_id"])
                selection["parameters"] = candidate_record(selected)
            selections.append({"horizon": horizon, "family": family, **selection})
        print(json.dumps({"horizon": horizon, "validation_trials_completed": len(grid),
                          "selected": selections[-3:]}), flush=True)
    if len(trials) != spec["validation_entry_trials"]:
        raise ValueError("trial count differs from frozen plan")
    write_json(output / "cohort.json", cohort)
    write_json(output / "validation-trials.json", trials)
    write_json(output / "validation-controls.json", controls)
    freeze = {"created_utc": datetime.now(timezone.utc).isoformat(), "features": features,
              "selections": selections, "validation_trials_sha256": digest(output / "validation-trials.json"),
              "validation_controls_sha256": digest(output / "validation-controls.json"),
              "specification_sha256": digest(spec_path), "model_states": [
                  report["frozen_model"] for report in forecast_reports],
              "selection_controls": 9, "test_inspected_during_selection": False}
    # Only after this file is durable do we predict or evaluate the test cohort.
    write_json(output / "selection-freeze.json", freeze)
    test_results = []
    for horizon in spec["horizons_minutes"]:
        parts = chronological_parts(frame, spec, horizon)
        train, test = parts["training"], parts["test"]
        target = f"target_gross_bps_{horizon}"
        mean = float(train[target].mean())
        predictions = {f"momentum_l{lookback}": test[f"ret{lookback}"].to_numpy()
                       for lookback in spec["momentum_lookbacks_minutes"]}
        for family in ("ridge", "boosting"):
            with threadpool_limits(limits=2):
                predictions[family] = fitted[(horizon, family)].predict(test[features])
            forecast_reports.append({"horizon": horizon, "family": family, "phase": "test",
                "train_mean_bps": mean, **forecast_metrics(test[target].to_numpy(), predictions[family], mean)})
        saved = test.copy()
        for name, values in predictions.items():
            saved[f"prediction_{name}"] = values
        saved.to_parquet(output / f"predictions-test-h{horizon}.parquet", index=False)
        for selection in [s for s in selections if s["horizon"] == horizon]:
            if selection["abstain"]:
                forecast, threshold = np.zeros(len(test)), 10.0
            else:
                params = selection["parameters"]
                name = f"momentum_l{params['lookback']}" if params["family"] == "momentum" else params["family"]
                forecast, threshold = predictions[name], params["threshold_bps"]
            for cost in spec["test_costs_per_leg_bps"]:
                stem = f"test-h{horizon}-{selection['family']}-cost{cost:g}"
                summary = save_account(output, stem, account.account_replay(test, forecast, horizon,
                    threshold_net_bps=threshold, cost_per_leg_bps=cost))
                test_results.append({"horizon": horizon, "family": selection["family"], "phase": "test",
                                     "selected_candidate": selection["candidate_id"],
                                     "cost_per_leg_bps": cost, **summary})
    write_json(output / "results.json", {"selection_freeze_sha256": digest(output / "selection-freeze.json"),
               "validation_entry_trials": len(trials), "no_trade_selection_controls": 9,
               "test_account_replays": len(test_results), "test_results": test_results,
               "forecast_metrics": forecast_reports, "promotion_eligible": False})
    pd.DataFrame(trials).to_csv(output / "validation-trials.csv", index=False)
    pd.DataFrame(test_results).to_csv(output / "test-comparison.csv", index=False)
    print(json.dumps({"test_account_replays": len(test_results), "results": test_results}), flush=True)


if __name__ == "__main__":
    main()
