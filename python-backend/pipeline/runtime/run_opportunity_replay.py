from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Iterable

import pandas as pd

from pipeline.config import PipelineConfig
from pipeline.research.opportunity_replay import replay_opportunities
from pipeline.services.storage_service import StorageService


def recorded_rows(paths: Iterable[Path], bucket_seconds: int) -> Iterable[Dict[str, Any]]:
    for path in paths:
        frame = pd.read_parquet(
            path,
            columns=["received_at", "security_id", "packet_json"],
        )
        if bucket_seconds > 1:
            timestamps = pd.to_datetime(frame["received_at"], errors="coerce", utc=True)
            frame["_bucket"] = timestamps.dt.floor(f"{bucket_seconds}s")
            frame = frame.drop_duplicates(["security_id", "_bucket"], keep="last")
        for row in frame.itertuples(index=False):
            yield {"received_at": row.received_at, "packet_json": row.packet_json}


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay the production opportunity detector.")
    parser.add_argument("--date", required=True, help="Recorded market date in YYYY-MM-DD form.")
    parser.add_argument("--bucket-seconds", type=int, default=5)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    config = PipelineConfig()
    universe_path = config.stage1_results_dir / args.date / "universe.json"
    universe = json.loads(universe_path.read_text(encoding="utf-8"))
    raw_root = config.stage2_results_dir / args.date / "raw-depth"
    paths = sorted(
        raw_root.glob("hour=*/*.parquet"),
        key=lambda path: int(path.stem.split("-")[1]),
    )
    if not paths:
        raise FileNotFoundError(f"No raw Stage 2 packets found for {args.date}.")
    report = replay_opportunities(
        stocks=universe.get("stocks") or [],
        rows=recorded_rows(paths, max(1, args.bucket_seconds)),
        config=config,
    )
    output = args.output or (
        config.results_dir / "research" / "opportunity-replay" / f"{args.date}.json"
    )
    StorageService.save_snapshot(output, report)
    print(
        f"Replay complete: packets={report['packets']:,} events={report['event_count']:,} "
        f"elapsed={report['elapsed_seconds']:.2f}s output={output}",
        flush=True,
    )


if __name__ == "__main__":
    main()
