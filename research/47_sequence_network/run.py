"""Frozen chronological neural fitting, row forecasts and candle-account proxies."""

import argparse
from dataclasses import asdict
from hashlib import sha256
from importlib import import_module
import json
from pathlib import Path
import platform
import time

import numpy as np
import pandas as pd
import torch

from .network import (SEEDS, Scaler, ForecastNetwork, deterministic, fit_network, fit_ridge,
                      predict_normalized, ridge_predict, tabular)


def write(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False), encoding="utf-8")


def file_hash(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(part)
    return digest.hexdigest()


def array_hash(values: np.ndarray) -> str:
    values = np.ascontiguousarray(values)
    digest = sha256(f"{values.shape}|{values.dtype}".encode())
    digest.update(values.tobytes())
    return digest.hexdigest()


def metrics(target: np.ndarray, prediction: np.ndarray, training_majority_sign: int) -> dict:
    target, prediction = np.asarray(target), np.asarray(prediction)
    if target.shape != prediction.shape or target.ndim != 1 or not np.isfinite(target).all() or not np.isfinite(prediction).all():
        raise ValueError("aligned finite scalar predictions and targets required")
    if not len(target):
        return {"rows": 0}
    directional = target != 0
    return {"rows": len(target), "rmse_bps": float(np.sqrt(np.mean((target - prediction) ** 2))),
            "mae_bps": float(np.mean(np.abs(target - prediction))),
            "mean_target_bps": float(target.mean()), "mean_prediction_bps": float(prediction.mean()),
            "sign_accuracy": float(np.mean(np.sign(prediction[directional]) == np.sign(target[directional]))) if directional.any() else None,
            "nonzero_target_rows": int(directional.sum()),
            "training_majority_sign": training_majority_sign,
            "training_majority_sign_accuracy": float(np.mean(training_majority_sign == np.sign(target[directional]))) if directional.any() else None,
            "direction_semantics": "sign of raw entry-to-exit candle return; zero target excluded; zero prediction counts incorrect"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-module", required=True)
    parser.add_argument("--account-module", required=True)
    args = parser.parse_args()
    data_api, account_api = import_module(args.dataset_module), import_module(args.account_module)
    folder = Path(__file__).resolve().parent
    output = folder / "runs" / "initial-v1"
    if output.exists():
        raise ValueError("versioned evidence exists; use a newly frozen specification")
    rows, sequences, manifest = data_api.load_dataset()
    context_names = tuple(data_api.FEATURES_CONTEXT)
    context = rows.loc[:, context_names].to_numpy(dtype=np.float32)
    target = rows["target_gross_bps_15"].to_numpy(dtype=float)
    if not np.array_equal(rows["seq_index"].to_numpy(), np.arange(len(rows))):
        raise ValueError("row order differs from shared sequence identity")
    if not np.isfinite(target).all():
        raise ValueError("shared target contains missing/nonfinite labels")
    bounds = {"train": ("2022-01-01", "2023-12-31"), "validation": ("2024-01-01", "2024-12-31"),
              "test": ("2025-01-01", "2026-12-31")}
    masks = {name: rows.date.between(*dates).to_numpy() for name, dates in bounds.items()}
    if any(not mask.any() for mask in masks.values()) or not np.logical_or.reduce(list(masks.values())).all():
        raise ValueError("expected nonempty disjoint train/validation/test masks")
    train, validation = masks["train"], masks["validation"]
    output.mkdir(parents=True)
    source_digest = sha256()
    sources = list(folder.glob("*.py")) + list((folder / "tests").glob("*.py"))
    for path in sorted(sources):
        relative = path.relative_to(folder)
        source_digest.update(relative.as_posix().encode())
        source_digest.update(path.read_bytes())
        saved = output / "source" / relative
        saved.parent.mkdir(parents=True, exist_ok=True)
        saved.write_bytes(path.read_bytes())
    for module, name in ((data_api, "shared-dataset-source.py"), (account_api, "shared-account-source.py")):
        (output / name).write_bytes(Path(module.__file__).read_bytes())
    write(output / "plan.json", {"runtime": {"python": platform.python_version(), "torch": torch.__version__,
         "numpy": np.__version__, "pandas": pd.__version__, "cuda": torch.cuda.is_available()},
         "source_sha256": source_digest.hexdigest(), "preregistration_sha256": file_hash(folder / "preregistration.md"),
         "dataset_module": args.dataset_module, "account_module": args.account_module,
         "dataset_source_sha256": file_hash(Path(data_api.__file__)), "account_source_sha256": file_hash(Path(account_api.__file__)),
         "dataset_manifest": manifest, "rows": len(rows), "phase_rows": {name: int(mask.sum()) for name, mask in masks.items()},
         "sequence_shape": list(sequences.shape), "sequence_sha256": array_hash(sequences),
         "context_names": list(context_names), "context_sha256": array_hash(context),
         "sequence_channels": ["ret1_bps", "body_bps", "range_bps", "log1p_causal_volume_local_ratio", "vwapdev_bps"],
         "target_sha256": array_hash(target), "seeds": list(SEEDS), "horizon_minutes": 15,
         "cost_per_leg_bps": [2, 5, 10], "threshold_net_bps": 2, "promotion_eligible": False,
         "limitations": ["historical data, no untouched prospective holdout", "candle execution proxy, no observed spread or source latency",
                         "full-session ex-post data eligibility and current survivor coverage", "multiple models and seeds; no test-based tuning"]})
    scaler = Scaler.fit(sequences[train], context[train], target[train])
    write(output / "scaler.json", asdict(scaler))
    train_sequence, train_context = scaler.transform(sequences[train], context[train])
    validation_sequence, validation_context = scaler.transform(sequences[validation], context[validation])
    train_target = (target[train] - scaler.target_mean) / scaler.target_scale
    validation_target = (target[validation] - scaler.target_mean) / scaler.target_scale
    ridge = fit_ridge(tabular(train_sequence, train_context), train_target)
    np.savez_compressed(output / "ridge.npz", mean=ridge[0], scale=ridge[1], coefficients=ridge[2])
    models, histories, validation_forecasts = {}, {}, {}
    for architecture in ("mlp", "gru"):
        for seed in SEEDS:
            name = f"{architecture}_seed_{seed}"
            started = time.perf_counter()
            model, report = fit_network(architecture, seed, train_sequence, train_context, train_target,
                                        validation_sequence, validation_context, validation_target)
            models[name], histories[name] = model, report
            torch.save(model.state_dict(), output / f"{name}.pt")
            validation_forecasts[name] = predict_normalized(model, validation_sequence, validation_context) * scaler.target_scale + scaler.target_mean
            restored = ForecastNetwork(architecture, sequences.shape[2], context.shape[1])
            restored.load_state_dict(torch.load(output / f"{name}.pt", weights_only=True, map_location="cpu"))
            restored_prediction = predict_normalized(restored, validation_sequence, validation_context) * scaler.target_scale + scaler.target_mean
            if not np.array_equal(restored_prediction, validation_forecasts[name]):
                raise ValueError("persisted checkpoint does not reproduce validation forecasts exactly")
            write(output / f"training-{name}.json", report)
            print(json.dumps({"event": "trained", "variant": name, "selected_epoch": report["selected_epoch"],
                              "validation_mse": report["selected_validation_mse"],
                              "seconds": round(time.perf_counter() - started, 3)}), flush=True)
    validation_forecasts["ridge"] = ridge_predict(tabular(validation_sequence, validation_context), ridge) * scaler.target_scale + scaler.target_mean
    validation_forecasts["constant_training_mean"] = np.full(validation.sum(), scaler.target_mean)
    validation_forecasts["zero_return"] = np.zeros(validation.sum())
    for architecture in ("mlp", "gru"):
        validation_forecasts[f"{architecture}_seed_average"] = np.mean([validation_forecasts[f"{architecture}_seed_{seed}"] for seed in SEEDS], axis=0)
    validation_rmse = {name: float(np.sqrt(np.mean((forecast - target[validation]) ** 2))) for name, forecast in validation_forecasts.items()}
    selected = min(validation_rmse, key=lambda name: (validation_rmse[name], name))
    model_files = [output / f"{name}.pt" for name in models] + [output / "ridge.npz", output / "scaler.json"]
    write(output / "frozen-selection.json", {"selected_by_validation_rmse": selected,
          "validation_rmse_bps": validation_rmse, "test_used_for_selection": False,
          "model_sha256": {path.name: file_hash(path) for path in model_files},
          "all_seeds_reported": True, "frozen_before_test_predictions": True})
    sequence, scaled_context = scaler.transform(sequences, context)
    predictions = {"constant_training_mean": np.full(len(rows), scaler.target_mean), "zero_return": np.zeros(len(rows)),
                   "ridge": ridge_predict(tabular(sequence, scaled_context), ridge) * scaler.target_scale + scaler.target_mean}
    for name, model in models.items():
        predictions[name] = predict_normalized(model, sequence, scaled_context) * scaler.target_scale + scaler.target_mean
    for architecture in ("mlp", "gru"):
        predictions[f"{architecture}_seed_average"] = np.mean([predictions[f"{architecture}_seed_{seed}"] for seed in SEEDS], axis=0)
    ledger = rows.copy()
    ledger["phase"] = np.select([masks[name] for name in ("train", "validation", "test")],
                                 ["train", "validation", "test"], default="outside")
    for name, prediction in predictions.items():
        if not np.isfinite(prediction).all():
            raise ValueError(f"nonfinite forecast from {name}")
        ledger[f"prediction_{name}_gross_bps"] = prediction
    ledger.to_parquet(output / "predictions.parquet", index=False, compression="zstd")
    readback = pd.read_parquet(output / "predictions.parquet")
    if not np.array_equal(readback.seq_index.to_numpy(), rows.seq_index.to_numpy()):
        raise ValueError("persisted prediction row identity changed")
    for name, prediction in predictions.items():
        if not np.array_equal(readback[f"prediction_{name}_gross_bps"].to_numpy(), prediction):
            raise ValueError("persisted prediction values changed")
    majority = 1 if np.mean(target[train] > 0) >= np.mean(target[train] < 0) else -1
    forecast_results, account_results = [], []
    for name, prediction in predictions.items():
        for phase_name, mask in masks.items():
            forecast_results.append({"variant": name, "phase": phase_name, "selected_by_validation": name == selected,
                                     **metrics(target[mask], prediction[mask], majority)})
        for phase_name in ("validation", "test"):
            mask = masks[phase_name]
            for cost in (2, 5, 10):
                summary, trades, daily = account_api.account_replay(rows.loc[mask].reset_index(drop=True), prediction[mask],
                            horizon=15, threshold_net_bps=2, cost_per_leg_bps=cost)
                stem = f"{name}-{phase_name}-cost{cost}"
                write(output / f"account-{stem}.json", summary)
                trades.to_parquet(output / f"trades-{stem}.parquet", index=False, compression="zstd")
                daily.to_parquet(output / f"daily-{stem}.parquet", index=False, compression="zstd")
                account_results.append({"variant": name, "phase": phase_name, "cost_per_leg_bps": cost, **summary})
    write(output / "forecast-metrics.json", forecast_results)
    pd.DataFrame(forecast_results).to_csv(output / "forecast-metrics.csv", index=False)
    write(output / "account-metrics.json", account_results)
    write(output / "verification.json", {"rows": len(rows), "variants": len(predictions),
          "predictions_sha256": file_hash(output / "predictions.parquet"),
          "all_finite_predictions": True, "row_order_unchanged": True,
          "all_weights_frozen_before_test": True, "all_saved_checkpoints_reproduce_validation_exactly": True,
          "persisted_predictions_exact_readback": True, "promotion_eligible": False})
    print(json.dumps({"event": "completed", "output": str(output), "selected_validation_variant": selected}), flush=True)


if __name__ == "__main__":
    main()
