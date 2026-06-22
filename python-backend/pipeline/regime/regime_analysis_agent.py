from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional, Tuple

from pipeline.config import PipelineConfig

try:
    from agno.agent import Agent

    from pipeline.llm import create_trading_model

    AGNO_AVAILABLE = True
except Exception:  # pragma: no cover - optional runtime dependency
    Agent = None  # type: ignore
    create_trading_model = None  # type: ignore
    AGNO_AVAILABLE = False


class RegimeAnalysisAgent:
    """Unified market-regime agent.

    Deterministic market math feeds this agent as features; the agent returns the
    final structured regime decision consumed by downstream stages.
    """

    REQUIRED_KEYS = {
        "market_regime",
        "index_regime",
        "breadth_regime",
        "volatility_regime",
        "flow_regime",
        "event_regime",
        "global_context_regime",
        "confidence",
        "is_actionable",
        "new_trade_permission",
        "participation_bias",
        "max_position_size_multiplier",
        "allowed_setup_types",
        "avoid_setup_types",
        "risk_flags",
        "source_staleness",
        "reasoning_summary",
        "human_readable_report",
    }

    def __init__(self, config: Optional[PipelineConfig] = None) -> None:
        self.config = config or PipelineConfig()
        self.agent_name = os.getenv("REGIME_ANALYSIS_AGENT_NAME", "REGIME_ANALYSIS_AGENT")
        self.model_id = os.getenv("REGIME_MODEL_ID", self.config.regime_model_id).strip() or self.config.regime_model_id
        self.use_agno = os.getenv("REGIME_ANALYSIS_USE_AGNO", "1").strip().lower() not in {"0", "false"}

    def analyze(self, regime_packet: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        if not self.use_agno:
            return None, "regime_analysis_agent_disabled"
        if not AGNO_AVAILABLE or Agent is None or create_trading_model is None:
            return None, "regime_analysis_agent_dependency_not_available"
        try:
            agent = Agent(
                name=self.agent_name,
                model=create_trading_model(id=self.model_id),
                description=(
                    "Classify the Indian intraday market regime from supplied market internals, "
                    "manual feature metrics, news, institutional flows, options, futures, and global context."
                ),
                instructions=[
                    "Use only the supplied regime_packet. Do not infer facts from outside data.",
                    "This system trades the Indian stock market. Use IST/Indian market-time fields for session interpretation; UTC fields are audit timestamps.",
                    "You are the single source of truth for the final market regime; deterministic labels are feature hints only.",
                    "Distinguish current data from stale or fallback data. Never treat stale FII/DII flow as today's live flow.",
                    "Separate Indian market internals from global context and news.",
                    "Separate systemic, sectoral, and isolated company news.",
                    "Do not recommend a specific stock, entry, stop, target, or quantity.",
                    "Return one strict JSON object only. No markdown fences and no prose outside JSON.",
                    "The JSON must include: market_regime, index_regime, breadth_regime, volatility_regime, flow_regime, event_regime, global_context_regime, confidence, is_actionable, new_trade_permission, participation_bias, max_position_size_multiplier, allowed_setup_types, avoid_setup_types, risk_flags, source_staleness, reasoning_summary, human_readable_report.",
                    "Use confidence from 0 to 100. Use max_position_size_multiplier from 0.0 to 1.0.",
                    "Valid new_trade_permission examples: allowed, reduced, scalp_only, blocked, unavailable.",
                    "Valid participation_bias examples: aggressive, normal, selective, defensive, observation_only.",
                ],
                markdown=False,
                add_datetime_to_context=False,
                debug_mode=True,
            )
            response = agent.run(self._build_prompt(regime_packet))
            text = self._extract_text(response).strip()
            if not text:
                return None, "regime_analysis_agent_empty_response"
            parsed = self._safe_parse_json(text)
            if not parsed:
                return None, f"regime_analysis_agent_invalid_json::{text[:500]}"
            return self.normalize(parsed), None
        except Exception as exc:
            return None, f"regime_analysis_agent_failure::{type(exc).__name__}::{exc}"

    def normalize(self, parsed: Dict[str, Any]) -> Dict[str, Any]:
        normalized = dict(parsed)
        normalized["market_regime"] = self._choice(normalized.get("market_regime"), "data_unavailable")
        normalized["index_regime"] = self._choice(normalized.get("index_regime"), "unknown")
        normalized["breadth_regime"] = self._choice(normalized.get("breadth_regime"), "unknown")
        normalized["volatility_regime"] = self._choice(normalized.get("volatility_regime"), "unknown")
        normalized["flow_regime"] = self._choice(normalized.get("flow_regime"), "unknown")
        normalized["event_regime"] = self._choice(normalized.get("event_regime"), "none")
        normalized["global_context_regime"] = self._choice(normalized.get("global_context_regime"), "unknown")
        normalized["confidence"] = round(self._float_range(normalized.get("confidence"), 0.0, 0.0, 100.0), 2)
        normalized["is_actionable"] = bool(normalized.get("is_actionable"))
        normalized["new_trade_permission"] = self._choice(normalized.get("new_trade_permission"), "unavailable")
        normalized["participation_bias"] = self._choice(normalized.get("participation_bias"), "observation_only")
        normalized["max_position_size_multiplier"] = round(
            self._float_range(normalized.get("max_position_size_multiplier"), 0.0, 0.0, 1.0),
            3,
        )
        normalized["allowed_setup_types"] = self._string_list(normalized.get("allowed_setup_types"))
        normalized["avoid_setup_types"] = self._string_list(normalized.get("avoid_setup_types"))
        normalized["risk_flags"] = self._string_list(normalized.get("risk_flags"))
        source_staleness = normalized.get("source_staleness")
        normalized["source_staleness"] = source_staleness if isinstance(source_staleness, dict) else {}
        normalized["reasoning_summary"] = self._text(normalized.get("reasoning_summary"))
        normalized["human_readable_report"] = self._text(normalized.get("human_readable_report"))
        for key in self.REQUIRED_KEYS:
            normalized.setdefault(key, None)
        return normalized

    def _build_prompt(self, regime_packet: Dict[str, Any]) -> str:
        return (
            "Classify the market regime and output strict JSON only.\n"
            "Use Indian market time/IST fields for market-session reasoning.\n"
            "Treat deterministic/manual labels as input features, not binding decisions.\n"
            "Regime packet JSON:\n"
            f"{json.dumps(regime_packet, ensure_ascii=True)}"
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
        return str(response)

    def _safe_parse_json(self, text: str) -> Optional[Dict[str, Any]]:
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

    def _choice(self, value: Any, default: str) -> str:
        text = self._text(value).strip().lower().replace(" ", "_")
        return text or default

    def _text(self, value: Any) -> str:
        return " ".join(str(value or "").split()).strip()

    def _string_list(self, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [self._text(item) for item in value if self._text(item)]

    def _float_range(self, value: Any, default: float, low: float, high: float) -> float:
        try:
            number = float(value)
        except Exception:
            return default
        return max(low, min(high, number))
