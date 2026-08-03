import os
from dataclasses import dataclass
from typing import Any, Dict

from agno.models.message import Message
from agno.models.openai.like import OpenAILike
from agno.models.response import ModelResponse


MIMO_OPENAI_BASE_URL = os.getenv(
    "MIMO_OPENAI_BASE_URL",
    "https://token-plan-ams.xiaomimimo.com/v1",
)


@dataclass
class XiaomiMiMoModel(OpenAILike):
    """
    MiMo's thinking mode requires assistant reasoning_content to be replayed
    in later turns when tool calls exist in history. Agno parses that field,
    but the generic OpenAI-like serializer does not send it back.
    """

    def _format_message(self, message: Message, compress_tool_results: bool = False) -> Dict[str, Any]:
        try:
            message_dict = super()._format_message(message, compress_tool_results=compress_tool_results)
        except TypeError as exc:
            if "compress_tool_results" not in str(exc):
                raise
            # Support older Agno builds whose OpenAIChat._format_message()
            # accepted only (message) while keeping newer builds working too.
            message_dict = super()._format_message(message)

        if message.role == "assistant" and message.reasoning_content:
            message_dict["reasoning_content"] = message.reasoning_content

        return message_dict

    def _parse_provider_response_delta(self, response_delta: Any) -> ModelResponse:
        model_response = super()._parse_provider_response_delta(response_delta)

        # Agno Team streaming only yields content events when `.content` is not
        # None. MiMo streams thinking as reasoning-only deltas, so expose an
        # empty content delta to let the existing event pipeline carry
        # `reasoning_content` without adding text to the final answer.
        if model_response.reasoning_content is not None and model_response.content is None:
            model_response.content = ""

        return model_response


def get_mimo_model(model: str) -> XiaomiMiMoModel:
    api_key = os.getenv("MIMO_API_KEY") or os.getenv("XIAOMI_MIMO_API_KEY")
    return XiaomiMiMoModel(
        id=model,
        name="XiaomiMiMo",
        provider="Xiaomi MiMo",
        api_key=api_key,
        base_url=MIMO_OPENAI_BASE_URL,
    )
