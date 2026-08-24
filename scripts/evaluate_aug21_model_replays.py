#!/usr/bin/env python3
"""Evaluate simulated replay orders against recorded one-second prices."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow.compute as pc
import pyarrow.dataset as ds


ROOT = Path(__file__).resolve().parent.parent
SNAPSHOTS = ROOT / "python-backend" / "results" / "stage2" / "2026-08-21" / "one-second"
REPLAY_FILES = (
    ROOT / "ox-alpha-aug21-replay" / "data.json",
    ROOT / "minimax-m3-aug21-replay" / "data.json",
    ROOT / "kimi-k2-6-aug21-replay" / "data.json",
    ROOT / "deepseek-v4-flash-vision-aug21-replay" / "data.json",
)


def load_prices(security_ids: list[int]) -> pd.DataFrame:
    dataset = ds.dataset(SNAPSHOTS, format="parquet", partitioning="hive")
    table = dataset.to_table(
        columns=["received_at", "security_id", "last_price"],
        filter=pc.field("security_id").isin(security_ids),
    )
    frame = table.to_pandas()
    frame["received_at"] = pd.to_datetime(frame["received_at"], errors="coerce", utc=True).dt.tz_convert("Asia/Kolkata")
    frame["last_price"] = pd.to_numeric(frame["last_price"], errors="coerce")
    return frame.dropna(subset=["received_at", "security_id", "last_price"]).sort_values(
        ["security_id", "received_at"]
    )


def first_entry_index(path: pd.DataFrame, order: dict[str, Any], signal_price: float) -> int | None:
    if path.empty:
        return None
    side = str(order["side"])
    entry = float(order["entry"])
    order_type = str(order.get("order_type") or "LIMIT")
    if order_type == "MARKET":
        return int(path.index[0])
    marketable = signal_price <= entry if side == "BUY" else signal_price >= entry
    if marketable:
        return int(path.index[0])
    touches = path[path["last_price"] <= entry] if side == "BUY" else path[path["last_price"] >= entry]
    return int(touches.index[0]) if not touches.empty else None


def evaluate_order(run: dict[str, Any], security_prices: pd.DataFrame) -> dict[str, Any] | None:
    order = run.get("order")
    if not order or not order.get("valid"):
        return None
    signal_at = pd.Timestamp(run["signal"]["time"])
    path = security_prices[security_prices["received_at"] >= signal_at].copy().reset_index(drop=True)
    if path.empty:
        return {"entered": False, "outcome": "NO_RECORDED_PRICES", "entered_at": None, "outcome_at": None}
    signal_price = float(run["signal"]["price"])
    entry_index = first_entry_index(path, order, signal_price)
    if entry_index is None:
        return {"entered": False, "outcome": "ENTRY_NOT_TOUCHED", "entered_at": None, "outcome_at": None}

    active = path.loc[entry_index:].copy()
    side = str(order["side"])
    entry = float(order["entry"])
    target = float(order["target"])
    stop = float(order["stop"])
    if side == "BUY":
        target_rows = active[active["last_price"] >= target]
        stop_rows = active[active["last_price"] <= stop]
        favorable = float(active["last_price"].max() - entry)
        adverse = float(entry - active["last_price"].min())
    else:
        target_rows = active[active["last_price"] <= target]
        stop_rows = active[active["last_price"] >= stop]
        favorable = float(entry - active["last_price"].min())
        adverse = float(active["last_price"].max() - entry)
    target_at = target_rows.iloc[0]["received_at"] if not target_rows.empty else None
    stop_at = stop_rows.iloc[0]["received_at"] if not stop_rows.empty else None
    if target_at is not None and (stop_at is None or target_at < stop_at):
        outcome, outcome_at = "TARGET", target_at
    elif stop_at is not None:
        outcome, outcome_at = "STOP", stop_at
    else:
        outcome, outcome_at = "NO_EXIT", None
    risk = abs(entry - stop)
    return {
        "entered": True,
        "entered_at": active.iloc[0]["received_at"].isoformat(),
        "outcome": outcome,
        "outcome_at": outcome_at.isoformat() if outcome_at is not None else None,
        "max_favorable_excursion": round(favorable, 4),
        "max_adverse_excursion": round(adverse, 4),
        "mfe_r": round(favorable / risk, 4) if risk else None,
        "mae_r": round(adverse / risk, 4) if risk else None,
        "source": "recorded_one_second_last_price",
    }


def update_file(path: Path, prices: pd.DataFrame) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    outcomes: dict[str, int] = {}
    for run in data["runs"]:
        security_id = int(run["security_id"])
        security_prices = prices[prices["security_id"] == security_id]
        run["path_evaluation"] = evaluate_order(run, security_prices)
        outcome = (run.get("path_evaluation") or {}).get("outcome")
        if outcome:
            outcomes[outcome] = outcomes.get(outcome, 0) + 1
    orders = [run for run in data["runs"] if run.get("order") and run["order"].get("valid")]
    entered = [run for run in orders if (run.get("path_evaluation") or {}).get("entered")]
    targets = sum((run.get("path_evaluation") or {}).get("outcome") == "TARGET" for run in entered)
    stops = sum((run.get("path_evaluation") or {}).get("outcome") == "STOP" for run in entered)
    data["summary"]["outcomes_from_one_second_prices"] = outcomes
    data["summary"]["entered_orders"] = len(entered)
    data["summary"]["resolved_orders"] = targets + stops
    data["summary"]["target_before_stop"] = targets
    data["summary"]["stop_before_target"] = stops
    data["summary"].pop("outcomes_from_15m_bars", None)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    os.replace(temporary, path)
    return data["summary"]


def main() -> int:
    available = [path for path in REPLAY_FILES if path.exists()]
    if not available:
        raise RuntimeError("No replay data files exist")
    security_ids: set[int] = set()
    for path in available:
        payload = json.loads(path.read_text(encoding="utf-8"))
        security_ids.update(int(run["security_id"]) for run in payload.get("runs") or [])
    prices = load_prices(sorted(security_ids))
    for path in available:
        summary = update_file(path, prices)
        print(f"{path.parent.name}: {json.dumps(summary, sort_keys=True)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
