from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from agno.agent import Agent
from agno.media import Image
from agno.models.groq import Groq
from agno.models.openrouter import OpenRouter
from agno.models.google import Gemini


class RiskAnalyzeAgent:
    def __init__(self) -> None:
        self.agent_name = os.getenv("RISK_ANALYZER_AGENT_NAME", "RISK_ANALYZER")
        self.use_agno = os.getenv("RISK_ANALYZER_USE_AGNO", "1").strip().lower() not in {"0", "false"}

    def is_enabled(self) -> bool:
        return self.use_agno

    def analyze(self, risk_packet: Dict[str, Any], chart_paths: List[str]) -> str:
        if not self.is_enabled():
            raise RuntimeError("risk_analyzer_disabled")

        agent = Agent(
            name=self.agent_name,
            model=Gemini(id="gemini-2.5-flash"),
            description=(
                "Compare three intraday stock analysis reports against market and account-risk context, then choose the single best tradable candidate."
            ),
            instructions=[
                "You are the risk monitoring layer in an intraday trading pipeline.",
                "You receive three stock analysis reports, six chart images, market context, and the user's account state.",
                "Your primary job is not to find the most exciting trade, but the safest high-quality trade among the supplied choices.",
                "Respect available funds, position overlap, and concentration.",
                "Treat the market context as background information only; make your own independent risk decision from the supplied evidence.",
                "If the account context or chart evidence make all trades unattractive, recommend avoid.",
                "Use only the supplied facts and images.",
                "Start the report with these exact header lines so the runtime can read your decision:",
                "Decision: <TRADE or AVOID>",
                "Selected Symbol: <symbol or NONE>",
                "Selected Display Name: <display name or NONE>",
                "Selected Security ID: <security id or 0>",
                "Trade Side: <LONG, SHORT, or AVOID>",
                "Conviction: <0.00 to 1.00>",
                "After those lines, write the report using these sections:",
                "1. Why This Choice",
                "2. Ranking Across The Three Stocks",
                "3. Account And Risk Constraints",
                "4. Execution Notes",
                "If available funds are effectively zero or trading should not happen, make that explicit.",
                "NOTE :- currently im testing this system and i have connected my dhan account which has 0 balance but because we are in testing mode you have to provide one stock and ignore funds and other things for now so provide proper response with one stock",
            ],
            markdown=False,
            add_datetime_to_context=True,
            debug_mode=True,
        )

        images = [Image(filepath=path) for path in chart_paths]
        response = agent.run(self._build_prompt(risk_packet), images=images)
        response_text = self._extract_text(response).strip()
        if not response_text:
            raise RuntimeError("risk_analyzer_empty_response")
        return response_text

    def _build_prompt(self, risk_packet: Dict[str, Any]) -> str:
        compact_packet = {
            "market_date": risk_packet.get("market_date"),
            "summary": risk_packet.get("summary"),
            "account_context": risk_packet.get("account_context"),
            "stock_reports": risk_packet.get("stock_reports"),
        }
        market_context = risk_packet.get("market_context") or risk_packet.get("regime") or {}
        return (
            "Compare the three supplied intraday stock candidates and select the single best one for the execution layer.\n"
            "Interpret the six chart images as two charts per stock in report order: 5-minute then 15-minute.\n"
            "Evaluate position concentration and available funds independently.\n"
            "If current open positions, holdings overlap, or risk concentration make the setup unsuitable, say so clearly.\n"
            "<context>\n"
            f"{json.dumps({'market_context': market_context}, ensure_ascii=True)}\n"
            "</context>\n"
            "Risk packet JSON:\n"
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
