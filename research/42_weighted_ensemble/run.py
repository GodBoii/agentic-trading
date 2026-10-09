"""Freeze base models and stacking weights before replaying historical evaluations."""

from dataclasses import asdict, replace
from hashlib import sha256
import json
from pathlib import Path

import numpy as np

from research.common.data import DEVELOPMENT, VALIDATION, AUDIT, ROOT, file_hash, load_manifest, load_ticks
from research.common.runner import Variant, run_track
from research.intraday_lab.domain import PolicyConfig
from .strategy import (Ensemble, EnsemblePolicy, VARIANTS, SPECIALISTS, GROUPS,
                       RIDGE, SHRINKAGE, executable_labels, fit_ensemble)


def write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False), encoding="utf-8")


def fingerprint(array: np.ndarray) -> str:
    value = np.ascontiguousarray(array, dtype="<f8")
    digest = sha256(str(value.shape).encode())
    digest.update(value.tobytes())
    return digest.hexdigest()


def metrics(predicted: np.ndarray, y: np.ndarray, constant: np.ndarray) -> dict:
    predicted, y = np.asarray(predicted), np.asarray(y)
    if predicted.shape != y.shape or y.ndim != 2 or y.shape[1] != 2:
        raise ValueError("prediction metrics require aligned long/short targets")
    if not len(y):
        return {"samples": 0}
    selected = predicted.argmax(axis=1)
    indices = np.arange(len(y))
    chosen = y[indices, selected]
    admitted = predicted[indices, selected] >= 2
    ties = np.abs(y[:, 0] - y[:, 1]) < 1e-12
    preferred = y.argmax(axis=1)
    return {
        "samples": len(y),
        "rmse_net_bps": float(np.sqrt(np.mean((predicted - y) ** 2))),
        "constant_training_mean_rmse_net_bps": float(np.sqrt(np.mean((constant - y) ** 2))),
        "preferred_side_accuracy": float(np.mean(selected[~ties] == preferred[~ties])) if (~ties).any() else None,
        "preferred_side_target_ties_excluded": int(ties.sum()),
        "always_long_preferred_side_accuracy": float(np.mean(preferred[~ties] == 0)) if (~ties).any() else None,
        "always_short_preferred_side_accuracy": float(np.mean(preferred[~ties] == 1)) if (~ties).any() else None,
        "selected_label_mean_net_bps": float(chosen.mean()),
        "selected_label_profit_fraction": float(np.mean(chosen > 0)),
        "predicted_edge_ge_2bps_rows": int(admitted.sum()),
        "admitted_fraction": float(admitted.mean()),
        "admitted_label_mean_net_bps": float(chosen[admitted].mean()) if admitted.any() else None,
        "admitted_label_profit_fraction": float(np.mean(chosen[admitted] > 0)) if admitted.any() else None,
        "admitted_training_mean_rmse_net_bps": float(np.sqrt(np.mean((constant - y[admitted]) ** 2))) if admitted.any() else None,
        "admitted_model_rmse_net_bps": float(np.sqrt(np.mean((predicted[admitted] - y[admitted]) ** 2))) if admitted.any() else None,
    }


def diagnostics(model: Ensemble | None, x: np.ndarray, y: np.ndarray) -> dict:
    if model is None or not len(x):
        return {"samples": len(x), "fitted": model is not None}
    values = {name: metrics(model.predict(x, name), y, np.asarray(model.constant_net)) for name in VARIANTS}
    residuals = np.stack([(model.predict(x, name) - y).reshape(-1) for name in SPECIALISTS])
    errors = np.corrcoef(residuals)
    return {"samples": len(x), "fitted": True, "variants": values,
            "specialist_error_correlations": errors.tolist(), "specialist_order": list(SPECIALISTS),
            "preferred_side_semantics": "higher realized two-sided executable net label, not profitable-trade accuracy"}


def main() -> None:
    folder = Path(__file__).resolve().parent
    model_folder = folder / "models" / "initial-v1"
    if model_folder.exists() or (folder / "runs" / "initial-v1").exists():
        raise ValueError("versioned evidence already exists; freeze a new specification")
    models, reports = {}, {}
    dependency = ROOT / "research/08_statistical_models/strategy.py"
    for mode in ("recent_trade", "receipt_proxy"):
        config = replace(PolicyConfig(), freshness_mode=mode)
        rows, sources = {}, []
        for day in DEVELOPMENT:
            x, y, counts = executable_labels(load_ticks(day), config)
            rows[day] = (x, y)
            sources.append({"date": day, "input_sha256": load_manifest(day)["cache_sha256"],
                            "x_sha256": fingerprint(x), "y_sha256": fingerprint(y), **counts})
        x = np.concatenate([rows[day][0] for day in DEVELOPMENT[:2]])
        y = np.concatenate([rows[day][1] for day in DEVELOPMENT[:2]])
        stack_x, stack_y = rows[DEVELOPMENT[2]]
        models[mode] = fit_ensemble(x, y, stack_x, stack_y, DEVELOPMENT, mode)
        reports[mode] = {"base_fit_dates": list(DEVELOPMENT[:2]), "weight_fit_dates": [DEVELOPMENT[2]],
                         "status": "fitted" if models[mode] else "insufficient_training",
                         "base_rows": len(x), "weight_rows": len(stack_x), "inputs": sources,
                         "model": asdict(models[mode]) if models[mode] else None,
                         "feature_dependency_sha256": file_hash(dependency),
                         "preregistration_sha256": file_hash(folder / "preregistration.md"),
                         "weights_fit_on_base_training_predictions": False,
                         "evaluation_used_for_normalization_or_weights": False}
        print(json.dumps({"event": "training_finished", "mode": mode, "base_rows": len(x),
                          "weight_rows": len(stack_x), "status": reports[mode]["status"]}), flush=True)
    model_folder.mkdir(parents=True)
    (model_folder / "track08-strategy-source.py").write_bytes(dependency.read_bytes())
    write(model_folder / "frozen-models.json", reports)
    frozen_hash = file_hash(model_folder / "frozen-models.json")
    variants = [Variant(name, lambda cfg: EnsemblePolicy(cfg, models[cfg.freshness_mode], DEVELOPMENT),
                        {"specialist_groups": [list(group) for group in GROUPS], "ridge_l2": RIDGE,
                         "convex_weight_shrinkage": SHRINKAGE, "minimum_predicted_net_bps": 2,
                         "frozen_models_sha256": frozen_hash, "frozen_training": reports},
                        {"horizon_seconds": 60, "cooldown_seconds": 180}) for name in VARIANTS]
    output = run_track(folder, variants, dates=VALIDATION + AUDIT)
    write(output / "frozen-models.json", reports)
    evaluations, pooled = [], {mode: [] for mode in models}
    for day in VALIDATION + AUDIT:
        ticks = load_ticks(day)
        for mode, model in models.items():
            x, y, counts = executable_labels(ticks, replace(PolicyConfig(), freshness_mode=mode))
            pooled[mode].append((x, y))
            evaluations.append({"date": day, "mode": mode, **counts, **diagnostics(model, x, y)})
    for mode, rows in pooled.items():
        evaluations.append({"date": "pooled_four_evaluation_sessions", "mode": mode,
                            **diagnostics(models[mode], np.concatenate([row[0] for row in rows]),
                                          np.concatenate([row[1] for row in rows]))})
    write(output / "forecast-diagnostics.json", evaluations)
    if file_hash(dependency) != reports["receipt_proxy"]["feature_dependency_sha256"]:
        raise ValueError("shared feature dependency changed during the experiment")
    print(json.dumps({"event": "completed", "output": str(output)}), flush=True)


if __name__ == "__main__":
    main()
