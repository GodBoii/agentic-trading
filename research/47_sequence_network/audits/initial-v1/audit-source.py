"""Verify frozen weights, prediction rows and account arithmetic without refitting."""

from importlib import import_module
from hashlib import sha256
import json
from pathlib import Path

import numpy as np
import pandas as pd
import torch

from .network import ForecastNetwork, Scaler, deterministic, predict_normalized, ridge_predict, tabular
from .run import file_hash, write


def main() -> None:
    folder = Path(__file__).resolve().parent
    run = folder / "runs" / "initial-v1"
    output = folder / "audits" / "initial-v1"
    if output.exists():
        raise ValueError("audit evidence exists; use a new audit version")
    plan = json.loads((run / "plan.json").read_text())
    frozen = json.loads((run / "frozen-selection.json").read_text())
    original = json.loads((run / "verification.json").read_text())
    source_digest = sha256()
    for path in sorted((run / "source").rglob("*.py")):
        relative = path.relative_to(run / "source")
        source_digest.update(relative.as_posix().encode())
        source_digest.update(path.read_bytes())
        if (folder / relative).read_bytes() != path.read_bytes():
            raise ValueError("original model or runner source changed after freezing")
    if source_digest.hexdigest() != plan["source_sha256"]:
        raise ValueError("frozen model source snapshot digest mismatch")
    rows, sequences, manifest = import_module(plan["dataset_module"]).load_dataset()
    predictions = pd.read_parquet(run / "predictions.parquet")
    if file_hash(run / "predictions.parquet") != original["predictions_sha256"]:
        raise ValueError("prediction ledger hash differs from recorded output")
    if manifest != plan["dataset_manifest"] or not predictions.loc[:, rows.columns].equals(rows):
        raise ValueError("original dataset rows or source hashes differ from prediction ledger")
    for name, digest in frozen["model_sha256"].items():
        if file_hash(run / name) != digest:
            raise ValueError("frozen fitted model fingerprint changed")
    selected = min(frozen["validation_rmse_bps"], key=lambda name: (frozen["validation_rmse_bps"][name], name))
    if selected != frozen["selected_by_validation_rmse"] or frozen["test_used_for_selection"]:
        raise ValueError("model selection differs from frozen validation-only rule")
    values = json.loads((run / "scaler.json").read_text())
    scaler = Scaler(tuple(values["sequence_mean"]), tuple(values["sequence_scale"]),
                    tuple(values["context_mean"]), tuple(values["context_scale"]),
                    values["target_mean"], values["target_scale"])
    context = rows.loc[:, plan["context_names"]].to_numpy(dtype=np.float32)
    train = rows.date.between("2022-01-01", "2023-12-31").to_numpy()
    training_scaler = Scaler.fit(sequences[train], context[train], rows.loc[train, "target_gross_bps_15"].to_numpy())
    if scaler != training_scaler:
        raise ValueError("saved scalers differ from training-only statistics")
    # Sample deterministic identities from every phase, independently of target or prediction values.
    sampled = np.concatenate([np.flatnonzero(predictions.phase.to_numpy() == phase)[:64]
                              for phase in ("train", "validation", "test")])
    sequence, scaled_context = scaler.transform(sequences[sampled], context[sampled])
    checkpoints = []
    for path in sorted(run.glob("*_seed_*.pt")):
        name = path.stem
        architecture = name.split("_seed_")[0]
        deterministic(17)
        model = ForecastNetwork(architecture, sequences.shape[2], context.shape[1])
        model.load_state_dict(torch.load(path, weights_only=True, map_location="cpu"))
        actual = predict_normalized(model, sequence, scaled_context) * scaler.target_scale + scaler.target_mean
        expected = predictions.iloc[sampled][f"prediction_{name}_gross_bps"].to_numpy()
        if not np.allclose(actual, expected, rtol=1e-6, atol=1e-4):
            raise ValueError("saved weights differ from independent sampled inference")
        checkpoints.append({"variant": name, "sampled_rows": len(sampled),
                            "maximum_absolute_difference_bps": float(np.max(np.abs(actual - expected))),
                            "inference_tolerance_absolute_bps": 1e-4, "inference_tolerance_relative": 1e-6})
    fitted = np.load(run / "ridge.npz")
    actual = ridge_predict(tabular(sequence, scaled_context), (fitted["mean"], fitted["scale"], fitted["coefficients"])) * scaler.target_scale + scaler.target_mean
    if not np.allclose(actual, predictions.iloc[sampled].prediction_ridge_gross_bps, rtol=1e-10, atol=1e-10):
        raise ValueError("saved ridge does not reproduce sample inference")
    for architecture in ("mlp", "gru"):
        seed_columns = [f"prediction_{architecture}_seed_{seed}_gross_bps" for seed in (17, 29, 43)]
        average = predictions.loc[:, seed_columns].to_numpy().mean(axis=1)
        if not np.array_equal(average, predictions[f"prediction_{architecture}_seed_average_gross_bps"].to_numpy()):
            raise ValueError("seed average differs from equal averaging")
    account_checks = []
    for path in sorted(run.glob("account-*-cost*.json")):
        summary = json.loads(path.read_text())
        stem = path.stem.removeprefix("account-")
        trades, daily = pd.read_parquet(run / f"trades-{stem}.parquet"), pd.read_parquet(run / f"daily-{stem}.parquet")
        if len(trades) != summary["trades"] or len(daily) != summary["sessions"]:
            raise ValueError("account ledger count mismatch")
        for column in ("gross_pnl", "fees", "net_pnl"):
            actual = float(trades[column].sum()) if len(trades) else 0.0
            if not np.isclose(actual, summary[column], rtol=1e-10, atol=1e-5):
                raise ValueError("account trade arithmetic mismatch")
        if len(trades):
            if not ((trades.decision_us < trades.entry_us) & (trades.entry_us < trades.exit_us)).all():
                raise ValueError("account ledger uses invalid fill chronology")
            gross = trades.side * (trades.exit_price - trades.entry_price) * trades.quantity
            if not np.allclose(gross, trades.gross_pnl, rtol=1e-10, atol=1e-7):
                raise ValueError("account gross arithmetic mismatch")
            if not np.allclose(trades.gross_pnl - trades.fees, trades.net_pnl, rtol=1e-10, atol=1e-7):
                raise ValueError("account net arithmetic mismatch")
        if (daily.maximum_slots > 3).any() or not np.isclose(daily.net_pnl.sum(), summary["net_pnl"], rtol=1e-10, atol=1e-5):
            raise ValueError("account daily capacity or aggregation mismatch")
        account_checks.append({"account": stem, "trades": len(trades), "pass": True})
    output.mkdir(parents=True)
    (output / "audit-source.py").write_bytes(Path(__file__).read_bytes())
    write(output / "report.json", {"frozen_models_sha256": frozen["model_sha256"], "rows": len(rows),
          "prediction_sha256": file_hash(run / "predictions.parquet"),
          "checkpoint_checks": checkpoints, "account_checks": account_checks,
          "training_only_scaler_exact_match": True, "dataset_row_identity_exact_match": True,
          "original_frozen_source_snapshot_and_live_source_match": True,
          "validation_only_selection_rule": True, "seed_average_exact_match": True,
          "refit_or_tuning": False, "promotion_eligible": False})
    print(json.dumps({"event": "audit_completed", "rows": len(rows), "account_checks": len(account_checks)}))


if __name__ == "__main__":
    main()
