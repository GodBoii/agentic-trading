from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Tuple

try:
    from agno.agent import Agent
    from agno.models.openrouter import OpenRouter

    AGNO_AVAILABLE = True
except Exception:  # pragma: no cover - optional runtime dependency
    AGNO_AVAILABLE = False
    Agent = None  # type: ignore
    OpenRouter = None  # type: ignore


class RegimeNewsAnalyzerAgent:
    """
    Dedicated Agno agent wrapper for BSE news/disclosure interpretation.

    This module exists so the regime orchestrator can run the deterministic
    market-logic branch and the LLM news-analysis branch independently.
    """

    def __init__(self) -> None:
        self.use_agno = os.getenv("REGIME_NEWS_USE_AGNO", "1").strip() not in {"0", "false", "False"}
        self.openrouter_model_id = os.getenv("REGIME_NEWS_AGNO_MODEL_ID", "inclusionai/ling-2.6-1t:free")
        self.agent_name = os.getenv("REGIME_NEWS_AGNO_AGENT_NAME", "REGIME_NEWS_AGENT")

    def is_enabled(self) -> bool:
        return self.use_agno

    def is_available(self) -> bool:
        return AGNO_AVAILABLE and Agent is not None and OpenRouter is not None

    def analyze(self, rows: List[Dict[str, Any]]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        if not rows:
            return None, "no_headlines_to_analyze"
        if not self.is_enabled():
            return None, "agno_disabled"
        if not self.is_available():
            return None, "agno_dependency_not_available"

        try:
            agent = Agent(
                name=self.agent_name,
                description=(
                    "Analyze BSE-originated disclosures and determine whether they imply "
                    "isolated stock activity, sector-level pressure, or broad intraday regime risk."
                ),
                model=OpenRouter(id=self.openrouter_model_id),
                instructions=[
                    "Use only the supplied BSE-originated evidence.",
                    "Focus on intraday regime implications for Indian equities.",
                    "Separate isolated company filings from repeated or broad event clusters.",
                    "Reserve high severity for broad, repeated, or clearly destabilizing signals.",
                    "Do not give trading tips, targets, or narrative fluff.",
                    "Return only valid JSON matching the requested schema.",
                ],
                expected_output=(
                    "A valid JSON object with headline_summary, market_sentiment, confidence_score, "
                    "event_severity_score, affected_sectors, event_clusters, "
                    "risk_of_abnormal_volatility, trade_caution_level, llm_regime_overlay, "
                    "and structured_reasoning."
                ),
                add_datetime_to_context=True,
                markdown=False,
                debug_mode=True,
            )
            response = agent.run(self._build_prompt(rows))
            response_status = str(getattr(response, "status", "") or "").lower()
            if "error" in response_status:
                response_message = self._extract_text(response)
                return None, f"agno_run_error::{response_message or 'unknown_error'}"
            raw_text = self._extract_text(response)
            parsed = self._safe_parse_json(raw_text)
            if not isinstance(parsed, dict):
                return None, "agno_invalid_json"
            return self._normalize_analysis_dict(parsed, rows), None
        except Exception as exc:
            return None, f"agno_failure::{type(exc).__name__}::{exc}"

    def _build_prompt(self, rows: List[Dict[str, Any]]) -> str:
        preview = [
            {
                "source": row.get("source"),
                "section": row.get("section"),
                "title": row.get("title"),
                "published_at_utc": row.get("published_at_utc"),
                "event_date": row.get("event_date"),
                "company_name": row.get("company_name"),
                "security_code": row.get("security_code"),
                "detail_title": row.get("detail_title"),
                "detail_subtitle": row.get("detail_subtitle"),
                "detail_text": row.get("detail_text"),
                "attachment_url": row.get("attachment_url"),
            }
            for row in rows[:25]
        ]
        return (
            "You are the regime news analyst inside a stock-market execution stack.\n"
            "A separate deterministic regime analyzer is evaluating price, breadth, futures, and options.\n"
            "Your job is only to interpret the BSE-originated disclosure/news stream and return a structured overlay.\n"
            "Output ONLY valid JSON with this exact schema:\n"
            "{"
            '"headline_summary": "string", '
            '"market_sentiment": "bullish|bearish|mixed|neutral", '
            '"confidence_score": 0.0, '
            '"event_severity_score": 0.0, '
            '"affected_sectors": ["string"], '
            '"event_clusters": ["string"], '
            '"risk_of_abnormal_volatility": "low|medium|high", '
            '"trade_caution_level": "low|medium|high", '
            '"llm_regime_overlay": {"regime_bias":"event_driven|risk_on|risk_off|mixed|neutral","impact_horizon":"immediate_intraday|same_day|multi_day|unclear","breadth_signal":"broad|sectoral|isolated|mixed"}, '
            '"structured_reasoning": "string"'
            "}\n"
            "Calibration rules:\n"
            "- confidence_score and event_severity_score must be floats between 0 and 1.\n"
            "- Use only the provided BSE evidence; do not invent macro headlines.\n"
            "- Many corporate filings are routine. Do not overstate their regime importance.\n"
            "- High severity requires broad, repeated, or materially destabilizing signals.\n"
            "- Keep structured_reasoning concise and about regime relevance.\n"
            "- Do not include markdown fences or commentary outside JSON.\n\n"
            f"BSE items JSON:\n{json.dumps(preview, ensure_ascii=True)}"
        )

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

    def _safe_parse_json(self, text: str) -> Optional[Dict[str, Any]]:
        if not text:
            return None
        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            pass
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                parsed = json.loads(text[start : end + 1])
                return parsed if isinstance(parsed, dict) else None
            except Exception:
                return None
        return None

    def _normalize_analysis_dict(self, parsed: Dict[str, Any], rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        sentiment = self._normalize_choice(parsed.get("market_sentiment"), {"bullish", "bearish", "mixed", "neutral"}, "neutral")
        severity = self._float01(parsed.get("event_severity_score"), 0.0)
        confidence = self._float01(parsed.get("confidence_score"), 0.0)
        volatility_risk = self._normalize_choice(parsed.get("risk_of_abnormal_volatility"), {"low", "medium", "high"}, "medium")
        caution = self._normalize_choice(parsed.get("trade_caution_level"), {"low", "medium", "high"}, "medium")

        sectors = parsed.get("affected_sectors")
        if not isinstance(sectors, list):
            sectors = []
        sectors = [self._compact_text(str(item)) for item in sectors if self._compact_text(str(item))]

        clusters = parsed.get("event_clusters")
        if not isinstance(clusters, list):
            clusters = []
        clusters = [self._compact_text(str(item)) for item in clusters if self._compact_text(str(item))]

        raw_overlay = parsed.get("llm_regime_overlay")
        if not isinstance(raw_overlay, dict):
            raw_overlay = {}
        overlay = {
            "regime_bias": self._normalize_choice(
                raw_overlay.get("regime_bias"),
                {"event_driven", "risk_on", "risk_off", "mixed", "neutral"},
                "neutral",
            ),
            "impact_horizon": self._normalize_choice(
                raw_overlay.get("impact_horizon"),
                {"immediate_intraday", "same_day", "multi_day", "unclear"},
                "unclear",
            ),
            "breadth_signal": self._normalize_choice(
                raw_overlay.get("breadth_signal"),
                {"broad", "sectoral", "isolated", "mixed"},
                "mixed",
            ),
        }

        summary = self._compact_text(str(parsed.get("headline_summary") or ""))
        reasoning = self._compact_text(str(parsed.get("structured_reasoning") or ""))
        if not summary:
            summary = self._fallback_summary(rows, sentiment, severity)
        if not reasoning:
            reasoning = "Agno output omitted structured_reasoning; summary normalized from the returned JSON."

        return {
            "analysis_scope": "bse_only",
            "market_sentiment": sentiment,
            "event_severity_score": severity,
            "confidence_score": confidence,
            "risk_of_abnormal_volatility": volatility_risk,
            "trade_caution_level": caution,
            "affected_sectors": sectors[:8],
            "event_clusters": clusters[:8],
            "headline_summary": summary,
            "structured_reasoning": reasoning,
            "llm_regime_overlay": overlay,
        }

    def _float01(self, value: Any, default: float) -> float:
        try:
            number = float(value)
        except Exception:
            return default
        return max(0.0, min(1.0, number))

    def _normalize_choice(self, value: Any, allowed: set[str], default: str) -> str:
        candidate = self._compact_text(str(value or "")).lower().replace(" ", "_")
        return candidate if candidate in allowed else default

    def _fallback_summary(self, rows: List[Dict[str, Any]], sentiment: str, severity: float) -> str:
        lead_titles = [self._compact_text(str(item.get("title") or "")) for item in rows[:3]]
        lead_titles = [item for item in lead_titles if item]
        joined = " | ".join(lead_titles) if lead_titles else "No BSE headline previews."
        return f"Sentiment={sentiment}; event_severity={round(severity, 3)}. Top BSE items: {joined}"

    def _compact_text(self, value: str) -> str:
        return " ".join(str(value or "").split()).strip()
