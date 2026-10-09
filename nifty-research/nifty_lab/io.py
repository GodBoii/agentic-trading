from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterator
from datetime import datetime, time, timezone, timedelta
from pathlib import Path
from typing import Any

IST = timezone(timedelta(hours=5, minutes=30))


def number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def capture_time(row: dict) -> datetime:
    stamp = datetime.fromisoformat(row["captured_at_utc"])
    if stamp.tzinfo is None:
        raise ValueError("Capture timestamp must include a timezone")
    return stamp.astimezone(timezone.utc)


def trading_capture(stamp: datetime, market_date: str) -> bool:
    local = stamp.astimezone(IST)
    # This excludes weekends. Special sessions need an explicit exchange-calendar
    # adapter; no such session is silently inferred from a packet's existence.
    return (local.date().isoformat() == market_date and local.weekday() < 5
            and time(9, 15) <= local.time() < time(15, 30))


def read_records(path: Path, audit: dict) -> Iterator[dict]:
    digest = hashlib.sha256()
    stat = path.stat()
    audit.update(path=str(path.resolve()), bytes=stat.st_size, mtime_ns=stat.st_mtime_ns,
                 rows=0, malformed=0, malformed_examples=[])
    with path.open("rb") as handle:
        for line_number, line in enumerate(handle, 1):
            digest.update(line)
            if not line.strip():
                continue
            audit["rows"] += 1
            try:
                row = json.loads(line)
                if not isinstance(row, dict):
                    raise ValueError("Record must be an object")
            except (ValueError, UnicodeDecodeError) as exc:
                audit["malformed"] += 1
                if len(audit["malformed_examples"]) < 5:
                    audit["malformed_examples"].append({"line": line_number, "error": str(exc)})
                continue
            yield row
    audit["sha256"] = digest.hexdigest()
    after = path.stat()
    if (after.st_size, after.st_mtime_ns) != (stat.st_size, stat.st_mtime_ns):
        raise RuntimeError(f"Source changed during read: {path}")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, allow_nan=False, default=str) + "\n", encoding="utf-8")


def source_fingerprint(paths: list[Path]) -> dict[str, dict]:
    return {str(p.resolve()): {"bytes": p.stat().st_size, "mtime_ns": p.stat().st_mtime_ns}
            for p in sorted(paths) if p.is_file()}
