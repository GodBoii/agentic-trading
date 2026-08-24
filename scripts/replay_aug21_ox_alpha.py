#!/usr/bin/env python3
"""Replay the 44 August 21 stock-agent scenarios with stealth/ox-alpha.

This script cannot place broker orders. Its only model tool records one
simulated protected order so the model's decision can be compared with the
saved live-agent decision and the recorded end-of-day price path.
"""

from __future__ import annotations

import argparse
import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from dotenv import dotenv_values


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MODEL_ID = "stealth/ox-alpha"
MODEL_ID = DEFAULT_MODEL_ID
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MARKET_DATE = "2026-08-21"
START_EPOCH = int(datetime(2026, 8, 20, 18, 30, tzinfo=timezone.utc).timestamp())
END_EPOCH = int(datetime(2026, 8, 21, 18, 30, tzinfo=timezone.utc).timestamp())
ARTIFACTS_DIR = ROOT / "python-backend" / "results" / "agents" / "artifacts" / MARKET_DATE
BASE_REVIEW_PATH = ROOT / "august-21-trade-review" / "data.json"
OUTPUT_DIR = ROOT / "ox-alpha-aug21-replay"
CHECKPOINT_PATH = OUTPUT_DIR / "checkpoint.json"
OUTPUT_PATH = OUTPUT_DIR / "data.json"

EXECUTE_TOOL = {
    "type": "function",
    "function": {
        "name": "execute_trade_super_order",
        "description": (
            "Record one simulated protected intraday order for this historical replay. "
            "This does not contact a broker. Call only when a sound trade exists."
        ),
        "parameters": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "side",
                "quantity",
                "entry_price",
                "target_price",
                "stop_loss_price",
                "order_type",
                "rationale",
            ],
            "properties": {
                "side": {"type": "string", "enum": ["BUY", "SELL"]},
                "quantity": {"type": "integer", "minimum": 1},
                "entry_price": {"type": "number", "exclusiveMinimum": 0},
                "target_price": {"type": "number", "exclusiveMinimum": 0},
                "stop_loss_price": {"type": "number", "exclusiveMinimum": 0},
                "order_type": {"type": "string", "enum": ["MARKET", "LIMIT"]},
                "trailing_jump": {"type": "number", "minimum": 0},
                "rationale": {"type": "string", "minLength": 10, "maxLength": 1000},
            },
        },
    },
}


def load_environment() -> dict[str, str]:
    values: dict[str, str] = {}
    for path in (ROOT / ".env", ROOT / ".env.local", ROOT / "python-backend" / ".env"):
        if path.exists():
            values.update({key: str(value) for key, value in dotenv_values(path).items() if value})
    values.update({key: value for key, value in os.environ.items() if value})
    return values


def fetch_archived_sessions(environment: dict[str, str]) -> list[dict[str, Any]]:
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
            "created_at": f"gte.{START_EPOCH}",
            "and": f"(created_at.lt.{END_EPOCH},metadata->>stage.eq.stock_agent)",
            "order": "created_at.asc",
        },
        timeout=60,
    )
    response.raise_for_status()
    rows = response.json()
    if not isinstance(rows, list) or len(rows) != 44:
        raise RuntimeError(f"Expected 44 archived sessions, received {len(rows) if isinstance(rows, list) else 'invalid'}")
    return rows


def image_index() -> dict[str, Path]:
    index: dict[str, Path] = {}
    for path in ARTIFACTS_DIR.rglob("*.png"):
        index[path.name.lower()] = path
    return index


def data_url(path: Path) -> str:
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def safe_model_slug(model_id: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", model_id.lower()).strip("-")


def replay_directory(model_id: str) -> Path:
    names = {
        "stealth/ox-alpha": "ox-alpha-aug21-replay",
        "minimax/minimax-m3": "minimax-m3-aug21-replay",
        "moonshotai/kimi-k2.6": "kimi-k2-6-aug21-replay",
        "deepseek/deepseek-v4-flash-vision-exp": "deepseek-v4-flash-vision-aug21-replay",
    }
    return ROOT / names.get(model_id, f"{safe_model_slug(model_id)}-aug21-replay")


def original_messages(row: dict[str, Any]) -> tuple[str, str]:
    runs = row.get("runs") or []
    run = runs[-1] if runs else {}
    messages = run.get("messages") or []
    system = str(messages[0].get("content") or "") if messages else ""
    user = str(messages[1].get("content") or "") if len(messages) > 1 else str((run.get("input") or {}).get("input_content") or "")
    if not system or not user:
        raise RuntimeError(f"Archived prompt is missing for {row.get('session_id')}")
    system = system.replace(
        "Exactly two tools are available: estimate_intraday_quantity and place_protected_intraday_order.",
        "Exactly one tool is available: execute_trade_super_order.",
    ).replace(
        "Before any order, call estimate_intraday_quantity with the intended entry and stop, then use its recommended quantity.",
        "Choose a conservative whole-share quantity within the supplied strict cash/notional and risk limits.",
    )
    system += (
        "\n\nHistorical replay override. The supplied date, time, account state, charts, and prices are the complete "
        "August 21 snapshot. Do not use present-day information. The execute_trade_super_order tool records a simulation "
        "and cannot contact a broker. Call it at most once. If no sound entry exists, do not call it."
        " Keep the final response under 500 words."
    )
    user = user.replace(
        "The only available tools size a trade and place a protected order.",
        "The only available tool records one simulated protected order.",
    )
    return system, user


def image_paths(row: dict[str, Any], index: dict[str, Path]) -> list[Path]:
    metadata = row.get("metadata") or {}
    storage_paths = metadata.get("image_storage_paths") or []
    names = [Path(str(value).replace("\\", "/")).name.lower() for value in storage_paths]
    paths = [index[name] for name in names if name in index]
    if len(paths) != 9:
        raise RuntimeError(f"Expected nine local charts for {metadata.get('display_name')}, found {len(paths)}")
    return paths


def post_completion(api_key: str, body: dict[str, Any], *, attempts: int = 7) -> dict[str, Any]:
    last_response: requests.Response | None = None
    for attempt in range(attempts):
        if attempt:
            time.sleep(min(20, 2**attempt))
        last_response = requests.post(
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "http://localhost/trader-model-replay",
                "X-Title": "Trader model August 21 replay",
            },
            json=body,
            timeout=240,
        )
        if last_response.ok:
            payload = last_response.json()
            if not payload.get("error"):
                return payload
            continue
        retryable_credit_pressure = (
            last_response.status_code == 402
            and "in_flight_budget_exhausted" in last_response.text
        )
        if last_response.status_code not in {408, 409, 429, 500, 502, 503, 504} and not retryable_credit_pressure:
            break
    if last_response is None:
        raise RuntimeError("OpenRouter returned no response")
    raise RuntimeError(f"OpenRouter HTTP {last_response.status_code}: {last_response.text[:1200]}")


def parse_arguments(tool_call: dict[str, Any]) -> dict[str, Any]:
    function = tool_call.get("function") or {}
    raw = function.get("arguments")
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    raise ValueError("The model returned invalid tool arguments")


def validate_simulated_order(arguments: dict[str, Any]) -> tuple[bool, str]:
    try:
        side = str(arguments["side"]).upper()
        quantity = int(arguments["quantity"])
        entry = float(arguments["entry_price"])
        target = float(arguments["target_price"])
        stop = float(arguments["stop_loss_price"])
    except (KeyError, TypeError, ValueError):
        return False, "missing_or_invalid_required_field"
    if side not in {"BUY", "SELL"} or quantity < 1 or min(entry, target, stop) <= 0:
        return False, "invalid_side_quantity_or_price"
    if side == "BUY" and not stop < entry < target:
        return False, "invalid_buy_price_geometry"
    if side == "SELL" and not target < entry < stop:
        return False, "invalid_sell_price_geometry"
    return True, "accepted"


def run_scenario(api_key: str, row: dict[str, Any], chart_index: dict[str, Path]) -> dict[str, Any]:
    system, user = original_messages(row)
    paths = image_paths(row, chart_index)
    user_content: list[dict[str, Any]] = [{"type": "text", "text": user}]
    user_content.extend({"type": "image_url", "image_url": {"url": data_url(path)}} for path in paths)
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_content},
    ]
    started = time.monotonic()
    first_payload = post_completion(
        api_key,
        {
            "model": MODEL_ID,
            "provider": {"data_collection": "allow", "zdr": False},
            "temperature": 0,
            "messages": messages,
            "tools": [EXECUTE_TOOL],
            "tool_choice": "auto",
        },
    )
    first_message = ((first_payload.get("choices") or [{}])[0].get("message") or {})
    first_choice = (first_payload.get("choices") or [{}])[0]
    tool_calls = first_message.get("tool_calls") or []
    order: dict[str, Any] | None = None
    final_text = str(first_message.get("content") or "")
    tool_error: str | None = None

    if tool_calls:
        call = tool_calls[0]
        try:
            arguments = parse_arguments(call)
            valid, validation = validate_simulated_order(arguments)
            order = {
                "side": str(arguments.get("side") or "").upper(),
                "quantity": arguments.get("quantity"),
                "entry": arguments.get("entry_price"),
                "target": arguments.get("target_price"),
                "stop": arguments.get("stop_loss_price"),
                "order_type": arguments.get("order_type"),
                "trailing_jump": arguments.get("trailing_jump", 0),
                "rationale": arguments.get("rationale"),
                "valid": valid,
                "validation": validation,
                "status": "SIMULATED" if valid else "REJECTED_SIMULATION",
            }
        except (ValueError, json.JSONDecodeError) as exc:
            arguments = {}
            valid = False
            validation = "unparseable_tool_arguments"
            tool_error = str(exc)

        messages.append(
            {
                "role": "assistant",
                "content": first_message.get("content"),
                "tool_calls": [call],
            }
        )
        messages.append(
            {
                "role": "tool",
                "tool_call_id": call.get("id"),
                "name": "execute_trade_super_order",
                "content": json.dumps(
                    {
                        "status": "success" if valid else "error",
                        "execution": "simulated_only",
                        "validation": validation,
                        "recorded_order": order,
                    }
                ),
            }
        )
        final_payload = post_completion(
            api_key,
            {
                "model": MODEL_ID,
                "provider": {"data_collection": "allow", "zdr": False},
                "temperature": 0,
                "messages": messages,
            },
        )
        final_message = ((final_payload.get("choices") or [{}])[0].get("message") or {})
        final_text = str(final_message.get("content") or final_text)
        usage = merge_usage(first_payload.get("usage") or {}, final_payload.get("usage") or {})
        request_ids = [first_payload.get("id"), final_payload.get("id")]
    else:
        usage = first_payload.get("usage") or {}
        request_ids = [first_payload.get("id")]

    metadata = row.get("metadata") or {}
    archived_run = (row.get("runs") or [{}])[-1]
    return {
        "session_id": row.get("session_id"),
        "request_id": metadata.get("request_id"),
        "security_id": metadata.get("security_id"),
        "name": metadata.get("display_name"),
        "symbol": metadata.get("symbol"),
        "model": MODEL_ID,
        "analysis": final_text,
        "initial_content": str(first_message.get("content") or ""),
        "reasoning": str(first_message.get("reasoning") or first_message.get("reasoning_content") or ""),
        "reasoning_details": first_message.get("reasoning_details") or [],
        "finish_reason": first_choice.get("finish_reason"),
        "native_finish_reason": first_choice.get("native_finish_reason"),
        "response_fields": sorted(first_message.keys()),
        "incomplete": first_choice.get("finish_reason") == "length",
        "order": order,
        "tool_error": tool_error,
        "tool_call_count": len(tool_calls),
        "usage": usage,
        "duration_seconds": round(time.monotonic() - started, 3),
        "request_ids": request_ids,
        "chart_files": [path.name for path in paths],
        "original_model": archived_run.get("model"),
    }


def merge_usage(first: dict[str, Any], second: dict[str, Any]) -> dict[str, Any]:
    keys = ("prompt_tokens", "completion_tokens", "total_tokens", "cost")
    return {key: sum(float(source.get(key) or 0) for source in (first, second)) for key in keys}


def load_checkpoint() -> dict[str, Any]:
    if not CHECKPOINT_PATH.exists():
        return {"model": MODEL_ID, "runs": {}}
    payload = json.loads(CHECKPOINT_PATH.read_text(encoding="utf-8"))
    if payload.get("model") != MODEL_ID or not isinstance(payload.get("runs"), dict):
        raise RuntimeError("Checkpoint belongs to a different replay")
    return payload


def save_checkpoint(checkpoint: dict[str, Any]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    temporary = CHECKPOINT_PATH.with_name(f".{CHECKPOINT_PATH.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(checkpoint, ensure_ascii=False, indent=2), encoding="utf-8")
    for attempt in range(10):
        try:
            os.replace(temporary, CHECKPOINT_PATH)
            return
        except PermissionError:
            if attempt == 9:
                break
            time.sleep(0.2 * (attempt + 1))
    # Windows indexing or virus scanning can hold the destination briefly.
    # A direct single-writer fallback is safer than losing a completed run.
    CHECKPOINT_PATH.write_text(json.dumps(checkpoint, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.unlink(missing_ok=True)


def evaluate_path(order: dict[str, Any] | None, candles: list[dict[str, Any]], signal_time: str) -> dict[str, Any] | None:
    if not order or not order.get("valid"):
        return None
    side = str(order["side"])
    entry = float(order["entry"])
    target = float(order["target"])
    stop = float(order["stop"])
    start = datetime.fromisoformat(signal_time).timestamp()
    subsequent = [candle for candle in candles if datetime.fromisoformat(candle["time"]).timestamp() + 900 >= start]
    entered_at: str | None = None
    active = False
    for candle in subsequent:
        low, high = float(candle["low"]), float(candle["high"])
        if not active and low <= entry <= high:
            active = True
            entered_at = candle["time"]
        if not active:
            continue
        target_hit = high >= target if side == "BUY" else low <= target
        stop_hit = low <= stop if side == "BUY" else high >= stop
        if target_hit and stop_hit:
            return {"entered": True, "entered_at": entered_at, "outcome": "AMBIGUOUS_SAME_CANDLE", "outcome_at": candle["time"]}
        if target_hit:
            return {"entered": True, "entered_at": entered_at, "outcome": "TARGET", "outcome_at": candle["time"]}
        if stop_hit:
            return {"entered": True, "entered_at": entered_at, "outcome": "STOP", "outcome_at": candle["time"]}
    return {"entered": active, "entered_at": entered_at, "outcome": "NO_EXIT" if active else "ENTRY_NOT_TOUCHED", "outcome_at": None}


def build_output(checkpoint: dict[str, Any], base: dict[str, Any]) -> dict[str, Any]:
    completed_by_request = checkpoint["runs"]
    runs: list[dict[str, Any]] = []
    for original in base["runs"]:
        replay = completed_by_request.get(str(original["request_id"]))
        if replay is None:
            continue
        if MODEL_ID == "stealth/ox-alpha" and not replay.get("response_fields"):
            # Exclude the capped one-run calibration created before the user
            # required fully uncapped replay responses.
            continue
        replay["number"] = original["number"]
        replay["signal"] = original["signal"]
        replay["original"] = {
            "analysis": original["content"],
            "order": original["order"],
            "model": original["model"],
        }
        replay["path_evaluation"] = evaluate_path(
            replay.get("order"),
            base["candles"].get(str(original["security_id"]), []),
            original["signal"]["time"],
        )
        runs.append(replay)
    trade_count = sum(run.get("order") is not None for run in runs)
    valid_trade_count = sum(bool(run.get("order") and run["order"].get("valid")) for run in runs)
    outcomes: dict[str, int] = {}
    for run in runs:
        outcome = (run.get("path_evaluation") or {}).get("outcome")
        if outcome:
            outcomes[outcome] = outcomes.get(outcome, 0) + 1
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "market_date": MARKET_DATE,
        "model": MODEL_ID,
        "safety": "All execute_trade_super_order calls were simulated and never contacted Dhan.",
        "summary": {
            "completed_runs": len(runs),
            "no_trade": len(runs) - trade_count,
            "trade_calls": trade_count,
            "valid_simulated_orders": valid_trade_count,
            "outcomes_from_15m_bars": outcomes,
        },
        "vision_test": json.loads(
            (ROOT / "model-vision-tests" / safe_model_slug(MODEL_ID) / "vision-test.json").read_text(encoding="utf-8")
        ),
        "runs": sorted(runs, key=lambda item: int(item["number"])),
        "candles": base["candles"],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=DEFAULT_MODEL_ID, help="OpenRouter model ID")
    parser.add_argument("--limit", type=int, default=None, help="Run only the first N unfinished scenarios")
    parser.add_argument("--run", type=int, action="append", dest="run_numbers", help="Run a specific 1-based scenario number")
    parser.add_argument("--force", action="store_true", help="Rerun selected scenarios even when checkpointed")
    parser.add_argument("--workers", type=int, default=1, help="Concurrent model requests, from 1 to 44")
    return parser.parse_args()


def main() -> int:
    global MODEL_ID, OUTPUT_DIR, CHECKPOINT_PATH, OUTPUT_PATH
    args = parse_args()
    if args.workers < 1 or args.workers > 44:
        raise ValueError("--workers must be between 1 and 44")
    MODEL_ID = str(args.model).strip()
    if not MODEL_ID or "/" not in MODEL_ID:
        raise ValueError("--model must be an OpenRouter model ID")
    OUTPUT_DIR = replay_directory(MODEL_ID)
    CHECKPOINT_PATH = OUTPUT_DIR / "checkpoint.json"
    OUTPUT_PATH = OUTPUT_DIR / "data.json"
    environment = load_environment()
    api_key = environment.get("OPENROUTER_API_KEY", "")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not configured")
    base = json.loads(BASE_REVIEW_PATH.read_text(encoding="utf-8"))
    sessions = fetch_archived_sessions(environment)
    charts = image_index()
    checkpoint = load_checkpoint()
    selected = set(args.run_numbers or range(1, 45))
    pending = [
        (index, row)
        for index, row in enumerate(sessions, start=1)
        if index in selected
        and (args.force or str((row.get("metadata") or {}).get("request_id")) not in checkpoint["runs"])
    ]
    if args.limit is not None:
        pending = pending[: max(args.limit, 0)]
    with ThreadPoolExecutor(max_workers=args.workers, thread_name_prefix="model-replay") as executor:
        future_rows = {}
        for position, (index, row) in enumerate(pending, start=1):
            name = (row.get("metadata") or {}).get("display_name")
            print(f"[{position}/{len(pending)}] queued run {index}: {name}", flush=True)
            future_rows[executor.submit(run_scenario, api_key, row, charts)] = (index, row)
        for future in as_completed(future_rows):
            index, _row = future_rows[future]
            try:
                result = future.result()
            except Exception as exc:
                print(f"run {index} failed: {type(exc).__name__}: {exc}", flush=True)
                continue
            checkpoint["runs"][str(result["request_id"])] = result
            save_checkpoint(checkpoint)
            decision = result.get("order") or {}
            print(
                f"run {index} complete: {decision.get('side', 'NO_TRADE')} "
                f"{decision.get('entry', '')} in {result['duration_seconds']}s",
                flush=True,
            )
    output = build_output(checkpoint, base)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(output, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {OUTPUT_PATH} with {len(output['runs'])} completed runs", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
