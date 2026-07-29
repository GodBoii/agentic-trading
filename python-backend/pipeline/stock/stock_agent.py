from __future__ import annotations

from dataclasses import asdict, is_dataclass
import json
import os
from typing import Any, Dict, List, Optional

from agno.agent import Agent
from agno.media import Image
from agno.tools import Toolkit

from pipeline.llm import create_multimodal_trading_model
from pipeline.services.cloud_persistence_service import CloudPersistenceService


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
            tool_call_limit=12,
            instructions=[
                "You are an expert intraday Indian equity trader.",
                "Study the assigned stock using the attached charts and any available tools that are useful.",
                "The attached image order is: current-day 1m EXECUTION, current-day 5m SETUP, current-day 15m STRUCTURE, then previous-session 15m CONTEXT.",
                "The charts are price-focused. Use get_technical_data and get_security_overview for exact RSI, ATR, RVOL, volume acceleration, opening-range, liquidity, and level values.",
                "Do not assume stock CVD, footprint, historical DOM, or trade aggressor data exists. Dhan historical candles do not contain those fields.",
                "Before making the trade decision, call get_security_overview and get_technical_data once so the chart reading is checked against exact numeric data.",
                "Understand how price is moving and evaluate price action, volume, momentum, liquidity, liquidity pools or sweeps, market structure, and risk-reward wherever relevant.",
                "Decide whether a sound intraday entry exists and place it when appropriate. Any trade opened by you is for the current trading day only.",
                "Focus only on the stock assigned to you.",
                "Any live position or order in another stock belongs to another agent or workflow. Never modify, cancel, exit, hedge, convert, or otherwise touch it.",
                "If the assigned stock already has a live position or active order, do not create another entry.",
                "After completing your analysis and before your final decision or order, call get_current_stock_state once, use its newly fetched quote and OHLC data to update your view, and then proceed.",
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
        response = agent.run(
            self._build_prompt(stock_packet),
            images=images,
            metadata=run_metadata,
        )
        self.last_run_metadata = self._extract_metadata(response)
        response_text = self._extract_text(response).strip()
        if not response_text:
            raise RuntimeError("stock_agent_empty_response")
        return response_text

    def _build_prompt(self, stock_packet: Dict[str, Any]) -> str:
        selected_stock = stock_packet.get("selected_stock") or {}
        timing_context = stock_packet.get("timing_context") or {}
        market_session = timing_context.get("market_session") or {}
        current_time = (
            timing_context.get("current_market_time_ist")
            or timing_context.get("stock_agent_started_at_ist")
            or ""
        )
        lines = [
            "Analyze the assigned stock for an intraday trade using the attached charts and available tools.",
            "Attached charts: current 1m execution, current 5m setup, current 15m structure, previous-session 15m context.",
            "",
            "## Assignment",
            f"- Security ID: {selected_stock.get('security_id')}",
            f"- Stock: {selected_stock.get('display_name') or selected_stock.get('symbol')}",
        ]
        if selected_stock.get("symbol"):
            lines.append(f"- Symbol: {selected_stock.get('symbol')}")
        if current_time:
            lines.append(f"- Indian date and time: {current_time}")
        lines.append(f"- Regular market session: {market_session.get('regular_session') or '09:15-15:30 IST'}")
        if market_session.get("is_open_now") is not None:
            lines.append(f"- Market open now: {bool(market_session.get('is_open_now'))}")
        if market_session.get("minutes_to_close") is not None:
            lines.append(f"- Minutes to close: {market_session.get('minutes_to_close')}")
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
