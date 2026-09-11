"""Read-only chart export from a day's broad one-second tape."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq


def export(root: Path, day: str) -> dict:
    signal_path = root / day / "setup-events.jsonl"
    signals = [json.loads(line) for line in signal_path.read_text().splitlines() if line.strip()]
    keys = {(s["exchange_segment"], int(s["security_id"])) for s in signals if s.get("market_date") == day}
    identifiers = sorted({sid for _, sid in keys})
    frames = []
    manifest = []
    for path in sorted((root / day / "one-second").glob("hour=*/*.parquet")):
        stat = path.stat()
        manifest.append({"path": str(path), "bytes": stat.st_size, "mtime_ns": stat.st_mtime_ns})
        frame = pq.read_table(path, columns=["received_at", "exchange_segment", "security_id", "last_price", "vwap", "day_volume", "spread_percent", "last_trade_age_seconds"],
                              filters=[("security_id", "in", identifiers)]).to_pandas()
        frame = frame[[key in keys for key in zip(frame.exchange_segment, frame.security_id)]]
        frames.append(frame)
    data = pd.concat(frames, ignore_index=True)
    data["t"] = pd.to_datetime(data.received_at, utc=True, format="mixed").array.as_unit("ns").asi8 / 1e9
    data = data[np.isfinite(data.last_price) & (data.last_price > 0)].sort_values("t")
    data["minute"] = (data.t // 60 * 60).astype("int64")
    charts = {}
    for (segment, sid), frame in data.groupby(["exchange_segment", "security_id"], sort=False):
        frame = frame.drop_duplicates("t", keep="last")
        grouped = frame.groupby("minute", sort=True)
        bars = grouped.agg(o=("last_price", "first"), h=("last_price", "max"), l=("last_price", "min"),
                           c=("last_price", "last"), vwap=("vwap", "last"), cum=("day_volume", "last"),
                           first=("t", "min"), last=("t", "max"), samples=("t", "size"))
        bars["volume"] = bars.cum.diff().clip(lower=0).fillna(0)
        bars = bars.reset_index().rename(columns={"minute": "t"})
        rows = json.loads(bars.drop(columns="cum").to_json(orient="records"))
        times, prices = frame.t.to_numpy(), frame.last_price.to_numpy()
        outcomes = {}
        for signal in signals:
            if (signal["exchange_segment"], int(signal["security_id"])) != (segment, sid):
                continue
            t = pd.Timestamp(signal["created_at"]).timestamp()
            start = np.searchsorted(times, t)
            end = np.searchsorted(times, t + 300)
            if start >= len(times) or end >= len(times) or times[start] - t > 10 or times[end] - t - 300 > 10:
                continue
            window = prices[start:end + 1]
            sign = 1 if signal["direction"] == "LONG" else -1
            outcomes[signal["event_id"]] = {
                "return_5m_pct": sign * (float(prices[end]) / signal["price"] - 1) * 100,
                "range_5m_pct": float(window.max() - window.min()) / signal["price"] * 100,
            }
        charts[f"{segment}|{sid}"] = {"bars": rows, "rows": len(frame), "first": float(times[0]),
                                        "last": float(times[-1]), "outcomes": outcomes}
    for item in manifest:
        stat = Path(item["path"]).stat()
        if stat.st_size != item["bytes"] or stat.st_mtime_ns != item["mtime_ns"]:
            raise RuntimeError("Source changed during chart export")
    return {"day": day, "charts": charts, "manifest": manifest,
            "signal_sha256": hashlib.sha256(signal_path.read_bytes()).hexdigest(),
            "interpretation": "One-minute OHLC reconstructed from recorded one-second observations; gaps are not interpolated."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--day", required=True)
    args = parser.parse_args()
    print(json.dumps(export(args.root, args.day), separators=(",", ":"), allow_nan=False))
