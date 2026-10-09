"""Fit the fixed ICICI/AXIS pair on development only and preserve later diagnostics."""

from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
import platform

from research.common.data import AUDIT, DEVELOPMENT, VALIDATION, load_manifest, load_ticks
from .strategy import PAIR, ar1_diagnostics, fit_pair, synchronize, two_leg_outcomes


def write(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, sort_keys=True, indent=2, allow_nan=False), encoding="utf-8")


def main() -> None:
    root = Path(__file__).parent
    output = root / "runs/initial-v3"
    if output.exists():
        raise ValueError("evidence exists; choose a new explicitly versioned run")
    output.mkdir(parents=True)
    source_hash = sha256()
    for path in sorted(root.rglob("*.py")):
        if "runs" in path.relative_to(root).parts:
            continue
        content = path.read_bytes()
        source_hash.update(path.relative_to(root).as_posix().encode())
        source_hash.update(content)
        target = output / "source" / path.relative_to(root)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    days = DEVELOPMENT + VALIDATION + AUDIT
    plan = {"experiment_kind": "pair_diagnostic", "pair_security_ids": PAIR,
            "pair_selection": "fixed bank pair from prior Aug18 universe",
            "training_dates": DEVELOPMENT, "evaluation_dates": VALIDATION + AUDIT,
            "input_hashes": {day: load_manifest(day)["cache_sha256"] for day in days},
            "source_sha256": source_hash.hexdigest(), "python": platform.python_version(),
            "grid_seconds": 60, "maximum_receipt_quote_age_seconds": 5,
            "modes": ["recent_trade", "receipt_proxy"], "minimum_training_points": 100,
            "z_entry": 2, "counterfactual_delay_seconds": 60, "holding_seconds": 300,
            "combined_entry_notional": 100000, "aggregate_depth_fraction": .01,
            "slippage_each_leg_bps": 1, "cointegration_test": "not available; descriptive diagnostics only",
            "promotion_eligible": False, "role": "fixed-pair diagnostics and two-leg counterfactual, not account replay"}
    write(output / "plan.json", plan)
    points = {mode: {} for mode in plan["modes"]}
    for day in days:
        ticks = load_ticks(day)
        for mode in points:
            samples, counts = synchronize(ticks, receipt_proxy=mode == "receipt_proxy")
            points[mode][day] = samples
            write(output / f"coverage-{day}-{mode}.json", counts)
    models = {}
    for mode, sessions in points.items():
        train = [point for day in DEVELOPMENT for point in sessions[day]]
        model = fit_pair(train)
        models[mode] = model
        training = {"mode": mode, "points": len(train), "model": asdict(model) if model else None,
                    "training_dates": DEVELOPMENT}
        if model:
            training["reversion_diagnostic"] = ar1_diagnostics(train, model)
        write(output / f"frozen-model-{mode}.json", training)
        print(json.dumps({"event": "trained", "mode": mode, "points": len(train),
                          "model": asdict(model) if model else None}), flush=True)
    results = []
    for day in VALIDATION + AUDIT:
        for mode, model in models.items():
            samples = points[mode][day]
            outcomes, economics = two_leg_outcomes(samples, model)
            diagnostic = ar1_diagnostics(samples, model) if model else {"status": "insufficient_training"}
            result = {"date": day, "mode": mode, "diagnostics": diagnostic, "counterfactual": economics}
            results.append(result)
            write(output / f"outcomes-{day}-{mode}.json", outcomes)
            print(json.dumps(result), flush=True)
    write(output / "diagnostics.json", {"experiment_kind": "pair_diagnostic", "results": results,
                                        "account_replays": 0, "promotion_eligible": False})


if __name__ == "__main__":
    main()
