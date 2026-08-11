"""Leakage-safe replay of the production indicator-event detector.

Saved one-second observations are read-only inputs.  Reports are written to a
separate research directory and never back into Stage 2's live input folders.
"""

from __future__ import annotations

from collections import Counter
from datetime import timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List

import pandas as pd
import pyarrow as pa
import pyarrow.dataset as pads

from pipeline.stages.indicator_event_engine import IndicatorEventEngine
from pipeline.stages.trade_readiness import evaluate_trade_readiness


REPLAY_COLUMNS = [
    "received_at",
    "security_id",
    "exchange_segment",
    "symbol",
    "last_price",
    "day_volume",
    "vwap",
    "opening_range_high",
    "opening_range_low",
    "spread_percent",
    "estimated_slippage_percent",
    "connection_warm",
    "best_bid",
    "best_ask",
    "bid_quantity_5",
    "ask_quantity_5",
    "relative_volume",
    "volume_acceleration",
    "depth_imbalance",
    "order_count_imbalance",
]


def _partial_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    frame["received_at"] = pd.to_datetime(frame["received_at"], errors="coerce", utc=True)
    for column in ("security_id", "last_price", "day_volume"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna(subset=["received_at", "security_id", "last_price"])
    if frame.empty:
        return frame
    frame["security_id"] = frame["security_id"].astype(int)
    frame["minute"] = frame["received_at"].dt.floor("min")
    frame = frame.sort_values("received_at")
    keys = ["security_id", "minute"]
    grouped = frame.groupby(keys, sort=False, observed=True)
    result = grouped.agg(
        first_at=("received_at", "first"),
        last_at=("received_at", "last"),
        open=("last_price", "first"),
        high=("last_price", "max"),
        low=("last_price", "min"),
        close=("last_price", "last"),
        cumulative_volume=("day_volume", "max"),
        exchange_segment=("exchange_segment", "last"),
        symbol=("symbol", "last"),
        vwap=("vwap", "last"),
        opening_range_high=("opening_range_high", "last"),
        opening_range_low=("opening_range_low", "last"),
        spread_percent=("spread_percent", "last"),
        estimated_slippage_percent=("estimated_slippage_percent", "last"),
        connection_warm=("connection_warm", "last"),
        best_bid=("best_bid", "last"),
        best_ask=("best_ask", "last"),
        bid_quantity_5=("bid_quantity_5", "last"),
        ask_quantity_5=("ask_quantity_5", "last"),
        relative_volume=("relative_volume", "last"),
        volume_acceleration=("volume_acceleration", "last"),
        depth_imbalance=("depth_imbalance", "median"),
        order_count_imbalance=("order_count_imbalance", "median"),
    )
    return result.reset_index()


def _partial_minutes(path: Path) -> pd.DataFrame:
    return _partial_frame(pd.read_parquet(path, columns=REPLAY_COLUMNS))


def load_recorded_minutes(one_second_root: Path) -> pd.DataFrame:
    """Collapse many small one-second Parquet files without loading all ticks at once."""
    schema = pa.schema(
        [
            pa.field("received_at", pa.string()),
            pa.field("security_id", pa.int64()),
            pa.field("exchange_segment", pa.string()),
            pa.field("symbol", pa.string()),
            *[
                pa.field(name, pa.float64())
                for name in (
                    "last_price",
                    "day_volume",
                    "vwap",
                    "opening_range_high",
                    "opening_range_low",
                    "spread_percent",
                    "estimated_slippage_percent",
                    "relative_volume",
                    "volume_acceleration",
                    "depth_imbalance",
                    "order_count_imbalance",
                )
            ],
            pa.field("connection_warm", pa.bool_()),
            *[
                pa.field(name, pa.float64())
                for name in ("best_bid", "best_ask", "bid_quantity_5", "ask_quantity_5")
            ],
        ]
    )
    dataset = pads.dataset(one_second_root, format="parquet", partitioning="hive", schema=schema)
    partials: List[pd.DataFrame] = []
    for batch in dataset.scanner(columns=REPLAY_COLUMNS, batch_size=500_000).to_batches():
        partial = _partial_frame(batch.to_pandas())
        if not partial.empty:
            partials.append(partial)
    if not partials:
        return pd.DataFrame()
    frame = pd.concat(partials, ignore_index=True).sort_values(
        ["security_id", "minute", "first_at"]
    )
    keys = ["security_id", "minute"]
    grouped = frame.groupby(keys, sort=False, observed=True)
    combined = grouped.agg(
        first_at=("first_at", "min"),
        last_at=("last_at", "max"),
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        cumulative_volume=("cumulative_volume", "max"),
        exchange_segment=("exchange_segment", "last"),
        symbol=("symbol", "last"),
        vwap=("vwap", "last"),
        opening_range_high=("opening_range_high", "last"),
        opening_range_low=("opening_range_low", "last"),
        spread_percent=("spread_percent", "last"),
        estimated_slippage_percent=("estimated_slippage_percent", "last"),
        connection_warm=("connection_warm", "last"),
        best_bid=("best_bid", "last"),
        best_ask=("best_ask", "last"),
        bid_quantity_5=("bid_quantity_5", "last"),
        ask_quantity_5=("ask_quantity_5", "last"),
        relative_volume=("relative_volume", "last"),
        volume_acceleration=("volume_acceleration", "last"),
        depth_imbalance=("depth_imbalance", "median"),
        order_count_imbalance=("order_count_imbalance", "median"),
    ).reset_index()
    combined = combined.sort_values(["security_id", "minute"])
    combined["volume"] = (
        combined.groupby("security_id", observed=True)["cumulative_volume"]
        .diff()
        .clip(lower=0)
        .fillna(0.0)
    )
    return combined


def _replay_safety_failures(row: pd.Series) -> List[str]:
    """Approximate production safety gates from normalized saved fields.

    Full depth arrays are not present in the one-second files, so non-zero
    top-five quantities act only as a recorded-depth-availability proxy.
    """
    failures: List[str] = []
    spread = pd.to_numeric(row.get("spread_percent"), errors="coerce")
    slippage = pd.to_numeric(row.get("estimated_slippage_percent"), errors="coerce")
    if pd.isna(spread) or float(spread) > 0.20:
        failures.append("SPREAD_TOO_WIDE")
    if pd.isna(slippage) or float(slippage) > 0.20:
        failures.append("INSUFFICIENT_DEPTH_CAPACITY")
    if not bool(row.get("connection_warm")):
        failures.append("CONNECTION_WARMING_UP")
    if float(row.get("bid_quantity_5") or 0) <= 0 or float(row.get("ask_quantity_5") or 0) <= 0:
        failures.append("DEPTH_PROXY_UNAVAILABLE")
    if pd.Timestamp(row["minute"]).tz_convert("Asia/Kolkata").time().isoformat() >= "15:00:00":
        failures.append("ENTRY_CUTOFF")
    return failures


def replay_indicator_events(
    minutes: pd.DataFrame,
    *,
    aggregation_seconds: int = 60,
    event_cooldown_seconds: int = 600,
    stock_agent_cooldown_seconds: int = 1200,
    volume_surge_ratio: float = 1.8,
    readiness_score_threshold: float = 75.0,
    readiness_direction_margin: float = 10.0,
    readiness_min_completed_bars: int = 45,
) -> Dict[str, Any]:
    event_counts: Counter[str] = Counter()
    direction_counts: Counter[str] = Counter()
    gate_counts: Counter[str] = Counter()
    aggregates: List[Dict[str, Any]] = []
    detected_event_total = 0
    readiness_passed = 0
    readiness_failure_counts: Counter[str] = Counter()

    for security_id, stock_rows in minutes.groupby("security_id", sort=False, observed=True):
        engine = IndicatorEventEngine(
            event_cooldown_seconds=event_cooldown_seconds,
            volume_surge_ratio=volume_surge_ratio,
        )
        state = IndicatorEventEngine.state_fields()
        pending: List[Dict[str, Any]] = []
        deadline: pd.Timestamp | None = None
        last_agent_at: pd.Timestamp | None = None

        def flush(row: pd.Series, at: pd.Timestamp) -> None:
            nonlocal pending, deadline, last_agent_at, readiness_passed
            if not pending:
                return
            directions = {item["direction"] for item in pending if item["direction"] in {"LONG", "SHORT"}}
            direction = (
                "LONG" if directions == {"LONG"} else
                "SHORT" if directions == {"SHORT"} else
                "MIXED" if directions == {"LONG", "SHORT"} else
                "NEUTRAL"
            )
            failures = _replay_safety_failures(row)
            if last_agent_at is not None and (at - last_agent_at).total_seconds() < stock_agent_cooldown_seconds:
                failures.append("STOCK_AGENT_COOLDOWN")
            gate_counts.update(failures)
            features = {
                "received_at": at.isoformat(),
                "last_price": float(row["close"]),
                "vwap": None if pd.isna(row.get("vwap")) else float(row["vwap"]),
                "opening_range_high": None if pd.isna(row.get("opening_range_high")) else float(row["opening_range_high"]),
                "opening_range_low": None if pd.isna(row.get("opening_range_low")) else float(row["opening_range_low"]),
                "relative_volume": None if pd.isna(row.get("relative_volume")) else float(row["relative_volume"]),
                "volume_acceleration": None if pd.isna(row.get("volume_acceleration")) else float(row["volume_acceleration"]),
                "spread_percent": None if pd.isna(row.get("spread_percent")) else float(row["spread_percent"]),
                "estimated_slippage_percent": None if pd.isna(row.get("estimated_slippage_percent")) else float(row["estimated_slippage_percent"]),
                "depth_imbalance_median_30s": None if pd.isna(row.get("depth_imbalance")) else float(row["depth_imbalance"]),
                "order_count_imbalance_median_30s": None if pd.isna(row.get("order_count_imbalance")) else float(row["order_count_imbalance"]),
                "depth_sample_count_30s": 0,
                # LTT was not persisted in older sessions.  Keep it unknown so
                # replay cannot invent trade freshness.
                "last_trade_age_seconds": None,
            }
            readiness = evaluate_trade_readiness(
                bars=list(state.get("minute_bars") or []),
                events=pending,
                features=features,
                threshold=readiness_score_threshold,
                direction_margin=readiness_direction_margin,
                min_completed_bars=readiness_min_completed_bars,
            )
            readiness_failure_counts.update(readiness.get("failures") or [])
            safety_accepted = not failures
            accepted = safety_accepted and bool(readiness.get("ready"))
            if accepted:
                last_agent_at = at
                readiness_passed += 1
            aggregates.append(
                {
                    "security_id": int(security_id),
                    "symbol": str(row.get("symbol") or ""),
                    "at": at.isoformat(),
                    "direction": direction,
                    "event_types": [item["event_type"] for item in pending],
                    "accepted_by_approximate_safety_gates": safety_accepted,
                    "accepted_by_trade_readiness": accepted,
                    "failures": failures,
                    "readiness": readiness,
                }
            )
            direction_counts[direction] += 1
            weak_types = {
                "DOJI",
                "VOLUME_SURGE",
                "RSI_ENTERED_OVERSOLD",
                "RSI_ENTERED_OVERBOUGHT",
            }
            event_types = {str(item.get("event_type") or "") for item in pending}
            weak_only = bool(event_types) and event_types.issubset(weak_types)
            evidence_ages = []
            for item in pending:
                try:
                    evidence_ages.append(
                        max(
                            0.0,
                            (
                                at
                                - pd.Timestamp(item.get("detected_at"))
                            ).total_seconds(),
                        )
                    )
                except (TypeError, ValueError):
                    evidence_ages.append(601.0)
            expired = bool(evidence_ages) and max(evidence_ages) >= 600.0
            if accepted or failures or weak_only or expired:
                pending = []
                deadline = None
            else:
                deadline = at + timedelta(seconds=60)

        previous_row: pd.Series | None = None
        for _, row in stock_rows.sort_values("minute").iterrows():
            detected_at = pd.Timestamp(row["minute"]) + timedelta(minutes=1)
            opening_high = pd.to_numeric(row.get("opening_range_high"), errors="coerce")
            opening_low = pd.to_numeric(row.get("opening_range_low"), errors="coerce")
            bar = {
                "minute_start": pd.Timestamp(row["minute"]).isoformat(),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row["volume"]),
                "vwap": None if pd.isna(row.get("vwap")) else float(row["vwap"]),
            }
            events = engine.on_closed_bar(
                state,
                bar=bar,
                detected_at=detected_at.to_pydatetime(),
                opening_range_high=None if pd.isna(opening_high) else float(opening_high),
                opening_range_low=None if pd.isna(opening_low) else float(opening_low),
                opening_range_complete=detected_at.tz_convert("Asia/Kolkata").time().isoformat() >= "09:30:00",
            )
            for event in events:
                event_counts[event["event_type"]] += 1
            detected_event_total += len(events)
            if events:
                if deadline is None:
                    deadline = detected_at + timedelta(seconds=aggregation_seconds)
                pending.extend(events)
            if deadline is not None and detected_at >= deadline:
                flush(row, detected_at)
            previous_row = row
        if pending and previous_row is not None:
            flush(previous_row, deadline or pd.Timestamp(previous_row["minute"]) + timedelta(minutes=1))

    accepted = sum(item["accepted_by_approximate_safety_gates"] for item in aggregates)
    return {
        "method": "causal_completed_one_minute_bars",
        "input_minute_rows": int(len(minutes)),
        "stocks": int(minutes["security_id"].nunique()) if not minutes.empty else 0,
        "indicator_events_detected": detected_event_total,
        "event_type_counts": dict(event_counts.most_common()),
        "aggregates_formed": len(aggregates),
        "aggregates_passing_approximate_safety_gates": accepted,
        "aggregates_passing_trade_readiness": readiness_passed,
        "direction_counts": dict(direction_counts.most_common()),
        "gate_failure_counts": dict(gate_counts.most_common()),
        "readiness_failure_counts": dict(readiness_failure_counts.most_common()),
        "parameters": {
            "aggregation_seconds": aggregation_seconds,
            "event_cooldown_seconds": event_cooldown_seconds,
            "stock_agent_cooldown_seconds": stock_agent_cooldown_seconds,
            "volume_surge_ratio": volume_surge_ratio,
            "readiness_score_threshold": readiness_score_threshold,
            "readiness_direction_margin": readiness_direction_margin,
            "readiness_min_completed_bars": readiness_min_completed_bars,
        },
        "limitations": [
            "One-second snapshots preserve top-five summaries, not full depth arrays; depth completeness is approximated.",
            "This report measures detector volume and operational gating, not profitability.",
            "Missing portions of a recorded session remain missing and are not synthesized.",
            "Historical recordings before this change do not contain exchange last-trade time or persistent depth sample counts.",
        ],
        "aggregates": aggregates,
    }
