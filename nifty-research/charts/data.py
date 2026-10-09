"""Read archived broker packets without changing the source recordings."""
from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

IST = "Asia/Kolkata"


def records(path: Path, day: str, audit: dict) -> Iterator[tuple[pd.Timestamp, dict]]:
    before = path.stat()
    digest = hashlib.sha256()
    audit.update(path=str(path.resolve()), bytes=before.st_size, malformed=0, outside_session=0)
    with path.open("rb") as handle:
        for line in handle:
            digest.update(line)
            try:
                row = json.loads(line)
                stamp = pd.Timestamp(row["captured_at_utc"])
                if stamp.tzinfo is None:
                    raise ValueError("Naive timestamp")
                stamp = stamp.tz_convert(IST)
            except (ValueError, KeyError, TypeError, UnicodeDecodeError):
                audit["malformed"] += 1
                continue
            if (stamp.date().isoformat() != day or stamp.weekday() >= 5
                    or not "09:15:00" <= stamp.strftime("%H:%M:%S") < "15:30:00"):
                audit["outside_session"] += 1
                continue
            yield stamp, row
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise RuntimeError(f"Archive changed while reading {path}")
    audit["sha256"] = digest.hexdigest()


def finite(value: object) -> float:
    result = float(value)
    if not np.isfinite(result):
        raise ValueError("Non-finite packet value")
    return result


def load_market(path: Path, day: str) -> tuple[pd.DataFrame, dict]:
    audit: dict = {"invalid": 0, "non_increasing": 0, "resets": 0}
    rows = []
    previous = None
    segment = 0
    for stamp, row in records(path, day, audit):
        packet = row.get("packet", {})
        if packet.get("type") != "Full Data":
            continue
        try:
            price, volume = finite(packet["LTP"]), finite(packet["volume"])
            best = packet["depth"][0]
            bid, ask = finite(best["bid_price"]), finite(best["ask_price"])
            bq, aq = finite(best["bid_quantity"]), finite(best["ask_quantity"])
            oi = finite(packet["OI"])
            if price <= 0 or bid <= 0 or ask <= bid or min(volume, bq, aq, oi) < 0:
                raise ValueError("Invalid market quote")
        except (ValueError, TypeError, KeyError, IndexError):
            audit["invalid"] += 1
            continue
        sid = str(packet["security_id"])
        if previous is not None and stamp <= previous["time"]:
            audit["non_increasing"] += 1
            continue
        reset = previous is None or (stamp - previous["time"]).total_seconds() > 10
        if previous is not None:
            reset |= volume < previous["cumulative"] or sid != previous["sid"]
            seq, oldseq = row.get("event_sequence"), previous["seq"]
            reset |= isinstance(seq, int) and isinstance(oldseq, int) and seq < oldseq
        if reset and previous is not None:
            segment += 1
            audit["resets"] += 1
        increment = 0 if reset else volume - previous["cumulative"]
        side = 1 if price >= ask else -1 if price <= bid else 0
        if side == 0 and previous is not None and not reset:
            side = int(price > previous["price"]) - int(price < previous["price"])
        mid = (bid + ask) / 2
        rows.append(dict(time=stamp, price=price, volume=increment, oi=oi, sid=sid,
                         segment=segment, spread=ask - bid, signed=side * increment,
                         unknown=increment if side == 0 else 0,
                         micro=((ask * bq + bid * aq) / (bq + aq) - mid) if bq + aq else np.nan))
        previous = dict(time=stamp, price=price, cumulative=volume, sid=sid, seq=row.get("event_sequence"))
    if not rows:
        raise ValueError(f"No valid market packets in {path}")
    audit["accepted"] = len(rows)
    return pd.DataFrame(rows).set_index("time"), audit


def make_bars(ticks: pd.DataFrame, day: str, minutes: int = 1) -> pd.DataFrame:
    """Aggregate within reset segments, never combine instruments or bridge gaps."""
    parts = []
    for segment, group in ticks.groupby("segment", sort=False):
        bars = group.resample(f"{minutes}min", origin="start_day", offset="15min").agg(
            open=("price", "first"), high=("price", "max"), low=("price", "min"),
            close=("price", "last"), volume=("volume", "sum"), oi=("oi", "last"),
            signed=("signed", "sum"), unknown=("unknown", "sum"),
            spread=("spread", "median"), micro=("micro", "median"), count=("price", "count"))
        bars["segment"] = segment
        bars["sid"] = group["sid"].iloc[0]
        bars["first"] = group.index.to_series().resample(f"{minutes}min", origin="start_day", offset="15min").first()
        bars["last"] = group.index.to_series().resample(f"{minutes}min", origin="start_day", offset="15min").last()
        parts.append(bars.loc[bars["count"] > 0])
    frame = pd.concat(parts).sort_index(kind="stable")
    # A restart inside a bar makes that bar ambiguous. Do not invent one candle.
    frame = frame.loc[~frame.index.duplicated(keep=False)]
    index = pd.date_range(f"{day} 09:15", f"{day} 15:29", freq=f"{minutes}min", tz=IST)
    frame = frame.reindex(index)
    frame["complete"] = ((frame["first"] - frame.index.to_series()).dt.total_seconds() <= 2) & (
        (frame.index.to_series() + pd.Timedelta(minutes=minutes) - frame["last"]).dt.total_seconds() <= 2)
    # Restart all rolling studies after missing or partial candles as well.
    breaks = frame["segment"].ne(frame["segment"].shift()) | ~frame["complete"] | ~frame["complete"].shift(fill_value=False)
    frame["run"] = breaks.cumsum()
    return frame


def load_depth(path: Path, day: str) -> tuple[list[dict], dict]:
    audit: dict = {"invalid": 0, "stale_or_crossed": 0, "non_increasing": 0}
    sides: dict = {}
    snapshots: dict = {}
    previous = None
    for stamp, row in records(path, day, audit):
        if previous is not None and stamp < previous:
            audit["non_increasing"] += 1
            continue
        previous = stamp
        side = row.get("side")
        if side not in {"bid", "ask"}:
            audit["invalid"] += 1
            continue
        try:
            levels = [(finite(x["price"]), finite(x["quantity"])) for x in row["depth"]]
            if not levels or any(p <= 0 or q < 0 for p, q in levels):
                raise ValueError("Invalid depth level")
            prices = [x[0] for x in levels]
            if prices != sorted(set(prices), reverse=side == "bid"):
                raise ValueError("Unsorted or duplicate depth prices")
        except (ValueError, TypeError, KeyError):
            audit["invalid"] += 1
            sides.pop(side, None)
            continue
        old = sides.get(side)
        seq = row.get("event_sequence")
        if old and isinstance(seq, int) and isinstance(old["seq"], int) and seq < old["seq"]:
            sides.clear()
        sides[side] = dict(time=stamp, levels=levels, sid=str(row.get("security_id")), seq=seq)
        if len(sides) != 2:
            continue
        bid, ask = sides["bid"], sides["ask"]
        age = max((stamp - bid["time"]).total_seconds(), (stamp - ask["time"]).total_seconds())
        if age > 1 or bid["sid"] != ask["sid"] or bid["levels"][0][0] >= ask["levels"][0][0]:
            audit["stale_or_crossed"] += 1
            continue
        snapshots[stamp.floor("min")] = dict(time=stamp.isoformat(), bid=bid["levels"], ask=ask["levels"],
                                                sid=bid["sid"], age=age)
    audit["snapshots"] = len(snapshots)
    return list(snapshots.values()), audit


def load_options(path: Path, day: str) -> tuple[pd.DataFrame, dict]:
    audit: dict = {"invalid": 0}
    rows = []
    for stamp, row in records(path, day, audit):
        try:
            bid, ask, strike, oi = [finite(row[k]) for k in ("best_bid", "best_ask", "strike_price", "open_interest")]
            expiry, kind = row["expiry_date"], row["option_type"]
            datetime.strptime(expiry, "%Y-%m-%d")
            if bid < 0 or ask <= bid or strike <= 0 or oi < 0 or expiry < day or kind not in {"CE", "PE"}:
                raise ValueError("Invalid option")
        except (ValueError, KeyError, TypeError):
            audit["invalid"] += 1
            continue
        rows.append(dict(time=stamp, bid=bid, ask=ask, strike=strike, oi=oi,
                         expiry=expiry, kind=kind, sid=str(row["security_id"])))
    if not rows:
        return pd.DataFrame(), audit
    raw = pd.DataFrame(rows).sort_values("time").drop_duplicates(["time", "sid"], keep="last")
    grid = pd.DataFrame({"cutoff": pd.date_range(f"{day} 09:16", f"{day} 15:30", freq="min", tz=IST)})
    samples = []
    for (expiry, strike, kind, sid), quotes in raw.groupby(["expiry", "strike", "kind", "sid"]):
        joined = pd.merge_asof(grid, quotes, left_on="cutoff", right_on="time", tolerance=pd.Timedelta(seconds=2))
        joined = joined.dropna(subset=["bid"])
        joined["expiry"], joined["strike"], joined["kind"], joined["sid"] = expiry, strike, kind, sid
        samples.append(joined)
    audit.update(accepted=len(raw), fresh_minute_quotes=sum(map(len, samples)))
    return pd.concat(samples, ignore_index=True), audit
