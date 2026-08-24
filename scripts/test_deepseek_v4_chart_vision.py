#!/usr/bin/env python3
"""Test DeepSeek V4 Flash Vision against one archived trading chart."""

from __future__ import annotations

import base64
import argparse
import json
import os
import re
import time
from pathlib import Path
from typing import Any

import requests
from dotenv import dotenv_values


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MODEL_ID = "deepseek/deepseek-v4-flash-vision-exp"
CHART_PATH = (
    ROOT
    / "python-backend"
    / "results"
    / "agents"
    / "artifacts"
    / "2026-08-21"
    / "kiri-industries"
    / "kiri-industries-2026-08-21-current-15m.png"
)
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


def environment() -> dict[str, str]:
    values: dict[str, str] = {}
    for path in (ROOT / ".env", ROOT / ".env.local", ROOT / "python-backend" / ".env"):
        if path.exists():
            values.update({key: str(value) for key, value in dotenv_values(path).items() if value})
    values.update({key: value for key, value in os.environ.items() if value})
    return values


def image_data_url(path: Path) -> str:
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def request_model(api_key: str, model_id: str) -> dict[str, Any]:
    prompt = """Explain this trading chart carefully. Read the visible text and describe the price action without inventing indicators that are not shown.

End with a JSON object using exactly these keys:
stock, timeframe, data_through_ist, last_price, vwap, atr_14, last_candle_status, trend_vs_vwap, ema_9_vs_ema_21, previous_day_high, previous_day_close, previous_day_low.
Use numbers for prices and ATR. Use null only when the chart truly does not show the value."""
    request_body = {
            "model": model_id,
            "provider": {"data_collection": "allow", "zdr": False},
            "temperature": 0,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": image_data_url(CHART_PATH)}},
                    ],
                }
            ],
        }
    response: requests.Response | None = None
    for attempt, delay in enumerate((0, 2, 4, 8, 12, 16)):
        if delay:
            time.sleep(delay)
        response = requests.post(
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "http://localhost/trader-model-replay",
                "X-Title": "Trader chart comprehension test",
            },
            json=request_body,
            timeout=180,
        )
        if response.status_code != 429 or attempt == 5:
            break
    if response is None or not response.ok:
        status = response.status_code if response is not None else "unknown"
        body = response.text[:1000] if response is not None else "no response"
        raise RuntimeError(f"OpenRouter HTTP {status}: {body}")
    payload = response.json()
    if payload.get("error"):
        raise RuntimeError(str(payload["error"]))
    return payload


def extract_json(text: str) -> dict[str, Any] | None:
    fenced = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    candidates = fenced + re.findall(r"(\{[^{}]+\})", text, flags=re.DOTALL)
    for candidate in reversed(candidates):
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return None


def close_to(value: Any, expected: float, tolerance: float = 0.06) -> bool:
    try:
        return abs(float(value) - expected) <= tolerance
    except (TypeError, ValueError):
        return False


def grade(fields: dict[str, Any] | None) -> dict[str, Any]:
    if fields is None:
        return {"passed": False, "score": 0, "checks": {"parseable_json": False}}
    checks = {
        "stock": "kiri" in str(fields.get("stock") or "").lower(),
        "timeframe": "15" in str(fields.get("timeframe") or "").lower(),
        "data_time": "10:49" in str(fields.get("data_through_ist") or ""),
        "last_price": close_to(fields.get("last_price"), 464.40),
        "vwap": close_to(fields.get("vwap"), 463.38),
        "atr": close_to(fields.get("atr_14"), 3.94),
        "partial_candle": "partial" in str(fields.get("last_candle_status") or "").lower(),
        "above_vwap": "above" in str(fields.get("trend_vs_vwap") or "").lower(),
        "ema_alignment": "above" in str(fields.get("ema_9_vs_ema_21") or "").lower(),
        "previous_day_high": close_to(fields.get("previous_day_high"), 479.95),
        "previous_day_close": close_to(fields.get("previous_day_close"), 460.50),
        "previous_day_low": close_to(fields.get("previous_day_low"), 434.00),
    }
    score = sum(checks.values())
    return {"passed": score >= 10, "score": score, "maximum": len(checks), "checks": checks}


def safe_model_slug(model_id: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", model_id.lower()).strip("-")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=DEFAULT_MODEL_ID)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    model_id = str(args.model).strip()
    if not model_id or "/" not in model_id:
        raise ValueError("--model must be an OpenRouter model ID")
    api_key = environment().get("OPENROUTER_API_KEY", "")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not configured")
    payload = request_model(api_key, model_id)
    choice = (payload.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    response_text = str(message.get("content") or "")
    fields = extract_json(response_text)
    result = {
        "model": model_id,
        "chart": str(CHART_PATH.relative_to(ROOT)).replace("\\", "/"),
        "response": response_text,
        "extracted": fields,
        "grade": grade(fields),
        "usage": payload.get("usage") or {},
        "provider": payload.get("provider"),
        "request_id": payload.get("id"),
    }
    output_path = ROOT / "model-vision-tests" / safe_model_slug(model_id) / "vision-test.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0 if result["grade"]["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
