from __future__ import annotations

from collections import Counter
from datetime import datetime
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .config import ResearchConfig
from .io import IST, capture_time, number, read_records, trading_capture


def _stamp(row: dict, day: str, audit: dict) -> datetime | None:
    try:
        stamp = capture_time(row)
    except (KeyError, TypeError, ValueError):
        audit["invalid_timestamp"] = audit.get("invalid_timestamp", 0) + 1
        return None
    if not trading_capture(stamp, day):
        audit["outside_regular_session"] = audit.get("outside_regular_session", 0) + 1
        return None
    return stamp


def read_market(path: Path, day: str, config: ResearchConfig) -> tuple[pd.DataFrame, dict]:
    audit: dict = {}; rows = []; previous: dict | None = None; segment = 0; cvd = 0.0
    audit.update(invalid_quote=0, backwards_timestamp=0, resets=0, gaps=[], ambiguous_volume_rows=0)
    for record in read_records(path, audit):
        stamp = _stamp(record, day, audit)
        if stamp is None:
            continue
        packet = record.get("packet")
        if not isinstance(packet, dict) or packet.get("type") != "Full Data":
            audit["non_full_packets"] = audit.get("non_full_packets", 0) + 1
            continue
        levels = packet.get("depth") or []
        if not isinstance(levels, list) or not levels:
            audit["invalid_quote"] += 1; continue
        best = levels[0]
        bid, ask = number(best.get("bid_price")), number(best.get("ask_price"))
        price, volume = number(packet.get("LTP")), number(packet.get("volume"))
        if bid is None or ask is None or bid <= 0 or ask <= bid or price is None or volume is None:
            audit["invalid_quote"] += 1; continue
        sid = str(packet.get("security_id")); seq = record.get("event_sequence")
        reset = previous is None
        if previous is not None:
            elapsed = (stamp - previous["timestamp"]).total_seconds()
            if elapsed <= 0:
                audit["backwards_timestamp"] += 1; continue
            sequence_reset = isinstance(seq, int) and isinstance(previous["sequence"], int) and seq < previous["sequence"]
            reset = (elapsed > config.packet_gap_seconds or sid != previous["security_id"]
                     or volume < previous["volume"] or sequence_reset)
            if elapsed > config.packet_gap_seconds:
                audit["gaps"].append({"start": previous["timestamp"].isoformat(),
                                      "end": stamp.isoformat(), "seconds": round(elapsed, 3)})
            if reset:
                audit["resets"] += 1; segment += 1; cvd = 0.0
        delta = 0.0 if reset else volume - previous["volume"]
        side = 0
        if price >= ask: side = 1
        elif price <= bid: side = -1
        elif previous is not None and not reset:
            side = int(price > previous["ltp"]) - int(price < previous["ltp"])
        ltq = number(packet.get("LTQ")) or 0.0
        if delta > ltq:
            audit["ambiguous_volume_rows"] += 1
        cvd += side * delta
        bq = number(best.get("bid_quantity")) or 0.0
        aq = number(best.get("ask_quantity")) or 0.0
        mid = (bid + ask) / 2
        ltt_age = None
        try:
            local = stamp.astimezone(IST)
            last_time = datetime.strptime(packet["LTT"], "%H:%M:%S").time()
            ltt_age = (local - datetime.combine(local.date(), last_time, IST)).total_seconds()
        except (KeyError, TypeError, ValueError):
            audit["missing_last_trade_time"] = audit.get("missing_last_trade_time", 0) + 1
        rows.append({"timestamp": stamp, "date": day, "segment": segment, "security_id": sid,
                     "mid": mid, "ltp": price, "spread_bps": (ask - bid) / mid * 10000,
                     "microprice_bps": (((ask * bq + bid * aq) / (bq + aq)) / mid - 1) * 10000 if bq + aq else 0.0,
                     "volume_increment": delta, "oi": number(packet.get("OI")),
                     "estimated_signed_volume": side * delta, "estimated_cvd": cvd,
                     "last_trade_age_seconds": ltt_age})
        previous = {"timestamp": stamp, "sequence": seq, "security_id": sid, "volume": volume, "ltp": price}
    audit["accepted_rows"] = len(rows)
    return pd.DataFrame(rows), audit


def book_features(bids: list[dict], asks: list[dict]) -> dict[str, float]:
    mid = (bids[0]["price"] + asks[0]["price"]) / 2
    result = {}
    for count in (5, 20, 200):
        buy = sum(x["quantity"] for x in bids[:count]); sell = sum(x["quantity"] for x in asks[:count])
        result[f"imbalance_{count}"] = (buy - sell) / (buy + sell) if buy + sell else 0.0
    for width in (5, 10, 25, 50):
        buy = sum(x["quantity"] for x in bids if 0 <= mid - x["price"] <= width)
        sell = sum(x["quantity"] for x in asks if 0 <= x["price"] - mid <= width)
        result[f"imbalance_points_{width}"] = (buy - sell) / (buy + sell) if buy + sell else 0.0
    buy = sum(x["quantity"] / (1 + abs(mid - x["price"])) for x in bids)
    sell = sum(x["quantity"] / (1 + abs(mid - x["price"])) for x in asks)
    result["imbalance_weighted"] = (buy - sell) / (buy + sell) if buy + sell else 0.0
    result["book_spread_bps"] = (asks[0]["price"] - bids[0]["price"]) / mid * 10000
    return result


def read_depth(path: Path, day: str, config: ResearchConfig) -> tuple[pd.DataFrame, dict]:
    audit: dict = {"invalid_book": 0, "backwards_timestamp": 0, "stale_pair": 0, "crossed_pair": 0}
    sides: dict[str, dict] = {}; rows = []; previous_stamp = None; last_emit = None
    counts: Counter = Counter()
    for record in read_records(path, audit):
        stamp = _stamp(record, day, audit)
        if stamp is None: continue
        if previous_stamp is not None and stamp < previous_stamp:
            audit["backwards_timestamp"] += 1; continue
        previous_stamp = stamp
        side = record.get("side"); levels = record.get("depth")
        if side not in {"bid", "ask"} or not isinstance(levels, list):
            audit["invalid_book"] += 1; continue
        counts[side] += 1
        if side in sides:
            oldseq, seq = sides[side]["sequence"], record.get("event_sequence")
            if isinstance(oldseq, int) and isinstance(seq, int) and seq < oldseq:
                sides.clear()
        clean = []
        for level in levels:
            if not isinstance(level, dict): continue
            price, quantity = number(level.get("price")), number(level.get("quantity"))
            if price is not None and price > 0 and quantity is not None and quantity >= 0:
                clean.append({"price": price, "quantity": quantity})
        if (not clean or any((a["price"] < b["price"] if side == "bid" else a["price"] > b["price"])
                             for a, b in zip(clean, clean[1:]))):
            audit["invalid_book"] += 1; sides.pop(side, None); continue
        sides[side] = {"timestamp": stamp, "sequence": record.get("event_sequence"),
                       "security_id": str(record.get("security_id")), "levels": clean}
        if len(sides) < 2: continue
        bid, ask = sides["bid"], sides["ask"]
        age = max((stamp - bid["timestamp"]).total_seconds(), (stamp - ask["timestamp"]).total_seconds())
        if age > config.depth_side_age_seconds or bid["security_id"] != ask["security_id"]:
            audit["stale_pair"] += 1; continue
        if bid["levels"][0]["price"] >= ask["levels"][0]["price"]:
            audit["crossed_pair"] += 1; continue
        if last_emit is not None and (stamp - last_emit).total_seconds() < config.depth_emit_seconds:
            continue
        rows.append({"timestamp": stamp, "date": day, "security_id": bid["security_id"],
                     "side_age_seconds": age, **book_features(bid["levels"], ask["levels"])})
        last_emit = stamp
    audit.update(side_counts=dict(counts), accepted_features=len(rows))
    return pd.DataFrame(rows), audit


def read_options(path: Path, day: str) -> tuple[pd.DataFrame, dict]:
    audit: dict = {"invalid_quote": 0}; rows = []
    for record in read_records(path, audit):
        stamp = _stamp(record, day, audit)
        if stamp is None: continue
        bid, ask, strike = (number(record.get(key)) for key in ("best_bid", "best_ask", "strike_price"))
        option_type, expiry = record.get("option_type"), record.get("expiry_date")
        try:
            valid_expiry = datetime.strptime(expiry, "%Y-%m-%d").date().isoformat() >= day
        except (TypeError, ValueError): valid_expiry = False
        if (bid is None or ask is None or strike is None or bid < 0 or ask <= bid
                or option_type not in {"CE", "PE"} or not valid_expiry):
            audit["invalid_quote"] += 1; continue
        rows.append({"timestamp": stamp, "date": day, "security_id": str(record.get("security_id")),
                     "expiry": expiry, "strike": strike, "option_type": option_type,
                     "bid": bid, "ask": ask, "oi": number(record.get("open_interest"))})
    audit["accepted_rows"] = len(rows)
    audit["execution_limitations"] = ["No quote sizes or exchange quote timestamps", "Prices imply fills only conditionally"]
    frame = pd.DataFrame(rows)
    if not frame.empty:
        frame = frame.sort_values("timestamp", kind="stable").drop_duplicates(["timestamp", "security_id"], keep="last")
    return frame, audit


def minute_features(market: pd.DataFrame, depth: pd.DataFrame, config: ResearchConfig) -> pd.DataFrame:
    if market.empty: return pd.DataFrame()
    chunks = []
    for (_, _, sid), group in market.groupby(["date", "segment", "security_id"], sort=False):
        group = group.sort_values("timestamp").copy()
        group["minute"] = group["timestamp"].dt.floor("min")
        bars = group.groupby("minute", sort=True).agg(
            close=("mid", "last"), high=("mid", "max"), low=("mid", "min"),
            volume=("volume_increment", "sum"), oi=("oi", "last"), spread_bps=("spread_bps", "last"),
            microprice_bps=("microprice_bps", "last"), signed_volume=("estimated_signed_volume", "sum"),
            source_at=("timestamp", "last"), first_at=("timestamp", "first"),
            last_trade_age_seconds=("last_trade_age_seconds", "last"))
        bars["decision_at"] = bars.index + pd.Timedelta(minutes=1)
        # Partial boundary minutes do not become ordinary 60-second samples.
        full_minute = ((bars["first_at"] - bars.index.to_series()).dt.total_seconds() <= 2.0
                       ) & ((bars["decision_at"] - bars["source_at"]).dt.total_seconds() <= 2.0)
        bars["complete_minute"] = full_minute
        bars["ret_1_bps"] = np.log(bars["close"] / bars["close"].shift(1)) * 10000
        bars["ret_5_bps"] = np.log(bars["close"] / bars["close"].shift(5)) * 10000
        bars["rv_5_bps"] = bars["ret_1_bps"].rolling(5).std()
        bars["range_5_bps"] = (bars["high"].rolling(5).max() - bars["low"].rolling(5).min()) / bars["close"] * 10000
        bars["log_volume"] = np.log1p(bars["volume"])
        bars["oi_change_bps"] = (bars["oi"] / bars["oi"].shift(5) - 1) * 10000
        bars["signed_volume_ratio"] = bars["signed_volume"].rolling(5).sum() / bars["volume"].rolling(5).sum().replace(0, np.nan)
        bars["date"] = group["date"].iloc[0]; bars["segment"] = group["segment"].iloc[0]; bars["security_id"] = sid
        local = bars["decision_at"].dt.tz_convert("Asia/Kolkata")
        bars["minutes_from_open"] = local.dt.hour * 60 + local.dt.minute - 555
        horizon = config.horizon_minutes
        bars["label_at"] = bars["decision_at"].shift(-horizon)
        contiguous = ((bars["label_at"] - bars["decision_at"]) == pd.Timedelta(minutes=horizon))
        # Require complete historical and future windows, all in this segment.
        history_ok = bars["complete_minute"].rolling(6).sum().eq(6)
        bars["feature_ready"] = history_ok
        future_ok = bars["complete_minute"].rolling(horizon).sum().shift(-horizon).eq(horizon)
        bars["target_bps"] = (np.log(bars["close"].shift(-horizon) / bars["close"]) * 10000).where(contiguous & history_ok & future_ok)
        bars = bars.reset_index(drop=True)
        if not depth.empty:
            same = depth[(depth["date"] == group["date"].iloc[0]) & (depth["security_id"] == sid)].sort_values("timestamp")
            if not same.empty:
                same = same.drop(columns=["date", "security_id"]).rename(columns={"timestamp": "depth_at"})
                bars = pd.merge_asof(bars.sort_values("decision_at"), same, left_on="decision_at", right_on="depth_at",
                                     direction="backward", allow_exact_matches=False,
                                     tolerance=pd.Timedelta(seconds=config.depth_feature_age_seconds))
        chunks.append(bars)
    return pd.concat(chunks, ignore_index=True).sort_values("decision_at").reset_index(drop=True)


def prepare_session(directory: Path, output: Path, config: ResearchConfig) -> dict:
    day = directory.name; report: dict = {"date": day, "source": str(directory.resolve()), "files": {}}
    market, audit = read_market(directory / "full_market.ndjson", day, config)
    report["files"]["full_market"] = audit
    depth = pd.DataFrame()
    if (directory / "depth_200.ndjson").exists():
        depth, audit = read_depth(directory / "depth_200.ndjson", day, config); report["files"]["depth"] = audit
    features = minute_features(market, depth, config)
    output.mkdir(parents=True, exist_ok=True)
    if not features.empty:
        features.to_parquet(output / "features.parquet", index=False)
    if (directory / "options_feed.ndjson").exists():
        options, audit = read_options(directory / "options_feed.ndjson", day)
        report["files"]["options"] = audit
        if not options.empty: options.to_parquet(output / "options.parquet", index=False)
    report.update(feature_rows=len(features), labelled_rows=int(features["target_bps"].notna().sum()) if not features.empty else 0)
    # Saved CVD is evidence of collector state only; it is never a model input.
    cvd_path = directory / "cvd_series.ndjson"
    if cvd_path.exists():
        with cvd_path.open(encoding="utf-8") as handle:
            first = next((json.loads(line) for line in handle if line.strip()), {})
        report["saved_cvd_first"] = {key: first.get(key) for key in ("cvd", "cumulative_buy_volume", "cumulative_sell_volume", "cumulative_neutral_volume")}
    return report
