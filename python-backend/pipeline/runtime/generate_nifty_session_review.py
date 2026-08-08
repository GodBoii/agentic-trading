"""Generate a full-session NIFTY market-microstructure review pack.

This is an offline reader for data already captured by nifty-50-market-depth.
It never connects to Dhan or modifies the source recordings.
"""

from __future__ import annotations

import argparse
import html
import json
import math
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LogNorm

IST = "Asia/Kolkata"
BG = "#f7f8fa"
PANEL = "#ffffff"
GRID = "#e4e7eb"
TEXT = "#17212b"
MUTED = "#637083"
GREEN = "#16856b"
RED = "#c84b4b"
BLUE = "#315b9c"
PURPLE = "#6d5bd0"
ORANGE = "#d97706"


@dataclass(frozen=True)
class ReviewPaths:
    data: Path
    output: Path


def _read_ndjson(path: Path) -> Iterable[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON in {path.name} line {line_number}") from exc


def _timestamp(value: Any) -> pd.Timestamp:
    stamp = pd.Timestamp(value)
    if stamp.tzinfo is None:
        stamp = stamp.tz_localize("UTC")
    return stamp.tz_convert(IST)


def _number(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
        return result if math.isfinite(result) else default
    except (TypeError, ValueError):
        return default


def _style_axes(*axes: Any) -> None:
    for axis in axes:
        axis.set_facecolor(PANEL)
        axis.grid(True, color=GRID, linewidth=0.6, alpha=0.85)
        axis.tick_params(colors=TEXT)
        axis.xaxis.label.set_color(TEXT)
        axis.yaxis.label.set_color(TEXT)
        axis.title.set_color(TEXT)


def _finish(fig: Any, output: Path) -> None:
    fig.patch.set_facecolor(BG)
    fig.tight_layout()
    fig.savefig(output, dpi=145, bbox_inches="tight", facecolor=BG)
    plt.close(fig)


def _load_full_market(path: Path) -> pd.DataFrame:
    rows = []
    for row in _read_ndjson(path):
        packet = row.get("packet") or {}
        depth = packet.get("depth") or []
        best = depth[0] if depth else {}
        bid = _number(best.get("bid_price"), np.nan)
        ask = _number(best.get("ask_price"), np.nan)
        ltp = _number(packet.get("LTP"), np.nan)
        rows.append(
            {
                "timestamp": _timestamp(row["captured_at_utc"]),
                "price": ltp,
                "average_price": _number(packet.get("avg_price"), np.nan),
                "volume": _number(packet.get("volume"), np.nan),
                "open_interest": _number(packet.get("OI"), np.nan),
                "best_bid": bid,
                "best_ask": ask,
                "spread": ask - bid if math.isfinite(bid) and math.isfinite(ask) else np.nan,
                "spread_bps": (ask - bid) / ltp * 10000 if ltp and math.isfinite(bid) and math.isfinite(ask) else np.nan,
                "buy_quantity": _number(packet.get("total_buy_quantity"), np.nan),
                "sell_quantity": _number(packet.get("total_sell_quantity"), np.nan),
            }
        )
    frame = pd.DataFrame(rows).dropna(subset=["timestamp", "price"]).sort_values("timestamp")
    return frame.drop_duplicates("timestamp", keep="last")


def _minute_market(frame: pd.DataFrame) -> pd.DataFrame:
    indexed = frame.set_index("timestamp")
    bars = indexed["price"].resample("1min").ohlc()
    for column in ["average_price", "volume", "open_interest", "best_bid", "best_ask", "spread_bps", "buy_quantity", "sell_quantity"]:
        bars[column] = indexed[column].resample("1min").last()
    bars["minute_volume"] = bars["volume"].diff().clip(lower=0)
    bars["oi_change"] = bars["open_interest"].diff()
    denominator = bars["buy_quantity"] + bars["sell_quantity"]
    bars["quote_quantity_imbalance"] = (bars["buy_quantity"] - bars["sell_quantity"]) / denominator.replace(0, np.nan)
    return bars.dropna(subset=["close"])


def _load_cvd(path: Path) -> pd.DataFrame:
    rows = []
    for row in _read_ndjson(path):
        rows.append(
            {
                "timestamp": _timestamp(row["captured_at_utc"]),
                "price": _number(row.get("latest_price"), np.nan),
                "cvd": _number(row.get("cvd"), np.nan),
                "cvd_5min": _number(row.get("cvd_5min"), np.nan),
                "buy": _number(row.get("cumulative_buy_volume")),
                "sell": _number(row.get("cumulative_sell_volume")),
                "neutral": _number(row.get("cumulative_neutral_volume")),
            }
        )
    return pd.DataFrame(rows).dropna(subset=["timestamp", "price", "cvd"]).sort_values("timestamp")


def _load_imbalance(path: Path) -> pd.DataFrame:
    rows = []
    for row in _read_ndjson(path):
        rows.append(
            {
                "timestamp": _timestamp(row["captured_at_utc"]),
                "price": _number(row.get("latest_price"), np.nan),
                "imbalance_200": _number(row.get("imbalance"), np.nan),
                "imbalance_top5": _number(row.get("top5_imbalance"), np.nan),
                "bid_total": _number(row.get("bid_total_qty"), np.nan),
                "ask_total": _number(row.get("ask_total_qty"), np.nan),
                "bid_top5": _number(row.get("bid_top5_qty"), np.nan),
                "ask_top5": _number(row.get("ask_top5_qty"), np.nan),
                "largest_bid_price": _number((row.get("largest_bid") or {}).get("price"), np.nan),
                "largest_bid_qty": _number((row.get("largest_bid") or {}).get("quantity"), np.nan),
                "largest_ask_price": _number((row.get("largest_ask") or {}).get("price"), np.nan),
                "largest_ask_qty": _number((row.get("largest_ask") or {}).get("quantity"), np.nan),
            }
        )
    return pd.DataFrame(rows).dropna(subset=["timestamp"]).sort_values("timestamp")


def _load_trade_ticks(path: Path) -> pd.DataFrame:
    rows = []
    for row in _read_ndjson(path):
        rows.append(
            {
                "timestamp": _timestamp(row["captured_at_utc"]),
                "price": _number(row.get("latest_price"), np.nan),
                "volume_delta": max(0.0, _number(row.get("volume_delta"))),
                "aggressor": str(row.get("aggressor") or "neutral"),
            }
        )
    return pd.DataFrame(rows).dropna(subset=["timestamp", "price"]).sort_values("timestamp")


def _aggregate_depth(path: Path, valid_min: float, valid_max: float) -> dict[str, Any]:
    quantity_sum: dict[tuple[pd.Timestamp, str, float], float] = defaultdict(float)
    packet_counts: Counter[tuple[pd.Timestamp, str]] = Counter()
    last_sides: dict[str, dict[str, Any]] = {}
    row_count = 0
    for row in _read_ndjson(path):
        row_count += 1
        side = str(row.get("side"))
        minute = _timestamp(row["captured_at_utc"]).floor("1min")
        packet_counts[(minute, side)] += 1
        last_sides[side] = row
        for level in row.get("depth") or []:
            price = round(_number(level.get("price")))
            if valid_min <= price <= valid_max:
                quantity_sum[(minute, side, price)] += _number(level.get("quantity"))
    minutes = sorted({key[0] for key in packet_counts})
    prices = np.arange(math.floor(valid_min), math.ceil(valid_max) + 1, dtype=float)
    minute_index = {value: index for index, value in enumerate(minutes)}
    price_index = {value: index for index, value in enumerate(prices)}
    bid = np.zeros((len(prices), len(minutes)), dtype=np.float32)
    ask = np.zeros_like(bid)
    for (minute, side, price), total in quantity_sum.items():
        denominator = packet_counts[(minute, side)]
        if denominator and price in price_index:
            target = bid if side == "bid" else ask
            target[price_index[price], minute_index[minute]] = total / denominator
    return {
        "minutes": minutes,
        "prices": prices,
        "bid": bid,
        "ask": ask,
        "last_sides": last_sides,
        "row_count": row_count,
    }


def _load_options(path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    minute_last: dict[tuple[pd.Timestamp, str], dict[str, Any]] = {}
    first_contract: dict[str, dict[str, Any]] = {}
    final_contract: dict[str, dict[str, Any]] = {}
    for row in _read_ndjson(path):
        timestamp = _timestamp(row["captured_at_utc"])
        security_id = str(row["security_id"])
        record = {
            "timestamp": timestamp,
            "minute": timestamp.floor("1min"),
            "security_id": security_id,
            "strike": _number(row.get("strike_price")),
            "option_type": str(row.get("option_type")),
            "expiry": str(row.get("expiry_date")),
            "price": _number(row.get("latest_price")),
            "volume": _number(row.get("volume")),
            "open_interest": _number(row.get("open_interest")),
            "best_bid": _number(row.get("best_bid")),
            "best_ask": _number(row.get("best_ask")),
        }
        minute_last[(record["minute"], security_id)] = record
        first_contract.setdefault(security_id, record)
        final_contract[security_id] = record
    minute = pd.DataFrame(minute_last.values()).sort_values(["minute", "strike", "option_type"])
    final_rows = []
    for security_id, final in final_contract.items():
        first = first_contract[security_id]
        final = dict(final)
        final["oi_change"] = final["open_interest"] - first["open_interest"]
        final["volume_change"] = final["volume"] - first["volume"]
        final_rows.append(final)
    final = pd.DataFrame(final_rows).sort_values(["strike", "option_type"])
    return minute, final


def _load_large_order_activity(path: Path) -> tuple[pd.DataFrame, np.ndarray, dict[str, Any]]:
    counts: Counter[tuple[pd.Timestamp, str, str]] = Counter()
    active: dict[tuple[str, float], deque[pd.Timestamp]] = defaultdict(deque)
    lifetimes: list[float] = []
    rows = 0
    appeared = removed = 0
    for row in _read_ndjson(path):
        rows += 1
        timestamp = _timestamp(row["captured_at_utc"])
        minute = timestamp.floor("1min")
        side = str(row.get("side"))
        event_type = str(row.get("type"))
        price = _number(row.get("price"))
        counts[(minute, side, event_type)] += 1
        key = (side, price)
        if event_type == "large_order_appeared":
            appeared += 1
            active[key].append(timestamp)
        elif event_type == "large_order_removed":
            removed += 1
            if active[key]:
                duration = (timestamp - active[key].popleft()).total_seconds()
                if 0 <= duration <= 3600:
                    lifetimes.append(duration)
    records = [
        {"minute": minute, "side": side, "event_type": event_type, "count": count}
        for (minute, side, event_type), count in counts.items()
    ]
    return pd.DataFrame(records), np.asarray(lifetimes), {
        "rows": rows,
        "appeared": appeared,
        "removed": removed,
        "matched_lifetimes": len(lifetimes),
    }


def _plot_session(minute: pd.DataFrame, output: Path, market_date: str) -> dict[str, Any]:
    fig, axes = plt.subplots(3, 1, figsize=(18, 11), sharex=True, gridspec_kw={"height_ratios": [2.4, 1.2, 1.2]})
    _style_axes(*axes)
    axes[0].plot(minute.index, minute["close"], color=BLUE, linewidth=1.4, label="NIFTY futures")
    axes[0].plot(minute.index, minute["average_price"], color=PURPLE, linewidth=1.1, label="Dhan average price")
    axes[0].fill_between(minute.index, minute["low"], minute["high"], color=BLUE, alpha=0.09)
    axes[0].set_ylabel("Price")
    axes[0].legend(loc="upper left", frameon=False, ncol=2)
    colors = np.where(minute["close"] >= minute["open"], GREEN, RED)
    axes[1].bar(minute.index, minute["minute_volume"].fillna(0), width=0.0006, color=colors, alpha=0.75)
    axes[1].set_ylabel("Volume/min")
    axes[2].plot(minute.index, minute["open_interest"], color=ORANGE, linewidth=1.2, label="Open interest")
    axes[2].fill_between(minute.index, minute["open_interest"], minute["open_interest"].min(), color=ORANGE, alpha=0.10)
    axes[2].set_ylabel("Futures OI")
    axes[2].xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=minute.index.tz))
    axes[2].set_xlabel("Market time (IST)")
    fig.suptitle(f"NIFTY futures session — {market_date}", color=TEXT)
    _finish(fig, output)
    return {
        "open": round(float(minute["open"].iloc[0]), 2),
        "high": round(float(minute["high"].max()), 2),
        "low": round(float(minute["low"].min()), 2),
        "close": round(float(minute["close"].iloc[-1]), 2),
        "change_percent": round((float(minute["close"].iloc[-1]) / float(minute["open"].iloc[0]) - 1) * 100, 3),
    }


def _plot_cvd(cvd: pd.DataFrame, output: Path, market_date: str) -> dict[str, Any]:
    fig, (price_axis, cvd_axis) = plt.subplots(2, 1, figsize=(18, 9), sharex=True, gridspec_kw={"height_ratios": [1.5, 1]})
    _style_axes(price_axis, cvd_axis)
    price_axis.plot(cvd["timestamp"], cvd["price"], color=BLUE, linewidth=1.25)
    price_axis.set_ylabel("Futures price")
    cvd_axis.plot(cvd["timestamp"], cvd["cvd"], color=GREEN, linewidth=1.25, label="CVD")
    cvd_axis.plot(cvd["timestamp"], cvd["cvd"].rolling(50, min_periods=1).mean(), color=PURPLE, linewidth=1, label="CVD rolling mean")
    cvd_axis.fill_between(cvd["timestamp"], cvd["cvd"], 0, where=cvd["cvd"] >= 0, color=GREEN, alpha=0.15)
    cvd_axis.fill_between(cvd["timestamp"], cvd["cvd"], 0, where=cvd["cvd"] < 0, color=RED, alpha=0.15)
    cvd_axis.axhline(0, color=MUTED, linewidth=0.8)
    cvd_axis.set_ylabel("Cumulative volume delta")
    cvd_axis.set_xlabel("Market time (IST)")
    cvd_axis.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=cvd["timestamp"].dt.tz))
    cvd_axis.legend(loc="upper left", frameon=False)
    fig.suptitle(f"NIFTY futures price and inferred aggressor CVD — {market_date}", color=TEXT)
    _finish(fig, output)
    return {
        "final_cvd": round(float(cvd["cvd"].iloc[-1]), 2),
        "session_high": round(float(cvd["cvd"].max()), 2),
        "session_low": round(float(cvd["cvd"].min()), 2),
    }


def _plot_imbalance(frame: pd.DataFrame, output: Path, market_date: str) -> dict[str, Any]:
    fig, (price_axis, imbalance_axis, quantity_axis) = plt.subplots(3, 1, figsize=(18, 11), sharex=True, gridspec_kw={"height_ratios": [1.3, 1, 1]})
    _style_axes(price_axis, imbalance_axis, quantity_axis)
    price_axis.plot(frame["timestamp"], frame["price"], color=BLUE, linewidth=1.2)
    price_axis.set_ylabel("Price")
    imbalance_axis.plot(frame["timestamp"], frame["imbalance_200"], color=PURPLE, linewidth=1.1, label="All 200 levels")
    imbalance_axis.plot(frame["timestamp"], frame["imbalance_top5"], color=ORANGE, linewidth=0.9, alpha=0.8, label="Top 5 levels")
    imbalance_axis.axhline(0, color=MUTED, linewidth=0.8)
    imbalance_axis.fill_between(frame["timestamp"], frame["imbalance_200"], 0, where=frame["imbalance_200"] >= 0, color=GREEN, alpha=0.10)
    imbalance_axis.fill_between(frame["timestamp"], frame["imbalance_200"], 0, where=frame["imbalance_200"] < 0, color=RED, alpha=0.10)
    imbalance_axis.set_ylabel("Bid/ask imbalance")
    imbalance_axis.legend(loc="upper left", ncol=2, frameon=False)
    quantity_axis.plot(frame["timestamp"], frame["bid_total"], color=GREEN, linewidth=0.9, label="Bid quantity")
    quantity_axis.plot(frame["timestamp"], frame["ask_total"], color=RED, linewidth=0.9, label="Ask quantity")
    quantity_axis.set_ylabel("200-level quantity")
    quantity_axis.set_xlabel("Market time (IST)")
    quantity_axis.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=frame["timestamp"].dt.tz))
    quantity_axis.legend(loc="upper left", ncol=2, frameon=False)
    fig.suptitle(f"NIFTY 200-level order-book imbalance — {market_date}", color=TEXT)
    _finish(fig, output)
    return {
        "median_200_level_imbalance": round(float(frame["imbalance_200"].median()), 4),
        "median_top5_imbalance": round(float(frame["imbalance_top5"].median()), 4),
    }


def _plot_bookmap(depth: dict[str, Any], minute: pd.DataFrame, output: Path, market_date: str) -> dict[str, Any]:
    combined = depth["bid"] + depth["ask"]
    nonzero = combined[combined > 0]
    vmax = float(np.percentile(nonzero, 99.5)) if nonzero.size else 1.0
    fig, axis = plt.subplots(figsize=(19, 9))
    _style_axes(axis)
    x = mdates.date2num([stamp.to_pydatetime() for stamp in depth["minutes"]])
    extent = [x[0], x[-1], depth["prices"][0] - 0.5, depth["prices"][-1] + 0.5]
    image = axis.imshow(
        np.ma.masked_less_equal(combined, 0),
        origin="lower",
        aspect="auto",
        extent=extent,
        interpolation="nearest",
        cmap="magma",
        norm=LogNorm(vmin=max(1.0, float(np.percentile(nonzero, 10))) if nonzero.size else 1.0, vmax=max(vmax, 2.0)),
    )
    axis.plot(minute.index, minute["close"], color="#65d1ff", linewidth=1.3, label="Futures price")
    axis.xaxis_date()
    axis.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=minute.index.tz))
    axis.set_xlabel("Market time (IST)")
    axis.set_ylabel("Price level")
    axis.set_title(f"Full-session 200-level liquidity heatmap — {market_date}", loc="left")
    axis.legend(loc="upper left", frameon=False)
    colorbar = fig.colorbar(image, ax=axis, pad=0.01)
    colorbar.set_label("Average resting quantity per minute (log scale)")
    _finish(fig, output)
    return {"depth_packets": depth["row_count"], "price_min": float(depth["prices"][0]), "price_max": float(depth["prices"][-1])}


def _plot_wall_persistence(depth: dict[str, Any], output: Path, market_date: str) -> dict[str, Any]:
    records = []
    summaries: dict[str, list[dict[str, Any]]] = {}
    for side, matrix in (("Bid", depth["bid"]), ("Ask", depth["ask"])):
        positive = matrix[matrix > 0]
        threshold = float(np.percentile(positive, 95)) if positive.size else 0
        minutes_present = (matrix >= threshold).sum(axis=1)
        mean_quantity = np.where((matrix > 0).sum(axis=1) > 0, matrix.sum(axis=1) / np.maximum((matrix > 0).sum(axis=1), 1), 0)
        indexes = np.argsort(minutes_present)[-12:]
        side_rows = []
        for index in indexes:
            side_rows.append({"side": side, "price": float(depth["prices"][index]), "minutes": int(minutes_present[index]), "mean_quantity": float(mean_quantity[index])})
        summaries[side.lower()] = sorted(side_rows, key=lambda row: row["minutes"], reverse=True)
        records.extend(side_rows)
    frame = pd.DataFrame(records)
    fig, axes = plt.subplots(1, 2, figsize=(18, 7), sharey=False)
    _style_axes(*axes)
    for axis, side, color in zip(axes, ("Bid", "Ask"), (GREEN, RED)):
        local = frame[frame["side"] == side].sort_values("minutes")
        labels = [f"{price:.0f}" for price in local["price"]]
        axis.barh(labels, local["minutes"], color=color, alpha=0.8)
        for y, value in enumerate(local["minutes"]):
            axis.text(value + 0.3, y, f"{int(value)}m", va="center", color=TEXT, fontsize=8)
        axis.set_xlabel("Minutes at/above side's 95th percentile quantity")
        axis.set_ylabel("Price level")
        axis.set_title(f"Persistent {side.lower()} walls")
    fig.suptitle(f"NIFTY liquidity-wall persistence — {market_date}", color=TEXT)
    _finish(fig, output)
    return summaries


def _plot_volume_profile(trades: pd.DataFrame, output: Path, market_date: str) -> dict[str, Any]:
    local = trades.copy()
    local["price_bin"] = local["price"].round()
    local["buy_volume"] = np.where(local["aggressor"] == "buy", local["volume_delta"], 0)
    local["sell_volume"] = np.where(local["aggressor"] == "sell", local["volume_delta"], 0)
    profile = local.groupby("price_bin")[["buy_volume", "sell_volume", "volume_delta"]].sum().sort_index()
    fig, axis = plt.subplots(figsize=(11, 9))
    _style_axes(axis)
    axis.barh(profile.index, profile["buy_volume"], color=GREEN, alpha=0.8, label="Aggressive buy volume")
    axis.barh(profile.index, -profile["sell_volume"], color=RED, alpha=0.8, label="Aggressive sell volume")
    axis.axvline(0, color=MUTED, linewidth=0.8)
    axis.set_xlabel("Sell volume ← 0 → Buy volume")
    axis.set_ylabel("Futures price")
    axis.legend(loc="lower right", frameon=False)
    axis.set_title(f"NIFTY futures aggressor volume profile — {market_date}", loc="left")
    _finish(fig, output)
    total = profile["buy_volume"] + profile["sell_volume"]
    poc = float(total.idxmax()) if not total.empty else None
    return {"point_of_control": poc, "price_levels": len(profile), "classified_volume": round(float(total.sum()), 2)}


def _plot_options(final: pd.DataFrame, output: Path, market_date: str) -> dict[str, Any]:
    strikes = sorted(final["strike"].unique())
    ce = final[final["option_type"] == "CE"].set_index("strike").reindex(strikes)
    pe = final[final["option_type"] == "PE"].set_index("strike").reindex(strikes)
    x = np.arange(len(strikes)); width = 0.36
    fig, axes = plt.subplots(2, 1, figsize=(15, 10), sharex=True)
    _style_axes(*axes)
    axes[0].bar(x - width / 2, ce["open_interest"], width, color=RED, alpha=0.8, label="Call OI")
    axes[0].bar(x + width / 2, pe["open_interest"], width, color=GREEN, alpha=0.8, label="Put OI")
    axes[0].set_ylabel("Final open interest")
    axes[0].legend(loc="upper left", frameon=False)
    axes[1].bar(x - width / 2, ce["oi_change"], width, color=RED, alpha=0.8, label="Call OI change")
    axes[1].bar(x + width / 2, pe["oi_change"], width, color=GREEN, alpha=0.8, label="Put OI change")
    axes[1].axhline(0, color=MUTED, linewidth=0.8)
    axes[1].set_ylabel("Session OI change")
    axes[1].set_xlabel("Strike")
    axes[1].set_xticks(x, [f"{strike:.0f}" for strike in strikes])
    axes[1].legend(loc="upper left", frameon=False)
    fig.suptitle(f"NIFTY nearest-expiry option OI and OI change — {market_date}", color=TEXT)
    _finish(fig, output)
    call_oi = float(ce["open_interest"].sum())
    put_oi = float(pe["open_interest"].sum())
    return {
        "expiry": str(final["expiry"].iloc[0]),
        "strikes": strikes,
        "put_call_oi_ratio": round(put_oi / call_oi, 4) if call_oi else None,
        "max_call_oi_strike": float(ce["open_interest"].idxmax()),
        "max_put_oi_strike": float(pe["open_interest"].idxmax()),
    }


def _plot_pcr(options: pd.DataFrame, output: Path, market_date: str) -> dict[str, Any]:
    expected_contracts = int(options["security_id"].nunique())
    coverage = options.groupby("minute")["security_id"].nunique()
    complete_minutes = coverage[coverage == expected_contracts].index
    complete = options[options["minute"].isin(complete_minutes)]
    totals = complete.groupby(["minute", "option_type"])["open_interest"].sum().unstack()
    if totals.empty:
        raise RuntimeError("No option minutes contain complete contract coverage")
    totals["pcr"] = totals.get("PE", 0) / totals.get("CE", np.nan)
    fig, axis = plt.subplots(figsize=(18, 6))
    _style_axes(axis)
    axis.plot(totals.index, totals["pcr"], color=PURPLE, linewidth=1.3)
    axis.axhline(1, color=MUTED, linewidth=0.8, linestyle="--")
    axis.fill_between(totals.index, totals["pcr"], 1, where=totals["pcr"] >= 1, color=GREEN, alpha=0.12)
    axis.fill_between(totals.index, totals["pcr"], 1, where=totals["pcr"] < 1, color=RED, alpha=0.12)
    axis.set_xlabel("Market time (IST)")
    axis.set_ylabel("Put/call OI ratio (captured strikes only)")
    axis.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=totals.index.tz))
    axis.set_title(f"NIFTY captured-strike PCR through the session — {market_date}", loc="left")
    _finish(fig, output)
    return {
        "open": round(float(totals["pcr"].iloc[0]), 4),
        "close": round(float(totals["pcr"].iloc[-1]), 4),
        "expected_contracts": expected_contracts,
        "complete_minutes": len(totals),
    }


def _plot_large_orders(activity: pd.DataFrame, lifetimes: np.ndarray, output: Path, market_date: str) -> dict[str, Any]:
    pivot = activity.pivot_table(index="minute", columns=["side", "event_type"], values="count", aggfunc="sum", fill_value=0)
    fig, (rate_axis, lifetime_axis) = plt.subplots(2, 1, figsize=(18, 10), gridspec_kw={"height_ratios": [1.4, 1]})
    _style_axes(rate_axis, lifetime_axis)
    appeared = pivot.xs("large_order_appeared", axis=1, level=1).sum(axis=1) if "large_order_appeared" in pivot.columns.get_level_values(1) else pd.Series(dtype=float)
    removed = pivot.xs("large_order_removed", axis=1, level=1).sum(axis=1) if "large_order_removed" in pivot.columns.get_level_values(1) else pd.Series(dtype=float)
    rate_axis.plot(appeared.index, appeared, color=GREEN, linewidth=1, label="Appeared")
    rate_axis.plot(removed.index, removed, color=RED, linewidth=1, label="Removed")
    rate_axis.set_ylabel("Events/minute")
    rate_axis.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=appeared.index.tz))
    rate_axis.legend(loc="upper left", ncol=2, frameon=False)
    clipped = lifetimes[(lifetimes >= 0) & (lifetimes <= 60)]
    lifetime_axis.hist(clipped, bins=np.arange(0, 61, 1), color=ORANGE, alpha=0.8)
    lifetime_axis.set_xlabel("Matched appear-to-remove lifetime (seconds, clipped at 60s)")
    lifetime_axis.set_ylabel("Matched events")
    fig.suptitle(f"NIFTY large-order event churn — {market_date}", color=TEXT)
    _finish(fig, output)
    return {
        "median_lifetime_seconds": round(float(np.median(lifetimes)), 3) if lifetimes.size else None,
        "under_5_seconds_percent": round(float((lifetimes <= 5).mean() * 100), 2) if lifetimes.size else None,
        "under_30_seconds_percent": round(float((lifetimes <= 30).mean() * 100), 2) if lifetimes.size else None,
    }


def _plot_final_dom(depth: dict[str, Any], output: Path, market_date: str) -> dict[str, Any]:
    rows = []
    for side in ("bid", "ask"):
        for level in (depth["last_sides"].get(side) or {}).get("depth") or []:
            rows.append({"side": side, "price": _number(level.get("price")), "quantity": _number(level.get("quantity")), "orders": _number(level.get("orders"))})
    frame = pd.DataFrame(rows)
    if frame.empty:
        raise RuntimeError("No final DOM data")
    center = frame["price"].median()
    local = frame[(frame["price"] >= center - 35) & (frame["price"] <= center + 35)].copy()
    local["signed_quantity"] = np.where(local["side"] == "bid", local["quantity"], -local["quantity"])
    local = local.groupby(["price", "side"], as_index=False)["signed_quantity"].sum().sort_values("price")
    fig, axis = plt.subplots(figsize=(11, 10))
    _style_axes(axis)
    colors = np.where(local["side"] == "bid", GREEN, RED)
    axis.barh(local["price"], local["signed_quantity"], height=0.65, color=colors, alpha=0.8)
    axis.axvline(0, color=MUTED, linewidth=0.8)
    axis.set_xlabel("Ask quantity ← 0 → Bid quantity")
    axis.set_ylabel("Price")
    axis.set_title(f"Final NIFTY 200-level DOM near market — {market_date}", loc="left")
    _finish(fig, output)
    bid = frame[frame["side"] == "bid"]
    ask = frame[frame["side"] == "ask"]
    return {
        "largest_bid": bid.loc[bid["quantity"].idxmax()].to_dict(),
        "largest_ask": ask.loc[ask["quantity"].idxmax()].to_dict(),
    }


def _build_index(charts: list[dict[str, str]], summary: dict[str, Any], output: Path) -> None:
    sections = "".join(
        f"<section><h2>{html.escape(chart['title'])}</h2><p>{html.escape(chart['description'])}</p>"
        f"<a href=\"charts/{html.escape(chart['file'])}\"><img src=\"charts/{html.escape(chart['file'])}\" alt=\"{html.escape(chart['title'])}\"></a></section>"
        for chart in charts
    )
    document = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>NIFTY session review {html.escape(summary['market_date'])}</title><style>
body{{font-family:system-ui,sans-serif;margin:24px;background:#f7f8fa;color:#17212b}}main{{max-width:1500px;margin:auto}}section{{margin:36px 0 52px}}img{{width:100%;height:auto;background:#fff;border:1px solid #dce1e7}}p{{color:#4d5966;max-width:1050px}}a{{color:#315b9c}}code{{background:#e9edf2;padding:2px 5px}}</style></head>
<body><main><h1>NIFTY full-session review — {html.escape(summary['market_date'])}</h1>
<p>Built from the saved NIFTY futures Full Packet feed, 200-level depth, trade ticks, captured options and derived event streams. No live API was used.</p>
<p><a href="review-summary.json">Machine-readable summary</a></p>{sections}</main></body></html>"""
    output.write_text(document, encoding="utf-8")


def generate(paths: ReviewPaths) -> dict[str, Any]:
    paths.output.mkdir(parents=True, exist_ok=True)
    charts_dir = paths.output / "charts"
    charts_dir.mkdir(exist_ok=True)
    market_date = paths.data.name
    print("Loading full-market, CVD, imbalance and trade data", flush=True)
    full = _load_full_market(paths.data / "full_market.ndjson")
    minute = _minute_market(full)
    cvd = _load_cvd(paths.data / "cvd_series.ndjson")
    imbalance = _load_imbalance(paths.data / "depth_imbalance_series.ndjson")
    trades = _load_trade_ticks(paths.data / "trade_ticks.ndjson")
    price_min = float(minute["low"].min()) - 60
    price_max = float(minute["high"].max()) + 60
    print("Aggregating all 200-level depth packets", flush=True)
    depth = _aggregate_depth(paths.data / "depth_200.ndjson", price_min, price_max)
    print("Aggregating option snapshots", flush=True)
    options_minute, options_final = _load_options(paths.data / "options_feed.ndjson")
    print("Aggregating large-order churn", flush=True)
    order_activity, lifetimes, order_counts = _load_large_order_activity(paths.data / "large_order_events.ndjson")

    definitions = [
        ("session", "NIFTY futures session", "Price, Dhan average price, minute volume and futures open interest.", _plot_session, (minute,)),
        ("cvd", "Price and cumulative volume delta", "Shows whether inferred aggressive buying/selling confirmed the price move.", _plot_cvd, (cvd,)),
        ("imbalance", "200-level depth imbalance", "Compares the full 200-level book with the visible top five levels.", _plot_imbalance, (imbalance,)),
        ("bookmap", "Full-session liquidity heatmap", "Average resting depth at each one-point price level for every minute.", _plot_bookmap, (depth, minute)),
        ("walls", "Liquidity-wall persistence", "Price levels that repeatedly held unusually large resting bid or ask quantities.", _plot_wall_persistence, (depth,)),
        ("volume-profile", "Aggressor volume profile", "Inferred aggressive buy and sell volume grouped by traded futures price.", _plot_volume_profile, (trades,)),
        ("options-oi", "Options OI and session OI change", "Final OI and first-to-last change for the five captured nearest-expiry strikes.", _plot_options, (options_final,)),
        ("options-pcr", "Captured-strike PCR", "Put/call OI ratio through the day; it covers only the five subscribed strikes.", _plot_pcr, (options_minute,)),
        ("large-orders", "Large-order detector churn", "Appear/remove rate and matched lifetime; use this to judge how noisy the current detector is.", _plot_large_orders, (order_activity, lifetimes)),
        ("final-dom", "Final 200-level DOM", "Resting quantity near the market in the final recorded bid and ask snapshots.", _plot_final_dom, (depth,)),
    ]
    charts = []
    metrics: dict[str, Any] = {}
    for key, title, description, function, args in definitions:
        filename = f"{key}.png"
        print(f"Rendering {title}", flush=True)
        metrics[key] = function(*args, charts_dir / filename, market_date)
        charts.append({"key": key, "title": title, "description": description, "file": filename})
    metrics["large-orders"]["counts"] = order_counts
    summary = {
        "market_date": market_date,
        "generated_at": datetime.now().astimezone().isoformat(),
        "source": str(paths.data.resolve()),
        "chart_count": len(charts),
        "charts": charts,
        "metrics": metrics,
        "limitations": [
            "CVD aggressor side is inferred from price versus best bid/ask and tick direction; it is not exchange-provided aggressor metadata.",
            "The options feed contains five strikes and one expiry, so PCR and option walls describe only the subscribed slice.",
            "Resting depth can be cancelled or spoofed and does not identify banks, hedge funds or individual participants.",
            "Large-order appear/remove events are highly noisy; persistence is more meaningful than the raw count.",
        ],
    }
    (paths.output / "review-summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    _build_index(charts, summary, paths.output / "index.html")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True, help="Market date in YYYY-MM-DD format")
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "results" / "nifty-50-market-depth",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    data = args.results_dir / args.date
    output = args.output or data / "session-review"
    summary = generate(ReviewPaths(data=data, output=output))
    print(json.dumps({"output": str(output.resolve()), "chart_count": summary["chart_count"]}, indent=2))


if __name__ == "__main__":
    main()
