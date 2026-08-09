"""Generate a human-reviewable chart pack from an Intra-Finder shadow run.

The report uses only persisted Stage 2 data.  It does not call Dhan and is safe
to run while the market is closed.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

import matplotlib
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402


IST = "Asia/Kolkata"


@dataclass(frozen=True)
class ReviewPaths:
    stage2_day: Path
    output: Path
    quality_events: Path | None = None

    @property
    def events(self) -> Path:
        return self.stage2_day / "setup-events.jsonl"

    @property
    def snapshots(self) -> Path:
        return self.stage2_day / "one-second"


def _event_time(event: dict[str, Any]) -> pd.Timestamp:
    evidence = event.get("evidence_timestamps") or []
    value = evidence[-1] if evidence else event.get("created_at")
    if not value:
        raise ValueError(f"Event {event.get('event_id')} has no evidence timestamp")
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize(IST)
    return timestamp.tz_convert(IST)


def _safe_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:70] or "stock"


def _load_events(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            event = json.loads(line)
            event["_event_time"] = _event_time(event)
            event["_line_number"] = line_number
            events.append(event)
    return events


def _selected_quality_rows(path: Path, market_date: str) -> dict[str, dict[str, Any]]:
    frame = pd.read_csv(path)
    required = {"market_date", "event_id", "selected", "entry_time", "entry_price", "quality_score"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Quality-event file is missing columns: {sorted(missing)}")
    selected = frame[
        frame["market_date"].astype(str).eq(market_date)
        & frame["selected"].astype(str).str.lower().isin({"true", "1", "yes"})
    ]
    return {str(row["event_id"]): row.to_dict() for _, row in selected.iterrows()}


def _apply_quality_selection(
    events: list[dict[str, Any]], quality_rows: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    used_event_ids: set[str] = set()
    for event in events:
        event_id = str(event.get("event_id"))
        row = quality_rows.get(event_id)
        if row is None or event_id in used_event_ids:
            continue
        event = dict(event)
        timestamp = pd.Timestamp(row["entry_time"])
        if timestamp.tzinfo is None:
            timestamp = timestamp.tz_localize(IST)
        event["_event_time"] = timestamp.tz_convert(IST)
        event["_raw_setup_score"] = event.get("setup_score")
        event["setup_score"] = float(row["quality_score"])
        event["price"] = float(row["entry_price"])
        for event_key, row_key in (
            ("vwap", "vwap"),
            ("relative_volume", "relative_volume"),
            ("volume_acceleration", "volume_acceleration"),
            ("spread", "spread_percent"),
            ("estimated_slippage", "estimated_slippage_percent"),
        ):
            value = row.get(row_key)
            if value is not None and not pd.isna(value):
                event[event_key] = float(value)
        depth = dict(event.get("five_level_depth_summary") or {})
        if not pd.isna(row.get("depth_imbalance")):
            depth["imbalance"] = float(row["depth_imbalance"])
        if not pd.isna(row.get("order_count_imbalance")):
            depth["order_count_imbalance"] = float(row["order_count_imbalance"])
        event["five_level_depth_summary"] = depth
        event["_quality_row"] = row
        selected.append(event)
        used_event_ids.add(event_id)
    return selected


def _load_snapshots(path: Path, security_ids: set[int]) -> pd.DataFrame:
    columns = [
        "received_at",
        "security_id",
        "exchange_segment",
        "symbol",
        "last_price",
        "day_volume",
        "vwap",
        "opening_range_high",
        "opening_range_low",
        "relative_volume",
        "spread_percent",
        "depth_imbalance",
    ]
    fragments: list[pd.DataFrame] = []
    for parquet_path in sorted(path.rglob("*.parquet")):
        names = set(pq.read_schema(parquet_path).names)
        available = [column for column in columns if column in names]
        fragment = pq.read_table(parquet_path, columns=available).to_pandas()
        if "security_id" not in fragment:
            continue
        fragment["security_id"] = pd.to_numeric(fragment["security_id"], errors="coerce")
        fragment = fragment[fragment["security_id"].isin(security_ids)]
        if fragment.empty:
            continue
        for column in columns:
            if column not in fragment:
                fragment[column] = np.nan
        fragments.append(fragment[columns])
    if not fragments:
        raise RuntimeError(f"No snapshots matched {len(security_ids)} selected securities")
    frame = pd.concat(fragments, ignore_index=True, sort=False)
    # Persisted snapshots can contain ISO timestamps both with and without
    # fractional seconds, so pandas must not infer one rigid format from row 1.
    frame["received_at"] = pd.to_datetime(
        frame["received_at"], format="mixed", utc=True
    ).dt.tz_convert(IST)
    frame = frame.sort_values(["security_id", "received_at"])
    frame = frame.drop_duplicates(["security_id", "received_at"], keep="last")
    return frame


def _minute_bars(frame: pd.DataFrame) -> pd.DataFrame:
    data = frame.set_index("received_at").sort_index()
    prices = data["last_price"].resample("1min").ohlc()
    bars = prices.rename(columns={"open": "open", "high": "high", "low": "low", "close": "close"})
    for column in [
        "day_volume",
        "vwap",
        "opening_range_high",
        "opening_range_low",
        "relative_volume",
        "spread_percent",
        "depth_imbalance",
    ]:
        bars[column] = data[column].resample("1min").last()
    bars["volume"] = bars["day_volume"].diff().clip(lower=0)
    if not bars.empty and pd.notna(bars["day_volume"].iloc[0]):
        bars.iloc[0, bars.columns.get_loc("volume")] = 0
    return bars.dropna(subset=["close"])


def _nearest_row(frame: pd.DataFrame, timestamp: pd.Timestamp) -> pd.Series | None:
    if frame.empty:
        return None
    positions = frame["received_at"].searchsorted(timestamp)
    candidates = []
    if positions < len(frame):
        candidates.append(frame.iloc[int(positions)])
    if positions > 0:
        candidates.append(frame.iloc[int(positions) - 1])
    if not candidates:
        return None
    return min(candidates, key=lambda row: abs(row["received_at"] - timestamp))


def _future_price(frame: pd.DataFrame, timestamp: pd.Timestamp, minutes: int) -> float | None:
    target = timestamp + timedelta(minutes=minutes)
    position = int(frame["received_at"].searchsorted(target))
    if position >= len(frame):
        return None
    row = frame.iloc[position]
    if row["received_at"] - target > timedelta(seconds=45):
        return None
    return float(row["last_price"])


def _path_review(
    frame: pd.DataFrame,
    timestamp: pd.Timestamp,
    entry_price: float,
    direction: str,
    minutes: int,
    threshold_percent: float = 0.20,
) -> dict[str, Any]:
    """Measure excursion and which symmetric scalp boundary was touched first."""
    if direction not in {"LONG", "SHORT"}:
        return {
            "mfe": None,
            "mae": None,
            "first_touch": "NOT_DIRECTIONAL",
            "first_touch_at": None,
        }
    end = timestamp + timedelta(minutes=minutes)
    path = frame[(frame["received_at"] >= timestamp) & (frame["received_at"] <= end)]
    if path.empty or entry_price <= 0:
        return {"mfe": None, "mae": None, "first_touch": "NO_DATA", "first_touch_at": None}
    multiplier = 1 if direction == "LONG" else -1
    returns = multiplier * (path["last_price"].astype(float) / entry_price - 1) * 100
    favorable = returns[returns >= threshold_percent]
    adverse = returns[returns <= -threshold_percent]
    favorable_time = path.loc[favorable.index[0], "received_at"] if not favorable.empty else None
    adverse_time = path.loc[adverse.index[0], "received_at"] if not adverse.empty else None
    if favorable_time is not None and (adverse_time is None or favorable_time < adverse_time):
        first_touch = "TARGET_FIRST"
        first_touch_at = favorable_time
    elif adverse_time is not None:
        first_touch = "STOP_FIRST"
        first_touch_at = adverse_time
    else:
        first_touch = "NEITHER"
        first_touch_at = None
    return {
        "mfe": round(float(returns.max()), 4),
        "mae": round(float(returns.min()), 4),
        "first_touch": first_touch,
        "first_touch_at": first_touch_at.isoformat() if first_touch_at is not None else None,
    }


def _mechanical_checks(event: dict[str, Any], tape_row: pd.Series | None) -> tuple[bool, list[str]]:
    failures: list[str] = []
    price = float(event.get("price") or 0)
    direction = str(event.get("direction"))
    setup = str(event.get("setup_type"))
    opening_range = event.get("opening_range") or {}
    buffer_fraction = 0.0005
    if setup == "ORB":
        if direction == "LONG" and price < float(opening_range.get("high") or math.inf) * (1 + buffer_fraction):
            failures.append("price_below_orb_long_threshold")
        if direction == "SHORT" and price > float(opening_range.get("low") or -math.inf) * (1 - buffer_fraction):
            failures.append("price_above_orb_short_threshold")
    if setup == "VWAP_RECLAIM_PULLBACK":
        vwap = float(event.get("vwap") or 0)
        if direction == "LONG" and price <= vwap:
            failures.append("long_not_above_vwap")
        if direction == "SHORT" and price >= vwap:
            failures.append("short_not_below_vwap")
    if tape_row is None:
        failures.append("no_nearby_snapshot")
    else:
        tape_price = float(tape_row["last_price"])
        tolerance = max(0.05, price * 0.0025)
        if abs(tape_price - price) > tolerance:
            failures.append("event_price_differs_from_tape")
        if abs(tape_row["received_at"] - event["_event_time"]) > timedelta(seconds=5):
            failures.append("snapshot_more_than_5s_away")
    return not failures, failures


def _review_event(event: dict[str, Any], tape: pd.DataFrame) -> dict[str, Any]:
    timestamp = event["_event_time"]
    nearest = _nearest_row(tape, timestamp)
    valid, failures = _mechanical_checks(event, nearest)
    direction = str(event["direction"])
    direction_multiplier = 1 if direction == "LONG" else -1 if direction == "SHORT" else None
    price = float(event["price"])
    outcomes: dict[int, float | None] = {}
    for minutes in (1, 5, 15, 30):
        later = _future_price(tape, timestamp, minutes)
        outcomes[minutes] = (
            None
            if later is None or price <= 0
            else None
            if direction_multiplier is None
            else round(direction_multiplier * (later / price - 1) * 100, 4)
        )
    path_5m = _path_review(tape, timestamp, price, event["direction"], 5)
    path_15m = _path_review(tape, timestamp, price, event["direction"], 15)
    return {
        "event_id": event["event_id"],
        "timestamp": timestamp,
        "setup": event["setup_type"],
        "direction": event["direction"],
        "score": float(event["setup_score"]),
        "price": price,
        "vwap": float(event.get("vwap") or 0),
        "rvol": event.get("relative_volume"),
        "spread": event.get("spread"),
        "imbalance": (event.get("five_level_depth_summary") or {}).get("imbalance"),
        "slippage": event.get("estimated_slippage"),
        "mechanically_valid": valid,
        "mechanical_failures": failures,
        "returns": outcomes,
        "path_5m": path_5m,
        "path_15m": path_15m,
    }


def _draw_candles(axis: Any, bars: pd.DataFrame) -> None:
    x_values = mdates.date2num(bars.index.to_pydatetime())
    width = 0.00048
    span = max(float(bars["high"].max() - bars["low"].min()), 0.01)
    min_body = span * 0.0008
    for x, (_, row) in zip(x_values, bars.iterrows()):
        rising = row["close"] >= row["open"]
        color = "#16856b" if rising else "#c84b4b"
        axis.vlines(x, row["low"], row["high"], color=color, linewidth=0.65, alpha=0.9)
        bottom = min(row["open"], row["close"])
        height = max(abs(row["close"] - row["open"]), min_body)
        axis.add_patch(Rectangle((x - width / 2, bottom), width, height, facecolor=color, edgecolor=color, linewidth=0.4))


def _make_chart(
    bars: pd.DataFrame,
    events: list[dict[str, Any]],
    symbol: str,
    output: Path,
    report_label: str = "every Intra-Finder signal",
) -> None:
    fig, (price_axis, volume_axis) = plt.subplots(
        2,
        1,
        figsize=(18, 8.5),
        sharex=True,
        gridspec_kw={"height_ratios": [4, 1]},
    )
    fig.patch.set_facecolor("#f7f8fa")
    for axis in (price_axis, volume_axis):
        axis.set_facecolor("#ffffff")
        axis.grid(True, color="#e4e7eb", linewidth=0.6, alpha=0.8)
    _draw_candles(price_axis, bars)
    price_axis.plot(bars.index, bars["vwap"], color="#6d5bd0", linewidth=1.2, label="Session VWAP")
    or_high = bars["opening_range_high"].dropna()
    or_low = bars["opening_range_low"].dropna()
    if not or_high.empty:
        price_axis.axhline(float(or_high.iloc[-1]), color="#4f6b8a", linewidth=0.9, linestyle="--", label="OR high")
    if not or_low.empty:
        price_axis.axhline(float(or_low.iloc[-1]), color="#8795a5", linewidth=0.9, linestyle="--", label="OR low")

    grouped_at_time: Counter[str] = Counter()
    for index, event in enumerate(events, 1):
        timestamp = event["_event_time"]
        key = timestamp.floor("min").isoformat()
        grouped_at_time[key] += 1
        offset = grouped_at_time[key] - 1
        price = float(event["price"])
        direction = str(event["direction"])
        is_long = direction == "LONG"
        is_short = direction == "SHORT"
        is_orb = event["setup_type"] == "ORB"
        is_indicator = event["setup_type"] == "INDICATOR_EVENT"
        marker = "D" if is_indicator else "^" if is_long else "v"
        color = "#087f5b" if is_long else "#c92a2a" if is_short else "#9c36b5"
        price_axis.scatter(
            [timestamp],
            [price],
            marker=marker,
            s=64 if is_orb or is_indicator else 52,
            facecolors=color if is_orb or is_indicator else "none",
            edgecolors=color,
            linewidths=1.1,
            zorder=6,
        )
        annotation_above = is_long or not is_short
        y_offset = (10 + offset * 11) * (1 if annotation_above else -1)
        price_axis.annotate(
            str(index),
            (timestamp, price),
            xytext=(0, y_offset),
            textcoords="offset points",
            ha="center",
            va="bottom" if annotation_above else "top",
            fontsize=7,
            color=color,
            fontweight="bold",
        )

    volumes = bars["volume"].fillna(0)
    volume_colors = np.where(bars["close"] >= bars["open"], "#7bc8b7", "#e59a9a")
    volume_axis.bar(bars.index, volumes, width=0.00055, color=volume_colors, edgecolor="none")
    volume_axis.set_ylabel("Volume/min")
    volume_axis.xaxis.set_major_locator(mdates.HourLocator())
    volume_axis.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=bars.index.tz))
    price_axis.set_ylabel("Price (INR)")
    price_axis.set_title(f"{symbol} — one-minute replay with {report_label}", loc="left", fontsize=14)
    price_axis.legend(loc="upper left", ncol=3, frameon=False, fontsize=8)
    volume_axis.set_xlabel("Market time (IST)")
    fig.text(
        0.995,
        0.01,
        "Diamond = indicator-event aggregate · Filled triangle = legacy ORB · Hollow triangle = legacy VWAP · Green = long · Red = short · Purple = mixed/neutral · Number = event table row",
        ha="right",
        fontsize=8,
        color="#4d5966",
    )
    fig.tight_layout(rect=(0.02, 0.03, 0.99, 0.98))
    fig.savefig(output, dpi=135, bbox_inches="tight")
    plt.close(fig)


def _format_number(value: Any, digits: int = 3) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "—"
    return f"{float(value):.{digits}f}"


def _stock_page(
    symbol: str,
    security_id: int,
    chart_name: str,
    reviewed: list[dict[str, Any]],
    output: Path,
    report_label: str = "saved Stage 2 signals",
) -> None:
    rows = []
    for index, item in enumerate(reviewed, 1):
        returns = item["returns"]
        status = "PASS" if item["mechanically_valid"] else "CHECK"
        failures = ", ".join(item["mechanical_failures"]) or "—"
        rows.append(
            "<tr>"
            f"<td>{index}</td><td>{html.escape(item['timestamp'].strftime('%H:%M:%S'))}</td>"
            f"<td>{html.escape(item['setup'])}</td><td>{html.escape(item['direction'])}</td>"
            f"<td>{item['score']:.2f}</td><td>{item['price']:.2f}</td><td>{item['vwap']:.2f}</td>"
            f"<td>{_format_number(item['rvol'], 2)}</td><td>{_format_number(item['spread'], 4)}</td>"
            f"<td>{_format_number(item['imbalance'], 3)}</td><td>{_format_number(returns[1])}%</td>"
            f"<td>{_format_number(returns[5])}%</td><td>{_format_number(returns[15])}%</td>"
            f"<td>{_format_number(returns[30])}%</td>"
            f"<td>{_format_number(item['path_5m']['mfe'])}%</td>"
            f"<td>{_format_number(item['path_5m']['mae'])}%</td>"
            f"<td>{html.escape(item['path_5m']['first_touch'])}</td>"
            f"<td>{status}</td><td>{html.escape(failures)}</td>"
            "</tr>"
        )
    document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(symbol)} signal review</title>
<style>
body{{font-family:system-ui,sans-serif;margin:24px;color:#17212b;background:#f7f8fa}}a{{color:#315b9c}}img{{width:100%;height:auto;background:#fff;border:1px solid #dce1e7}}table{{width:100%;border-collapse:collapse;background:#fff;font-size:12px}}th,td{{padding:7px;border-bottom:1px solid #e4e7eb;text-align:right}}th{{position:sticky;top:0;background:#eef1f4}}th:nth-child(2),td:nth-child(2),th:nth-child(3),td:nth-child(3),th:nth-child(4),td:nth-child(4),th:last-child,td:last-child{{text-align:left}}.scroll{{overflow:auto}}code{{background:#e9edf2;padding:2px 5px}}</style></head>
<body><p><a href="../index.html">← All stocks</a></p><h1>{html.escape(symbol)}</h1>
<p>Security ID <code>{security_id}</code> · {len(reviewed)} {html.escape(report_label)}. Direction-adjusted returns: positive means the signal moved correctly.</p>
<img src="../charts/{html.escape(chart_name)}" alt="One-minute candlestick chart with Stage 2 signals">
<div class="scroll"><table><thead><tr><th>#</th><th>Time</th><th>Setup</th><th>Side</th><th>Score</th><th>Price</th><th>VWAP</th><th>RVOL</th><th>Spread %</th><th>Depth</th><th>1m</th><th>5m</th><th>15m</th><th>30m</th><th>5m MFE</th><th>5m MAE</th><th>First +/-0.20%</th><th>Rule check</th><th>Reason</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></div></body></html>"""
    output.write_text(document, encoding="utf-8")


def _index_page(rows: list[dict[str, Any]], summary: dict[str, Any], output: Path) -> None:
    table_rows = []
    for row in rows:
        table_rows.append(
            "<tr "
            f"data-text=\"{html.escape((row['symbol']+' '+row['setups']+' '+row['directions']).lower())}\">"
            f"<td><a href=\"stocks/{html.escape(row['page'])}\">{html.escape(row['symbol'])}</a></td>"
            f"<td>{row['security_id']}</td><td>{row['event_count']}</td><td>{html.escape(row['setups'])}</td>"
            f"<td>{html.escape(row['directions'])}</td><td>{row['mean_score']:.2f}</td>"
            f"<td>{row['mechanical_passes']}/{row['event_count']}</td>"
            f"<td>{_format_number(row['median_5m'])}%</td><td>{_format_number(row['median_15m'])}%</td>"
            f"<td>{_format_number(row['median_30m'])}%</td></tr>"
        )
    document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(summary['report_title'])} {html.escape(summary['market_date'])}</title>
<style>
body{{font-family:system-ui,sans-serif;margin:24px;color:#17212b;background:#f7f8fa}}a{{color:#315b9c}}input{{padding:9px;width:min(430px,90%);margin:8px 0 16px}}table{{width:100%;border-collapse:collapse;background:#fff;font-size:13px}}th,td{{padding:8px;border-bottom:1px solid #e4e7eb;text-align:right}}th{{position:sticky;top:0;background:#eef1f4}}th:first-child,td:first-child,th:nth-child(4),td:nth-child(4),th:nth-child(5),td:nth-child(5){{text-align:left}}.scroll{{overflow:auto}}.note{{max-width:1000px}}code{{background:#e9edf2;padding:2px 5px}}</style></head>
<body><h1>{html.escape(summary['report_title'])} — {html.escape(summary['market_date'])}</h1>
<p class="note">{summary['event_count']} {html.escape(summary['report_label'])} across {summary['stock_count']} stocks. Rule checks confirm nearby tape consistency and, for legacy events, the saved ORB/VWAP definition; they do not prove profitability. Open a stock to inspect every numbered entry on its replay chart.</p>
<p><a href="review-summary.json">Machine-readable summary</a> · <a href="signals.csv">All signal measurements</a></p>
<label for="filter">Find a stock, setup, or direction</label><br><input id="filter" type="search" placeholder="Example: MARICO, ORB, SHORT">
<div class="scroll"><table><thead><tr><th>Stock</th><th>Security ID</th><th>Signals</th><th>Setups</th><th>Sides</th><th>Mean score</th><th>Rule pass</th><th>Median 5m</th><th>Median 15m</th><th>Median 30m</th></tr></thead><tbody id="stocks">{''.join(table_rows)}</tbody></table></div>
<script>const q=document.getElementById('filter');q.addEventListener('input',()=>{{const v=q.value.trim().toLowerCase();document.querySelectorAll('#stocks tr').forEach(r=>r.hidden=v&&!r.dataset.text.includes(v));}});</script>
</body></html>"""
    output.write_text(document, encoding="utf-8")


def _median(values: Iterable[float | None]) -> float | None:
    present = [float(value) for value in values if value is not None]
    return round(float(np.median(present)), 4) if present else None


def generate(
    paths: ReviewPaths,
    limit: int | None = None,
    reuse_charts: bool = False,
) -> dict[str, Any]:
    events = _load_events(paths.events)
    quality_mode = paths.quality_events is not None
    if quality_mode:
        quality_rows = _selected_quality_rows(paths.quality_events, paths.stage2_day.name)
        events = _apply_quality_selection(events, quality_rows)
    if not events:
        raise RuntimeError("No matching setup events were found")
    report_label = "quality-v3 selected entries" if quality_mode else "saved Stage 2 signals"
    chart_label = "quality-v3 selected entries" if quality_mode else "every Intra-Finder signal"
    by_security: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        by_security[int(event["security_id"])].append(event)
    ordered_ids = sorted(by_security, key=lambda key: (-len(by_security[key]), key))
    if limit:
        ordered_ids = ordered_ids[:limit]
        events = [event for security_id in ordered_ids for event in by_security[security_id]]

    paths.output.mkdir(parents=True, exist_ok=True)
    chart_dir = paths.output / "charts"
    stock_dir = paths.output / "stocks"
    chart_dir.mkdir(exist_ok=True)
    stock_dir.mkdir(exist_ok=True)
    snapshots = _load_snapshots(paths.snapshots, set(ordered_ids))

    signal_rows: list[dict[str, Any]] = []
    stock_rows: list[dict[str, Any]] = []
    for number, security_id in enumerate(ordered_ids, 1):
        stock_events = sorted(by_security[security_id], key=lambda event: event["_event_time"])
        tape = snapshots[snapshots["security_id"] == security_id].copy().reset_index(drop=True)
        if tape.empty:
            continue
        symbol = str(stock_events[0].get("symbol") or tape["symbol"].iloc[0] or security_id)
        slug = f"{security_id}-{_safe_slug(symbol)}"
        reviewed = [_review_event(event, tape) for event in stock_events]
        bars = _minute_bars(tape)
        chart_name = f"{slug}.png"
        page_name = f"{slug}.html"
        chart_path = chart_dir / chart_name
        if not reuse_charts or not chart_path.exists():
            _make_chart(bars, stock_events, symbol, chart_path, chart_label)
        _stock_page(
            symbol,
            security_id,
            chart_name,
            reviewed,
            stock_dir / page_name,
            report_label,
        )
        for item in reviewed:
            signal_rows.append(
                {
                    "symbol": symbol,
                    "security_id": security_id,
                    "event_id": item["event_id"],
                    "timestamp_ist": item["timestamp"].isoformat(),
                    "setup": item["setup"],
                    "direction": item["direction"],
                    "score": item["score"],
                    "raw_stage2_score": next(
                        (
                            event.get("_raw_setup_score")
                            for event in stock_events
                            if event.get("event_id") == item["event_id"]
                        ),
                        item["score"],
                    ),
                    "price": item["price"],
                    "vwap": item["vwap"],
                    "rvol": item["rvol"],
                    "spread_percent": item["spread"],
                    "depth_imbalance": item["imbalance"],
                    "slippage_percent": item["slippage"],
                    "mechanically_valid": item["mechanically_valid"],
                    "mechanical_failures": "|".join(item["mechanical_failures"]),
                    "return_1m_percent": item["returns"][1],
                    "return_5m_percent": item["returns"][5],
                    "return_15m_percent": item["returns"][15],
                    "return_30m_percent": item["returns"][30],
                    "mfe_5m_percent": item["path_5m"]["mfe"],
                    "mae_5m_percent": item["path_5m"]["mae"],
                    "first_touch_5m_0_20_percent": item["path_5m"]["first_touch"],
                    "first_touch_5m_at": item["path_5m"]["first_touch_at"],
                    "mfe_15m_percent": item["path_15m"]["mfe"],
                    "mae_15m_percent": item["path_15m"]["mae"],
                    "first_touch_15m_0_20_percent": item["path_15m"]["first_touch"],
                    "first_touch_15m_at": item["path_15m"]["first_touch_at"],
                    "chart": f"charts/{chart_name}",
                    "page": f"stocks/{page_name}",
                }
            )
        stock_rows.append(
            {
                "symbol": symbol,
                "security_id": security_id,
                "event_count": len(reviewed),
                "setups": ", ".join(sorted({item["setup"] for item in reviewed})),
                "directions": ", ".join(sorted({item["direction"] for item in reviewed})),
                "mean_score": float(np.mean([item["score"] for item in reviewed])),
                "mechanical_passes": sum(item["mechanically_valid"] for item in reviewed),
                "median_5m": _median(item["returns"][5] for item in reviewed),
                "median_15m": _median(item["returns"][15] for item in reviewed),
                "median_30m": _median(item["returns"][30] for item in reviewed),
                "page": page_name,
            }
        )
        if number % 25 == 0 or number == len(ordered_ids):
            print(f"Rendered {number}/{len(ordered_ids)} stock charts", flush=True)

    csv_path = paths.output / "signals.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(signal_rows[0]))
        writer.writeheader()
        writer.writerows(signal_rows)

    returns_15 = [row["return_15m_percent"] for row in signal_rows if row["return_15m_percent"] is not None]
    first_touch_5m = Counter(row["first_touch_5m_0_20_percent"] for row in signal_rows)
    first_touch_15m = Counter(row["first_touch_15m_0_20_percent"] for row in signal_rows)
    summary = {
        "market_date": str(events[0]["market_date"]),
        "report_title": "Stage 2 quality-entry review" if quality_mode else "Stage 2 signal review",
        "report_label": report_label,
        "selection_source": str(paths.quality_events.resolve()) if paths.quality_events else None,
        "generated_at": datetime.now().astimezone().isoformat(),
        "event_count": len(signal_rows),
        "stock_count": len(stock_rows),
        "mechanically_valid": sum(row["mechanically_valid"] for row in signal_rows),
        "mechanically_invalid": sum(not row["mechanically_valid"] for row in signal_rows),
        "mechanical_failure_counts": dict(
            Counter(
                reason
                for row in signal_rows
                for reason in str(row["mechanical_failures"]).split("|")
                if reason
            )
        ),
        "median_direction_adjusted_return_15m_percent": _median(returns_15),
        "positive_direction_adjusted_return_15m_percent": round(
            100 * sum(value > 0 for value in returns_15) / len(returns_15), 2
        ) if returns_15 else None,
        "first_touch_5m_at_0_20_percent": dict(first_touch_5m),
        "first_touch_15m_at_0_20_percent": dict(first_touch_15m),
        "output": str(paths.output.resolve()),
    }
    (paths.output / "review-summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    _index_page(stock_rows, summary, paths.output / "index.html")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True, help="Market date in YYYY-MM-DD format")
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "results",
        help="Pipeline results directory",
    )
    parser.add_argument("--output", type=Path, help="Optional report output directory")
    parser.add_argument(
        "--quality-events",
        type=Path,
        help="Optional all-evaluated-events.csv; render only rows selected by the quality policy",
    )
    parser.add_argument("--limit", type=int, help="Render only the busiest N stocks (for testing)")
    parser.add_argument(
        "--reuse-charts",
        action="store_true",
        help="Keep existing PNG charts while rebuilding measurements and HTML pages",
    )
    args = parser.parse_args()
    stage2_day = args.results_dir / "stage2" / args.date
    output = args.output or stage2_day / (
        "quality-entry-review" if args.quality_events else "signal-review"
    )
    summary = generate(
        ReviewPaths(
            stage2_day=stage2_day,
            output=output,
            quality_events=args.quality_events,
        ),
        limit=args.limit,
        reuse_charts=args.reuse_charts,
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
