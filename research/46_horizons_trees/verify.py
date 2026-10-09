"""Check frozen source/account evidence and independently reproduce model states."""

from importlib import import_module
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .run import ROOT, TRACK, digest, write_json


def predict_nodes(features: np.ndarray, model_path: Path) -> np.ndarray:
    """Evaluate saved numeric decision nodes, without loading an estimator pickle."""
    values = np.asarray(features, dtype=float)
    with np.load(model_path, allow_pickle=False) as state:
        output = np.full(len(values), float(state["baseline"].ravel()[0]))
        tree_names = sorted((name for name in state.files if name.startswith("nodes_")),
                            key=lambda name: int(name.split("_")[1]))
        for name in tree_names:
            nodes = state[name]
            if nodes["is_categorical"].any():
                raise ValueError("numeric-node verifier does not support categorical branches")
            position = np.zeros(len(values), dtype=int)
            active = ~nodes[position]["is_leaf"].astype(bool)
            while active.any():
                row_indices = np.flatnonzero(active)
                branch = nodes[position[active]]
                condition = values[row_indices, branch["feature_idx"]] <= branch["num_threshold"]
                position[active] = np.where(condition, branch["left"], branch["right"])
                active = ~nodes[position]["is_leaf"].astype(bool)
            output += nodes[position]["value"]
    return output


def main() -> None:
    output = TRACK / "runs/initial-v1"
    plan = json.loads((output / "plan.json").read_text())
    for name, expected in plan["source_hashes"].items():
        if digest(ROOT / name) != expected or digest(output / "source" / name) != expected:
            raise ValueError(f"source changed: {name}")
    if digest(TRACK / "specification.json") != plan["specification_sha256"]:
        raise ValueError("specification changed after plan")
    selection = json.loads((output / "selection-freeze.json").read_text())
    results = json.loads((output / "results.json").read_text())
    if digest(output / "selection-freeze.json") != results["selection_freeze_sha256"]:
        raise ValueError("selection freeze changed after test")
    for name in ("validation-trials", "validation-controls"):
        if digest(output / f"{name}.json") != selection[f"{name.replace('-', '_')}_sha256"]:
            raise ValueError(f"selection input changed: {name}")
    for state in selection["model_states"]:
        if digest(output / state["file"]) != state["sha256"]:
            raise ValueError(f"model changed: {state['file']}")
    dataset = import_module("research.45_market_dataset.dataset")
    _, _, current_manifest = dataset.load_dataset()
    if current_manifest != json.loads((output / "dataset-manifest.json").read_text()):
        raise ValueError("dataset manifest changed")
    forecast_checks = []
    features = selection["features"]
    for horizon in (5, 15, 30):
        ridge = json.loads((output / f"model-h{horizon}-ridge.json").read_text())
        for phase in ("validation", "test"):
            frame = pd.read_parquet(output / f"predictions-{phase}-h{horizon}.parquet")
            x = frame[features].to_numpy(dtype=float)
            actual = ((x - np.asarray(ridge["mean"])) / np.asarray(ridge["scale"])) @ np.asarray(
                ridge["coefficients"]) + ridge["intercept"]
            np.testing.assert_allclose(actual, frame.prediction_ridge, rtol=1e-11, atol=1e-11)
            boosted = predict_nodes(x, output / f"model-h{horizon}-boosting.npz")
            np.testing.assert_allclose(boosted, frame.prediction_boosting, rtol=1e-11, atol=1e-11)
            forecast_checks.append({"horizon": horizon, "phase": phase, "rows": len(frame),
                "ridge_max_error": float(np.max(np.abs(actual - frame.prediction_ridge))),
                "boosting_max_error": float(np.max(np.abs(boosted - frame.prediction_boosting)))})
    account_checks = []
    for path in sorted(output.glob("account-*.json")):
        stem = path.name.removeprefix("account-").removesuffix(".json")
        summary = json.loads(path.read_text())
        trades_path = output / f"trades-{stem}.csv"
        trades = pd.DataFrame() if not trades_path.read_text().strip() else pd.read_csv(trades_path)
        daily = pd.read_csv(output / f"daily-{stem}.csv")
        if len(trades) != summary["trades"] or len(daily) != summary["sessions"]:
            raise ValueError(f"account ledger length differs: {stem}")
        if (daily.maximum_slots > 3).any() or abs(daily.net_pnl.sum() - summary["net_pnl"]) > 1e-5:
            raise ValueError(f"account daily invariant differs: {stem}")
        if not trades.empty:
            if not ((trades.decision_us < trades.entry_us) & (trades.entry_us < trades.exit_us)).all():
                raise ValueError(f"noncausal trade: {stem}")
            for column in ("gross_pnl", "fees", "net_pnl"):
                if abs(trades[column].sum() - summary[column]) > 1e-5:
                    raise ValueError(f"ledger {column} differs: {stem}")
            if np.max(np.abs(trades.gross_pnl - trades.fees - trades.net_pnl)) > 1e-5:
                raise ValueError(f"net accounting differs: {stem}")
            for _, group in trades.groupby(["date", "security_id"]):
                group = group.sort_values("decision_us")
                if any(a > b for a, b in zip(group.exit_us.to_numpy()[:-1], group.decision_us.to_numpy()[1:])):
                    raise ValueError(f"instrument trades overlap: {stem}")
        account_checks.append({"stem": stem, "trades": len(trades), "verified": True})
    report = {"verified": True, "forecast_checks": forecast_checks, "account_checks": account_checks,
              "frozen_selection_before_test": selection["created_utc"],
              "minimum_test_file_mtime": min(path.stat().st_mtime for path in output.glob("predictions-test-*.parquet"))}
    write_json(TRACK / "evidence-verification.json", report)
    print(json.dumps({"verified": True, "forecast_cohorts": len(forecast_checks), "accounts": len(account_checks)}))


if __name__ == "__main__":
    main()
