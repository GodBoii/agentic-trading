from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .config import ResearchConfig, default_sources
from .experiment import walk_forward
from .ingest import prepare_session
from .io import source_fingerprint, write_json

LAB = Path(__file__).resolve().parents[1]
LOG = logging.getLogger("nifty_lab")


def prepare(sources: list[Path], output: Path, config: ResearchConfig, rebuild: bool) -> dict:
    if any(output.resolve().is_relative_to(source.resolve()) or source.resolve().is_relative_to(output.resolve())
           for source in sources):
        raise ValueError("Source and output directories must not overlap")
    sessions = {}
    for source in sources:
        if not source.is_dir(): raise FileNotFoundError(source)
        for directory in sorted(source.iterdir()):
            if directory.is_dir() and (directory / "full_market.ndjson").exists():
                if directory.name in sessions:
                    raise ValueError(f"Duplicate date across archives: {directory.name}")
                sessions[directory.name] = directory
    code_digest = hashlib.sha256()
    for name in ("config.py", "io.py", "ingest.py"):
        code_digest.update((LAB / "nifty_lab" / name).read_bytes())
    code_hash = code_digest.hexdigest()
    reports = []
    source_files = [file for directory in sessions.values() for file in directory.glob("*.ndjson")]
    before = source_fingerprint(source_files)
    for day, directory in sorted(sessions.items()):
        destination = output / "sessions" / day; cache = destination / "audit.json"
        files = [directory / name for name in ("full_market.ndjson", "depth_200.ndjson", "options_feed.ndjson", "cvd_series.ndjson")]
        key = {"sources": source_fingerprint(files), "config": config.to_dict(), "prepare_code_sha256": code_hash}
        if not rebuild and cache.exists():
            report = json.loads(cache.read_text(encoding="utf-8"))
            if report.get("cache_key") == key and report.get("outputs") == source_fingerprint(list(destination.glob("*.parquet"))):
                LOG.info("Using verified cache for %s", day); reports.append(report); continue
        LOG.info("Reading %s, %.2f GB", day, sum(p.stat().st_size for p in files if p.exists()) / 1e9)
        # Remove only derived caches owned by this directory before regeneration.
        for name in ("features.parquet", "options.parquet"):
            target = destination / name
            if target.exists(): target.unlink()
        report = prepare_session(directory, destination, config)
        report["cache_key"] = key
        report["outputs"] = source_fingerprint(list(destination.glob("*.parquet")))
        write_json(cache, report); reports.append(report)
        LOG.info("Prepared %s: %s labelled minutes", day, report["labelled_rows"])
    after = source_fingerprint(source_files)
    if before != after: raise RuntimeError("Source archive changed during preparation")
    paths = sorted((output / "sessions").glob("*/features.parquet"))
    valid_days = {report["date"] for report in reports if report["feature_rows"]}
    frames = [pd.read_parquet(path) for path in paths if path.parent.name in valid_days]
    if not frames: raise ValueError("No valid regular-session features")
    frame = pd.concat(frames, ignore_index=True).sort_values("decision_at").reset_index(drop=True)
    frame.to_parquet(output / "features.parquet", index=False)
    manifest = {"created_at_utc": datetime.now(timezone.utc).isoformat(), "config": config.to_dict(),
                "prepare_code_sha256": code_hash, "sources_unchanged": before == after,
                "sessions": reports, "feature_rows": len(frame),
                "labelled_rows": int(frame["target_bps"].notna().sum())}
    write_json(output / "manifest.json", manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Offline Nifty research; no broker access")
    parser.add_argument("command", choices=["prepare", "evaluate", "replay", "report", "run"])
    parser.add_argument("--workspace", type=Path, default=LAB.parent)
    parser.add_argument("--source", type=Path, action="append")
    parser.add_argument("--output", type=Path, default=LAB / "artifacts" / "v1")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--rebuild", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to((LAB / "artifacts").resolve()):
        parser.error("Output must be inside nifty-research/artifacts to protect source archives")
    config = ResearchConfig(**json.loads(args.config.read_text(encoding="utf-8"))) if args.config else ResearchConfig()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
    output.mkdir(parents=True, exist_ok=True)
    if args.command in {"prepare", "run"}:
        prepare(args.source or default_sources(args.workspace.resolve()), output, config, args.rebuild)
    if args.command in {"evaluate", "run"}:
        manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
        if manifest["config"] != config.to_dict(): raise ValueError("Configuration differs from prepared archive; prepare again")
        predictions, summary = walk_forward(pd.read_parquet(output / "features.parquet"), config)
        write_json(output / "forecast-results.json", summary)
        if not predictions.empty: predictions.to_parquet(output / "predictions.parquet", index=False)
        LOG.info("Forecast status %s; scored rows %s", summary["status"], summary.get("scored_rows", 0))
    if args.command in {"replay", "run"}:
        from .replay import replay
        replay(output, config)
    if args.command in {"report", "run"}:
        from .report import build_report
        build_report(output)


if __name__ == "__main__":
    main()
