"""Check whether saved minute candles support full-session paper-rule tests."""

from collections import Counter
from hashlib import sha256
import json
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    rows: list[dict] = []
    totals: Counter[str] = Counter()
    eligible: list[dict] = []
    paths = sorted((ROOT / "context/stocks-data/NSE").glob("*/intraday_1m/*.parquet"))
    for path in paths:
        frame = pd.read_parquet(path)
        needed = {"timestamp", "open", "high", "low", "close", "volume"}
        if not needed.issubset(frame):
            rows.append({"path": str(path.relative_to(ROOT)), "missing_columns": sorted(needed - set(frame))})
            totals["files_missing_columns"] += 1
            continue
        clock = pd.to_datetime(frame.timestamp, unit="s", utc=True).dt.tz_convert("Asia/Kolkata")
        frame["date"] = clock.dt.strftime("%Y-%m-%d")
        frame["minute"] = clock.dt.hour * 60 + clock.dt.minute
        market = frame[frame.minute.between(555, 929)].copy()
        values = market[["open", "high", "low", "close", "volume"]].to_numpy()
        market["valid"] = (
            np.isfinite(values).all(axis=1)
            & (values[:, :4] > 0).all(axis=1)
            & (values[:, 4] >= 0)
            & (market.high >= market[["open", "close", "low"]].max(axis=1))
            & (market.low <= market[["open", "close", "high"]].min(axis=1))
        )
        full = 0
        for day, group in market.groupby("date", sort=True):
            totals["instrument_days"] += 1
            if len(group) == 375 and group.minute.nunique() == 375 and group.valid.all() and group.volume.sum() > 0:
                eligible.append({"security_id": int(path.parent.parent.name), "date": day, "path": str(path.relative_to(ROOT))})
                full += 1
                totals["complete_375_bar_instrument_days"] += 1
            else:
                totals["incomplete_or_invalid_instrument_days"] += 1
        rows.append({
            "path": str(path.relative_to(ROOT)),
            "sha256": sha256(path.read_bytes()).hexdigest(),
            "rows": len(frame), "regular_rows": len(market),
            "first": clock.min().isoformat(), "last": clock.max().isoformat(),
            "dates": int(market.date.nunique()), "complete_375_bar_dates": full,
            "invalid_regular_rows": int((~market.valid).sum()),
            "duplicate_minutes": int(market.duplicated(["date", "minute"]).sum()),
            "nonzero_timestamp_seconds": int((clock.dt.second != 0).sum()),
        })
        totals["files"] += 1
        totals["rows"] += len(frame)
    result = {"totals": dict(totals), "files": rows, "eligible": eligible,
              "rule": "Exactly 375 unique regular minute buckets 09:15..15:29 IST, positive finite consistent OHLC, nonnegative volume, positive session volume. Floor recorded timestamp seconds to its minute, timestamp candle labeling remains unverified."}
    (Path(__file__).parent / "minute-data-audit.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({"totals": dict(totals), "eligible_instruments": len({r['security_id'] for r in eligible}), "eligible_first": eligible[:5]}))


if __name__ == "__main__":
    main()
