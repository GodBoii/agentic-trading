from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from agno.agent import Agent
from agno.media import Image

from pipeline.llm import create_mimo_model


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
            model=create_mimo_model(),
            description=(
                "Analyze one shortlisted intraday stock using structured market context and supplied candlestick charts."
            ),
            instructions=[
                "You are the first stock analyzer in an intraday trading pipeline.",
                "Use only the provided stock facts, market context, chart images, and technical_metadata.",
                "Focus on intraday trading quality, not swing trading.",
                "Treat chart images as primary evidence. Use technical_metadata numbers to confirm what you see.",
                "Treat the market context as background only; it is not trade permission or a veto.",
                "The monitor/stage-2 pipeline already shortlisted this stock; judge the setup from its own evidence.",
                "Do not say 'do not trade' only because of market regime/news; only flag concrete stock-level problems.",
                "",
                "═══ CHART VISUAL LEGEND (what each element means) ═══",
                "",
                "PANEL 1 — PRICE (top, largest panel):",
                "• Candlesticks: Green (#00dc82) = bullish (close>open), Red (#ff4757) = bearish (close<open)",
                "• Wicks = high/low extremes of that candle period",
                "• VWAP (orange #ff9f1a, thick line) = Volume Weighted Average Price. Price above = bullish intraday bias, below = bearish",
                "• EMA9 (cyan #00bfff, thin line) = 9-period Exponential Moving Average — fast trend",
                "• EMA21 (magenta #e040fb, thin line) = 21-period EMA — intermediate trend. EMA9 crossing above EMA21 = bullish signal",
                "• Bollinger Bands (light blue shaded area) = 20-period ±2 std dev. Price at upper band = extended, at lower band = oversold. Squeeze (narrow bands) = breakout imminent",
                "• Horizontal dashed green lines = SUPPORT levels (price bounced here before)",
                "• Horizontal dashed red lines = RESISTANCE levels (price rejected here before)",
                "• Dotted yellow line labeled 'PDH' = Previous Day High",
                "• Dotted purple line labeled 'PDL' = Previous Day Low",
                "• Dotted gray line labeled 'PDC' = Previous Day Close",
                "• Green shaded horizontal bands = DEMAND ZONES (institutional buy orders likely parked here — price may bounce)",
                "• Red shaded horizontal bands = SUPPLY ZONES (institutional sell orders — price may reverse down)",
                "• Triangle markers with labels = Candlestick patterns detected (▲=bullish, ▼=bearish): Hammer, Doji, Bull Engulf, Bear Engulf, Shooting Star",
                "",
                "PANEL 2 — VOLUME:",
                "• Bar height = shares traded per candle. Color matches candle direction.",
                "• High volume on a move = conviction/confirmation. Low volume = weak/suspect move.",
                "",
                "PANEL 3 — RSI (14):",
                "• Yellow line oscillating 0-100. Above 70 (red dashed) = overbought, below 30 (green dashed) = oversold.",
                "• RSI divergence from price = early reversal signal. RSI 40-60 = neutral/trending without extreme.",
                "",
                "PANEL 4 — CVD (Cumulative Volume Delta):",
                "• Blue line = running total of buy_volume minus sell_volume.",
                "• Rising CVD = buyers dominating. Falling CVD = sellers dominating.",
                "• CVD divergence from price (price up but CVD falling) = hidden selling, unreliable rally.",
                "",
                "═══ HOW TO READ SUPPLY/DEMAND ZONES ═══",
                "• Demand Zone: area where a strong bullish impulse originated. Unfilled buy orders remain. Price returning here = likely bounce.",
                "• Supply Zone: area where a strong bearish impulse originated. Unfilled sell orders. Price returning = likely rejection.",
                "• 'Strong' zones had impulse candles > 2.5x ATR. 'Moderate' = 1.8-2.5x ATR.",
                "• Fresh (untested) zones are strongest. Zones already tested once are weaker.",
                "",
                "═══ CHART IMAGE ORDER ═══",
                "Current day: 1m, 5m, 15m, 30m, 1h (x-axis: full session 09:15–15:30, candles ending before 15:30 = market still open)",
                "Previous day: 5m, 15m, 1h (prior session, weekends skipped)",
                "Compare current-day structure against prior-day levels for gap analysis and continuation/reversal signals.",
                "",
                "═══ OUTPUT FORMAT ═══",
                "Write a compact analyst report in markdown with these sections:",
                "1. Verdict (one line: strong buy / buy / neutral / sell / strong sell + confidence %)",
                "2. Context Fit (how market regime aligns with this setup)",
                "3. Chart Read (reference specific timeframes, indicators, zones, and patterns by name)",
                "4. Strengths",
                "5. Risks",
                "6. Trade Plan (Bias, Entry Zone, Invalidation, Profit Objective)",
            ],
            markdown=True,
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
            "chart_artifacts": {
                k: v for k, v in (candidate_packet.get("chart_artifacts") or {}).items()
                if k != "chart_paths_ordered"
            },
        }
        market_context = candidate_packet.get("market_context") or candidate_packet.get("regime") or {}
        technical_metadata = (candidate_packet.get("chart_artifacts") or {}).get("technical_metadata") or {}

        # Build concise technical summary text
        tech_text = ""
        if technical_metadata:
            tech_text = (
                "\n<technical_metadata>\n"
                f"{json.dumps(technical_metadata, ensure_ascii=False)}\n"
                "</technical_metadata>\n"
            )

        return (
            "Analyze the supplied intraday stock candidate.\n"
            "Your downstream reader is a risk agent, so be precise, concrete, and usable.\n"
            "Chart images are provided in order: Current day (1m→5m→15m→30m→1h), then Previous day (5m→15m→1h).\n"
            "Each chart has 4 panels: Price (with overlays), Volume, RSI, CVD.\n"
            "Use the chart visual legend in your instructions to identify each indicator by color.\n"
            "Cross-reference the technical_metadata numbers with what you see on charts.\n"
            f"{tech_text}"
            "<context>\n"
            f"{json.dumps({'market_context': market_context}, ensure_ascii=True)}\n"
            "</context>\n"
            "Candidate packet:\n"
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
