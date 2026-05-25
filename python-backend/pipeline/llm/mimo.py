from __future__ import annotations

from dataclasses import dataclass, field
from os import getenv
from pathlib import Path
from typing import Any, Dict, Optional

from dotenv import load_dotenv

from agno.exceptions import ModelAuthenticationError
from agno.models.message import Message
from agno.models.openai.like import OpenAILike


DEFAULT_MIMO_BASE_URL = "https://token-plan-ams.xiaomimimo.com/v1"
DEFAULT_MIMO_MODEL_ID = "mimo-v2.5"
_ENV_LOADED = False


@dataclass
class MiMo(OpenAILike):
    """
    OpenAI-compatible Agno model adapter for Xiaomi MiMo.

    MiMo requires prior assistant `reasoning_content` to be sent back in
    multi-turn agent/tool conversations when thinking mode is enabled. Agno can
    store that field, so this adapter only preserves it in outbound messages.
    """

    id: str = field(default_factory=lambda: getenv("MIMO_MODEL_ID", DEFAULT_MIMO_MODEL_ID))
    name: str = "MiMo"
    provider: str = "MiMo"

    api_key: Optional[str] = field(default_factory=lambda: getenv("MIMO_API_KEY"))
    base_url: str = field(default_factory=lambda: getenv("MIMO_BASE_URL", DEFAULT_MIMO_BASE_URL))
    max_completion_tokens: Optional[int] = field(
        default_factory=lambda: _optional_int(getenv("MIMO_MAX_COMPLETION_TOKENS"), 4096)
    )
    temperature: Optional[float] = field(default_factory=lambda: _optional_float(getenv("MIMO_TEMPERATURE")))
    top_p: Optional[float] = field(default_factory=lambda: _optional_float(getenv("MIMO_TOP_P")))
    supports_native_structured_outputs: bool = False

    def _get_client_params(self) -> Dict[str, Any]:
        _load_env_files()
        if not self.api_key:
            self.api_key = getenv("MIMO_API_KEY")
            if not self.api_key:
                raise ModelAuthenticationError(
                    message="MIMO_API_KEY not set. Please set the MIMO_API_KEY environment variable.",
                    model_name=self.name,
                )
        return super()._get_client_params()

    def _format_message(self, message: Message, compress_tool_results: bool = False) -> Dict[str, Any]:
        formatted = super()._format_message(message, compress_tool_results)
        if message.reasoning_content:
            formatted["reasoning_content"] = message.reasoning_content
        return formatted


def create_mimo_model(**overrides: Any) -> MiMo:
    _load_env_files()
    extra_body = dict(overrides.pop("extra_body", {}) or {})
    thinking_type = getenv("MIMO_THINKING_TYPE", "disabled").strip()
    if thinking_type:
        extra_body.setdefault("thinking", {"type": thinking_type})
    return MiMo(extra_body=extra_body or None, **overrides)


def _load_env_files() -> None:
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    backend_dir = Path(__file__).resolve().parents[2]
    root_dir = backend_dir.parent
    load_dotenv(root_dir / ".env", override=False)
    load_dotenv(backend_dir / ".env", override=False)
    _ENV_LOADED = True


def _optional_int(value: Optional[str], default: Optional[int] = None) -> Optional[int]:
    if value is None or value.strip() == "":
        return default
    return int(value)


def _optional_float(value: Optional[str], default: Optional[float] = None) -> Optional[float]:
    if value is None or value.strip() == "":
        return default
    return float(value)
