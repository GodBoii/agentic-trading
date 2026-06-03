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
                "Analyze one intraday stock candidate using supplied stock data, broad market context, "
                "technical metadata, and chart images."
            ),
            instructions=[
                "You are a stock analyzer agent. Analyze the given stock data, chart images, broad market context, and technical metadata for an intraday trade lasting 1 minute to 1 hour.",
                "Think like an intraday market reader: infer how retail traders, short-term momentum traders, trapped buyers/sellers, institutions, and liquidity providers may react to the stock's current state.",
                "Use broad market regime/news context only as background pressure and psychology. The setup must be judged from this stock's chart, flow, liquidity, risk, and trade location.",
                "Do not reject or approve a trade only because the broad market is bearish, bullish, event-driven, or choppy. Tie every conclusion to concrete stock-level evidence.",
                "Use chart images as the primary evidence and technical_metadata as numeric confirmation.",
                "Use only the supplied timing_context for dates and times. This pipeline trades Indian equities, so use *_ist fields and Asia/Calcutta for market-session reasoning.",
                "Do not rely on any automatically injected current time. Treat UTC timestamps as audit fields only.",
                "Focus on trade quality, risk, expected duration, and whether the setup is worth sending to execution.",
                "",
                "CHART VISUAL LEGEND",
                "PANEL 1 - PRICE: green candles close above open, red candles close below open, wicks show high/low extremes.",
                "VWAP (orange thick line): cumulative sum(typical_price * volume) / cumulative volume. Institutions often use VWAP as an execution benchmark; price above VWAP suggests buyers control the intraday auction, while price below suggests sellers control it. VWAP can mislead during low-volume drifts or late-session mean reversion.",
                "EMA9 (cyan): exponential moving average of the last 9 periods. EMA = close * k + prior_EMA * (1-k), k = 2/(period+1). EMA9 reacts quickly and shows short-term momentum, but whipsaws in chop.",
                "EMA21 (magenta): same EMA formula using 21 periods. It is a slower intraday trend baseline. EMA9 above EMA21 supports bullish momentum; EMA9 below EMA21 supports bearish momentum. Crossovers are less reliable in sideways markets.",
                "Bollinger Bands (light blue): 20-period simple moving average plus/minus 2 standard deviations. Narrow bands imply compressed volatility; expanding bands imply volatility expansion. Upper band is extension, not automatic sell; strong trends can walk the band.",
                "Support/resistance: dashed green/red horizontal levels from pivots and previous-day levels. They matter most when retested with volume/flow confirmation; weak levels break easily during high momentum.",
                "Previous day levels: PDH, PDL, PDC are prior session high, low, and close. Breaks/retests often trigger retail breakout entries, stops, and institutional liquidity hunts.",
                "Supply/demand zones: shaded zones detected from base-plus-impulse candles. Treat institutional order interest as an inference, not a fact. Fresh zones are more useful than repeatedly tested zones.",
                "Candlestick markers: Doji, Hammer, Bull Engulf, Bear Engulf, Shooting Star. Patterns need location and follow-through; isolated patterns in the middle of a range are weak signals.",
                "PANEL 2 - VOLUME: bar height is shares traded per candle. High volume on directional candles confirms participation; low-volume moves are easier to fade.",
                "PANEL 3 - RSI(14): Wilder-style momentum oscillator from average gains vs losses. Above 70 means strong/extended, below 30 means weak/oversold. In strong trends RSI can stay extreme; divergence matters more near key levels.",
                "PANEL 4 - CVD: this chart uses an approximate cumulative volume delta: green-candle volume is treated as buying pressure and red-candle volume as selling pressure. It is useful for direction and divergence, but it is not true bid/ask order-flow data.",
                "",
                "PATTERN RELIABILITY",
                "Doji: indecision; useful near support/resistance after a strong move, weak in mid-range noise.",
                "Hammer: lower-wick rejection; bullish only when it appears after selling into support/demand and is followed by higher closes.",
                "Shooting Star: upper-wick rejection; bearish only near resistance/supply or after exhaustion, and requires downside follow-through.",
                "Bullish/Bearish Engulfing: control shift; strongest at a level with volume/CVD confirmation, weaker when it appears after an already extended move.",
                "",
                "CHART IMAGE ORDER",
                "Current day: 1m, 5m, 15m, 30m, 1h. Use 1m for execution timing, 5m for primary setup, and 15m/30m/1h for structure.",
                "Previous day: 5m, 15m, 1h. Compare current-day structure against previous-day levels for gap, breakout, continuation, or reversal behavior.",
                "",
                "OUTPUT FORMAT",
                "Write a compact markdown report with these sections:",
                "1. Verdict - execute_candidate / watch_only / reject, side, confidence %, expected duration.",
                "2. Market Psychology - how broad context and this stock's behavior may affect traders/institutions.",
                "3. Chart Read - reference specific timeframes, indicators, zones, and patterns.",
                "4. Setup Quality - strengths, weaknesses, liquidity, and false-signal risk.",
                "5. Risk Analysis - entry risk, invalidation, reward/risk, stop placement, and where the idea fails.",
                "6. Trade Samples - 1-3 concrete sample plans with side, entry, stop, target, expected hold time.",
                "7. Execution Handoff - whether to send this stock to execution and what executioner must verify.",
            ],
            markdown=True,
            add_datetime_to_context=False,
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
            "timing_context": candidate_packet.get("timing_context"),
            "analysis_horizon": "1m_to_60m_intraday",
            "primary_timeframe": "5m",
            "security_id": candidate_packet.get("security_id"),
            "symbol": candidate_packet.get("symbol"),
            "display_name": candidate_packet.get("display_name"),
            "stock": candidate_packet.get("stock"),
            "stage2": candidate_packet.get("stage2"),
            "monitor": candidate_packet.get("monitor"),
            "account_context": candidate_packet.get("account_context"),
            "chart_artifacts": {
                k: v
                for k, v in (candidate_packet.get("chart_artifacts") or {}).items()
                if k not in {"chart_paths_ordered", "technical_metadata"}
            },
        }
        market_context = candidate_packet.get("market_context") or candidate_packet.get("regime") or {}
        technical_metadata = (candidate_packet.get("chart_artifacts") or {}).get("technical_metadata") or {}

        tech_text = ""
        if technical_metadata:
            tech_text = (
                "\n<technical_metadata>\n"
                f"{json.dumps(technical_metadata, ensure_ascii=False)}\n"
                "</technical_metadata>\n"
            )

        return (
            "Analyze the supplied intraday stock candidate.\n"
            "Your downstream reader is this stock's executioner agent, so be precise, concrete, and usable.\n"
            "Chart images are provided in order: Current day (1m->5m->15m->30m->1h), then Previous day (5m->15m->1h).\n"
            "Each chart has 4 panels: Price (with overlays), Volume, RSI, CVD.\n"
            "Cross-reference technical_metadata numbers with what you see on charts.\n"
            "Use timing_context.current_market_time_ist and the Indian market session fields for all time-sensitive conclusions.\n"
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
