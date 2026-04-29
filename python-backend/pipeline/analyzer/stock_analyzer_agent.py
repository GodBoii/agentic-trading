from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

try:
    from agno.agent import Agent
    from agno.media import Image
    AGNO_CORE_AVAILABLE = True
except Exception:  # pragma: no cover - optional runtime dependency
    AGNO_CORE_AVAILABLE = False
    Agent = None  # type: ignore
    Image = None  # type: ignore

try:
    from agno.models.groq import Groq
except Exception:  # pragma: no cover - optional runtime dependency
    Groq = None  # type: ignore

try:
    from agno.models.openrouter import OpenRouter
except Exception:  # pragma: no cover - optional runtime dependency
    OpenRouter = None  # type: ignore



class StockAnalyzerLevels(BaseModel):
    preferred_entry_zone: str = Field(..., description="Compact intraday entry zone or trigger description.")
    invalidation_zone: str = Field(..., description="Zone where the setup is considered invalid.")
    profit_objective_zone: str = Field(..., description="Primary intraday target area.")


class StockAnalyzerOutput(BaseModel):
    symbol: str
    display_name: str
    regime_alignment: str = Field(..., description="How well the stock aligns with the regime.")
    trade_bias: str = Field(..., description="long, short, or avoid")
    confidence: float = Field(..., ge=0.0, le=1.0)
    setup_quality: str = Field(..., description="A concise quality assessment.")
    setup_summary: str = Field(..., description="One tight paragraph on the intraday setup.")
    key_strengths: List[str] = Field(default_factory=list)
    key_risks: List[str] = Field(default_factory=list)
    chart_observations: List[str] = Field(default_factory=list)
    levels: StockAnalyzerLevels
    final_verdict: str = Field(..., description="A crisp actionable conclusion for the downstream risk agent.")


class StockAnalyzerAgent:
    def __init__(self) -> None:
        self.provider = os.getenv("STOCK_ANALYZER_PROVIDER", "groq").strip().lower()
        self.model_id = os.getenv("STOCK_ANALYZER_MODEL_ID", "meta-llama/llama-4-scout-17b-16e-instruct")
        self.agent_name = os.getenv("STOCK_ANALYZER_AGENT_NAME", "STOCK_ANALYZER")
        self.use_agno = os.getenv("STOCK_ANALYZER_USE_AGNO", "1").strip().lower() not in {"0", "false"}

    def is_enabled(self) -> bool:
        return self.use_agno

    def is_available(self) -> bool:
        if not AGNO_CORE_AVAILABLE or Agent is None or Image is None:
            return False
        if self.provider == "groq":
            return Groq is not None
        if self.provider == "openrouter":
            return OpenRouter is not None
        return False

    def _availability_error(self) -> str:
        if not AGNO_CORE_AVAILABLE or Agent is None or Image is None:
            return "stock_analyzer_dependencies_unavailable::agno_core"
        if self.provider == "groq" and Groq is None:
            return "stock_analyzer_dependencies_unavailable::groq"
        if self.provider == "openrouter" and OpenRouter is None:
            return "stock_analyzer_dependencies_unavailable::openrouter"
        if self.provider not in {"groq", "openrouter"}:
            return f"stock_analyzer_dependencies_unavailable::unsupported_provider::{self.provider}"
        return "stock_analyzer_dependencies_unavailable"

    def _build_model(self) -> Any:
        if self.provider == "groq":
            if Groq is None:
                raise RuntimeError("stock_analyzer_provider_unavailable::groq")
            return Groq(id=self.model_id)
        if self.provider == "openrouter":
            if OpenRouter is None:
                raise RuntimeError("stock_analyzer_provider_unavailable::openrouter")
            return OpenRouter(id=self.model_id)
        raise RuntimeError(f"stock_analyzer_provider_unsupported::{self.provider}")

    def analyze(
        self,
        candidate_packet: Dict[str, Any],
        chart_paths: List[str],
    ) -> Dict[str, Any]:
        if not self.is_enabled():
            raise RuntimeError("stock_analyzer_disabled")
        if not self.is_available():
            raise RuntimeError(self._availability_error())

        agent = Agent(
            name=self.agent_name,
            model=self._build_model(),
            description=(
                "Analyze one shortlisted intraday stock using structured market context and supplied candlestick charts."
            ),
            instructions=[
                "You are the first stock analyzer in an intraday trading pipeline.",
                "Use only the provided stock facts, regime context, and chart images.",
                "Focus on intraday trading quality, not swing trading.",
                "Treat chart images as evidence to validate price structure, candle behavior, and momentum continuation quality.",
                "Do not invent indicators that were not provided.",
                "If evidence is mixed, prefer 'avoid' over forcing a directional trade bias.",
                "Keep strengths and risks concrete and specific to this stock.",
                "Return only structured output following the schema.",
            ],
            output_schema=StockAnalyzerOutput,
            use_json_mode=True,
            parse_response=True,
            markdown=False,
            add_datetime_to_context=True,
            debug_mode=True,
        )

        images = [Image(filepath=path) for path in chart_paths]
        response = agent.run(self._build_prompt(candidate_packet), images=images)
        response_status = str(getattr(response, "status", "") or "").lower()
        if "error" in response_status:
            raise RuntimeError(f"stock_analyzer_run_error::{self._extract_text(response)}")
        parsed = self._extract_parsed_response(response)
        parsed.setdefault("symbol", candidate_packet.get("symbol"))
        parsed.setdefault("display_name", candidate_packet.get("display_name"))
        return parsed

    def _build_prompt(self, candidate_packet: Dict[str, Any]) -> str:
        compact_packet = {
            "candidate_source": candidate_packet.get("candidate_source"),
            "market_date": candidate_packet.get("market_date"),
            "stock": candidate_packet.get("stock"),
            "stage2": candidate_packet.get("stage2"),
            "monitor": candidate_packet.get("monitor"),
            "regime": candidate_packet.get("regime"),
            "chart_artifacts": candidate_packet.get("chart_artifacts"),
        }
        return (
            "Analyze the supplied intraday stock candidate.\n"
            "Your downstream reader is a risk agent, so be precise and structured.\n"
            "Give a directional bias only if the chart structure and regime context support it.\n"
            "Interpret the two chart images as 5-minute and 15-minute candlestick charts.\n"
            "The monitor stage already screened for live tradability; still mention any warning signs you infer from the charts.\n"
            "Candidate packet JSON:\n"
            f"{json.dumps(compact_packet, ensure_ascii=True)}"
        )

    def _extract_parsed_response(self, response: Any) -> Dict[str, Any]:
        content = getattr(response, "content", None)
        if isinstance(content, StockAnalyzerOutput):
            return content.model_dump()
        if isinstance(content, dict):
            return content
        if hasattr(content, "model_dump"):
            return content.model_dump()  # type: ignore[no-any-return]

        parsed = getattr(response, "parsed", None)
        if isinstance(parsed, StockAnalyzerOutput):
            return parsed.model_dump()
        if isinstance(parsed, dict):
            return parsed
        if hasattr(parsed, "model_dump"):
            return parsed.model_dump()  # type: ignore[no-any-return]

        raise RuntimeError(f"stock_analyzer_unparsed_response::{type(content).__name__}")

    def _extract_text(self, response: Any) -> str:
        if response is None:
            return ""
        if isinstance(response, str):
            return response
        content = getattr(response, "content", None)
        if isinstance(content, str):
            return content
        messages = getattr(response, "messages", None)
        if isinstance(messages, list) and messages:
            maybe = getattr(messages[-1], "content", None)
            if isinstance(maybe, str):
                return maybe
        return str(response)
