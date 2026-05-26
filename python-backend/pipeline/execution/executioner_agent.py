from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from agno.agent import Agent
from agno.media import Image

from pipeline.llm import create_mimo_model
from pipeline.services.dhan_execution_toolkit import DhanExecutionToolkit


class ExecutionerAgent:
    def __init__(self, toolkit: DhanExecutionToolkit) -> None:
        self.agent_name = os.getenv("EXECUTIONER_AGENT_NAME", "EXECUTIONER")
        self.use_agno = os.getenv("EXECUTIONER_USE_AGNO", "1").strip().lower() not in {"0", "false"}
        self.toolkit = toolkit

    def is_enabled(self) -> bool:
        return self.use_agno

    def analyze(self, execution_packet: Dict[str, Any], chart_paths: List[str], trade_config: Dict[str, Any] = None) -> str:
        if not self.is_enabled():
            raise RuntimeError("executioner_disabled")

        # Build capital instruction dynamically from trade_config
        trade_mode = str((trade_config or {}).get("trade_mode") or "auto").lower()
        trade_amount = (trade_config or {}).get("trade_amount")

        if trade_mode == "manual" and trade_amount:
            capital_instruction = f"Do not place a new order whose approximate notional value exceeds Rs {trade_amount}. Trade with a budget of exactly Rs {trade_amount}."
            trade_range_instruction = f"Trade only within a budget of ₹{trade_amount}. Do not exceed this amount."
        elif trade_mode == "auto":
            capital_instruction = "Size trades from available balance, margin validation, supplied risk context, and any explicit capital cap in these instructions."
            trade_range_instruction = "Size trades based on the user's available account balance. Use the full available balance for position sizing."
        else:
            # Fallback to env var
            max_trade_value = os.getenv("EXECUTIONER_MAX_TRADE_VALUE_RUPEES", "").strip()
            capital_instruction = (
                f"Do not place a new order whose approximate notional value exceeds Rs {max_trade_value}."
                if max_trade_value
                else "Size trades from available balance, margin validation, supplied risk context, and any explicit capital cap in these instructions."
            )
            trade_range_instruction = f"Trade between ₹100 to ₹{max_trade_value}" if max_trade_value else "Size trades from available balance."

        agent = Agent(
            name=self.agent_name,
            model=create_mimo_model(),
            description=(
                "Make the final intraday execution decision for one shortlisted stock using charts, prior reports, risk context, and Dhan trading tools."
            ),
            tools=[self.toolkit],
            instructions=[
                "You are the final execution layer in an intraday trading pipeline.",
                "You receive one chosen stock, its analyzer report, the risk report, market context, user Dhan account context, and two chart images.",
                "Reason carefully and step by step, but only provide the final actionable answer.",
                "Treat the market context as background information only; it is not trade permission, a trade veto, or position-size instruction.",
                "Do not reject the selected stock solely because the broader market context is bearish, bullish, mixed, volatile, event-driven, or neutral.",
                "Only avoid because of concrete execution checks: insufficient usable balance or margin, dangerous position overlap, invalid quantity, tool/API block, stale or contradictory selected-stock evidence, or chart setup deterioration.",
                "Only place an order if account has usable balance, there is no dangerous position overlap, the stock setup is still attractive from the images, and quantity is positive.",
                "If any of those checks fail, do not place an order.",
                "If live order placement, Super Order placement, static IP whitelisting, or margin validation blocks the trade, treat that as an execution block and do not pretend an order was sent.",
                "Do not invent order ids, correlation ids, funds, or quantities.",
                "To execute a trade or query data, you must use the provided Dhan tools:",
                "1. calculate_margin_requirement: Before placing any live order, call this to validate that the margin requirement is satisfied for your specific security, side, quantity, and reference price.",
                "2. place_protected_intraday_super_order: Prefer this tool for placing new intraday trades because it places entry, target, and stop-loss together in a single call.",
                "3. place_intraday_equity_order: Use this tool only for fallback cases, such as manual exits or when a protected super order cannot be used.",
                "4. Live queries: Use tools to check order/position lists or funds if you need fresher information before committing to a decision.",
                "When calling calculate_margin_requirement, pass only these named arguments exactly: security_id, side, quantity, reference_price, product_type, exchange_segment, trigger_price. Use product_type INTRADAY for intraday equity margin checks. Do not include extra_kwargs or XML/parameter tags.",
                "Use Dhan exchange segment enums, not raw exchange names: BSE_EQ or NSE_EQ for equity cash. This pipeline's shortlisted equity securities are BSE-sourced, so prefer BSE_EQ unless the selected stock explicitly supplies another segment.",
                "Validate Super Orders strictly: for BUY orders, the stop_loss_price must be below entry_price, and target_price must be above entry_price. For SELL orders, target_price must be below entry_price, and stop_loss_price must be above entry_price.",
                "Do not write a long analysis report. Your job is to decide and act, not to produce commentary.",
                "After acting or deciding not to act, output only a concise execution outcome in normal markdown/text.",
                "Include actual order id, correlation id, side, quantity, and reference price only when they are known from tools or supplied context.",
                trade_range_instruction,
                capital_instruction,
            ],
            markdown=True,
            add_datetime_to_context=True,
            debug_mode=True,
        )

        images = [Image(filepath=path) for path in chart_paths]
        response = agent.run(self._build_prompt(execution_packet), images=images)
        response_text = self._extract_text(response).strip()
        if not response_text:
            raise RuntimeError("executioner_empty_response")
        return response_text

    def _build_prompt(self, execution_packet: Dict[str, Any]) -> str:
        compact_packet = {
            "market_date": execution_packet.get("market_date"),
            "selected_stock": execution_packet.get("selected_stock"),
            "stock_analysis": execution_packet.get("stock_analysis"),
            "risk_decision": execution_packet.get("risk_decision"),
            "risk_report_text": execution_packet.get("risk_report_text"),
            "account_context": execution_packet.get("account_context"),
            "user_profile": execution_packet.get("user_profile"),
        }
        market_context = execution_packet.get("market_context") or execution_packet.get("regime") or {}
        tool_instructions = {
            "freshness": "Use the provided Dhan tools when you need fresher account, order, or trade information before making the decision.",
            "margin": "Before any live order, use calculate_margin_requirement when you have a concrete security, side, quantity, and reference price.",
            "preferred_order": "Prefer place_protected_intraday_super_order for new intraday trades because it places entry, target, stop loss, and optional trailing stop together.",
            "fallback_order": "Use place_intraday_equity_order only for intentional fallback cases such as explicit exits or when a protected order cannot be used.",
            "super_order_validation": "For BUY Super Orders require stop_loss_price below entry_price and target_price above entry_price. For SELL Super Orders require target_price below entry_price and stop_loss_price above entry_price.",
            "margin_call_format": "For calculate_margin_requirement pass only security_id, side, quantity, reference_price, product_type, exchange_segment, and trigger_price. Do not pass any other arguments or XML-style parameter tags.",
            "exchange_segment": "Use Dhan enum exchange segments. For selected stocks from this pipeline, use BSE_EQ unless supplied context explicitly says otherwise.",
        }
        return (
            "Make the final intraday execution decision for the supplied stock.\n"
            "Interpret the two chart images as the 5-minute and 15-minute candlestick charts for the same stock.\n"
            "The execution layer may avoid trading, plan a trade, or place a trade using the available Dhan tools.\n"
            "Use the stock analyzer report for setup quality, the risk report for cross-stock selection context, and the account context for feasibility.\n"
            "Use market context as background only; do not treat regime labels or news tone as standalone permission or prohibition.\n"
            "Output only the final execution outcome. Do not produce a sectioned report or JSON object.\n"
            "<context>\n"
            f"{json.dumps({'market_context': market_context}, ensure_ascii=True)}\n"
            "</context>\n"
            "<tools>\n"
            f"{json.dumps(tool_instructions, ensure_ascii=True)}\n"
            "</tools>\n"
            "Execution packet JSON:\n"
            f"{json.dumps(compact_packet, ensure_ascii=True)}"
        )

    def _extract_text(self, response: Any) -> str:
        if response is None:
            return ""
        if isinstance(response, str):
            return response
        content = getattr(response, "content", None)
        if isinstance(content, str):
            return content
        if content is not None:
            return str(content)
        messages = getattr(response, "messages", None)
        if isinstance(messages, list) and messages:
            maybe = getattr(messages[-1], "content", None)
            if isinstance(maybe, str):
                return maybe
            if maybe is not None:
                return str(maybe)
        return str(response)
