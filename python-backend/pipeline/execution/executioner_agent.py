from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

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

    def analyze(
        self,
        execution_packet: Dict[str, Any],
        chart_paths: List[str],
        trade_config: Optional[Dict[str, Any]] = None,
    ) -> str:
        if not self.is_enabled():
            raise RuntimeError("executioner_disabled")

        trade_mode = str((trade_config or {}).get("trade_mode") or "auto").lower()
        trade_amount = (trade_config or {}).get("trade_amount")

        if trade_mode == "manual" and trade_amount:
            capital_instruction = (
                f"Treat Rs {trade_amount} as this stock's intraday margin budget, not as a notional cap. "
                "Size quantity from Dhan margin requirement, then verify margin before order placement."
            )
            trade_range_instruction = f"Use no more than Rs {trade_amount} margin for this stock."
        elif trade_mode == "auto":
            capital_instruction = "Size trades from available balance, Dhan margin validation, and supplied account context."
            trade_range_instruction = "Size trades based on the user's available account balance and margin response."
        else:
            max_trade_value = os.getenv("EXECUTIONER_MAX_TRADE_VALUE_RUPEES", "").strip()
            capital_instruction = (
                f"Use no more than Rs {max_trade_value} margin for this stock."
                if max_trade_value
                else "Size trades from available balance, Dhan margin validation, and supplied account context."
            )
            trade_range_instruction = capital_instruction

        agent = Agent(
            name=self.agent_name,
            model=create_mimo_model(),
            description=(
                "Make the final intraday execution decision for one analyzed stock using charts, "
                "the stock analyzer report, account context, and Dhan trading tools."
            ),
            tools=[self.toolkit],
            instructions=[
                "You are an entry-only executioner agent in an intraday trading pipeline.",
                "You receive one stock, its risk-aware stock analyzer report, user Dhan account context, and chart images.",
                "Your only job is to decide whether the supplied stock has a fresh intraday trade worth entering now, size it, place at most one protected entry order, and stop.",
                "Target trades that can complete within 1 minute to 1 hour; faster clean completion is better, but never force a trade just to be active.",
                "You are not a trade monitor, portfolio manager, recovery agent, or kill-switch agent.",
                "You receive up to 8 chart images for the selected stock:",
                "  Current Day: 1m, 5m, 15m, 30m, 1h",
                "  Previous Day: 5m, 15m, 1h",
                "Use previous-day charts for key levels and current-day charts for live setup quality.",
                "No broad market regime context is supplied to this execution layer. Validate this stock's current setup and execution feasibility only.",
                "Hard scope: only act on the selected_stock.security_id from the execution packet. Treat every other account order, holding, or position as read-only context.",
                "If the account already contains orders or positions for any other security, do not cancel, modify, exit, hedge, convert, or otherwise touch them.",
                "If there is an existing order or open position for the selected stock, do not manage or exit it. Report that the selected stock already has exposure/order overlap and stop.",
                "Never call destructive or management tools: exit_position, exit_all_intraday_positions, cancel_order, modify_order, cancel_super_order, modify_super_order, convert_position, cancel_forever_order, modify_forever_order, delete_conditional_trigger, cancel_conditional_trigger, or modify_conditional_trigger.",
                "Never place an exit-only order. Never place a SELL to close an existing long or a BUY to close an existing short. This agent only creates a new entry when there is no selected-stock overlap.",
                "After a live order is placed, do not monitor the trade, chase fills, modify prices, cancel orders, or issue exits. Verify the placed order once if needed, then output the result and stop.",
                "Only avoid because of concrete execution checks: insufficient usable balance or margin, dangerous position overlap, invalid quantity, tool/API block, stale or contradictory selected-stock evidence, or chart setup deterioration.",
                "Only place an order if account has usable balance, there is no dangerous position overlap, the stock setup is still attractive from the images, and quantity is positive.",
                "If live order placement, Super Order placement, static IP whitelisting, or margin validation blocks the trade, treat that as an execution block and do not pretend an order was sent.",
                "Do not invent order ids, correlation ids, funds, margins, or quantities.",
                "To execute a trade or query data, you must use the provided Dhan tools:",
                "1. calculate_intraday_equity_order_quantity: Use this first for new trades. It calculates Dhan margin for quantity=1 and returns the margin-budget-aware quantity.",
                "2. calculate_margin_requirement: Before placing any live order, call this again for the final quantity to validate that the margin requirement is satisfied.",
                "3. place_protected_intraday_super_order: Prefer this tool for new intraday trades because it places entry, target, and stop-loss together.",
                "4. place_intraday_equity_order: Use this only as an entry fallback when a protected Super Order cannot be used. Do not use it for exits or position management.",
                "5. Live queries: Use tools to check order/position lists or funds if you need fresher information before committing to a decision.",
                "For manual mode, do not size from share price <= budget. Size from margin_per_share returned by Dhan margin API.",
                "If calculate_intraday_equity_order_quantity returns recommended_quantity <= 0, do not place an order.",
                "When calling calculate_margin_requirement, pass only these named arguments exactly: security_id, side, quantity, reference_price, product_type, exchange_segment, trigger_price.",
                "Use product_type INTRADAY for intraday equity margin checks.",
                "Use Dhan exchange segment enums, not raw exchange names: BSE_EQ or NSE_EQ. This pipeline's shortlisted equity securities are BSE-sourced, so prefer BSE_EQ unless the selected stock explicitly supplies another segment.",
                "Validate Super Orders strictly: for BUY orders, stop_loss_price must be below entry_price and target_price above entry_price. For SELL orders, target_price must be below entry_price and stop_loss_price above entry_price.",
                "After acting or deciding not to act, output only a concise execution outcome in normal markdown/text.",
                "Include these headers when possible: Decision, Execution Status, Selected Security ID, Selected Display Name, Trade Side, Order Type, Quantity, Reference Price, Correlation ID, Order ID.",
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
            "account_context": execution_packet.get("account_context"),
            "user_profile": execution_packet.get("user_profile"),
            "trade_config": execution_packet.get("trade_config"),
        }
        tool_instructions = {
            "sizing": "For new intraday trades, first call calculate_intraday_equity_order_quantity with security_id, side, reference_price, margin_budget, and stop_loss_price.",
            "margin": "Before any live order, call calculate_margin_requirement for the final security, side, quantity, and reference price.",
            "preferred_order": "Prefer place_protected_intraday_super_order for new intraday trades.",
            "fallback_order": "Use place_intraday_equity_order only as a new-entry fallback. Never use it to exit or manage a live position.",
            "super_order_validation": "For BUY require stop_loss_price below entry_price and target_price above entry_price. For SELL require target_price below entry_price and stop_loss_price above entry_price.",
            "exchange_segment": "Use BSE_EQ unless supplied context explicitly says otherwise.",
            "hard_scope": "Act only on selected_stock.security_id. Other account orders and positions are read-only context.",
            "forbidden_actions": "Do not exit, cancel, modify, convert, hedge, or close any order or position. Do not manage trades after entry.",
            "terminal_behavior": "After placing one protected order, optionally verify once, then output the result and stop.",
        }
        return (
            "Make the final entry-only intraday execution decision for the supplied stock.\n"
            "You receive up to 8 chart images: Current Day (1m, 5m, 15m, 30m, 1h) then Previous Day (5m, 15m, 1h).\n"
            "Use previous-day levels for S/R context and current-day charts for live setup quality.\n"
            "The execution layer may avoid trading, plan a trade, or place one new entry trade using the available Dhan tools.\n"
            "Do not monitor, modify, cancel, exit, or repair trades after entry. Do not touch orders or positions for other securities.\n"
            "Use the stock analyzer report for setup quality and the account context for feasibility.\n"
            "No regime or broad market context is provided here.\n"
            "Output only the final execution outcome. Do not produce JSON.\n"
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
