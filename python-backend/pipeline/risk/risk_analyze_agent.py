from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from agno.agent import Agent
from agno.media import Image

from pipeline.llm import create_multimodal_trading_model


class RiskAnalyzeAgent:
    def __init__(self) -> None:
        self.agent_name = os.getenv("RISK_ANALYZER_AGENT_NAME", "RISK_ANALYZER")
        self.use_agno = os.getenv("RISK_ANALYZER_USE_AGNO", "1").strip().lower() not in {"0", "false"}

    def is_enabled(self) -> bool:
        return self.use_agno

    def analyze(self, risk_packet: Dict[str, Any], chart_paths: List[str], capital_instruction: str = None) -> str:
        if not self.is_enabled():
            raise RuntimeError("risk_analyzer_disabled")

        if capital_instruction:
            capital_line = capital_instruction
        else:
            capital_line = "Use a starting capital of Rs 100 to Rs 500 for trading calculations."

        agent = Agent(
            name=self.agent_name,
            model=create_multimodal_trading_model(),
            description=(
                "Compare three intraday stock analysis reports against market and account-risk context, "
                "then choose the single best tradable candidate."
            ),
            instructions=[
                "You are the risk monitoring layer in an intraday trading pipeline.",
                "You receive three stock analysis reports, chart images, an optional consolidated regime report, and the user's account state.",
                "Act as a purely logical risk monitoring system free from human emotions, greed, or behavioral biases. Perform objective mathematical and logical analysis to identify the safest, highest-quality trade with the best risk-to-reward ratio among the supplied choices.",
                "Analyze the risk-to-reward ratio for each potential trade, seeking optimal setups (e.g., 1:2, 1:3, or better) based on the entry, invalidation, and profit objective levels.",
                "Respect available funds, position overlap, and concentration.",
                "If a consolidated regime report is supplied, treat it as background information only; it is not trade permission, a trade veto, or a position-size instruction.",
                "Choose from the pre-shortlisted candidates using stock evidence, chart quality, account feasibility, and concentration risk.",
                "Use only the supplied facts and images.",
                "",
                "CHART IMAGE INTERPRETATION:",
                "You receive 3 charts per stock (9 total for 3 stocks), in stock-report order:",
                "  For each stock: Previous Day 15m, then Current Day 5m, then Current Day 15m.",
                "All charts have the full trading session x-axis (09:15-15:30) and are labeled 'CURRENT DAY' or 'PREVIOUS DAY' with their date.",
                "Use previous-day charts to identify key S/R levels and overnight context.",
                "Use current-day charts to assess live setup quality and momentum.",
                "",
                capital_line,
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
            add_datetime_to_context=False,
            debug_mode=True,
        )

        images = [Image(filepath=path) for path in chart_paths]
        response = agent.run(self._build_prompt(risk_packet), images=images)
        response_text = self._extract_text(response).strip()
        if not response_text:
            raise RuntimeError("risk_analyzer_empty_response")
        return response_text

    def _build_prompt(self, risk_packet: Dict[str, Any]) -> str:
        summary = risk_packet.get("summary") or {}
        regime_report = str(risk_packet.get("regime_report") or "").strip()
        account_context = risk_packet.get("account_context") or {}
        stock_reports = risk_packet.get("stock_reports") or []

        lines = [
            "Compare the three supplied intraday stock candidates and select the single best one for the execution layer.",
            "You receive 3 charts per stock (9 total), in stock-report order. For each stock: Previous Day 15m, Current Day 5m, Current Day 15m.",
            "Each chart spans the full trading session (09:15-15:30) on the x-axis and is labeled with day type and date.",
            "Evaluate position concentration and available funds independently.",
            "If current open positions, holdings overlap, or risk concentration make the setup unsuitable, say so clearly.",
            "If a regime report is supplied, use it only to describe backdrop; do not treat it as standalone permission or prohibition.",
            "Output ONLY a valid JSON object matching the requested schema. Do not include markdown code block formatting (like ```json) or explanation outside the JSON.",
            "",
            "## Session",
            f"Market date: {risk_packet.get('market_date')}",
            f"Stock report count: {summary.get('stock_report_count')}",
            f"Chart count supplied separately: {summary.get('chart_count')}",
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
                "## Account Context",
                json.dumps(account_context, ensure_ascii=True),
                "",
                "## Stock Reports",
                json.dumps(stock_reports, ensure_ascii=True),
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
