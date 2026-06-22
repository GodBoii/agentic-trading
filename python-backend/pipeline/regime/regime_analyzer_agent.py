from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Tuple

try:
    from agno.agent import Agent

    from pipeline.llm import create_trading_model

    AGNO_AVAILABLE = True
except Exception:  # pragma: no cover - optional runtime dependency
    AGNO_AVAILABLE = False
    Agent = None  # type: ignore
    create_trading_model = None  # type: ignore


class RegimeNewsAnalyzerAgent:
    """
    Dedicated Agno agent wrapper for market-context news/disclosure interpretation.

    This module exists so the regime orchestrator can run the deterministic
    market-logic branch and the LLM news-analysis branch independently.
    """

    def __init__(self) -> None:
        self.use_agno = os.getenv("REGIME_NEWS_USE_AGNO", "1").strip() not in {"0", "false", "False"}
        self.agent_name = os.getenv("REGIME_NEWS_AGNO_AGENT_NAME", "REGIME_NEWS_AGENT")

    def is_enabled(self) -> bool:
        return self.use_agno

    def is_available(self) -> bool:
        return AGNO_AVAILABLE and Agent is not None and create_trading_model is not None

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
                    "Analyze supplied Indian-equity market context and explain whether it points to "
                    "isolated stock activity, sector-level pressure, institutional-flow pressure, or broad context."
                ),
                model=create_trading_model(),
                instructions=[
                    "Use only the supplied evidence from the payload.",
                    "Focus on latest stock-related news, institutional FII/DII flow context, overall market tone, and a concise birds-eye view for Indian equities.",
                    "Separate isolated company filings/headlines from repeated, sectoral, or broad event clusters.",
                    "Treat this as market context only; do not decide whether a shortlisted intraday stock should be traded.",
                    "Do not give trading tips, targets, trade permission, trade caution levels, position sizing, or execution advice.",
                    "Return a compact markdown report in normal prose.",
                ],
                expected_output=(
                    "A compact markdown report with: headline summary, market tone, FII/DII context, "
                    "event clusters, affected sectors, abnormal-volatility context, and birds-eye view."
                ),
                add_datetime_to_context=False,
                markdown=True,
                debug_mode=True,
            )
            response = agent.run(self._build_prompt(rows))
            response_status = str(getattr(response, "status", "") or "").lower()
            if "error" in response_status:
                response_message = self._extract_text(response)
                return None, f"agno_run_error::{response_message or 'unknown_error'}"
            raw_text = self._extract_text(response)
            if not raw_text.strip():
                return None, "agno_empty_markdown"
            return {"llm_markdown_analysis": raw_text.strip()}, None
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
            "You are the REGIME_NEWS_AGENT inside an Indian-equity intraday system.\n"
            "A separate deterministic analyzer evaluates price, breadth, futures, options, and volatility.\n"
            "Your job is only to explain the supplied news/disclosure/institutional-flow context.\n\n"
            "Important boundaries:\n"
            "- The downstream stock, risk, and execution agents receive pre-shortlisted intraday candidates.\n"
            "- Do not say whether trading is safe, unsafe, allowed, reduced, blocked, or preferred.\n"
            "- Do not recommend a trade side, entry, stop, target, quantity, or position size.\n"
            "- A bearish or volatile market can still contain valid intraday long/short candidates; your output is context, not a veto.\n"
            "- Use only the supplied evidence. If data is stale, missing, or routine, say that clearly.\n\n"
            "Return normal markdown with these short sections:\n"
            "## Headline Summary\n"
            "## Market Tone\n"
            "## FII/DII Flow Context\n"
            "## Event Clusters\n"
            "## Affected Sectors\n"
            "## Abnormal Volatility Context\n"
            "## Birds-Eye View\n\n"
            f"Supplied market-context items JSON:\n{json.dumps(preview, ensure_ascii=True)}"
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

        sectors = parsed.get("affected_sectors")
        if not isinstance(sectors, list):
            sectors = []
        sectors = [self._compact_text(str(item)) for item in sectors if self._compact_text(str(item))]

        clusters = parsed.get("event_clusters")
        if not isinstance(clusters, list):
            clusters = []
        clusters = [self._compact_text(str(item)) for item in clusters if self._compact_text(str(item))]

        raw_view = parsed.get("birds_eye_view")
        if not isinstance(raw_view, dict):
            raw_view = {}
        birds_eye_view = {
            "scope": self._normalize_choice(
                raw_view.get("scope"),
                {"broad", "sectoral", "isolated", "mixed"},
                "mixed",
            ),
            "impact_horizon": self._normalize_choice(
                raw_view.get("impact_horizon"),
                {"immediate_intraday", "same_day", "multi_day", "unclear"},
                "unclear",
            ),
            "summary": self._compact_text(str(raw_view.get("summary") or "")),
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
            "affected_sectors": sectors[:8],
            "event_clusters": clusters[:8],
            "headline_summary": summary,
            "structured_reasoning": reasoning,
            "birds_eye_view": birds_eye_view,
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
        return f"Sentiment={sentiment}; event_severity={round(severity, 3)}. Top market-context items: {joined}"

    def _compact_text(self, value: str) -> str:
        return " ".join(str(value or "").split()).strip()
