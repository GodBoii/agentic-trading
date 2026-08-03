from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from agno.agent import Agent
from agno.media import Image

from pipeline.llm import create_multimodal_trading_model
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
            model=create_multimodal_trading_model(),
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
                "You receive 3 price-only chart images for the selected stock:",
                "  Current Day: 1m EXECUTION, 5m SETUP, 15m STRUCTURE",
                "Use embedded prior-day levels and technical metadata for context; do not expect historical order-flow panels.",
                "You also receive timing_context and fresh_market_snapshot. Always compare stock_analyzer_generated_at_utc with executioner_started_at_utc before deciding.",
                "For trading interpretation, use Indian market time fields ending in _ist and the configured market_timezone. UTC fields are for audit only.",
                "Chart images may be older than the fresh text snapshot. If current price/quote/OHLC contradicts the chart-based setup, trust the fresh text snapshot and treat the chart setup as potentially deteriorated.",
                "If fresh_market_snapshot is missing, failed, or stale, explicitly account for that data-quality risk in the final decision.",
                "If a consolidated regime report is supplied, treat it as non-binding background context only. Validate this stock's current setup and execution feasibility from the stock evidence first.",
                "Hard scope: only act on the selected_stock.security_id from the execution packet. Treat every other account order, holding, or position as read-only context.",
                "If the account already contains orders or positions for any other security, do not cancel, modify, exit, hedge, convert, or otherwise touch them.",
                "If there is an existing order or open position for the selected stock, do not manage or exit it. Report that the selected stock already has exposure/order overlap and stop.",
                "Never call destructive or management tools: exit_position, exit_all_intraday_positions, cancel_order, modify_order, cancel_super_order, modify_super_order, convert_position, cancel_forever_order, modify_forever_order, delete_conditional_trigger, cancel_conditional_trigger, or modify_conditional_trigger.",
                "Never place an exit-only order. Never place a SELL to close an existing long or a BUY to close an existing short. This agent only creates a new entry when there is no selected-stock overlap.",
                "After a live order is placed, do not monitor the trade, chase fills, modify prices, cancel orders, or issue exits. Verify the placed order once if needed, then output the result and stop.",
                "Order placement retry limit: make at most one place_protected_intraday_super_order attempt. If it fails with a broker/API input error, stop immediately. Only use one place_intraday_equity_order fallback if the protected order is unavailable for a non-input-error reason.",
                "If any Dhan placement tool returns DH-905, Input_Exception, invalid parameters, missing fields, or bad values, do not retry with alternate order types. Report execution_status failed and stop.",
                "Use only Dhan-documented order_type values: LIMIT, MARKET, STOP_LOSS, STOP_LOSS_MARKET. Do not use SL, SL-L, SL-M, or other aliases in tool calls.",
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
                "Use the exact Dhan exchange_segment supplied by the selected stock. Never infer or replace its venue.",
                "Validate Super Orders strictly: for BUY orders, stop_loss_price must be below entry_price and target_price above entry_price. For SELL orders, target_price must be below entry_price and stop_loss_price above entry_price.",
                "After acting or deciding not to act, output only a concise execution outcome in normal markdown/text.",
                "Include these headers when possible: Decision, Execution Status, Selected Security ID, Selected Display Name, Trade Side, Order Type, Quantity, Reference Price, Correlation ID, Order ID.",
                "Include actual order id, correlation id, side, quantity, and reference price only when they are known from tools or supplied context.",
                trade_range_instruction,
                capital_instruction,
            ],
            markdown=True,
            add_datetime_to_context=False,
            debug_mode=True,
        )

        images = [Image(filepath=path) for path in chart_paths]
        response = agent.run(self._build_prompt(execution_packet), images=images)
        response_text = self._extract_text(response).strip()
        if not response_text:
            raise RuntimeError("executioner_empty_response")
        return response_text

    def _build_prompt(self, execution_packet: Dict[str, Any]) -> str:
        timing_context = execution_packet.get("timing_context") or {}
        selected_stock = execution_packet.get("selected_stock") or {}
        stock_analysis = execution_packet.get("stock_analysis") or {}
        fresh_market_snapshot = execution_packet.get("fresh_market_snapshot") or {}
        account_context = execution_packet.get("account_context") or {}
        trade_config = execution_packet.get("trade_config") or {}
        regime_report = str(execution_packet.get("regime_report") or "").strip()
        tool_instructions = {
            "sizing": "For new intraday trades, first call calculate_intraday_equity_order_quantity with security_id, side, reference_price, margin_budget, and stop_loss_price.",
            "margin": "Before any live order, call calculate_margin_requirement for the final security, side, quantity, and reference price.",
            "preferred_order": "Prefer place_protected_intraday_super_order for new intraday trades.",
            "fallback_order": "Use place_intraday_equity_order only as a new-entry fallback. Never use it to exit or manage a live position.",
            "super_order_validation": "For BUY require stop_loss_price below entry_price and target_price above entry_price. For SELL require target_price below entry_price and stop_loss_price above entry_price.",
            "exchange_segment": "Copy the selected stock's exchange_segment exactly.",
            "hard_scope": "Act only on selected_stock.security_id. Other account orders and positions are read-only context.",
            "forbidden_actions": "Do not exit, cancel, modify, convert, hedge, or close any order or position. Do not manage trades after entry.",
            "terminal_behavior": "After placing one protected order, optionally verify once, then output the result and stop.",
            "retry_limit": "One protected entry attempt only. Stop on DH-905/Input_Exception. At most one normal entry fallback for non-input-error protected-order unavailability.",
            "order_type_enums": "Use only LIMIT, MARKET, STOP_LOSS, STOP_LOSS_MARKET.",
        }
        lines = [
            "Make the final entry-only intraday execution decision for the supplied stock.",
            "You receive 3 price-only chart images: Current Day 1m EXECUTION, 5m SETUP, then 15m STRUCTURE.",
            "Use the overlaid previous-day levels and technical metadata for S/R context.",
            "Before deciding, inspect timing_context.analysis_age_seconds and fresh_market_snapshot. The stock analyzer report and chart images can be older than the current quote/OHLC snapshot.",
            "Use the *_ist timing fields for market-session reasoning because this system trades Indian equities.",
            "If fresh_market_snapshot shows setup deterioration, stale data, a bad spread, or contradiction against the stock analyzer report, avoid the trade or require stricter confirmation.",
            "The execution layer may avoid trading, plan a trade, or place one new entry trade using the available Dhan tools.",
            "Do not monitor, modify, cancel, exit, or repair trades after entry. Do not touch orders or positions for other securities.",
            "Use the stock analyzer report for setup quality and the account context for feasibility.",
            "Output only the final execution outcome. Do not produce JSON.",
            "",
            "## Tool Rules",
            json.dumps(tool_instructions, ensure_ascii=True),
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
                    "monitor": selected_stock.get("monitor"),
                },
                ensure_ascii=True,
            ),
        ]

        if regime_report:
            lines.extend(
                [
                    "",
                    "## Regime Context",
                    "Use this report only as non-binding background context:",
                    regime_report,
                ]
            )

        lines.extend(
            [
                "",
                "## Stock Analyzer Report",
                json.dumps(stock_analysis, ensure_ascii=True),
                "",
                "## Fresh Market Snapshot",
                json.dumps(fresh_market_snapshot, ensure_ascii=True),
                "",
                "## Account Context",
                json.dumps(account_context, ensure_ascii=True),
                "",
                "## Trade Config",
                json.dumps(trade_config, ensure_ascii=True),
            ]
        )
        return "\n".join(lines)

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
