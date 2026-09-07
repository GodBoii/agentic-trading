"""Offline rank timings with mature histories; never connects to a broker."""

import argparse
import json
import platform
import statistics
import subprocess
import sys
import time
import types
from datetime import datetime

from pipeline.stages.activity_ranker import ActivityRanker
from pipeline.stages.live_state import LiveStockState


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", help="Git revision containing the reference live state")
    parser.add_argument("--stocks", type=int, default=3500)
    parser.add_argument("--runs", type=int, default=5)
    args = parser.parse_args()
    state_type = LiveStockState
    if args.baseline:
        source = subprocess.check_output(
            ["git", "show", f"{args.baseline}:python-backend/pipeline/stages/live_state.py"],
            text=True, encoding="utf-8",
        )
        module = types.ModuleType("benchmark_reference")
        sys.modules[module.__name__] = module
        exec(compile(source, "baseline_live_state.py", "exec"), module.__dict__)
        state_type = module.LiveStockState
    now = datetime.fromisoformat("2026-09-07T10:00:00+05:30")
    stamp = now.timestamp()
    baseline = {
        f"{minute // 60:02d}:{minute % 60:02d}": float((minute - 550) * 1000)
        for minute in range(555, 930, 5)
    }
    measurements = []
    for count in (3, 300, 900):
        states = {}
        for index in range(args.stocks):
            state = state_type("NSE_EQ", index + 1, f"S{index}", f"I{index}",
                               median_cumulative_volume=baseline)
            state.latest_price = 100 + index % 100
            state.last_packet_at = state.last_trade_at = now.isoformat()
            state.depth = [{}] * 5
            state.spread_percent = 0.03
            state.cumulative_volume = 100000 + index
            state.price_samples.extend(
                (stamp - count + 1 + i, state.latest_price + (i % 13) * 0.01)
                for i in range(count)
            )
            state.value_samples.extend(
                (stamp - count + 1 + i, float(i * 1000 + index)) for i in range(count)
            )
            states[state.key] = state
        ranker = ActivityRanker()
        ranker.rank(states, now)
        durations = []
        for _ in range(args.runs):
            started = time.perf_counter()
            result = ranker.rank(states, now)
            durations.append((time.perf_counter() - started) * 1000)
        measurements.append({"samples": count, "eligible": result.eligible_count,
                             "median_ms": statistics.median(durations),
                             "max_ms": max(durations), "runs_ms": durations})
    print(json.dumps({"python": platform.python_version(), "platform": platform.platform(),
                      "baseline": args.baseline, "stocks": args.stocks,
                      "measurements": measurements}, indent=2))


if __name__ == "__main__":
    main()
