from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from agno.models.openrouter import OpenRouter


TRADING_AGENT_MODEL_ID = "deepseek/deepseek-v4.1-flash"
DEFAULT_TEXT_MODEL_ID = TRADING_AGENT_MODEL_ID
DEFAULT_MULTIMODAL_MODEL_ID = TRADING_AGENT_MODEL_ID
DEFAULT_REASONING_EFFORT = "xhigh"
RETIRED_MODEL_REPLACEMENTS = {
    "deepseek/deepseek-v4-flash-vision-exp": TRADING_AGENT_MODEL_ID,
}
_ENV_LOADED = False
_WARNED_RETIRED_MODEL_IDS: set[str] = set()
logger = logging.getLogger(__name__)


def create_text_trading_model(**overrides: Any) -> OpenRouter:
    _load_env_files()
    model_id = _resolve_model_id(
        overrides.pop("id", None),
        env_name="OPENROUTER_TEXT_MODEL_ID",
        default=DEFAULT_TEXT_MODEL_ID,
    )
    _apply_reasoning_defaults(overrides)
    return OpenRouter(id=model_id, **overrides)


def create_multimodal_trading_model(**overrides: Any) -> OpenRouter:
    _load_env_files()
    model_id = _resolve_model_id(
        overrides.pop("id", None),
        env_name="OPENROUTER_MULTIMODAL_MODEL_ID",
        default=DEFAULT_MULTIMODAL_MODEL_ID,
    )
    _apply_reasoning_defaults(overrides)
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


def _resolve_model_id(explicit_id: Any, *, env_name: str, default: str) -> str:
    configured_id = str(explicit_id or os.getenv(env_name) or default).strip() or default
    replacement = RETIRED_MODEL_REPLACEMENTS.get(configured_id)
    if replacement is None:
        return configured_id

    if configured_id not in _WARNED_RETIRED_MODEL_IDS:
        logger.warning(
            "Replacing retired trading model %s with %s. Update %s in the deployment environment.",
            configured_id,
            replacement,
            env_name,
        )
        _WARNED_RETIRED_MODEL_IDS.add(configured_id)
    return replacement


def _apply_reasoning_defaults(overrides: dict[str, Any]) -> None:
    overrides.setdefault("max_tokens", None)

    enabled = os.getenv("OPENROUTER_ENABLE_REASONING", "1").strip().lower() not in {"0", "false", "no", "off"}
    if not enabled:
        return

    overrides.setdefault("reasoning_effort", DEFAULT_REASONING_EFFORT)

    extra_body = overrides.get("extra_body")
    if not isinstance(extra_body, dict):
        extra_body = {}
    extra_body.setdefault("reasoning", {"enabled": True, "exclude": False})
    overrides["extra_body"] = extra_body
