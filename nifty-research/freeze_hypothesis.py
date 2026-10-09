"""Freeze a selected exploratory hypothesis for later, genuinely new sessions."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import argparse
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parent


def linear_predict(bundle: dict, frame: pd.DataFrame) -> np.ndarray:
    values = frame[bundle["features"]].to_numpy(dtype=float)
    if not np.isfinite(values).all(): raise ValueError("Missing/nonfinite evidence cannot be predicted")
    return ((values - bundle["mean"]) / bundle["scale"]) @ bundle["coefficients"] + bundle["intercept"]


def save_frozen_bundle(destination: Path, bundle: dict) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    # An existing freeze is evidence. It must not silently become a refit.
    with destination.open("x", encoding="utf-8") as handle:
        json.dump(bundle, handle, indent=2, allow_nan=False)
        handle.write("\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a new immutable research freeze")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--frozen-on", type=date.fromisoformat, required=True)
    args = parser.parse_args()
    destination = args.output.resolve()
    if not destination.is_relative_to((ROOT / "research").resolve()):
        parser.error("Frozen output must stay inside nifty-research/research")
    if destination.exists():
        parser.error("Existing freeze cannot be overwritten; choose a new revision file")
    study_path = ROOT / "research/02_orderbook_horizons/study.py"
    spec = importlib.util.spec_from_file_location("frozen_book_study", study_path)
    study = importlib.util.module_from_spec(spec); spec.loader.exec_module(study)
    source = ROOT / "research/02_orderbook_horizons/artifacts/features.parquet"
    frame = study.horizon_targets(pd.read_parquet(source), 1)
    features = study.PRICE + study.NEAR
    training = frame[frame["feature_ready"] & frame["target_bps"].notna()
                     & np.isfinite(frame[features]).all(axis=1)]
    models = {}
    for name, columns in {"price": study.PRICE, "price_near": features}.items():
        model = make_pipeline(StandardScaler(), Ridge(alpha=100))
        model.fit(training[columns], training["target_bps"])
        models[name] = {"features": columns, "mean": model[0].mean_.tolist(), "scale": model[0].scale_.tolist(),
                        "coefficients": model[1].coef_.tolist(), "intercept": float(model[1].intercept_)}
        np.testing.assert_allclose(linear_predict(models[name], training), model.predict(training[columns]), rtol=1e-12, atol=1e-12)
    bundle = {"schema_version": 2, "status": "post_selection_frozen_research_only", "frozen_on": args.frozen_on.isoformat(), "execution_available": False,
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "feature_code_sha256": hashlib.sha256(study_path.read_bytes()).hexdigest(),
        "export_code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "shared_feature_code_sha256": {f"nifty_lab/{name}": hashlib.sha256((ROOT / "nifty_lab" / name).read_bytes()).hexdigest()
                                       for name in ("ingest.py", "io.py", "config.py")},
        "training_dates": sorted(training["date"].unique()), "training_rows":len(training),
        "last_training_label_at":training['label_at'].max().isoformat(), "horizon_minutes":1,
        "models":models, "selection_history":"Selected after examining 28 additions/horizon comparisons; Holm p 0.0547",
        "prospective_protocol":{
            "earliest_unviewed_date": (args.frozen_on + timedelta(days=1)).isoformat(), "minimum_regular_sessions":30,
            "session_calendar": "Must be checked against NSE trading calendar; a date cutoff is not a guarantee of a trading session",
            "sample":"At least 300 accepted complete minutes per session, fixed checks from study02",
            "cohort":"Common finite-feature cohort, six-minute complete history, fresh backward depth and continuous future labels",
            "training":"No refitting, threshold changes or feature changes during prospective phase",
            "primary_comparison":"Daily paired MSE improvement of price_near against frozen price model",
            "secondary_comparison":"RMSE against zero-return reference, descriptive direction accuracy",
            "inference":"Report all sessions and failed predictions; day-block interval, no interim selection or early-win stopping",
            "economic_validation":"Separate option price/cost/size replay required; forecast improvement is not trading approval",
            "data_collection":"Not enabled by this script; fresh data must be explicitly collected and timestamped"}}
    original = ROOT / "research/frozen-near-depth-hypothesis.json"
    if original.exists():
        bundle["original_freeze_sha256"] = hashlib.sha256(original.read_bytes()).hexdigest()
        bundle["revision_reason"] = "Export provenance and immutability correction, not feature or hyperparameter selection"
    save_frozen_bundle(destination, bundle)
    print(json.dumps({"training_rows":len(training),"training_dates":len(bundle['training_dates']),"serialized_prediction_parity":"passed"}))


if __name__ == '__main__': main()
