"""Audit raw trade timestamps without confusing them with quote event times."""

import argparse
from collections import Counter
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq


def audit_raw(root: Path, day: str, security_ids: set[int], limit: int) -> dict:
    if limit < 1:
        raise ValueError("positive sample limit required")
    ages = []
    types: Counter[str] = Counter()
    counts: Counter[str] = Counter()
    examples = []
    manifest = []
    digest = sha256()
    for path in sorted((root / day / "raw-depth").rglob("*.parquet")):
        stat = path.stat()
        manifest.append({"path": str(path.resolve()), "size": stat.st_size, "modified_ns": stat.st_mtime_ns})
        parquet = pq.ParquetFile(path)
        required = {"received_at", "security_id", "packet_json"}
        if not required.issubset(parquet.schema_arrow.names):
            raise ValueError(f"Raw capture missing required columns: {path}")
        columns = [name for name in ("received_at", "security_id", "packet_json", "capture_scope")
                   if name in parquet.schema_arrow.names]
        for batch in parquet.iter_batches(columns=columns):
            for row in batch.to_pylist():
                if int(row["security_id"]) not in security_ids:
                    continue
                packet = json.loads(row["packet_json"])
                digest.update(json.dumps(row, sort_keys=True, separators=(",", ":")).encode())
                counts["selected_packets"] += 1
                counts[f"scope_{row.get('capture_scope') or 'unknown'}"] += 1
                types[str(packet.get("type"))] += 1
                raw = packet.get("LTT")
                if raw is None:
                    counts["missing_LTT"] += 1
                else:
                    try:
                        at = datetime.fromisoformat(row["received_at"])
                        if at.tzinfo is None:
                            raise ValueError("receipt timestamp has no timezone")
                        time_part = datetime.strptime(str(raw), "%H:%M:%S").time()
                        trade_at = at.replace(hour=time_part.hour, minute=time_part.minute,
                                              second=time_part.second, microsecond=0)
                        age = (at - trade_at).total_seconds()
                        ages.append(age)
                        counts["negative_trade_age"] += age < 0
                        counts["trade_age_over_5s"] += age > 5
                        if len(examples) < 8:
                            examples.append({"received_at": row["received_at"], "security_id": row["security_id"],
                                             "LTT": raw, "signed_trade_age_seconds": age})
                    except ValueError:
                        counts["unparseable_LTT_or_receipt_time"] += 1
                if counts["selected_packets"] >= limit:
                    break
            if counts["selected_packets"] >= limit:
                break
        if path.stat().st_mtime_ns != stat.st_mtime_ns or path.stat().st_size != stat.st_size:
            raise RuntimeError(f"Raw source changed during audit: {path}")
        if counts["selected_packets"] >= limit:
            break
    return {"date": day, "counts": dict(counts), "types": dict(types), "sample_limit": limit,
            "trade_age_quantiles_seconds": {str(q): float(np.quantile(ages, q)) for q in (.5, .95, .99)} if ages else {},
            "sample_sha256": digest.hexdigest(), "source_files_read": manifest, "examples": examples,
            "sampling": "first selected packets in sorted file order; not a representative full-session sample",
            "interpretation": "receipt minus raw last-trade time; not quote event age or measured network latency",
            "missing_raw_data": not manifest}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--dates", nargs="+", required=True)
    parser.add_argument("--limit", type=int, default=20_000)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[2] / "python-backend/results/stage2")
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(Path(__file__).resolve().parent / "runs") or output.exists():
        parser.error("output must be a new file under research/intraday_lab/runs")
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    ids = {int(item["security_id"]) for item in plan["universe"]["selected"]}
    reports = [audit_raw(args.source, day, ids, args.limit) for day in args.dates]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(reports, indent=2, sort_keys=True, allow_nan=False), encoding="utf-8")
    print(json.dumps([{"date": row["date"], "counts": row["counts"],
                       "age_quantiles": row["trade_age_quantiles_seconds"]} for row in reports]), flush=True)


if __name__ == "__main__":
    main()
