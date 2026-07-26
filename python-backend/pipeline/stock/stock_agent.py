from __future__ import annotations

from dataclasses import asdict, is_dataclass
import json
import os
from typing import Any, Dict, List, Optional

from agno.agent import Agent
from agno.media import Image

from pipeline.llm import create_multimodal_trading_model
from pipeline.services.cloud_persistence_service import CloudPersistenceService
from pipeline.services.dhan_execution_toolkit import DhanExecutionToolkit


class StockAgent:
    def __init__(self, toolkit: DhanExecutionToolkit) -> None:
        self.agent_name = os.getenv("STOCK_AGENT_NAME", "STOCK_AGENT")
        self.use_agno = os.getenv("STOCK_AGENT_USE_AGNO", "1").strip().lower() not in {"0", "false"}
        self.toolkit = toolkit
        self.last_run_metadata: Dict[str, Any] = {}

    def is_enabled(self) -> bool:
        return self.use_agno

    def analyze(
        self,
        stock_packet: Dict[str, Any],
        image_urls: List[str],
        trade_config: Optional[Dict[str, Any]] = None,
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

        trade_mode = str((trade_config or {}).get("trade_mode") or "auto").lower()
        trade_amount = (trade_config or {}).get("trade_amount")
        if trade_mode == "manual" and trade_amount:
            capital_instruction = (
                f"Treat Rs {trade_amount} as this stock's intraday margin budget. "
                "Size from Dhan margin, not from notional stock value."
            )
        else:
            capital_instruction = "Size from available balance, Dhan margin validation, and supplied account context."

        agent = Agent(
            id=os.getenv("STOCK_AGENT_ID", "stock-agent"),
            name=self.agent_name,
            model=create_multimodal_trading_model(),
            db=CloudPersistenceService.agno_db(),
            session_id=agno_session_id,
            user_id=user_id,
            metadata=run_metadata,
            description=(
                "Analyze one intraday stock candidate and make the final entry-only execution decision "
                "using supplied charts, market context, account context, optional quote confirmation, and Dhan tools."
            ),
            tools=[self.toolkit],
            instructions=[
                "You are a combined stock agent for an intraday Indian equity trading pipeline.",
                "Analyze the assigned stock and then decide whether to place one new entry trade now.",
                "Target trades that can complete within 1 minute to 1 hour.",
                "Use chart images and technical metadata as the primary current market evidence; they are generated immediately before this stock agent runs.",
                "Use the supplied *_ist fields and Asia/Calcutta market timezone for time-sensitive reasoning.",
                "You receive chart images in this order: current day 1m, 5m, 15m, 30m, 1h; previous day 5m, 15m, 1h.",
                "Use 1m for execution timing, 5m for primary setup, and 15m/30m/1h plus previous-day charts for structure.",
                "Use stage2.live_quote, stage2.live_liquidity, stage2.data_quality, previous_session, static_tradability, and derivatives reference as structured evidence when present.",
                "Treat missing live quote/spread/derivatives data as a data-quality warning, not as permission to invent those values.",
                "If a regime report is supplied, treat it as non-binding background context only.",
                "fresh_market_snapshot is optional extra quote/OHLC confirmation, not a second-agent freshness gate.",
                "Do not reject a trade solely because fresh_market_snapshot is missing or failed. Use it as a veto only when it directly contradicts chart/technical metadata, shows dangerous spread/staleness, or exposes an execution feasibility problem.",
                "Hard scope: only act on selected_stock.security_id from the stock packet.",
                "Other holdings, orders, and positions are read-only context.",
                "If there is any existing order or open intraday position for the selected stock, do not trade; report overlap and stop.",
                "Never cancel, modify, exit, hedge, convert, or manage existing trades.",
                "Never place an exit-only order. This agent only creates a new entry when there is no selected-stock overlap.",
                "Use Dhan tools for execution checks: calculate_intraday_equity_order_quantity first, calculate_margin_requirement before live placement, and prefer place_protected_intraday_super_order.",
                "Use place_intraday_equity_order only as a new-entry fallback when protected Super Order is unavailable for a non-input-error reason.",
                "Make at most one protected order placement attempt and at most one fallback normal entry attempt.",
                "If a Dhan tool returns DH-905, Input_Exception, invalid parameters, bad values, or missing fields, stop and report failed.",
                "Use only Dhan order_type values: LIMIT, MARKET, STOP_LOSS, STOP_LOSS_MARKET.",
                "For BUY Super Orders, stop_loss_price must be below entry_price and target_price above entry_price.",
                "For SELL Super Orders, target_price must be below entry_price and stop_loss_price above entry_price.",
                "Do not invent order ids, correlation ids, funds, margins, quantities, or tool results.",
                capital_instruction,
                "After acting or deciding not to act, output a concise final outcome in normal markdown/text.",
                "Always include these parseable headers exactly once: Decision, Execution Status, Selected Security ID, Selected Display Name, Trade Side, Order Type, Quantity, Reference Price, Correlation ID, Order ID.",
                "Use Decision: trade only if an order was planned or placed after concrete checks. Otherwise use Decision: avoid.",
                "Use Execution Status: placed, planned, skipped, blocked, or failed.",
            ],
            markdown=True,
            store_media=True,
            store_tool_messages=True,
            store_events=True,
            add_datetime_to_context=False,
            debug_mode=True,
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
        candidate = stock_packet.get("candidate") or {}
        selected_stock = stock_packet.get("selected_stock") or {}
        timing_context = stock_packet.get("timing_context") or {}
        fresh_market_snapshot = stock_packet.get("fresh_market_snapshot") or {}
        has_optional_quote_snapshot = str(fresh_market_snapshot.get("fetch_status") or "").lower() == "success"
        account_context = stock_packet.get("account_context") or {}
        trade_config = stock_packet.get("trade_config") or {}
        technical_metadata = (candidate.get("chart_artifacts") or {}).get("technical_metadata") or {}
        regime_report = str(stock_packet.get("regime_report") or candidate.get("regime_report") or "").strip()
        margin_filter = candidate.get("manual_margin_filter") or {}

        lines = [
            "Analyze the supplied intraday stock candidate and make the final entry-only execution decision.",
            "Use the charts, technical metadata, Stage 2 context, optional quote confirmation, and account context together.",
            "",
            "## Timing Context",
            json.dumps(timing_context, ensure_ascii=True),
            "",
            "## Selected Stock",
            json.dumps(
                {
                    "rank": selected_stock.get("rank"),
                    "security_id": selected_stock.get("security_id"),
                    "symbol": selected_stock.get("symbol"),
                    "display_name": selected_stock.get("display_name"),
                    "candidate_source": selected_stock.get("candidate_source"),
                    "stock": selected_stock.get("stock"),
                    "stage2": selected_stock.get("stage2"),
                    "manual_margin_filter": margin_filter,
                },
                ensure_ascii=True,
            ),
        ]

        if regime_report:
            lines.extend(
                [
                    "",
                    "## Regime Context",
                    "Use this only as non-binding background context:",
                    regime_report,
                ]
            )

        lines.extend(
            [
                "",
                "## Technical Metadata",
                json.dumps(technical_metadata, ensure_ascii=True),
                "",
                "## Stage 2 Structured Evidence",
                json.dumps(
                    {
                        "stock": selected_stock.get("stock"),
                        "stage2": selected_stock.get("stage2"),
                    },
                    ensure_ascii=True,
                ),
            ]
        )
        if has_optional_quote_snapshot:
            lines.extend(
                [
                    "",
                    "## Optional Quote/OHLC Snapshot",
                    json.dumps(fresh_market_snapshot, ensure_ascii=True),
                ]
            )
        lines.extend(
            [
                "",
                "## Account Context",
                json.dumps(account_context, ensure_ascii=True),
                "",
                "## Trade Config",
                json.dumps(trade_config, ensure_ascii=True),
                "",
                "## Output Requirements",
                "First give a compact analysis covering chart read, setup quality, risk, and execution rationale.",
                "Then provide the required headers exactly as plain text lines.",
            ]
        )
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
