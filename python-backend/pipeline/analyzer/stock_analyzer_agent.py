from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from agno.agent import Agent
from agno.media import Image
from agno.models.groq import Groq
from agno.models.openrouter import OpenRouter


class StockAnalyzerAgent:
    def __init__(self) -> None:
        self.agent_name = os.getenv("STOCK_ANALYZER_AGENT_NAME", "STOCK_ANALYZER")
        self.use_agno = os.getenv("STOCK_ANALYZER_USE_AGNO", "1").strip().lower() not in {"0", "false"}

    def is_enabled(self) -> bool:
        return self.use_agno

    def analyze(
        self,
        candidate_packet: Dict[str, Any],
        chart_paths: List[str],
    ) -> str:
        if not self.is_enabled():
            raise RuntimeError("stock_analyzer_disabled")

        agent = Agent(
            name=self.agent_name,
            model=Groq(id="meta-llama/llama-4-scout-17b-16e-instruct"),
            description=(
                "Analyze one shortlisted intraday stock using structured market context and supplied candlestick charts."
            ),
            instructions=[
                "You are the first stock analyzer in an intraday trading pipeline.",
                "Use only the provided stock facts, market context, and chart images.",
                "Focus on intraday trading quality, not swing trading.",
                "Treat chart images as evidence to validate price structure, candle behavior, momentum continuation quality, and risk warnings.",
                "Do not invent indicators or data that were not provided.",
                "If evidence is mixed, clearly say so instead of forcing a trade.",
                "Treat the market context as background information only; make your own independent stock assessment from the supplied evidence.",
                "Write a compact but detailed analyst report in normal text.",
                "Use this exact section structure:",
                "1. Verdict",
                "2. Market Context",
                "3. Chart Read",
                "4. Strengths",
                "5. Risks",
                "6. Trade Plan",
                "Inside Trade Plan, explicitly include Bias, Entry Zone, Invalidation, and Profit Objective.",
            ],
            markdown=False,
            add_datetime_to_context=True,
            debug_mode=True,
        )

        images = [Image(filepath=path) for path in chart_paths]
        response = agent.run(self._build_prompt(candidate_packet), images=images)
        response_text = self._extract_text(response).strip()
        if not response_text:
            raise RuntimeError("stock_analyzer_empty_response")
        return response_text

    def _build_prompt(self, candidate_packet: Dict[str, Any]) -> str:
        compact_packet = {
            "candidate_source": candidate_packet.get("candidate_source"),
            "market_date": candidate_packet.get("market_date"),
            "symbol": candidate_packet.get("symbol"),
            "display_name": candidate_packet.get("display_name"),
            "stock": candidate_packet.get("stock"),
            "stage2": candidate_packet.get("stage2"),
            "monitor": candidate_packet.get("monitor"),
            "chart_artifacts": candidate_packet.get("chart_artifacts"),
        }
        market_context = candidate_packet.get("market_context") or candidate_packet.get("regime") or {}
        return (
            "Analyze the supplied intraday stock candidate.\n"
            "Your downstream reader is a risk agent, so be precise, concrete, and usable.\n"
            "Interpret the two chart images as 5-minute and 15-minute candlestick charts.\n"
            "The monitor stage already screened for live tradability; still mention any warning signs you infer from the charts.\n"
            "<context>\n"
            f"{json.dumps({'market_context': market_context}, ensure_ascii=True)}\n"
            "</context>\n"
            "Candidate packet JSON:\n"
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
