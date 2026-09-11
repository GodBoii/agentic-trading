"""Reduce immutable broad tapes to minute observations for local research.

Writes base64 Parquet, one JSON line per day, to stdout. No broker calls or
remote files are changed. Expensive analysis belongs on the receiving machine.
"""

import argparse
import base64
import json
from pathlib import Path
import sys

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq


COLUMNS = ["received_at", "exchange_segment", "security_id", "last_price", "day_volume", "vwap",
           "activity_rank", "spread_percent", "traded_value_5m", "realized_volatility_percent",
           "last_trade_age_seconds", "best_bid", "best_ask", "relative_volume", "volume_acceleration",
           "trend_efficiency", "return_5m_percent", "depth_imbalance_median_30s"]
KEYS = ["exchange_segment", "security_id", "minute"]


def reduce_day(root: Path, day: str) -> dict:
    chunks, manifest = [], []
    for path in sorted((root / day / "one-second").glob("hour=*/*.parquet")):
        stat = path.stat()
        manifest.append({"name": str(path), "bytes": stat.st_size, "mtime_ns": stat.st_mtime_ns})
        frame = pq.read_table(path, columns=COLUMNS, use_threads=False).to_pandas(use_threads=False)
        # ISO timestamps in this recorder always carry the same session offset.
        frame = frame.sort_values("received_at")
        frame["minute"] = frame.received_at.str.slice(0, 16)
        groups = frame.groupby(KEYS, sort=False)
        last = groups.tail(1).set_index(KEYS)
        last["open"] = groups.last_price.first()
        last["high"] = groups.last_price.max()
        last["low"] = groups.last_price.min()
        last["first_at"] = groups.received_at.first()
        last["samples"] = groups.last_price.count()
        chunks.append(last.reset_index())
    if not chunks:
        raise FileNotFoundError(f"No broad tape for {day}")
    data = pd.concat(chunks, ignore_index=True).sort_values("received_at")
    groups = data.groupby(KEYS, sort=False)
    last = groups.tail(1).set_index(KEYS)
    # Overlapping shards can finish in a different order than they started.
    opening = data.sort_values("first_at").groupby(KEYS, sort=False).first()
    last["open"] = opening.open
    last["high"] = groups.high.max()
    last["low"] = groups.low.min()
    last["first_at"] = opening.first_at
    last["samples"] = groups.samples.sum()
    for item in manifest:
        stat = Path(item["name"]).stat()
        if stat.st_size != item["bytes"] or stat.st_mtime_ns != item["mtime_ns"]:
            raise RuntimeError("Tape changed during export")
    buffer = pa.BufferOutputStream()
    pq.write_table(pa.Table.from_pandas(last.reset_index(), preserve_index=False), buffer, compression="zstd")
    return {"day": day, "rows": len(last), "manifest": manifest,
            "parquet": base64.b64encode(buffer.getvalue().to_pybytes()).decode("ascii")}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--days", nargs="+", required=True)
    args = parser.parse_args()
    for day in args.days:
        print(json.dumps(reduce_day(args.root, day), separators=(",", ":")), flush=True)
        print(f"Exported {day}", file=sys.stderr, flush=True)
