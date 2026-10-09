"""Reconstruct persisted density models and repeat one recorded session."""

from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path

import pandas as pd

from research.common.data import load_ticks
from research.common.runner import CheckedPolicy
from research.intraday_lab.domain import ExecutionConfig, PolicyConfig
from research.intraday_lab.replay import ReplayEngine
from .strategy import RegimePolicy, model_from_report


def main() -> None:
    folder = Path(__file__).parent / "runs" / "initial-v1"
    day = "2026-08-24"
    plan = json.loads((folder / "plan.json").read_text(encoding="utf-8"))
    target = folder / f"repeatability-{day}.json"
    if target.exists():
        raise ValueError("repeatability evidence exists; do not overwrite")
    ticks = load_ticks(day)
    checks = []
    for spec in plan["variants"]:
        cfg = PolicyConfig(**spec["policy"])
        report = spec["parameters"]["frozen_models"][cfg.freshness_mode]
        model = model_from_report(report)
        engine = ReplayEngine(cfg, ExecutionConfig(**spec["execution"]))
        engine.policy = CheckedPolicy(RegimePolicy(cfg, model, tuple(report["training_dates"])))
        actual = engine.run(ticks)
        stem = f"{day}-{spec['name']}-{spec['mode']}"
        expected = json.loads((folder / f"summary-{stem}.json").read_text(encoding="utf-8"))
        encoded = pd.DataFrame([asdict(trade) for trade in engine.trades]).to_csv(index=False).encode()
        original_hash = sha256((folder / f"trades-{stem}.csv").read_bytes()).hexdigest()
        repeat_hash = sha256(encoded).hexdigest()
        checks.append({"variant": spec["name"], "mode": spec["mode"],
                       "accounting_matches": all(expected[key] == value for key, value in actual.items()),
                       "trade_bytes_match": original_hash == repeat_hash,
                       "original_trade_sha256": original_hash, "repeat_trade_sha256": repeat_hash,
                       "trades": actual["trades"]})
    report = {"date": day, "checks": checks,
              "all_match": all(c["accounting_matches"] and c["trade_bytes_match"] for c in checks)}
    target.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    if not report["all_match"]:
        raise RuntimeError("repeatability failed; inspect evidence")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
