"""Train only development dates, freeze, then measure later historical diagnostics."""

from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path

import numpy as np

from research.common.data import AUDIT, DEVELOPMENT, VALIDATION, load_manifest, load_ticks
from research.common.runner import Variant, run_track
from research.intraday_lab.domain import PolicyConfig
from .strategy import FrozenModel, StatisticalPolicy, executable_labels, fit_model


def json_hash(payload: dict) -> str:
    return sha256(json.dumps(payload, sort_keys=True, allow_nan=False).encode()).hexdigest()


def forecast_diagnostics(model: FrozenModel | None, x: np.ndarray, y: np.ndarray,
                         frozen_profit_prevalence: list[float], frozen_mean_net: list[float]) -> dict:
    if model is None or not len(x):
        return {"samples": len(x), "fitted": model is not None}
    predictions = [model.predictions(row) for row in x]
    net = np.asarray([p[0] for p in predictions])
    prob = np.asarray([p[1] for p in predictions])
    outcomes = (y > 0).astype(float)
    results = []
    for side in range(2):
        baseline = frozen_profit_prevalence[side]
        correlation = (float(np.corrcoef(net[:, side], y[:, side])[0, 1])
                       if np.std(net[:, side]) > 0 and np.std(y[:, side]) > 0 else None)
        results.append({"side": "long" if side == 0 else "short",
                        "rmse_net_bps": float(np.sqrt(np.mean((net[:, side] - y[:, side]) ** 2))),
                        "mean_actual_net_bps": float(y[:, side].mean()),
                        "mean_predicted_net_bps": float(net[:, side].mean()),
                        "correlation": correlation,
                        "brier_score": float(np.mean((prob[:, side] - outcomes[:, side]) ** 2)),
                        "constant_probability_brier": float(np.mean((baseline - outcomes[:, side]) ** 2)),
                        "constant_mean_rmse_net_bps": float(np.sqrt(np.mean(
                            (frozen_mean_net[side] - y[:, side]) ** 2))),
                        "constant_probability_role": "frozen training-session profit prevalence"})
    return {"samples": len(x), "fitted": True, "sides": results}


def main() -> None:
    models, training = {}, {}
    for mode in ("recent_trade", "receipt_proxy"):
        config = replace(PolicyConfig(), freshness_mode=mode)
        xs, ys, reports = [], [], []
        for day in DEVELOPMENT:
            x, y, counts = executable_labels(load_ticks(day), config)
            xs.append(x)
            ys.append(y)
            reports.append({"date": day, "input_sha256": load_manifest(day)["cache_sha256"], **counts})
        x, y = np.concatenate(xs), np.concatenate(ys)
        model = fit_model(x, y)
        models[mode] = model
        payload = model.payload() if model else {"fitted": False, "reason": "fewer_than_100_training_rows"}
        training[mode] = {"dates": list(DEVELOPMENT), "inputs": reports,
                          "training_x_sha256": sha256(x.tobytes()).hexdigest(),
                          "training_y_sha256": sha256(y.tobytes()).hexdigest(),
                          "samples": len(x), "model": payload, "model_sha256": json_hash(payload),
                          "training_profit_prevalence": (y > 0).mean(axis=0).tolist() if len(y) else [],
                          "training_mean_net_bps": y.mean(axis=0).tolist() if len(y) else [],
                          "label_horizon_seconds": 60, "label_notional": 100_000,
                          "label_entry_latency_ms": 250, "label_slippage_per_leg_bps": 1,
                          "ridge_average_error_l2": .01, "logistic_iterations": 400,
                          "label_size_limitation": "fixed notional may understate fees on smaller risk-sized replay orders"}
        print(json.dumps({"event": "trained", "mode": mode, "samples": len(x), "fitted": model is not None}), flush=True)
    variants = []
    for name, method, minimum in (("ridge_net_2bps", "ridge", 2),
                                  ("logistic_probability_65", "logistic_plus_ridge", 2),
                                  ("ridge_net_5bps", "ridge", 5)):
        parameters = {"method": method, "minimum_predicted_net_bps": minimum,
                      "minimum_profit_probability": .65, "frozen_training": training}
        variants.append(Variant(name,
            lambda cfg, method=method, minimum=minimum: StatisticalPolicy(
                cfg, models[cfg.freshness_mode], method, minimum), parameters,
            {"horizon_seconds": 60, "cooldown_seconds": 180}))
    output = run_track(Path(__file__).parent, variants, run_name="initial-v2", dates=VALIDATION + AUDIT)
    diagnostics = []
    for day in VALIDATION + AUDIT:
        ticks = load_ticks(day)
        for mode, model in models.items():
            x, y, counts = executable_labels(ticks, replace(PolicyConfig(), freshness_mode=mode))
            diagnostics.append({"date": day, "mode": mode, **counts, **forecast_diagnostics(
                model, x, y, training[mode]["training_profit_prevalence"],
                training[mode]["training_mean_net_bps"])})
    (output / "frozen-models.json").write_text(json.dumps(training, indent=2, sort_keys=True), encoding="utf-8")
    (output / "forecast-diagnostics.json").write_text(json.dumps(diagnostics, indent=2, allow_nan=False), encoding="utf-8")


if __name__ == "__main__":
    main()
