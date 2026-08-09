from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from pipeline.research.indicator_event_replay import (
    load_recorded_minutes,
    replay_indicator_events,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay indicator events on saved Stage 2 observations.")
    parser.add_argument("--market-date", required=True)
    parser.add_argument("--results-root", default="results")
    parser.add_argument("--output")
    args = parser.parse_args()

    results_root = Path(args.results_root)
    input_root = results_root / "stage2" / args.market_date / "one-second"
    if not input_root.exists():
        raise FileNotFoundError(f"Recorded one-second input not found: {input_root}")
    output = (
        Path(args.output)
        if args.output
        else results_root / "stage2-research" / f"indicator-event-replay-{args.market_date}.json"
    )
    print(f"Loading read-only observations from {input_root} ...", flush=True)
    minutes = load_recorded_minutes(input_root)
    print(f"Replaying {len(minutes):,} completed stock-minute rows ...", flush=True)
    report = replay_indicator_events(minutes)
    report["market_date"] = args.market_date
    report["created_at"] = datetime.now().astimezone().isoformat()
    report["input_root"] = str(input_root)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(report, indent=2), encoding="utf-8")
    temporary.replace(output)
    compact = {key: value for key, value in report.items() if key != "aggregates"}
    print(json.dumps(compact, indent=2), flush=True)
    print(f"Saved {output}", flush=True)


if __name__ == "__main__":
    main()
