#!/usr/bin/env python3
"""Launch MiniMax and Kimi replays with a non-echoed in-memory API key."""

from __future__ import annotations

import argparse
import getpass
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
REPLAY_SCRIPT = ROOT / "scripts" / "replay_aug21_ox_alpha.py"
DEFAULT_MODELS = ("minimax/minimax-m3", "moonshotai/kimi-k2.6")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", action="append", dest="models", help="Model to run. Repeat for multiple models.")
    parser.add_argument("--workers", type=int, default=10, help="Concurrent scenarios per model")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    models = tuple(args.models or DEFAULT_MODELS)
    api_key = getpass.getpass("OpenRouter API key: ").strip()
    if not api_key:
        raise RuntimeError("No API key was supplied")
    environment = dict(os.environ)
    environment["OPENROUTER_API_KEY"] = api_key
    processes = [
        subprocess.Popen(
            [sys.executable, str(REPLAY_SCRIPT), "--model", model_id, "--workers", str(args.workers)],
            cwd=ROOT,
            env=environment,
        )
        for model_id in models
    ]
    api_key = ""
    exit_codes = [process.wait() for process in processes]
    return 0 if all(code == 0 for code in exit_codes) else 1


if __name__ == "__main__":
    raise SystemExit(main())
