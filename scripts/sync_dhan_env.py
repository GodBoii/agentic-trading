#!/usr/bin/env python3
"""Synchronize Dhan credentials between root and backend environment files.

Values are never printed. Data API credentials prefer python-backend/.env,
while application credentials prefer the root .env.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from dotenv import dotenv_values


ROOT = Path(__file__).resolve().parent.parent
ROOT_ENV = ROOT / ".env"
LOCAL_ENV = ROOT / ".env.local"
BACKEND_ENV = ROOT / "python-backend" / ".env"
APP_KEYS = ("DHAN_APP_ID", "DHAN_APP_SECRET")
DATA_KEYS = ("DHAN_DATA_CLIENT_ID", "DHAN_DATA_ACCESS_TOKEN")


def replace_or_append(path: Path, updates: dict[str, str]) -> None:
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    for key, value in updates.items():
        line = f"{key}={value}"
        pattern = re.compile(rf"(?m)^{re.escape(key)}=.*$")
        if pattern.search(text):
            text = pattern.sub(lambda _: line, text)
        else:
            if text and not text.endswith("\n"):
                text += "\n"
            text += line + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def require_values(source: dict[str, str | None], keys: tuple[str, ...], label: str) -> dict[str, str]:
    missing = [key for key in keys if not source.get(key)]
    if missing:
        raise RuntimeError(f"{label} is missing required keys: {', '.join(missing)}")
    return {key: str(source[key]) for key in keys}


def main() -> int:
    root_values = dotenv_values(ROOT_ENV)
    backend_values = dotenv_values(BACKEND_ENV)
    app_source = dict(root_values)
    app_source.update({key: os.environ[key] for key in APP_KEYS if os.environ.get(key)})
    app_values = require_values(app_source, APP_KEYS, f"{ROOT_ENV} or process environment")
    data_values = require_values(backend_values, DATA_KEYS, str(BACKEND_ENV))
    combined = {**app_values, **data_values}
    replace_or_append(ROOT_ENV, combined)
    # Next.js gives .env.local precedence over .env. Keep any existing app
    # credential overrides synchronized so a stale local value cannot win.
    if LOCAL_ENV.exists():
        replace_or_append(LOCAL_ENV, app_values)
    replace_or_append(BACKEND_ENV, combined)
    print("Synchronized Dhan credentials without displaying their values.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
