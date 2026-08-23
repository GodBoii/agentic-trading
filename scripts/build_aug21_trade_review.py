#!/usr/bin/env python3
"""Build the static August 21, 2026 stock-agent review dataset.

The report joins three sources that were written by the live system:

* Supabase ``agno_sessions`` rows for the agent response and tool calls.
* Stage 2 ``setup-events.jsonl`` for the signal that launched each agent.
* Stage 2 one-second Parquet snapshots for the intraday price path.

No broker or database records are changed. The generated JSON is safe to serve
as a static local file and intentionally excludes user IDs and credentials.
"""

from __future__ import annotations

import json
import os
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow.compute as pc
import pyarrow.dataset as ds
import requests
from dotenv import dotenv_values


ROOT = Path(__file__).resolve().parent.parent
MARKET_DATE = "2026-08-21"
MARKET_TIMEZONE = "Asia/Kolkata"
EVENTS_PATH = ROOT / "python-backend" / "results" / "stage2" / MARKET_DATE / "setup-events.jsonl"
SNAPSHOTS_PATH = ROOT / "python-backend" / "results" / "stage2" / MARKET_DATE / "one-second"
OUTPUT_PATH = ROOT / "august-21-trade-review" / "data.json"
SESSION_START_UTC = int(datetime(2026, 8, 20, 18, 30, tzinfo=timezone.utc).timestamp())
SESSION_END_UTC = int(datetime(2026, 8, 21, 18, 30, tzinfo=timezone.utc).timestamp())


def load_environment() -> dict[str, str]:
    values: dict[str, str] = {}
    for path in (ROOT / ".env", ROOT / ".env.local", ROOT / "python-backend" / ".env"):
        if path.exists():
            values.update({key: str(value) for key, value in dotenv_values(path).items() if value})
    values.update({key: value for key, value in os.environ.items() if value})
    return values


def fetch_agent_sessions(environment: dict[str, str]) -> list[dict[str, Any]]:
    base_url = environment.get("NEXT_PUBLIC_SUPABASE_URL", "").rstrip("/")
    service_key = environment.get("SUPABASE_SERVICE_ROLE_KEY", "")
    table = environment.get("AGNO_SESSION_TABLE", "agno_sessions")
    if not base_url or not service_key:
        raise RuntimeError("Supabase service credentials are not configured")

    response = requests.get(
        f"{base_url}/rest/v1/{table}",
        headers={"apikey": service_key, "Authorization": f"Bearer {service_key}"},
        params={
            "select": "session_id,metadata,runs,created_at,updated_at",
            "created_at": f"gte.{SESSION_START_UTC}",
            "and": f"(created_at.lt.{SESSION_END_UTC},metadata->>stage.eq.stock_agent)",
            "order": "created_at.asc",
        },
        timeout=60,
    )
    response.raise_for_status()
    rows = response.json()
    if not isinstance(rows, list):
        raise RuntimeError("Supabase returned an unexpected session payload")
    return rows


def load_setup_events() -> dict[str, dict[str, Any]]:
    events: dict[str, dict[str, Any]] = {}
    with EVENTS_PATH.open("r", encoding="utf-8") as handle:
        for line in handle:
            event = json.loads(line)
            event_id = str(event.get("event_id") or "")
            if event_id:
                events[event_id] = event
    return events


def parse_tool_arguments(run: dict[str, Any], tool_name: str) -> dict[str, Any] | None:
    for message in run.get("messages") or []:
        for call in message.get("tool_calls") or []:
            function = call.get("function") or {}
            if function.get("name") != tool_name:
                continue
            arguments = function.get("arguments")
            if isinstance(arguments, dict):
                return arguments
            if isinstance(arguments, str):
                try:
                    parsed = json.loads(arguments)
                except json.JSONDecodeError:
                    continue
                if isinstance(parsed, dict):
                    return parsed
    return None


def tool_messages(run: dict[str, Any], tool_name: str) -> list[str]:
    return [
        str(message.get("content") or "")
        for message in run.get("messages") or []
        if message.get("tool_name") == tool_name
    ]


def parse_result_field(result: str, name: str) -> str | None:
    match = re.search(rf"(?:^|\n)-\s*{re.escape(name)}:\s*([^\n]+)", result, flags=re.IGNORECASE)
    return match.group(1).strip() if match else None


def tool_event_time(run: dict[str, Any], tool_name: str) -> int | None:
    for event in reversed(run.get("events") or []):
        tool = event.get("tool") or {}
        if tool.get("tool_name") == tool_name and event.get("created_at"):
            return int(event["created_at"])
    return None


def build_order(run: dict[str, Any]) -> dict[str, Any] | None:
    arguments = parse_tool_arguments(run, "place_protected_intraday_order")
    if not arguments:
        return None

    messages = tool_messages(run, "place_protected_intraday_order")
    result = messages[-1] if messages else ""
    broker_status = parse_result_field(result, "broker_order_status")
    reached_broker = broker_status is not None
    blocked_reason = None
    if not reached_broker:
        compact = " ".join(result.split())
        blocked_reason = compact[:300] or "The order tool produced no broker result."

    return {
        "side": arguments.get("side"),
        "quantity": number_or_none(arguments.get("quantity")),
        "entry": number_or_none(arguments.get("entry_price")),
        "target": number_or_none(arguments.get("target_price")),
        "stop": number_or_none(arguments.get("stop_loss_price")),
        "order_type": arguments.get("order_type"),
        "trailing_jump": number_or_none(arguments.get("trailing_jump")),
        "correlation_id": arguments.get("correlation_id"),
        "attempted_at_epoch": tool_event_time(run, "place_protected_intraday_order"),
        "reached_broker": reached_broker,
        "broker_status": broker_status or "NOT_SENT",
        "filled_quantity": number_or_none(parse_result_field(result, "filled_quantity")),
        "order_id": parse_result_field(result, "order_id"),
        "blocked_reason": blocked_reason,
    }


def number_or_none(value: Any) -> float | int | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return int(number) if number.is_integer() else number


def epoch_to_iso(value: Any) -> str | None:
    number = number_or_none(value)
    if number is None:
        return None
    return datetime.fromtimestamp(float(number), tz=timezone.utc).isoformat().replace("+00:00", "Z")


def event_summary(event: dict[str, Any]) -> dict[str, Any]:
    readiness = event.get("trade_readiness") or {}
    diagnostics = readiness.get("diagnostics") or {}
    indicator_events = event.get("indicator_events") or []
    return {
        "time": event.get("created_at"),
        "price": number_or_none(event.get("price")),
        "direction": event.get("direction"),
        "setup_type": event.get("setup_type"),
        "setup_score": number_or_none(event.get("setup_score")),
        "entry_zone": [number_or_none(value) for value in event.get("entry_zone") or []],
        "vwap": number_or_none(event.get("vwap")),
        "relative_volume": number_or_none(event.get("relative_volume")),
        "volume_acceleration": number_or_none(event.get("volume_acceleration")),
        "trigger_rule": event.get("event_trigger_rule"),
        "ready": readiness.get("ready"),
        "readiness_failures": readiness.get("failures") or [],
        "nearest_support": number_or_none(diagnostics.get("nearest_support")),
        "nearest_resistance": number_or_none(diagnostics.get("nearest_resistance")),
        "indicators": [
            {
                "type": indicator.get("event_type"),
                "direction": indicator.get("direction"),
                "time": indicator.get("detected_at"),
                "timeframe": indicator.get("timeframe"),
                "price": number_or_none(indicator.get("price")),
            }
            for indicator in indicator_events
        ],
    }


def read_candles(security_ids: list[int]) -> dict[int, list[dict[str, Any]]]:
    dataset = ds.dataset(SNAPSHOTS_PATH, format="parquet", partitioning="hive")
    table = dataset.to_table(
        columns=["received_at", "security_id", "last_price", "day_volume"],
        filter=pc.field("security_id").isin(security_ids),
    )
    frame = table.to_pandas()
    frame["received_at"] = pd.to_datetime(frame["received_at"], errors="coerce", utc=True).dt.tz_convert(
        MARKET_TIMEZONE
    )
    frame["last_price"] = pd.to_numeric(frame["last_price"], errors="coerce")
    frame["day_volume"] = pd.to_numeric(frame["day_volume"], errors="coerce")
    frame = frame.dropna(subset=["received_at", "security_id", "last_price"])
    frame = frame.sort_values(["security_id", "received_at"])
    frame["bucket"] = frame["received_at"].dt.floor("15min")

    output: dict[int, list[dict[str, Any]]] = {}
    for (security_id, bucket), group in frame.groupby(["security_id", "bucket"], sort=True):
        prices = group["last_price"]
        volumes = group["day_volume"].dropna()
        volume = max(float(volumes.iloc[-1] - volumes.iloc[0]), 0.0) if len(volumes) > 1 else 0.0
        output.setdefault(int(security_id), []).append(
            {
                "time": bucket.isoformat(),
                "open": round(float(prices.iloc[0]), 4),
                "high": round(float(prices.max()), 4),
                "low": round(float(prices.min()), 4),
                "close": round(float(prices.iloc[-1]), 4),
                "volume": round(volume),
            }
        )
    return output


def run_record(index: int, row: dict[str, Any], event: dict[str, Any]) -> dict[str, Any]:
    metadata = row.get("metadata") or {}
    runs = row.get("runs") or []
    run = runs[-1] if runs else {}
    metrics = run.get("metrics") or {}
    order = build_order(run)
    return {
        "number": index,
        "session_id": row.get("session_id"),
        "run_id": run.get("run_id"),
        "request_id": metadata.get("request_id"),
        "security_id": int(metadata.get("security_id")),
        "name": metadata.get("display_name") or metadata.get("symbol"),
        "symbol": metadata.get("symbol"),
        "started_at": epoch_to_iso(run.get("created_at") or row.get("created_at")),
        "completed_at": latest_event_time(run),
        "status": str(run.get("status") or "UNKNOWN").upper(),
        "model": run.get("model"),
        "content": str(run.get("content") or ""),
        "reasoning": str(run.get("reasoning_content") or ""),
        "metrics": {
            "duration_seconds": number_or_none(metrics.get("duration")),
            "cost_usd": number_or_none(metrics.get("cost")),
            "input_tokens": number_or_none(metrics.get("input_tokens")),
            "output_tokens": number_or_none(metrics.get("output_tokens")),
            "reasoning_tokens": number_or_none(metrics.get("reasoning_tokens")),
        },
        "signal": event_summary(event),
        "order": order,
    }


def latest_event_time(run: dict[str, Any]) -> str | None:
    timestamps = [number_or_none(event.get("created_at")) for event in run.get("events") or []]
    available = [value for value in timestamps if value is not None]
    return epoch_to_iso(max(available)) if available else epoch_to_iso(run.get("created_at"))


def main() -> int:
    sessions = fetch_agent_sessions(load_environment())
    events = load_setup_events()
    records: list[dict[str, Any]] = []
    for index, row in enumerate(sessions, start=1):
        metadata = row.get("metadata") or {}
        request_id = str(metadata.get("request_id") or "")
        event = events.get(request_id)
        if event is None:
            raise RuntimeError(f"No setup event found for request {request_id}")
        records.append(run_record(index, row, event))

    if len(records) != 44:
        raise RuntimeError(f"Expected 44 stock-agent runs, found {len(records)}")

    security_ids = sorted({int(record["security_id"]) for record in records})
    candles = read_candles(security_ids)
    missing = [security_id for security_id in security_ids if not candles.get(security_id)]
    if missing:
        raise RuntimeError(f"No recorded price snapshots for security IDs: {missing}")

    broker_statuses = Counter(
        record["order"]["broker_status"]
        for record in records
        if record.get("order") and record["order"]["reached_broker"]
    )
    output = {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "market_date": MARKET_DATE,
        "timezone": MARKET_TIMEZONE,
        "methodology": {
            "signals": str(EVENTS_PATH.relative_to(ROOT)).replace("\\", "/"),
            "agents": "Supabase agno_sessions stock_agent rows",
            "prices": str(SNAPSHOTS_PATH.relative_to(ROOT)).replace("\\", "/"),
            "candle_note": "15-minute OHLC bars aggregated from recorded one-second last-price snapshots.",
            "status_note": "Broker statuses are the immediate responses saved in each agent run, not end-of-day order history.",
        },
        "summary": {
            "agent_runs": len(records),
            "unique_stocks": len(security_ids),
            "no_trade": sum(record["order"] is None for record in records),
            "trade_attempts": sum(record["order"] is not None for record in records),
            "broker_calls": sum(bool(record.get("order") and record["order"]["reached_broker"]) for record in records),
            "not_sent": sum(bool(record.get("order") and not record["order"]["reached_broker"]) for record in records),
            "broker_statuses": dict(sorted(broker_statuses.items())),
        },
        "runs": records,
        "candles": {str(security_id): candles[security_id] for security_id in security_ids},
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(output, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH} with {len(records)} runs and {len(security_ids)} stocks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
