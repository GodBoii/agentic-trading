"""Compare attention lists on recorded broad one-second data, without broker calls.

Decisions use the last observation before a five-minute boundary. Future prices
are labels only. This measures discovery, not fillable trades or trading profit.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq


KEYS = ["exchange_segment", "security_id"]
FEATURES = ["activity_rank", "spread_percent", "traded_value_5m", "realized_volatility_percent",
            "last_trade_age_seconds", "best_bid", "best_ask"]
COLUMNS = [*KEYS, "received_at", "last_price", *FEATURES]


def read_minutes(directory: Path) -> tuple[pd.DataFrame, list[dict]]:
    chunks = []
    manifest = []
    for path in sorted(directory.glob("hour=*/*.parquet")):
        stat = path.stat()
        manifest.append({"path": str(path), "bytes": stat.st_size, "mtime_ns": stat.st_mtime_ns})
        frame = pq.read_table(path, columns=COLUMNS).to_pandas()
        stamp = pd.to_datetime(frame.pop("received_at"), utc=True, errors="coerce", format="mixed")
        frame["timestamp"] = stamp.array.as_unit("ns").asi8 / 1e9
        frame = frame[stamp.notna() & np.isfinite(frame.last_price) & (frame.last_price > 0)].copy()
        frame["minute"] = (frame.timestamp // 60).astype("int64")
        frame = frame.sort_values("timestamp")
        grouped = frame.groupby([*KEYS, "minute"], sort=False)
        last = grouped.tail(1).set_index([*KEYS, "minute"])
        last["high"] = grouped.last_price.max()
        last["low"] = grouped.last_price.min()
        chunks.append(last.reset_index())
    if not chunks:
        raise FileNotFoundError(f"No one-second files in {directory}")
    frame = pd.concat(chunks, ignore_index=True).sort_values("timestamp")
    grouped = frame.groupby([*KEYS, "minute"], sort=False)
    last = grouped.tail(1).set_index([*KEYS, "minute"])
    last["high"] = grouped.high.max()
    last["low"] = grouped.low.min()
    return last.reset_index(), manifest


def label_minutes(frame: pd.DataFrame) -> pd.DataFrame:
    labelled = []
    for key, stock in frame.groupby(KEYS, sort=False):
        stock = stock.set_index("minute").sort_index()
        stock = stock.reindex(range(int(stock.index.min()), int(stock.index.max()) + 1))
        future = stock.shift(-1).iloc[::-1]
        high = future.high.rolling(5, min_periods=5).max().iloc[::-1]
        low = future.low.rolling(5, min_periods=5).min().iloc[::-1]
        decision = (stock.index.to_numpy() + 1) * 60
        stock["decision_at"] = decision
        stock["range_pct"] = (high - low) / stock.last_price * 100
        stock["return_pct"] = (stock.last_price.shift(-5) / stock.last_price - 1) * 100
        stock["label_available"] = high.notna() & low.notna() & (
            stock.timestamp.shift(-5) >= decision + 300 - 10
        )
        stock["entry_fresh"] = (decision - stock.timestamp).between(0, 10)
        for column, value in zip(KEYS, key):
            stock[column] = value
        labelled.append(stock.reset_index(names="minute"))
    return pd.concat(labelled, ignore_index=True)


def compare(frame: pd.DataFrame) -> dict:
    frame = label_minutes(frame)
    clock = pd.to_datetime(frame.decision_at, unit="s", utc=True).dt.tz_convert("Asia/Kolkata")
    minute_of_day = clock.dt.hour * 60 + clock.dt.minute
    frame = frame[(minute_of_day >= 560) & (minute_of_day <= 895) & (clock.dt.minute % 5 == 0)]
    # Eligibility uses only information available at the decision boundary.
    eligible = frame[frame.entry_fresh & frame.spread_percent.between(0, 0.2)
                     & frame.last_trade_age_seconds.between(0, 90)
                     & (frame.best_bid > 0) & (frame.best_ask >= frame.best_bid)].copy()
    counts = eligible.groupby("decision_at").security_id.count()
    eligible[["traded_value_5m", "realized_volatility_percent"]] = eligible[
        ["traded_value_5m", "realized_volatility_percent"]
    ].fillna(0)
    eligible["recent_score"] = eligible.groupby("decision_at")[
        ["traded_value_5m", "realized_volatility_percent"]
    ].rank(pct=True).min(axis=1)
    recorded = eligible[eligible.activity_rank.notna()].sort_values(["decision_at", "activity_rank", *KEYS])
    recent = eligible.sort_values(["decision_at", "recent_score", "traded_value_5m", *KEYS],
                                  ascending=[True, False, False, True, True])
    populations = {"eligible_control": eligible}
    for size in (10, 30, 60):
        populations[f"recorded_top{size}"] = recorded[recorded.activity_rank <= size]
        populations[f"recent_top{size}"] = recent.groupby("decision_at", sort=False).head(size)
    opportunities = eligible[eligible.label_available & (eligible.range_pct >= 0.5)]
    rows = {}
    for name, selected in populations.items():
        measured = selected[selected.label_available]
        captured = int((measured.range_pct >= 0.5).sum())
        rows[name] = {
            "selected": len(selected), "labelled": len(measured),
            "unique_stocks": len(selected[KEYS].drop_duplicates()),
            "median_next_5m_range_pct": float(measured.range_pct.median()) if len(measured) else None,
            "median_absolute_5m_return_pct": float(measured.return_pct.abs().median()) if len(measured) else None,
            "median_spread_pct": float(selected.spread_percent.median()) if len(selected) else None,
            "median_traded_value_5m": float(selected.traded_value_5m.median()) if len(selected) else None,
            "range_at_least_half_percent": captured,
            "capture_fraction": captured / len(opportunities) if len(opportunities) else None,
            "fraction_selected_with_range": captured / len(measured) if len(measured) else None,
        }
    return {"decision_times": len(counts), "median_eligible": float(counts.median()) if len(counts) else None,
            "eligible_labelled_opportunities": len(opportunities), "policies": rows}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True, help="Stage 2 result directory")
    parser.add_argument("--dates", nargs="+", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    reports = {}
    for day in args.dates:
        frame, manifest = read_minutes(args.root / day / "one-second")
        reports[day] = {**compare(frame), "input_files": len(manifest), "manifest": manifest}
        for item in manifest:
            stat = Path(item["path"]).stat()
            if stat.st_size != item["bytes"] or stat.st_mtime_ns != item["mtime_ns"]:
                raise RuntimeError(f"Input changed during comparison: {item['path']}")
    report = {"schema_version": 1, "decision_interval_seconds": 300, "horizon_seconds": 300,
              "entry_max_age_seconds": 10, "label_requires_five_observed_minutes": True,
              "interpretation": "Descriptive attention selection, not executable returns; previously inspected days are not holdouts.",
              "dates": reports}
    serialized = json.dumps(report, indent=2, allow_nan=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized + "\n", encoding="utf-8")
    else:
        print(serialized)


if __name__ == "__main__":
    main()
