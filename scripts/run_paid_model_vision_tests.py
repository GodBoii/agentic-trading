#!/usr/bin/env python3
"""Run identical chart tests with an API key read once from standard input."""

from __future__ import annotations

import argparse
import getpass
import json

from test_deepseek_v4_chart_vision import (
    CHART_PATH,
    ROOT,
    extract_json,
    grade,
    request_model,
    safe_model_slug,
)


DEFAULT_MODELS = ("minimax/minimax-m3", "moonshotai/kimi-k2.6")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", action="append", dest="models", help="Model to test. Repeat for multiple models.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    models = tuple(args.models or DEFAULT_MODELS)
    api_key = getpass.getpass("OpenRouter API key: ").strip()
    if not api_key:
        raise RuntimeError("No API key was supplied on standard input")
    failures = 0
    for model_id in models:
        print(f"Testing {model_id}", flush=True)
        try:
            payload = request_model(api_key, model_id)
            message = ((payload.get("choices") or [{}])[0].get("message") or {})
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
        except Exception as exc:
            result = {
                "model": model_id,
                "chart": str(CHART_PATH.relative_to(ROOT)).replace("\\", "/"),
                "error": f"{type(exc).__name__}: {exc}",
                "grade": {"passed": False, "score": 0, "maximum": 12, "checks": {}},
            }
            failures += 1
        output_path = ROOT / "model-vision-tests" / safe_model_slug(model_id) / "vision-test.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"model": model_id, "grade": result["grade"], "error": result.get("error")}), flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
