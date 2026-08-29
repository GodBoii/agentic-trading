from __future__ import annotations

import argparse
import json
import math
import time
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from pipeline.config import PipelineConfig
from pipeline.services.dhan_service import DhanService


MARKET_DATE = "2026-08-28"
IST = ZoneInfo("Asia/Kolkata")
ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "python-backend" / "results"


def load_json_lines(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON at {path}:{line_number}") from exc
            if isinstance(value, dict):
                rows.append(value)
    return rows


def first_result(archive_row: dict[str, Any]) -> dict[str, Any] | None:
    user_results = archive_row.get("decision", {}).get("user_results", [])
    if not user_results or not isinstance(user_results[0], dict):
        return None
    results = user_results[0].get("result", {}).get("results", [])
    if not results or not isinstance(results[0], dict):
        return None
    return results[0]


def parse_tool_calls(result: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not result:
        return []
    parsed: list[dict[str, Any]] = []
    for call in result.get("agent_metadata", {}).get("tool_calls", []):
        function = call.get("function", {}) if isinstance(call, dict) else {}
        raw_arguments = function.get("arguments", "{}")
        try:
            arguments = json.loads(raw_arguments) if isinstance(raw_arguments, str) else raw_arguments
        except json.JSONDecodeError:
            arguments = {"raw": raw_arguments}
        parsed.append({"name": function.get("name"), "arguments": arguments})
    return parsed


def placement_arguments(tool_calls: Iterable[dict[str, Any]]) -> dict[str, Any]:
    for call in tool_calls:
        if call.get("name") == "place_protected_intraday_order":
            arguments = call.get("arguments")
            return arguments if isinstance(arguments, dict) else {}
    return {}


def to_ist(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=IST)
    return parsed.astimezone(IST)


def finite_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def compact_bars(frame: pd.DataFrame) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    local = frame.copy()
    timestamps = pd.to_datetime(local["timestamp"], errors="coerce", utc=True).dt.tz_convert(IST)
    local["timestamp"] = timestamps
    local = local.loc[local["timestamp"].dt.date.astype(str) == MARKET_DATE]
    if local.empty:
        return []
    indexed = local.set_index("timestamp")
    five = indexed[["open", "high", "low", "close", "volume"]].resample(
        "5min", label="left", closed="left"
    ).agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
    five = five.dropna(subset=["open", "high", "low", "close"])
    return [
        {
            "time": timestamp.isoformat(),
            "open": round(float(row.open), 4),
            "high": round(float(row.high), 4),
            "low": round(float(row.low), 4),
            "close": round(float(row.close), 4),
            "volume": round(float(row.volume), 2),
        }
        for timestamp, row in five.iterrows()
    ]


def chart_accuracy(seed_bars: list[dict[str, Any]], frame: pd.DataFrame) -> dict[str, Any]:
    if frame.empty or not seed_bars:
        return {"overlap_minutes": 0, "verdict": "unverified"}
    broker = frame.copy()
    broker["timestamp"] = pd.to_datetime(broker["timestamp"], errors="coerce", utc=True).dt.floor("min")
    broker = broker.dropna(subset=["timestamp"]).drop_duplicates("timestamp", keep="last").set_index("timestamp")
    comparisons: list[dict[str, float]] = []
    close_references: list[float] = []
    volume_errors: list[float] = []
    for bar in seed_bars:
        timestamp = bar.get("minute_start") or bar.get("timestamp")
        if not timestamp:
            continue
        key = pd.Timestamp(timestamp)
        if key.tzinfo is None:
            key = key.tz_localize(IST)
        key = key.tz_convert("UTC").floor("min")
        if key not in broker.index:
            continue
        row = broker.loc[key]
        if isinstance(row, pd.DataFrame):
            row = row.iloc[-1]
        values: dict[str, float] = {}
        for field in ("open", "high", "low", "close"):
            seed = finite_number(bar.get(field))
            authoritative = finite_number(row.get(field))
            if seed is not None and authoritative is not None:
                values[field] = abs(seed - authoritative)
                if field == "close":
                    close_references.append(authoritative)
        seed_volume = finite_number(bar.get("volume"))
        broker_volume = finite_number(row.get("volume"))
        if seed_volume is not None and broker_volume is not None and broker_volume > 0:
            volume_errors.append(abs(seed_volume - broker_volume) / broker_volume)
        if values:
            comparisons.append(values)
    if not comparisons:
        return {"overlap_minutes": 0, "verdict": "unverified"}
    max_difference = max(max(item.values()) for item in comparisons)
    mean_close_difference = sum(item.get("close", 0.0) for item in comparisons) / len(comparisons)
    reference_price = sum(close_references) / len(close_references) if close_references else 0.0
    max_difference_percent = max_difference / reference_price * 100 if reference_price else None
    mean_close_difference_percent = mean_close_difference / reference_price * 100 if reference_price else None
    if max_difference_percent is None:
        verdict = "unverified"
    elif max_difference_percent > 0.5 or (mean_close_difference_percent or 0.0) > 0.05:
        verdict = "material_outlier"
    elif max_difference_percent > 0.25 or (mean_close_difference_percent or 0.0) > 0.03:
        verdict = "review"
    else:
        verdict = "close_match"
    return {
        "overlap_minutes": len(comparisons),
        "max_ohlc_difference_rupees": round(max_difference, 4),
        "mean_close_difference_rupees": round(mean_close_difference, 4),
        "max_ohlc_difference_percent": round(max_difference_percent, 4) if max_difference_percent is not None else None,
        "mean_close_difference_percent": round(mean_close_difference_percent, 4) if mean_close_difference_percent is not None else None,
        "mean_absolute_volume_error_percent": round(sum(volume_errors) / len(volume_errors) * 100, 2) if volume_errors else None,
        "verdict": verdict,
    }


def path_outcome(bars: list[dict[str, Any]], signal_at: datetime | None, direction: str) -> dict[str, Any]:
    if not bars or signal_at is None:
        return {}
    after = [bar for bar in bars if to_ist(bar["time"]) and to_ist(bar["time"]) >= signal_at.replace(second=0, microsecond=0)]
    if not after:
        return {}
    reference = float(after[0]["open"])
    last = float(after[-1]["close"])
    highest = max(float(bar["high"]) for bar in after)
    lowest = min(float(bar["low"]) for bar in after)
    sign = 1.0 if direction.upper() == "LONG" else -1.0
    return {
        "reference_price": round(reference, 4),
        "session_close": round(last, 4),
        "directional_close_return_percent": round(sign * (last - reference) / reference * 100, 3),
        "max_favorable_excursion_percent": round((highest - reference) / reference * 100 if sign > 0 else (reference - lowest) / reference * 100, 3),
        "max_adverse_excursion_percent": round((reference - lowest) / reference * 100 if sign > 0 else (highest - reference) / reference * 100, 3),
    }


def first_stop_touch(bars: list[dict[str, Any]], signal_at: datetime | None, side: str, stop: float | None) -> str | None:
    if signal_at is None or stop is None:
        return None
    for bar in bars:
        timestamp = to_ist(bar["time"])
        if timestamp is None or timestamp < signal_at.replace(second=0, microsecond=0):
            continue
        touched = float(bar["low"]) <= stop if side.upper() == "BUY" else float(bar["high"]) >= stop
        if touched:
            return timestamp.isoformat()
    return None


def infer_order_path(
    frame: pd.DataFrame,
    signal_at: datetime | None,
    placement: dict[str, Any],
) -> dict[str, Any]:
    if frame.empty or signal_at is None or not placement:
        return {}
    side = str(placement.get("side") or "").upper()
    order_type = str(placement.get("order_type") or "LIMIT").upper()
    entry = finite_number(placement.get("entry_price"))
    stop = finite_number(placement.get("stop_loss_price"))
    target = finite_number(placement.get("target_price"))
    if side not in {"BUY", "SELL"} or entry is None:
        return {}
    local = frame.copy()
    local["timestamp_ist"] = pd.to_datetime(local["timestamp"], errors="coerce", utc=True).dt.tz_convert(IST)
    local = local.loc[
        (local["timestamp_ist"] >= signal_at.replace(second=0, microsecond=0))
        & (local["timestamp_ist"].dt.date.astype(str) == MARKET_DATE)
    ]
    entry_index: int | None = None
    for index, row in local.reset_index(drop=True).iterrows():
        if order_type == "MARKET":
            entry_index = index
            break
        low = float(row["low"])
        high = float(row["high"])
        marketable = (side == "BUY" and entry >= float(row["open"])) or (
            side == "SELL" and entry <= float(row["open"])
        )
        if low <= entry <= high or marketable:
            entry_index = index
            break
    if entry_index is None:
        return {"entry_touch_ist": None, "minutes_from_signal_to_entry": None}
    rows = local.reset_index(drop=True)
    entry_time = rows.iloc[entry_index]["timestamp_ist"].to_pydatetime()
    result: dict[str, Any] = {
        "entry_touch_ist": entry_time.isoformat(),
        "minutes_from_signal_to_entry": round(max(0.0, (entry_time - signal_at).total_seconds() / 60), 2),
        "first_protection_touch": None,
        "first_protection_touch_ist": None,
    }
    for _, row in rows.iloc[entry_index + 1 :].iterrows():
        high = float(row["high"])
        low = float(row["low"])
        stop_hit = stop is not None and (low <= stop if side == "BUY" else high >= stop)
        target_hit = target is not None and (high >= target if side == "BUY" else low <= target)
        if not stop_hit and not target_hit:
            continue
        result["first_protection_touch"] = "ambiguous_same_bar" if stop_hit and target_hit else "stop" if stop_hit else "target"
        result["first_protection_touch_ist"] = row["timestamp_ist"].to_pydatetime().isoformat()
        break
    return result


def classify_run(archive_status: str, decision: dict[str, Any], filled_later: bool) -> str:
    if archive_status != "completed":
        return "model_error"
    if decision.get("execution_status") == "traded" or filled_later:
        return "trade"
    if decision.get("execution_status") == "blocked":
        return "blocked"
    if decision.get("execution_status") == "pending":
        return "unfilled_pending"
    if decision.get("execution_status") == "failed":
        return "tool_failed"
    return "skipped"


def find_chart_files(display_name: str, event_id: str) -> list[str]:
    slug = "-".join(part for part in "".join(character.lower() if character.isalnum() else " " for character in display_name).split())
    directory = RESULTS / "agents" / "artifacts" / MARKET_DATE / slug / event_id
    if not directory.exists():
        return []
    return [str(path.relative_to(ROOT)).replace("\\", "/") for path in sorted(directory.glob("*.png"))]


def build_report(output_path: Path, *, pause_seconds: float) -> None:
    setups = {
        row["event_id"]: row
        for row in load_json_lines(RESULTS / "stage2" / MARKET_DATE / "setup-events.jsonl")
        if row.get("event_id")
    }
    archive = {
        row["event_id"]: row
        for row in load_json_lines(RESULTS / "agents" / "event-decision-archive.ndjson")
        if row.get("market_date") == MARKET_DATE and row.get("event_id")
    }
    missing = sorted(set(setups) - set(archive))
    if missing:
        raise RuntimeError(f"Missing {len(missing)} dispatched events in the decision archive")

    dhan = DhanService(PipelineConfig(), prefer_gateway=False)
    positions_response = dhan.fetch_positions()
    positions = positions_response.get("data", []) if positions_response.get("status") == "success" else []
    positions_by_security = {str(row.get("securityId")): row for row in positions if row.get("securityId")}

    runs: list[dict[str, Any]] = []
    for index, setup in enumerate(sorted(setups.values(), key=lambda row: row.get("created_at", "")), start=1):
        event_id = str(setup["event_id"])
        archive_row = archive[event_id]
        result = first_result(archive_row)
        candidate = result.get("candidate", {}) if result else setup
        decision = result.get("decision", {}) if result else {}
        security_id = int(setup["security_id"])
        position = positions_by_security.get(str(security_id))
        tool_calls = parse_tool_calls(result)
        placement = placement_arguments(tool_calls)

        response = dhan.fetch_intraday_history(
            security_id,
            days=5,
            interval=1,
            exchange_segment=str(setup.get("exchange_segment") or "NSE_EQ"),
            instrument_candidates=[setup.get("instrument"), "EQUITY"],
        )
        if response.get("status") == "success":
            market_frame = dhan.intraday_response_to_df(response)
            market_error = None
        else:
            market_frame = pd.DataFrame()
            market_error = str(response.get("remarks") or "historical request failed")
        bars = compact_bars(market_frame)
        signal_at = to_ist(setup.get("created_at"))
        filled_later = bool(position and (int(position.get("dayBuyQty") or 0) or int(position.get("daySellQty") or 0)))
        run_class = classify_run(str(archive_row.get("status")), decision, filled_later)

        chart_artifacts = candidate.get("chart_artifacts", {}) if isinstance(candidate, dict) else {}
        chart_files = find_chart_files(str(setup.get("display_name") or setup.get("symbol")), event_id)
        chart_files.sort(key=lambda value: ("current-5m" not in value, "current-1m" not in value, value))
        stop = finite_number(placement.get("stop_loss_price"))
        side = str(placement.get("side") or decision.get("trade_side") or "")
        runs.append(
            {
                "ordinal": index,
                "event_id": event_id,
                "security_id": security_id,
                "symbol": setup.get("symbol"),
                "display_name": setup.get("display_name") or setup.get("symbol"),
                "signal_time_ist": signal_at.isoformat() if signal_at else setup.get("created_at"),
                "direction": setup.get("direction"),
                "readiness_score": setup.get("setup_score"),
                "indicator_events": setup.get("indicator_events", []),
                "indicator_snapshot": setup.get("indicator_snapshot", {}),
                "trade_readiness": setup.get("trade_readiness", {}),
                "entry_zone": setup.get("entry_zone"),
                "vwap": setup.get("vwap"),
                "opening_range": setup.get("opening_range"),
                "relative_volume": setup.get("relative_volume"),
                "volume_acceleration": setup.get("volume_acceleration"),
                "archive_status": archive_row.get("status"),
                "run_class": run_class,
                "error": archive_row.get("error"),
                "decision": decision,
                "placement": placement,
                "tool_calls": tool_calls,
                "analysis": result.get("analysis", "") if result else "",
                "reasoning": result.get("agent_metadata", {}).get("reasoning_content", "") if result else "",
                "tool_summary": result.get("agent_metadata", {}).get("tool_summary", {}) if result else {},
                "model": result.get("agent_metadata", {}).get("model") if result else None,
                "position": position,
                "market_bars_5m": bars,
                "market_data_error": market_error,
                "post_signal_outcome": path_outcome(bars, signal_at, str(setup.get("direction") or "")),
                "inferred_first_stop_touch_ist": first_stop_touch(bars, signal_at, side, stop),
                "inferred_order_path": infer_order_path(market_frame, signal_at, placement),
                "chart_accuracy": chart_accuracy(setup.get("chart_seed_bars", []), market_frame),
                "chart_files": chart_files,
                "chart_contract": {
                    "version": chart_artifacts.get("chart_contract_version"),
                    "history_cache_used": chart_artifacts.get("history_cache_used"),
                    "data_as_of_ist": chart_artifacts.get("data_as_of_ist"),
                    "current_5m_last_complete": chart_artifacts.get("charts", {}).get("current_5m", {}).get("last_candle_complete"),
                    "current_15m_last_complete": chart_artifacts.get("charts", {}).get("current_15m", {}).get("last_candle_complete"),
                    "technical_metadata": chart_artifacts.get("technical_metadata", {}),
                },
            }
        )
        if pause_seconds > 0 and index < len(setups):
            time.sleep(pause_seconds)

    summary_counts: dict[str, int] = {}
    for run in runs:
        summary_counts[run["run_class"]] = summary_counts.get(run["run_class"], 0) + 1
    trade_runs = [run for run in runs if run["run_class"] == "trade"]
    gross_pnl = sum(float(run.get("position", {}).get("realizedProfit") or 0.0) for run in trade_runs)
    accuracy_counts: dict[str, int] = {}
    for run in runs:
        verdict = run["chart_accuracy"]["verdict"]
        accuracy_counts[verdict] = accuracy_counts.get(verdict, 0) + 1

    payload = {
        "report": {
            "market_date": MARKET_DATE,
            "generated_at_ist": datetime.now(IST).isoformat(),
            "source": "Local Intra Finder ledger, Agno decision archive, Dhan historical OHLCV, and Dhan positions",
            "event_count": len(runs),
            "counts": summary_counts,
            "trade_count": len(trade_runs),
            "winning_trades": sum(1 for run in trade_runs if float(run["position"].get("realizedProfit") or 0) > 0),
            "gross_realized_pnl": round(gross_pnl, 2),
            "chart_accuracy_counts": accuracy_counts,
        },
        "runs": runs,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the 28 Aug 2026 trading forensic dataset")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--pause-seconds", type=float, default=0.25)
    args = parser.parse_args()
    build_report(args.output, pause_seconds=max(0.0, args.pause_seconds))


if __name__ == "__main__":
    main()
