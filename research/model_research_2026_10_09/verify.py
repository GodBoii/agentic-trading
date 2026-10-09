"""Validate original input hashes and exact planned output coverage across tracks."""

import importlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from research.common.data import ROOT, file_hash

data = importlib.import_module("research.45_market_dataset.dataset")


def require_names(folder: Path, pattern: str, expected: set[str]) -> None:
    actual = {p.name for p in folder.glob(pattern)}
    if actual != expected:
        raise ValueError(f"Incomplete or extra evidence in {folder}/{pattern}: missing {expected - actual}, extra {actual - expected}")


def main() -> None:
    output = Path(__file__).parent / "verification.json"
    if output.exists():
        raise ValueError("preserve existing report; use a newly versioned output")
    rows, sequence, manifest = data.load_dataset()
    for record in manifest["selection"] + manifest["inputs"]:
        if file_hash(ROOT / record["path"]) != record["sha256"]:
            raise ValueError("original selection or candle input changed")
    if rows.duplicated(["security_id", "decision_us"]).any() or not np.array_equal(rows.seq_index, np.arange(len(rows))):
        raise ValueError("duplicate or unaligned shared row identities")
    if not np.isfinite(rows[list(data.FEATURES_CONTEXT)]).all().all() or not np.isfinite(sequence).all():
        raise ValueError("invalid shared model inputs")
    if not (rows.entry_us - rows.decision_us == 60_000_000).all():
        raise ValueError("one-minute decision-to-entry delay changed")
    for horizon in data.HORIZONS:
        if not (rows[f"exit_us_{horizon}"] - rows.entry_us == horizon * 60_000_000).all():
            raise ValueError("target holding interval changed")
        expected = (rows[f"exit_reference_{horizon}"] / rows.entry_reference - 1) * 10000
        if not np.allclose(expected, rows[f"target_gross_bps_{horizon}"], rtol=0, atol=1e-10):
            raise ValueError("gross labels differ from original references")
    reports = []
    # Track46 keeps all candidate/control executions as individual account reports.
    track = ROOT / "research/46_horizons_trees"
    run = track / "runs/initial-v1"
    results = json.loads((run / "results.json").read_text())
    trials = json.loads((run / "validation-trials.json").read_text())
    expected_accounts = {f"validation-{t['candidate_id']}-cost2" for t in trials}
    expected_accounts |= {f"validation-h{h}-no-trade-cost2" for h in data.HORIZONS}
    expected_accounts |= {f"test-h{r['horizon']}-{r['family']}-cost{r['cost_per_leg_bps']:g}" for r in results["test_results"]}
    if len(trials) != 36 or len(expected_accounts) != 57 or len(results["test_results"]) != 18:
        raise ValueError("bounded-search execution count changed")
    require_names(run, "account-*.json", {f"account-{s}.json" for s in expected_accounts})
    for prefix in ["trades", "daily"]:
        require_names(run, f"{prefix}-*.csv", {f"{prefix}-{s}.csv" for s in expected_accounts})
    require_names(run, "predictions-*.parquet", {f"predictions-{phase}-h{h}.parquet"
                  for phase in ["validation", "test"] for h in data.HORIZONS})
    reports.append({"track": track.name, "exact_planned_account_outputs": 57,
                    "agent_verification_sha256": file_hash(track / "evidence-verification.json")})
    # Track47 retains all six seeds and both equal averages, including controls.
    track = ROOT / "research/47_sequence_network"
    run = track / "runs/initial-v1"
    results = json.loads((run / "account-metrics.json").read_text())
    expected_accounts = {f"{r['variant']}-{r['phase']}-cost{r['cost_per_leg_bps']:g}" for r in results}
    if len(results) != 66 or len(expected_accounts) != 66:
        raise ValueError("neural account coverage changed")
    require_names(run, "account-*.json", {f"account-{s}.json" for s in expected_accounts} | {"account-metrics.json"})
    for prefix in ["trades", "daily"]:
        require_names(run, f"{prefix}-*.parquet", {f"{prefix}-{s}.parquet" for s in expected_accounts})
    require_names(run, "*.pt", {f"{architecture}_seed_{seed}.pt" for architecture in ["mlp", "gru"] for seed in [17, 29, 43]})
    reports.append({"track": track.name, "exact_planned_account_outputs": 66,
                    "independent_audit_sha256": file_hash(track / "audits/initial-v1/report.json")})
    # Track48 separately records validation, pooled test and yearly test accounts.
    track = ROOT / "research/48_controlled_adaptation"
    run = track / "runs/initial-v1"
    results = json.loads((run / "summary.json").read_text())["results"]
    expected_accounts = {f"h{r['horizon']}-{r['method']}-{r['split']}-cost{r['cost_per_leg_bps']:g}" for r in results}
    if len(results) != 104 or len(expected_accounts) != 104:
        raise ValueError("adaptation account coverage changed")
    for prefix in ["trades", "daily"]:
        require_names(run, f"{prefix}-*.csv", {f"{prefix}-{s}.csv" for s in expected_accounts})
    require_names(run, "predictions-*.parquet", {f"predictions-h{h}.parquet" for h in data.HORIZONS})
    reports.append({"track": track.name, "exact_planned_account_outputs": 104,
                    "independent_verification_sha256": file_hash(track / "evidence/verification.json")})
    # Track49's strengthened verifier demands all six forecast and sixty account files.
    track = ROOT / "research/49_feature_ablation"
    run = track / "runs/initial-v1"
    verification = importlib.import_module("research.49_feature_ablation.verify")
    plan = json.loads((run / "plan.json").read_text())
    verification.require_coverage(run, plan["specification"])
    verified = json.loads((run / "verification-v2.json").read_text())
    if verified["verified_accounts"] != 60:
        raise ValueError("feature account coverage changed")
    reports.append({"track": track.name, "exact_planned_account_outputs": 60,
                    "strengthened_verification_sha256": file_hash(run / "verification-v2.json")})
    report = {"shared_rows": len(rows), "sequence_shape": list(sequence.shape), "phases": manifest["phases"],
              "unique_original_inputs": len({r["path"] for r in manifest["selection"] + manifest["inputs"]}),
              "source_hashes_and_all_target_intervals": "pass", "tracks": reports,
              "account_evaluations_with_saved_ledgers": sum(r["exact_planned_account_outputs"] for r in reports),
              "interpretation": "Scenario and yearly comparisons overlap; not independent observations. Shadow-selector utility calls are separate.",
              "promotion_eligible": False}
    output.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
