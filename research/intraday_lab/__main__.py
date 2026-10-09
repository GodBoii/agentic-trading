"""Run frozen offline experiments and preserve reproducible evidence."""

import argparse
from collections import Counter
from dataclasses import asdict, replace
from hashlib import sha256
import json
from pathlib import Path
import platform
import shutil
import time

import pandas as pd
import numpy as np
import pyarrow as pa

from .data import load_session, select_universe
from .domain import ExecutionConfig, PolicyConfig
from .replay import ReplayEngine


ROOT = Path(__file__).resolve().parents[2]


def configurations(*, receipt_proxy: bool = False) -> list[tuple[PolicyConfig, ExecutionConfig]]:
    baseline = PolicyConfig(freshness_mode="receipt_proxy" if receipt_proxy else "recent_trade")
    execution = ExecutionConfig()
    aligned = replace(baseline, name="vwap_aligned_v1", require_vwap_alignment=True)
    bounded = replace(aligned, name="cost_room_v1", require_cost_room=True)
    return [
        (baseline, execution), (aligned, execution), (bounded, execution),
        (replace(bounded, name="cost_room_delay_1000ms"), replace(execution, latency_ms=1000)),
        (replace(bounded, name="cost_room_slippage_3bps"), replace(execution, extra_slippage_bps=3.0)),
        (replace(bounded, name="cost_room_small_account"),
         replace(execution, starting_equity=100_000, maximum_position_value=20_000,
                 risk_per_trade=100, maximum_daily_loss=500)),
    ]


def code_hash() -> str:
    digest = sha256()
    for path in sorted(Path(__file__).parent.glob("*.py")):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dates", nargs="+", required=True)
    parser.add_argument("--universe", type=Path, default=ROOT / "python-backend/results/stage1/2026-08-18/universe.json")
    parser.add_argument("--count", type=int, default=12)
    parser.add_argument("--receipt-proxy", action="store_true",
                        help="sensitivity only: infer quote usability from receipt continuity; never valid live evidence")
    parser.add_argument("--source", type=Path, default=ROOT / "python-backend/results/stage2")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    dates = sorted(set(args.dates))
    lab_root = Path(__file__).resolve().parent
    output = args.output.resolve()
    if not output.is_relative_to(lab_root / "runs"):
        parser.error("output must be inside research/intraday_lab/runs")
    if output.exists():
        parser.error("choose a new run directory; previous experiment evidence cannot be overwritten")
    universe, universe_manifest = select_universe(args.universe, dates, args.count)
    policies = configurations(receipt_proxy=args.receipt_proxy)
    output.mkdir(parents=True)
    digest = code_hash()
    snapshot = output / "engine-source" / "intraday_lab"
    snapshot.mkdir(parents=True)
    for path in sorted(lab_root.glob("*.py")):
        shutil.copyfile(path, snapshot / path.name)
    shutil.copytree(lab_root / "tests", snapshot / "tests", ignore=shutil.ignore_patterns("__pycache__"))
    write_json(output / "experiment-plan.json", {
        "code_sha256": digest, "dates": dates, "universe": universe_manifest,
        "runtime": {"python": platform.python_version(), "platform": platform.platform(),
                    "pandas": pd.__version__, "numpy": np.__version__, "pyarrow": pa.__version__},
        "configs": [{"policy": asdict(p), "execution": asdict(e)} for p, e in policies],
        "data_role": "historical diagnostic; previously inspected dates are not pristine holdout",
        "freshness_role": "unverified receipt-proxy sensitivity" if args.receipt_proxy else "strict recent-trade gate",
        "assumptions": ["no broker connection", "NSE cash only", "next observed executable quote",
                        "all-or-none simulated fills; no passive queue model",
                        "10% of aggregate five-level depth is a sizing proxy, not best-quote capacity",
                        "spread included in bid/ask fills, extra slippage separate",
                        "per-order rounded frozen tariff requires contract-note reconciliation",
                        "each session starts with fixed paper equity; no reinvestment",
                        "strict mode rejects unknown freshness; proxy mode is an explicit sensitivity",
                        "unresolved positions are never fabricated closed"],
    })
    summaries = []
    run_started = time.perf_counter()
    for day in dates:
        started = time.perf_counter()
        ticks, manifest = load_session(args.source, day, [row["security_id"] for row in universe])
        write_json(output / f"input-{day}.json", manifest)
        print(json.dumps({"event": "loaded", "date": day, "rows": len(ticks),
                          "seconds": round(time.perf_counter() - started, 2)}), flush=True)
        for policy, execution in policies:
            started = time.perf_counter()
            engine = ReplayEngine(policy, execution)
            summary = engine.run(ticks)
            summary["market_date"] = day
            summary["replay_seconds"] = round(time.perf_counter() - started, 3)
            summaries.append(summary)
            write_json(output / f"summary-{day}-{policy.name}.json", summary)
            trade_frame = pd.DataFrame([asdict(trade) for trade in engine.trades])
            trade_frame.to_csv(output / f"trades-{day}-{policy.name}.csv", index=False)
            print(json.dumps({"event": "replayed", "date": day, "policy": policy.name,
                              "trades": summary["trades"], "net_pnl": summary["net_pnl"],
                              "complete": summary["complete"], "seconds": summary["replay_seconds"]}), flush=True)
    aggregates = []
    for policy, _ in policies:
        rows = [row for row in summaries if row["policy"]["name"] == policy.name]
        trades = sum(row["trades"] for row in rows)
        net = sum(row["net_pnl"] for row in rows)
        counts = Counter()
        for row in rows:
            counts.update(row["counts"])
        aggregates.append({"policy": policy.name, "sessions": len(rows), "trades": trades,
                           "promotion_eligible": False,
                           "gross_pnl": round(sum(row["gross_pnl"] for row in rows), 2),
                           "fees": round(sum(row["fees"] for row in rows), 2), "net_pnl": round(net, 2),
                           "expectancy": round(net / trades, 2) if trades else None,
                           "incomplete_sessions": sum(not row["complete"] for row in rows),
                           "worst_session_drawdown_marked": max(row["maximum_drawdown_marked"] for row in rows),
                           "counts": dict(counts)})
    if code_hash() != digest:
        raise RuntimeError("Research code changed during the run; results cannot be finalized")
    write_json(output / "aggregate.json", {"results": aggregates, "wall_seconds": time.perf_counter() - run_started})
    pd.DataFrame([{key: value for key, value in row.items() if key != "counts"}
                  for row in aggregates]).to_csv(output / "comparison.csv", index=False)
    print(json.dumps({"event": "complete", "output": str(output)}), flush=True)


if __name__ == "__main__":
    main()
