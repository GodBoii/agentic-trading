"""Prepare one fixed cohort once, then let independent tracks replay it."""

from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from research.intraday_lab.data import load_session, select_universe
from research.intraday_lab.domain import Tick


ROOT = Path(__file__).resolve().parents[2]
CACHE = Path(__file__).resolve().parent / "cache"
DATES = ("2026-08-19", "2026-08-20", "2026-08-21", "2026-08-24",
         "2026-08-25", "2026-08-31", "2026-09-01")
DEVELOPMENT = DATES[:3]
VALIDATION = DATES[3:5]
AUDIT = DATES[5:]


def phase(day: str) -> str:
    if day in DEVELOPMENT:
        return "development"
    if day in VALIDATION:
        return "validation_diagnostic"
    if day in AUDIT:
        return "historical_audit"
    raise ValueError("date has no preregistered phase")


def file_hash(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def prepare(cache: Path = CACHE) -> None:
    cache.mkdir(parents=True, exist_ok=True)
    universe, manifest = select_universe(
        ROOT / "python-backend/results/stage1/2026-08-18/universe.json", list(DATES), 12)
    universe_path = cache / "universe.json"
    if universe_path.exists():
        if json.loads(universe_path.read_text()) != manifest:
            raise ValueError("fixed universe changed; use a new cohort cache")
    else:
        universe_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    for day in DATES:
        tape_path = cache / f"{day}.parquet"
        manifest_path = cache / f"{day}.json"
        if tape_path.exists() or manifest_path.exists():
            if not tape_path.exists() or not manifest_path.exists():
                raise ValueError(f"incomplete cache for {day}")
            load_manifest(day, cache)
            print(json.dumps({"event": "cache_verified", "date": day}), flush=True)
            continue
        ticks, report = load_session(ROOT / "python-backend/results/stage2", day,
                                     [r["security_id"] for r in universe])
        tmp = tape_path.with_suffix(".pending")
        pq.write_table(pa.Table.from_pylist([asdict(tick) for tick in ticks]), tmp, compression="zstd")
        tmp.replace(tape_path)
        report["cache_sha256"] = file_hash(tape_path)
        report["phase"] = phase(day)
        manifest_path.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False), encoding="utf-8")
        print(json.dumps({"event": "cache_prepared", "date": day, "rows": len(ticks)}), flush=True)


def load_manifest(day: str, cache: Path = CACHE) -> dict:
    if day not in DATES:
        raise ValueError("only preregistered dates can be loaded")
    report = json.loads((cache / f"{day}.json").read_text(encoding="utf-8"))
    if file_hash(cache / f"{day}.parquet") != report["cache_sha256"]:
        raise ValueError(f"normalized cache changed for {day}")
    return report


def load_ticks(day: str, cache: Path = CACHE) -> list[Tick]:
    report = load_manifest(day, cache)
    rows = pq.ParquetFile(cache / f"{day}.parquet").read().to_pylist()
    ticks = [Tick(**row) for row in rows]
    if len(ticks) != report["diagnostics"]["rows_retained"]:
        raise ValueError("cache row count disagrees with manifest")
    if any(a.at_us > b.at_us for a, b in zip(ticks, ticks[1:])):
        raise ValueError("cache observation order changed")
    return ticks


if __name__ == "__main__":
    prepare()
