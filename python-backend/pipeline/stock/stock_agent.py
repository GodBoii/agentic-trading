from __future__ import annotations

from dataclasses import asdict, is_dataclass
import json
import os
from typing import Any, Callable, Dict, List, Optional

from agno.agent import Agent
from agno.media import Image
from agno.tools import Toolkit

from pipeline.llm import create_multimodal_trading_model
from pipeline.services.cloud_persistence_service import CloudPersistenceService
from pipeline.stock.toolkits.markdown_result import tool_result_markdown


class StockAgent:
    def __init__(self, toolkits: List[Toolkit]) -> None:
        self.agent_name = os.getenv("STOCK_AGENT_NAME", "STOCK_AGENT")
        self.use_agno = os.getenv("STOCK_AGENT_USE_AGNO", "1").strip().lower() not in {"0", "false"}
        self.debug_mode = os.getenv("STOCK_AGENT_DEBUG", "0").strip().lower() in {"1", "true", "yes"}
        self.toolkits = list(toolkits)
        self.last_run_metadata: Dict[str, Any] = {}

    def is_enabled(self) -> bool:
        return self.use_agno

    def analyze(
        self,
        stock_packet: Dict[str, Any],
        image_urls: List[str],
        run_context: Optional[Dict[str, Any]] = None,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> str:
        if not self.is_enabled():
            raise RuntimeError("stock_agent_disabled")

        persistence_context = dict(run_context or {})
        agno_session_id = str(persistence_context.get("agno_session_id") or "").strip()
        if not agno_session_id:
            raise RuntimeError("stock_agent_agno_session_id_required")
        user_id = str(persistence_context.get("user_id") or "").strip() or None
        run_metadata = {
            **persistence_context,
            "image_urls": list(image_urls),
            "media_persistence": "supabase_storage_public_url",
        }

        agent = Agent(
            id=os.getenv("STOCK_AGENT_ID", "stock-agent"),
            name=self.agent_name,
            model=create_multimodal_trading_model(),
            db=CloudPersistenceService.agno_db(),
            session_id=agno_session_id,
            user_id=user_id,
            metadata=run_metadata,
            description=(
                "Analyze one assigned Indian equity for an intraday entry and act when a sound setup exists."
            ),
            tools=self.toolkits,
            tool_call_limit=3,
            instructions=[
                "You are an expert intraday Indian equity trader.",
                "Study the assigned stock using the attached charts and the complete initial decision snapshot in the user message.",
                "The attached image order is: current-day 1m, current-day 5m, current-day 15m, previous-session 5m, previous-session 15m, volume and participation, momentum and volatility, OHLCV-derived price-structure liquidity, then current/previous TPO market profile.",
                "The initial snapshot is the single source for identity, time, market state, technical readings, account state, and risk budget. Do not look for read-only tools.",
                "Do not assume stock CVD, footprint, historical DOM, or trade aggressor data exists. Dhan historical candles do not contain those fields.",
                "The price-structure liquidity image is derived from OHLCV and the TPO image is time at price, not order-book liquidity or exact volume at price.",
                "Understand how price is moving and evaluate price action, volume, momentum, liquidity, liquidity pools or sweeps, market structure, and risk-reward wherever relevant.",
                "Decide whether a sound intraday entry exists and place it when appropriate. Any trade opened by you is for the current trading day only.",
                "Focus only on the stock assigned to you.",
                "Any live position or order in another stock belongs to another agent or workflow. Never modify, cancel, exit, hedge, convert, or otherwise touch it.",
                "If account data is unavailable, or the assigned stock already has a live position or active order, do not create another entry.",
                "Exactly two tools are available: estimate_intraday_quantity and place_protected_intraday_order.",
                "Before any order, call estimate_intraday_quantity with the intended entry and stop, then use its recommended quantity.",
                "Only place a protected order with an explicit entry, target, and stop-loss. There is no unprotected-order fallback.",
                "Give your final analysis and outcome naturally and concisely. Do not use a fixed response template.",
            ],
            markdown=True,
            store_media=True,
            store_tool_messages=True,
            store_events=True,
            add_datetime_to_context=False,
            debug_mode=self.debug_mode,
        )

        images = [Image(url=url) for url in image_urls]
        prompt = self._build_prompt(stock_packet)
        response_stream = agent.run(
            prompt,
            images=images,
            metadata=run_metadata,
            stream=True,
            stream_events=True,
            yield_run_output=True,
        )
        timeline: List[Dict[str, Any]] = []
        content_chunks: List[str] = []
        completed_content = ""
        final_response: Any = None

        for item in response_stream:
            event_name = str(getattr(item, "event", "") or "")
            if event_name:
                normalized = self._normalize_stream_event(item)
                if normalized is not None:
                    timeline.append(normalized)
                    if progress_callback is not None:
                        progress_callback(dict(normalized))
                if event_name == "RunContent":
                    content = getattr(item, "content", None)
                    if isinstance(content, str):
                        content_chunks.append(content)
                elif event_name == "RunCompleted":
                    content = getattr(item, "content", None)
                    if isinstance(content, str):
                        completed_content = content
                    final_response = item
            else:
                final_response = item

        self.last_run_metadata = self._extract_metadata(final_response)
        self.last_run_metadata["timeline"] = timeline
        self.last_run_metadata["tool_summary"] = self._build_tool_summary(timeline)
        response_text = self._extract_text(final_response).strip()
        if not response_text:
            response_text = completed_content.strip() or "".join(content_chunks).strip()
        if not response_text:
            raise RuntimeError("stock_agent_empty_response")
        return response_text

    def _normalize_stream_event(self, event: Any) -> Optional[Dict[str, Any]]:
        event_name = str(getattr(event, "event", "") or "")
        run_id = getattr(event, "run_id", None)
        base: Dict[str, Any] = {
            "agno_event": event_name,
            "agno_run_id": run_id,
            "created_at": getattr(event, "created_at", None),
        }
        if event_name in {"ReasoningContentDelta", "ReasoningStep"}:
            text = (
                getattr(event, "reasoning_content", None)
                or getattr(event, "content", None)
            )
            if not text:
                return None
            return {
                **base,
                "type": "stock_agent_thinking",
                "message": str(text),
            }
        if event_name == "RunContent":
            reasoning = getattr(event, "reasoning_content", None)
            if reasoning:
                return {
                    **base,
                    "type": "stock_agent_thinking",
                    "message": str(reasoning),
                }
            content = getattr(event, "content", None)
            if not content:
                return None
            return {
                **base,
                "type": "stock_agent_response_delta",
                "message": str(content),
            }
        if event_name == "ToolCallStarted":
            return {
                **base,
                "type": "stock_agent_tool_call_started",
                **self._tool_event_payload(getattr(event, "tool", None), include_result=False),
            }
        if event_name in {"ToolCallCompleted", "ToolCallError"}:
            tool_payload = self._tool_event_payload(
                getattr(event, "tool", None),
                include_result=True,
            )
            error = getattr(event, "error", None)
            if event_name == "ToolCallError" or tool_payload.get("tool_call_error"):
                return {
                    **base,
                    "type": "stock_agent_tool_call_error",
                    **tool_payload,
                    "error": str(error or tool_payload.get("result_preview") or "tool_call_failed"),
                }
            return {
                **base,
                "type": "stock_agent_tool_call_completed",
                **tool_payload,
            }
        if event_name == "RunError":
            return {
                **base,
                "type": "stock_agent_run_error",
                "error": str(getattr(event, "content", None) or "agent_run_failed"),
            }
        return None

    def _tool_event_payload(
        self,
        tool: Any,
        *,
        include_result: bool,
    ) -> Dict[str, Any]:
        if tool is None:
            return {
                "tool_call_id": None,
                "tool_name": "unknown_tool",
                "tool_args": {},
            }
        result = getattr(tool, "result", None)
        result_text = "" if result is None else str(result)
        metrics = getattr(tool, "metrics", None)
        duration = getattr(metrics, "duration", None) if metrics is not None else None
        payload: Dict[str, Any] = {
            "tool_call_id": getattr(tool, "tool_call_id", None),
            "tool_name": getattr(tool, "tool_name", None) or "unknown_tool",
            "tool_args": self._json_safe(getattr(tool, "tool_args", None) or {}),
            "tool_call_error": bool(getattr(tool, "tool_call_error", False)),
        }
        if duration is not None:
            payload["duration_seconds"] = round(float(duration), 4)
        if include_result:
            payload["result_length"] = len(result_text)
            payload["result_preview"] = result_text[:2000]
            payload["result"] = result_text
            try:
                parsed = json.loads(result_text)
            except (TypeError, ValueError):
                parsed = None
            if isinstance(parsed, dict):
                status = str(parsed.get("status") or "success").lower()
                payload["result_status"] = status
                payload["result_partial"] = status == "partial" or bool(parsed.get("partial"))
                for key in (
                    "as_of_ist",
                    "snapshot_fetched_at_ist",
                    "candle_data_as_of_ist",
                    "market_data_age_seconds",
                    "candle_data_age_seconds",
                ):
                    if parsed.get(key) is not None:
                        payload[key] = parsed.get(key)
            else:
                markdown_fields = self._markdown_result_fields(result_text)
                status = str(markdown_fields.get("status") or "success").lower()
                payload["result_status"] = status
                payload["result_partial"] = status == "partial" or str(
                    markdown_fields.get("partial") or ""
                ).lower() == "true"
                for key in (
                    "as_of_ist",
                    "snapshot_fetched_at_ist",
                    "candle_data_as_of_ist",
                    "market_data_age_seconds",
                    "candle_data_age_seconds",
                ):
                    if markdown_fields.get(key) is not None:
                        payload[key] = markdown_fields[key]
        return payload

    @staticmethod
    def _markdown_result_fields(result_text: str) -> Dict[str, str]:
        fields: Dict[str, str] = {}
        for line in str(result_text or "").splitlines():
            stripped = line.strip()
            if not stripped.startswith("- ") or ":" not in stripped:
                continue
            key, value = stripped[2:].split(":", 1)
            key = key.strip()
            if key and key not in fields:
                fields[key] = value.strip()
        return fields

    @staticmethod
    def _build_tool_summary(timeline: List[Dict[str, Any]]) -> Dict[str, Any]:
        completed = [
            item
            for item in timeline
            if item.get("type") in {
                "stock_agent_tool_call_completed",
                "stock_agent_tool_call_error",
            }
        ]
        succeeded = [
            item
            for item in completed
            if item.get("type") == "stock_agent_tool_call_completed"
            and not item.get("result_partial")
        ]
        partial = [item for item in completed if item.get("result_partial")]
        failed = [item for item in completed if item.get("type") == "stock_agent_tool_call_error"]
        result_lengths = [int(item.get("result_length") or 0) for item in completed]
        durations = [
            float(item["duration_seconds"])
            for item in completed
            if item.get("duration_seconds") is not None
        ]
        largest = max(completed, key=lambda item: int(item.get("result_length") or 0), default=None)
        return {
            "tool_calls": len(completed),
            "succeeded": len(succeeded),
            "partial": len(partial),
            "failed": len(failed),
            "success_rate": round(len(succeeded) / len(completed), 4) if completed else None,
            "total_result_characters": sum(result_lengths),
            "average_result_characters": (
                round(sum(result_lengths) / len(result_lengths), 2)
                if result_lengths
                else 0
            ),
            "total_duration_seconds": round(sum(durations), 4),
            "largest_result": (
                {
                    "tool": largest.get("tool_name"),
                    "characters": int(largest.get("result_length") or 0),
                }
                if largest
                else None
            ),
        }

    def _build_prompt(self, stock_packet: Dict[str, Any]) -> str:
        decision_context = stock_packet.get("decision_context") or {}
        lines = [
            "Analyze the assigned stock for an intraday trade using the attached charts and the initial decision snapshot below.",
            "Attached charts in order: current 1m, current 5m, current 15m, previous-session 5m, previous-session 15m, volume/participation, momentum/volatility, OHLCV-derived price-structure liquidity, and current/previous TPO market profile.",
            "",
            "All read-only evidence is already included exactly once. The only available tools size a trade and place a protected order.",
            "",
        ]
        rendered = tool_result_markdown(decision_context).replace(
            "## Tool result",
            "## Initial decision snapshot",
            1,
        )
        lines.append(rendered)
        return "\n".join(lines)

    def _extract_metadata(self, response: Any) -> Dict[str, Any]:
        if response is None:
            return {}

        metadata: Dict[str, Any] = {}
        for attr in ("reasoning_content", "reasoning_steps", "reasoning_messages", "metrics"):
            value = getattr(response, attr, None)
            if value:
                metadata[attr] = self._json_safe(value)

        metrics = metadata.get("metrics") if isinstance(metadata.get("metrics"), dict) else {}
        token_keys = (
            "reasoning_tokens",
            "thinking_tokens",
            "input_tokens",
            "output_tokens",
            "total_tokens",
            "prompt_tokens",
            "completion_tokens",
        )
        token_usage = {key: metrics.get(key) for key in token_keys if metrics.get(key) is not None}
        if token_usage:
            metadata["token_usage"] = token_usage

        tool_calls: List[Any] = []
        messages = getattr(response, "messages", None)
        if isinstance(messages, list):
            for message in messages:
                calls = getattr(message, "tool_calls", None)
                if calls:
                    safe_calls = self._json_safe(calls)
                    if isinstance(safe_calls, list):
                        tool_calls.extend(safe_calls)
                    else:
                        tool_calls.append(safe_calls)
        if tool_calls:
            metadata["tool_calls"] = tool_calls

        return metadata

    def _json_safe(self, value: Any, depth: int = 0) -> Any:
        if depth > 8:
            return str(value)

        if value is None or isinstance(value, (str, int, float, bool)):
            return value

        try:
            json.dumps(value, ensure_ascii=True)
            return value
        except TypeError:
            pass

        if isinstance(value, dict):
            return {str(key): self._json_safe(item, depth + 1) for key, item in value.items()}

        if isinstance(value, (list, tuple, set)):
            return [self._json_safe(item, depth + 1) for item in value]

        if is_dataclass(value):
            return self._json_safe(asdict(value), depth + 1)

        model_dump = getattr(value, "model_dump", None)
        if callable(model_dump):
            try:
                return self._json_safe(model_dump(mode="json"), depth + 1)
            except TypeError:
                return self._json_safe(model_dump(), depth + 1)
            except Exception:
                pass

        to_dict = getattr(value, "to_dict", None)
        if callable(to_dict):
            try:
                return self._json_safe(to_dict(), depth + 1)
            except Exception:
                pass

        object_dict = getattr(value, "__dict__", None)
        if isinstance(object_dict, dict) and object_dict:
            return {
                str(key): self._json_safe(item, depth + 1)
                for key, item in object_dict.items()
                if not str(key).startswith("_") and not callable(item)
            }

        return str(value)

    def _extract_text(self, response: Any) -> str:
        if response is None:
            return ""
        if isinstance(response, str):
            return response
        content = getattr(response, "content", None)
        if isinstance(content, str) and content.strip():
            return content
        if content is not None and str(content).strip():
            return str(content)
        reasoning = getattr(response, "reasoning_content", None)
        if isinstance(reasoning, str) and reasoning.strip():
            return reasoning
        messages = getattr(response, "messages", None)
        if isinstance(messages, list) and messages:
            for message in reversed(messages):
                maybe = getattr(message, "content", None)
                if isinstance(maybe, str) and maybe.strip():
                    return maybe
                if maybe is not None and str(maybe).strip():
                    return str(maybe)
        return str(response)
