"""Read-only Parquet ingestion with venue identity and coverage diagnostics."""

from collections import Counter
from datetime import date
from hashlib import sha256
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.dataset as pads
import pyarrow.parquet as pq

from .domain import Tick


SCHEMA = pa.schema([
    pa.field("received_at", pa.large_string()), pa.field("security_id", pa.int64()),
    pa.field("exchange_segment", pa.large_string()), pa.field("symbol", pa.large_string()),
    *[pa.field(name, pa.float64()) for name in (
        "last_price", "best_bid", "best_ask", "vwap", "bid_quantity_5",
        "ask_quantity_5", "last_trade_age_seconds")],
    pa.field("data_fresh", pa.bool_()), pa.field("connection_warm", pa.bool_()),
])


def select_universe(path: Path, dates: list[str], count: int) -> tuple[list[dict], dict]:
    if count < 1 or not dates:
        raise ValueError("a positive universe size and at least one replay date are required")
    payload = json.loads(path.read_text(encoding="utf-8"))
    source_date = str(payload["summary"]["market_date"])
    if date.fromisoformat(source_date) >= min(date.fromisoformat(day) for day in dates):
        raise ValueError("universe must predate every replay session")
    stocks = [row for row in payload["stocks"] if row.get("exchange_segment") == "NSE_EQ"
              and float((row.get("historical") or {}).get("adv_20_cr") or 0) > 0]
    stocks.sort(key=lambda row: (-float(row["historical"]["adv_20_cr"]), int(row["security_id"])))
    selected = stocks[:count]
    if not selected or len({int(row["security_id"]) for row in selected}) != len(selected):
        raise ValueError("empty or duplicate universe")
    rows = [{"security_id": int(row["security_id"]), "symbol": row["symbol"],
             "exchange_segment": "NSE_EQ", "adv_20_cr": row["historical"]["adv_20_cr"]} for row in selected]
    return rows, {"path": str(path.resolve()), "sha256": sha256(path.read_bytes()).hexdigest(),
                  "source_date": source_date, "selection": "descending prior-universe ADV; ID tie break",
                  "requested_count": count, "selected": rows}


def load_session(root: Path, day: str, security_ids: list[int]) -> tuple[list[Tick], dict]:
    date.fromisoformat(day)
    source = root / day / "one-second"
    paths = sorted(source.rglob("*.parquet"))
    if not paths:
        raise FileNotFoundError(f"No one-second tape for {day} under {source}")
    manifest = []
    for path in paths:
        stat = path.stat()
        manifest.append({"path": str(path.resolve()), "size": stat.st_size,
                         "modified_ns": stat.st_mtime_ns, "rows": pq.read_metadata(path).num_rows})
    dataset = pads.dataset([str(path) for path in paths], format="parquet", schema=SCHEMA)
    table = dataset.to_table(filter=(pads.field("security_id").isin(security_ids)
                                    & (pads.field("exchange_segment") == "NSE_EQ")),
                             columns=SCHEMA.names)
    frame = table.to_pandas()
    diagnostics: Counter[str] = Counter({"selected_rows_read": len(frame)})
    frame["timestamp"] = pd.to_datetime(frame["received_at"], utc=True, errors="coerce", format="mixed")
    valid_times = frame["timestamp"].notna()
    diagnostics["invalid_timestamp"] = int((~valid_times).sum())
    frame = frame[valid_times].copy()
    local = frame["timestamp"].dt.tz_convert("Asia/Kolkata")
    correct_day = local.dt.date == date.fromisoformat(day)
    diagnostics["wrong_session_date"] = int((~correct_day).sum())
    frame = frame[correct_day].copy()
    seconds = ((frame["timestamp"].dt.as_unit("us").astype("int64") // 1_000_000) + 19_800) % 86_400
    regular = (seconds >= 9 * 3600 + 15 * 60) & (seconds < 15 * 3600 + 30 * 60)
    diagnostics["outside_regular_session"] = int((~regular).sum())
    frame = frame[regular].copy()
    frame["at_us"] = frame["timestamp"].dt.as_unit("us").astype("int64")
    frame.sort_values(["at_us", "security_id"], kind="stable", inplace=True)
    duplicate = frame.duplicated(["at_us", "security_id"], keep=False)
    diagnostics["duplicate_identity_rows"] = int(duplicate.sum())
    # Conflicting duplicate observations have no knowable receipt order. Remove all.
    frame = frame[~duplicate].copy()
    core = ["best_bid", "best_ask", "last_price", "bid_quantity_5", "ask_quantity_5"]
    values = frame[core].to_numpy(dtype=float)
    valid_numbers = np.isfinite(values).all(axis=1) & (values >= 0).all(axis=1)
    diagnostics["invalid_core_numbers"] = int((~valid_numbers).sum())
    frame = frame[valid_numbers].copy()
    ticks = []
    coverage = []
    for sid, rows in frame.groupby("security_id", sort=True):
        deltas = rows["at_us"].diff().dropna() / 1_000_000
        coverage.append({"security_id": int(sid), "rows": len(rows),
                         "first_at": rows["received_at"].iloc[0], "last_at": rows["received_at"].iloc[-1],
                         "gaps_over_15s": int((deltas > 15).sum()),
                         "maximum_gap_seconds": float(deltas.max()) if not deltas.empty else None})
    for row in frame.itertuples(index=False):
        vwap = float(row.vwap) if pd.notna(row.vwap) and np.isfinite(row.vwap) and row.vwap > 0 else None
        age = (float(row.last_trade_age_seconds) if pd.notna(row.last_trade_age_seconds)
               and np.isfinite(row.last_trade_age_seconds) and row.last_trade_age_seconds >= 0 else None)
        tick = Tick(int(row.at_us), int(row.security_id), str(row.symbol), float(row.best_bid),
                    float(row.best_ask), float(row.last_price), vwap, float(row.bid_quantity_5),
                    float(row.ask_quantity_5), age,
                    bool(row.data_fresh) if pd.notna(row.data_fresh) else None,
                    bool(row.connection_warm) if pd.notna(row.connection_warm) else None)
        ticks.append(tick)
    diagnostics["rows_retained"] = len(ticks)
    diagnostics["missing_data_fresh_flag"] = int(frame["data_fresh"].isna().sum())
    diagnostics["missing_connection_warm_flag"] = int(frame["connection_warm"].isna().sum())
    diagnostics["missing_trade_age"] = sum(t.trade_age_seconds is None for t in ticks)
    diagnostics["usable_at_5s_age"] = sum(t.usable(5.0) for t in ticks)
    diagnostics["usable_receipt_proxy"] = sum(t.usable(5.0, receipt_proxy=True) for t in ticks)
    known_ages = [t.trade_age_seconds for t in ticks if t.trade_age_seconds is not None]
    age_quantiles = {str(q): float(np.quantile(known_ages, q)) for q in (.5, .95, .99)} if known_ages else {}
    missing = sorted(set(security_ids) - {t.security_id for t in ticks})
    # Fingerprint the exact normalized observations used, not only path metadata.
    normalized_hash = sha256(frame[SCHEMA.names].to_csv(index=False, lineterminator="\n").encode()).hexdigest()
    for item, path in zip(manifest, paths, strict=True):
        stat = path.stat()
        if stat.st_size != item["size"] or stat.st_mtime_ns != item["modified_ns"]:
            raise RuntimeError(f"Source changed while reading: {path}")
    return ticks, {"market_date": day, "source": str(source.resolve()),
                   "source_files": manifest, "normalized_tape_sha256": normalized_hash,
                   "diagnostics": dict(diagnostics), "missing_security_ids": missing,
                   "coverage": coverage, "trade_age_quantiles_seconds": age_quantiles,
                   "capture_semantics": "one received observation per second; not full tick tape"}
