from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from agno.agent import Agent
from agno.media import Image

from pipeline.llm import create_mimo_model


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
            model=create_mimo_model(),
            description=(
                "Compare three intraday stock analysis reports against market and account-risk context, then choose the single best tradable candidate."
            ),
            instructions=[
                "You are the risk monitoring layer in an intraday trading pipeline.",
                "You receive three stock analysis reports, six chart images, market context, and the user's account state.",
                "Act as a purely logical risk monitoring system free from human emotions, greed, or behavioral biases. Perform objective mathematical and logical analysis to identify the safest, highest-quality trade with the best risk-to-reward ratio among the supplied choices.",
                "Analyze the risk-to-reward ratio for each potential trade, seeking optimal setups (e.g., 1:2, 1:3, or better) based on the entry, invalidation, and profit objective levels.",
                "Respect available funds, position overlap, and concentration.",
                "Treat the market context as background information only; it is not trade permission, a trade veto, or position-size instruction.",
                "Choose from the pre-shortlisted candidates using stock evidence, chart quality, account feasibility, and concentration risk.",
                "Use only the supplied facts and images.",
                "Use a starting capital of ₹300 for trading calculations.",
                "Output ONLY a valid JSON object matching the requested schema. Do not include markdown code block formatting (like ```json) or explanation outside the JSON.",
            ],
            expected_output=(
                "A valid JSON object matching this schema:\n"
                "{\n"
                '  "selected_symbol": "symbol or NONE",\n'
                '  "selected_display_name": "display name or NONE",\n'
                '  "selected_security_id": security_id_or_0,\n'
                '  "conviction": conviction_score_between_0.0_and_1.0,\n'
                '  "why_this_choice": "detailed markdown text explaining why this stock was chosen (Section 1)",\n'
                '  "ranking_across_three_stocks": "detailed markdown text ranking the three stocks (Section 2)",\n'
                '  "account_and_risk_constraints": "detailed markdown text analyzing the account constraints and risk parameters (Section 3)",\n'
                '  "execution_notes": "detailed markdown text outlining execution notes and trade setup details (Section 4)",\n'
                '  "deep_analysis_report": "detailed mathematical and logical deep analysis of the stock setups, risk/reward, and charts (Section 5)"\n'
                "}"
            ),
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
            "Use market context only to describe backdrop; do not treat regime labels or news tone as standalone permission or prohibition.\n"
            "Output ONLY a valid JSON object matching the requested schema. Do not include markdown code block formatting (like ```json) or explanation outside the JSON.\n"
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
