import base64
import logging
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional

import requests


logger = logging.getLogger(__name__)

DEFAULT_MIC_MODEL = "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free"
OPENROUTER_CHAT_COMPLETIONS_URL = "https://openrouter.ai/api/v1/chat/completions"

SUPPORTED_AUDIO_FORMATS = {"wav", "mp3", "m4a", "ogg", "flac", "webm", "aac"}
MAX_AUDIO_BYTES = int(os.getenv("MIC_AGENT_MAX_AUDIO_BYTES", str(12 * 1024 * 1024)))
DEFAULT_TIMEOUT_SECONDS = float(os.getenv("MIC_AGENT_TIMEOUT_SECONDS", "90"))


class MicAgentError(RuntimeError):
    pass


@dataclass
class MicTranscriptionResult:
    text: str
    raw_text: str
    model: str
    usage: Optional[Dict[str, Any]] = None


def _clean_model_text(text: str) -> str:
    cleaned = str(text or "").strip()
    cleaned = re.sub(r"^```(?:json|text)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    cleaned = cleaned.strip().strip('"').strip("'").strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned


def _decode_audio_bytes(audio_base64: str) -> bytes:
    if not isinstance(audio_base64, str) or not audio_base64.strip():
        raise MicAgentError("audio is required")

    payload = audio_base64.strip()
    if payload.startswith("data:"):
        _, _, payload = payload.partition(",")

    try:
        return base64.b64decode(payload, validate=True)
    except Exception as exc:
        raise MicAgentError("audio must be valid base64") from exc


class MicAgent:
    """
    Small cloud mic agent.

    It uses an audio-capable OpenRouter chat model so the model can transcribe
    and resolve natural self-corrections in one pass.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        debug_mode: bool = True,
    ):
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        self.model = model or os.getenv("MIC_AGENT_MODEL") or DEFAULT_MIC_MODEL
        self.timeout_seconds = timeout_seconds
        self.debug_mode = debug_mode

    def transcribe(
        self,
        *,
        audio_base64: str,
        audio_format: str = "wav",
        language: str = "en",
    ) -> MicTranscriptionResult:
        if not self.api_key:
            raise MicAgentError("OPENROUTER_API_KEY is not configured")

        normalized_format = str(audio_format or "wav").strip().lower().lstrip(".")
        if normalized_format not in SUPPORTED_AUDIO_FORMATS:
            raise MicAgentError(f"unsupported audio format: {normalized_format}")

        audio_bytes = _decode_audio_bytes(audio_base64)
        if not audio_bytes:
            raise MicAgentError("audio is empty")
        if len(audio_bytes) > MAX_AUDIO_BYTES:
            raise MicAgentError("audio is too large")

        if self.debug_mode:
            logger.info(
                "MicAgent transcribe request model=%s format=%s audio_bytes=%s language=%s",
                self.model,
                normalized_format,
                len(audio_bytes),
                language,
            )

        encoded_audio = base64.b64encode(audio_bytes).decode("ascii")
        prompt = self._build_prompt(language=language)
        payload = self._build_payload(prompt, encoded_audio, normalized_format, use_camel_audio=False)

        response_json = self._post_openrouter(payload)
        text = self._extract_text(response_json)

        if self.debug_mode:
            logger.info("MicAgent transcribe response text_len=%s usage=%s", len(text), response_json.get("usage"))

        return MicTranscriptionResult(
            text=text,
            raw_text=text,
            model=self.model,
            usage=response_json.get("usage") if isinstance(response_json, dict) else None,
        )

    def _build_prompt(self, *, language: str) -> str:
        language_hint = str(language or "en").strip() or "en"
        return (
            "You are working under a mic functionality in a chat app. The user is speaking to a microphone instead of typing, "
            "and your job is to return the text they intended to put into the chat box. "
            "This is an intelligent mic, not a raw transcription tool. "
            f"Language hint: {language_hint}. "
            "Listen carefully, understand what the user said mistakenly or later corrected, and smartly remove the parts the user would not want in the final typed text. "
            "Resolve explicit corrections like 'no sorry', 'actually', 'wait', 'I mean', 'scratch that', 'make that', and later replacement values. "
            "Remove filler words, hesitation, repeated starts, and abandoned fragments when they are not part of the intended message. "
            "Keep the user's actual meaning, names, dates, times, numbers, and task details accurate. Do not invent missing details. "
            "Examples: "
            "Audio: 'hey emma lets meet today at the park at 4 pm oh no sorry 6 pm' -> 'hey emma lets meet today at the park at 6 pm.' "
            "Audio: 'remind me to call john tomorrow no wait actually call sara tomorrow morning' -> 'remind me to call sara tomorrow morning.' "
            "Audio: 'write this down um the budget is five thousand dollars actually make that seven thousand dollars for marketing' -> 'the budget is seven thousand dollars for marketing.' "
            "Audio: 'send a message saying i will arrive at noon scratch that i will arrive at 2 pm' -> 'i will arrive at 2 pm.' "
            "Return one clean sentence or paragraph only. No markdown, no labels, no quotes."
        )

    def _build_payload(
        self,
        prompt: str,
        encoded_audio: str,
        audio_format: str,
        *,
        use_camel_audio: bool,
    ) -> Dict[str, Any]:
        audio_key = "inputAudio" if use_camel_audio else "input_audio"
        return {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "input_audio",
                            audio_key: {
                                "data": encoded_audio,
                                "format": audio_format,
                            },
                        },
                    ],
                }
            ],
            "temperature": 0,
            "stream": False,
            "reasoning": {"enabled": True, "exclude": True},
        }

    def _post_openrouter(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": os.getenv("OPENROUTER_HTTP_REFERER", "https://aetheriaai.website"),
            "X-Title": os.getenv("OPENROUTER_X_TITLE", "Aetheria AI Mic"),
        }

        response = requests.post(
            OPENROUTER_CHAT_COMPLETIONS_URL,
            headers=headers,
            json=payload,
            timeout=self.timeout_seconds,
        )

        if response.status_code >= 400 and self._uses_snake_audio(payload):
            logger.warning(
                "OpenRouter mic request failed with snake_case audio payload; retrying camelCase. status=%s body=%s",
                response.status_code,
                response.text[:500],
            )
            content = payload["messages"][0]["content"]
            audio_part = next((part for part in content if part.get("type") == "input_audio"), None)
            if audio_part and "input_audio" in audio_part:
                audio_part["inputAudio"] = audio_part.pop("input_audio")
                response = requests.post(
                    OPENROUTER_CHAT_COMPLETIONS_URL,
                    headers=headers,
                    json=payload,
                    timeout=self.timeout_seconds,
                )

        if response.status_code >= 400:
            raise MicAgentError(f"OpenRouter mic request failed: HTTP {response.status_code} {response.text[:500]}")

        try:
            data = response.json()
        except ValueError as exc:
            raise MicAgentError("OpenRouter returned invalid JSON") from exc

        if not isinstance(data, dict):
            raise MicAgentError("OpenRouter returned an unexpected response")

        return data

    def _uses_snake_audio(self, payload: Dict[str, Any]) -> bool:
        try:
            content = payload["messages"][0]["content"]
            return any(part.get("type") == "input_audio" and "input_audio" in part for part in content)
        except Exception:
            return False

    def _extract_text(self, response_json: Dict[str, Any]) -> str:
        choices = response_json.get("choices") or []
        if not choices:
            raise MicAgentError("OpenRouter returned no transcription choices")

        message = choices[0].get("message") or {}
        content = message.get("content")

        if isinstance(content, str):
            text = _clean_model_text(content)
        elif isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict):
                    value = item.get("text") or item.get("content")
                    if value:
                        parts.append(str(value))
            text = _clean_model_text(" ".join(parts))
        else:
            text = ""

        if not text:
            raise MicAgentError("OpenRouter returned an empty transcription")

        return text


mic_agent = MicAgent()
