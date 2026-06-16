from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from agno.models.openrouter import OpenRouter


DEFAULT_TEXT_MODEL_ID = "deepseek/deepseek-v4-pro"
DEFAULT_MULTIMODAL_MODEL_ID = "minimax/minimax-m3"
_ENV_LOADED = False


def create_text_trading_model(**overrides: Any) -> OpenRouter:
    _load_env_files()
    model_id = overrides.pop("id", None) or os.getenv("OPENROUTER_TEXT_MODEL_ID", DEFAULT_TEXT_MODEL_ID)
    return OpenRouter(id=model_id, **overrides)


def create_multimodal_trading_model(**overrides: Any) -> OpenRouter:
    _load_env_files()
    model_id = overrides.pop("id", None) or os.getenv("OPENROUTER_MULTIMODAL_MODEL_ID", DEFAULT_MULTIMODAL_MODEL_ID)
    return OpenRouter(id=model_id, **overrides)


def create_trading_model(**overrides: Any) -> OpenRouter:
    return create_text_trading_model(**overrides)


def _load_env_files() -> None:
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    backend_dir = Path(__file__).resolve().parents[2]
    root_dir = backend_dir.parent
    load_dotenv(root_dir / ".env", override=False)
    load_dotenv(backend_dir / ".env", override=False)
    _ENV_LOADED = True
