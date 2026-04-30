from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from agno.agent import Agent
from agno.media import Image
from agno.models.groq import Groq

from pipeline.services.dhan_execution_toolkit import DhanExecutionToolkit


class ExecutionerAgent:
    def __init__(self, toolkit: DhanExecutionToolkit) -> None:
        self.agent_name = os.getenv("EXECUTIONER_AGENT_NAME", "EXECUTIONER")
        self.use_agno = os.getenv("EXECUTIONER_USE_AGNO", "1").strip().lower() not in {"0", "false"}
        self.toolkit = toolkit

    def is_enabled(self) -> bool:
        return self.use_agno

    def analyze(self, execution_packet: Dict[str, Any], chart_paths: List[str]) -> str:
        if not self.is_enabled():
            raise RuntimeError("executioner_disabled")

        agent = Agent(
            name=self.agent_name,
            model=Groq(id="meta-llama/llama-4-scout-17b-16e-instruct"),
            description=(
                "Make the final intraday execution decision for one shortlisted stock using charts, prior reports, risk context, and Dhan trading tools."
            ),
            tools=[self.toolkit],
            instructions=[
                "You are the final execution layer in an intraday trading pipeline.",
                "You receive one chosen stock, its analyzer report, the risk report, regime context, user Dhan account context, and two chart images.",
                "Reason carefully and step by step, but only provide the final actionable answer.",
                "Use the provided Dhan tools when you need fresher account, order, or trade information before making the decision.",
                "Only place an order if all of the following are true: regime allows trading, account has usable balance, there is no dangerous position overlap, the stock setup is still attractive from the images, and quantity is positive.",
                "If any of those checks fail, do not place an order.",
                "If live order placement is disabled by the tool response, treat that as an execution block and do not pretend an order was sent.",
                "Do not invent order ids, correlation ids, funds, or quantities.",
                "Start your response with these exact header lines:",
                "Decision: <TRADE or AVOID>",
                "Execution Status: <PLANNED or PLACED or SKIPPED or BLOCKED or FAILED>",
                "Selected Security ID: <security id or 0>",
                "Selected Display Name: <display name or NONE>",
                "Trade Side: <BUY, SELL, or AVOID>",
                "Order Type: <MARKET, LIMIT, STOP_LOSS, STOP_LOSS_MARKET, or NONE>",
                "Quantity: <integer>",
                "Reference Price: <number>",
                "Correlation ID: <value or NONE>",
                "Order ID: <value or NONE>",
                "After the headers, use these sections:",
                "1. Final Assessment",
                "2. Execution Checks",
                "3. Order Plan",
                "4. Risks And Fallbacks",
                "Inside Order Plan, explicitly include entry logic, stop logic, target logic, and whether the trade was actually sent or only planned.",
            ],
            markdown=False,
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
            "regime": execution_packet.get("regime"),
            "account_context": execution_packet.get("account_context"),
            "user_profile": execution_packet.get("user_profile"),
        }
        return (
            "Make the final intraday execution decision for the supplied stock.\n"
            "Interpret the two chart images as the 5-minute and 15-minute candlestick charts for the same stock.\n"
            "The execution layer may avoid trading, plan a trade, or place a trade using the available Dhan tools.\n"
            "Use the stock analyzer report for setup quality, the risk report for cross-stock selection context, and the account context for feasibility.\n"
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
