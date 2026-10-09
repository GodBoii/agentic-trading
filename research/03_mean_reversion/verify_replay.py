"""Reconstruct persisted hypotheses and check actual-tape determinism."""

import argparse
from dataclasses import asdict
from hashlib import sha256
from importlib import import_module
import json
from pathlib import Path

import pandas as pd

from research.common.data import DATES, ROOT, load_ticks
from research.common.runner import CheckedPolicy
from research.intraday_lab.domain import ExecutionConfig, PolicyConfig
from research.intraday_lab.replay import ReplayEngine


def verify(track: str, day: str) -> dict:
    folder = ROOT / "research" / track / "runs" / "initial-v1"
    plan = json.loads((folder / "plan.json").read_text(encoding="utf-8"))
    module = import_module(f"research.{track}.strategy")
    factory_names = {"03_mean_reversion": "ReversionPolicy",
                     "07_indicator_patterns": "IndicatorPolicy",
                     "10_vwap_pullback": "VWAPPullbackPolicy"}
    factory = getattr(module, factory_names[track])
    ticks = load_ticks(day)
    results = []
    for item in plan["variants"]:
        if item["mode"] != "receipt_proxy":
            continue
        engine = ReplayEngine(PolicyConfig(**item["policy"]), ExecutionConfig(**item["execution"]))
        engine.policy = CheckedPolicy(factory(engine.policy_config))
        actual = engine.run(ticks)
        stem = f"{day}-{item['name']}-{item['mode']}"
        expected = json.loads((folder / f"summary-{stem}.json").read_text(encoding="utf-8"))
        accounting_matches = all(expected[key] == value for key, value in actual.items())
        trades = pd.DataFrame([asdict(trade) for trade in engine.trades]).to_csv(index=False).encode()
        expected_digest = sha256((folder / f"trades-{stem}.csv").read_bytes()).hexdigest()
        actual_digest = sha256(trades).hexdigest()
        results.append({"variant": item["name"], "mode": item["mode"],
                        "accounting_matches": accounting_matches,
                        "trade_bytes_match": actual_digest == expected_digest,
                        "original_trade_sha256": expected_digest,
                        "repeat_trade_sha256": actual_digest,
                        "trades": actual["trades"]})
    report = {"track": track, "date": day, "source_plan_sha256": sha256((folder / "plan.json").read_bytes()).hexdigest(),
              "results": results, "all_match": all(r["accounting_matches"] and r["trade_bytes_match"] for r in results)}
    target = folder / f"repeatability-{day}.json"
    if target.exists():
        raise ValueError("repeatability evidence already exists; do not overwrite")
    target.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False), encoding="utf-8")
    if not report["all_match"]:
        raise RuntimeError(f"replay comparison failed; inspect {target}")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--track", choices=("03_mean_reversion", "07_indicator_patterns", "10_vwap_pullback"), default="03_mean_reversion")
    parser.add_argument("--day", choices=DATES, default="2026-08-24")
    args = parser.parse_args()
    print(json.dumps(verify(args.track, args.day), indent=2))


if __name__ == "__main__":
    main()
