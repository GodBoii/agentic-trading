"""Read-only exact-receipt volume attachment; never mutate the shared Tick schema."""

from collections import Counter
from hashlib import sha256
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.dataset as ds

from research.common.data import ROOT, load_manifest
from research.intraday_lab.domain import Tick


def load_volume(day: str, ticks: list[Tick]) -> tuple[dict[tuple[int, int], float], dict]:
    paths = sorted((ROOT / "python-backend/results/stage2" / day / "one-second").rglob("*.parquet"))
    ids = sorted({t.security_id for t in ticks})
    schema = pa.schema([pa.field("received_at", pa.large_string()), pa.field("security_id", pa.int64()),
                        pa.field("exchange_segment", pa.large_string()), pa.field("day_volume", pa.float64())])
    table = ds.dataset([str(path) for path in paths], format="parquet", schema=schema).to_table(
        filter=ds.field("security_id").isin(ids) & (ds.field("exchange_segment") == "NSE_EQ"))
    frame = table.to_pandas()
    times = pd.to_datetime(frame.received_at, utc=True, errors="coerce", format="mixed")
    frame = frame[times.notna()].copy()
    frame["at_us"] = times[times.notna()].dt.as_unit("us").astype("int64")
    frame.sort_values(["at_us", "security_id"], inplace=True, kind="stable")
    duplicate = frame.duplicated(["at_us", "security_id"], keep=False)
    frame = frame[~duplicate]
    identities = {(t.security_id, t.at_us) for t in ticks}
    lookup = {}
    counts = Counter()
    for row in frame.itertuples(index=False):
        key = (int(row.security_id), int(row.at_us))
        if key not in identities:
            continue
        value = row.day_volume
        if pd.isna(value) or value < 0 or not float(value) < float("inf"):
            counts["invalid_volume"] += 1
            continue
        lookup[key] = float(value)
    report = {"date": day, "matched_volume_rows": len(lookup), "ticks": len(ticks),
              "missing_volume_rows": len(ticks) - len(lookup), "counts": dict(counts),
              "normalization_sha256": sha256(frame.to_csv(index=False).encode()).hexdigest(),
              "quote_cache_sha256": load_manifest(day)["cache_sha256"],
              "volume_clock": "day_volume observed at exact received_at; source trade/volume event time unknown",
              "source_files": [str(p.resolve()) for p in paths]}
    return lookup, report
