from __future__ import annotations

import json
import os
import time
from datetime import datetime, time as dt_time, timezone
from typing import Any, Dict, List, Optional, Tuple

import requests

from pipeline.config import PipelineConfig
from pipeline.services.ai_trading_state_service import AITradingStateService
from pipeline.services.order_placement_gate import OrderPlacementStateService
from pipeline.services.market_calendar_service import MarketCalendarService, MarketSessionStatus
from pipeline.services.market_time_service import MarketTimeService
from pipeline.services.storage_service import StorageService
from pipeline.stages.stage1_sanitation import Stage1Sanitation
from pipeline.stages.stage2_momentum_ignition import Stage2MomentumIgnition


class SessionSupervisor:
    """Autonomous market-day runner for Stage 1, Stage 2, and agent triggers."""

    def __init__(self, config: Optional[PipelineConfig] = None):
        self.config = config or PipelineConfig()
        self.market_time = MarketTimeService(self.config)
        self.calendar = MarketCalendarService(self.config)
        self.stage1 = Stage1Sanitation(self.config)
        self.stage2 = Stage2MomentumIgnition(self.config)
        self.backend_url = (
            os.getenv("AI_TRADING_BACKEND_URL_INTERNAL")
            or os.getenv("AI_TRADING_BACKEND_URL")
            or "http://ai-trading-agents:8020"
        ).rstrip("/")
        self.backend_token = os.getenv("AI_TRADING_BACKEND_TOKEN", "").strip()
        self.loop_interval_seconds = int(os.getenv("SESSION_SUPERVISOR_LOOP_SECONDS", "30"))
        self.stage2_signature_history_limit = int(os.getenv("SESSION_SUPERVISOR_SIGNATURE_HISTORY", "20"))

    def run_forever(self) -> None:
        print("=" * 60)
        print("SESSION SUPERVISOR")
        print("=" * 60)
        print(f"Stage 1 target: {self.config.stage1_schedule_time} {self.config.market_timezone}")
        print(f"First Stage 2 target: {self.config.stage2_first_run_time} {self.config.market_timezone}")
        print(f"Stage 2 interval: {self.config.stage2_loop_interval_seconds} seconds")
        print(f"AI trading backend: {self.backend_url}")

        while True:
            try:
                self.run_once()
            except Exception as exc:  # pragma: no cover - runtime safety
                self._save_status("error", {"error": f"{type(exc).__name__}: {exc}"})
                print(f"Session supervisor error: {type(exc).__name__}: {exc}")
            time.sleep(self.loop_interval_seconds)

    def run_once(self) -> None:
        session = self.calendar.session_status()
        state = self._load_state()
        state = self._ensure_market_date_state(state, session.market_date)

        self._save_status(
            "running",
            {
                "session": session.to_dict(),
                "state": self._compact_state(state),
            },
        )

        if not session.is_trading_day:
            print(f"Supervisor idle: {session.reason} ({session.source}).")
            return

        if self._stage1_due(session, state):
            self._run_stage1(state, session)
            state = self._load_state()

        if self._stage2_due(session, state):
            stage2_payload = self._run_stage2(state, session)
            if stage2_payload:
                state = self._load_state()
                self._evaluate_agent_trigger(stage2_payload, state, session)
            return

        print(f"Supervisor idle: {session.reason}; next check in {self.loop_interval_seconds}s.")

    def _stage1_due(self, session: MarketSessionStatus, state: Dict[str, Any]) -> bool:
        if self._stage1_snapshot_exists(session.market_date):
            return False
        now = self.market_time.now()
        if now.time() < self._parse_hhmm(self.config.stage1_schedule_time):
            return False

        day_state = state.setdefault("days", {}).setdefault(session.market_date, {})
        last_attempt = self._parse_iso(day_state.get("stage1", {}).get("last_run_at_utc"))
        if last_attempt is None:
            return True
        elapsed = (datetime.now(timezone.utc) - last_attempt).total_seconds()
        return elapsed >= self.config.stage1_degraded_retry_interval_seconds

    def _stage2_due(self, session: MarketSessionStatus, state: Dict[str, Any]) -> bool:
        if not session.is_new_entry_window:
            return False
        if not self._stage1_snapshot_exists(session.market_date):
            return False

        now = self.market_time.now()
        if now.time() < self._parse_hhmm(self.config.stage2_first_run_time):
            return False

        day_state = state.setdefault("days", {}).setdefault(session.market_date, {})
        last_run_at = self._parse_iso(day_state.get("stage2", {}).get("last_run_at_utc"))
        if last_run_at is None:
            return True
        elapsed = (datetime.now(timezone.utc) - last_run_at).total_seconds()
        return elapsed >= self.config.stage2_loop_interval_seconds

    def _run_stage1(self, state: Dict[str, Any], session: MarketSessionStatus) -> None:
        print(f"Stage 1 is due for {session.market_date}. Running now.")
        self._save_status("stage1_running", {"session": session.to_dict()})
        payload = self.stage1.run()
        day_state = state.setdefault("days", {}).setdefault(session.market_date, {})
        day_state["stage1"] = {
            "last_run_at_utc": self._now_utc(),
            "generated_at_utc": payload.get("generated_at_utc"),
            "summary": payload.get("summary"),
        }
        self._save_state(state)
        status = str((payload.get("summary") or {}).get("status") or "").lower()
        if status != "completed":
            self._save_status(
                "stage1_degraded",
                {"session": session.to_dict(), "stage1": day_state["stage1"]},
            )
            print("Stage 1 was degraded; Stage 2 remains blocked.")
            return
        self._save_status("stage1_completed", {"session": session.to_dict(), "stage1": day_state["stage1"]})

    def _run_stage2(self, state: Dict[str, Any], session: MarketSessionStatus) -> Optional[Dict[str, Any]]:
        print(f"Stage 2 is due for {session.market_date}. Running now.")
        self._save_status("stage2_running", {"session": session.to_dict()})
        payload = self.stage2.run()
        day_state = state.setdefault("days", {}).setdefault(session.market_date, {})
        status = str((payload.get("summary") or {}).get("status") or "").lower()
        if status != "completed":
            day_state["stage2"] = {
                "last_run_at_utc": self._now_utc(),
                "generated_at_utc": payload.get("generated_at_utc"),
                "summary": payload.get("summary"),
            }
            self._save_state(state)
            self._save_status(
                "stage2_degraded",
                {"session": session.to_dict(), "stage2": day_state["stage2"]},
            )
            print("Stage 2 was degraded; AI agent triggering is blocked.")
            return None

        signature = self._stage2_signature(payload)
        signatures = list(day_state.get("stage2_signatures") or [])
        signatures.append({"generated_at_utc": payload.get("generated_at_utc"), "signature": signature})
        day_state["stage2_signatures"] = signatures[-self.stage2_signature_history_limit :]
        day_state["stage2"] = {
            "last_run_at_utc": self._now_utc(),
            "generated_at_utc": payload.get("generated_at_utc"),
            "signature": signature,
            "summary": payload.get("summary"),
        }
        self._save_state(state)
        self._save_status("stage2_completed", {"session": session.to_dict(), "stage2": day_state["stage2"]})
        return payload

    def _evaluate_agent_trigger(
        self,
        stage2_payload: Dict[str, Any],
        state: Dict[str, Any],
        session: MarketSessionStatus,
    ) -> None:
        decision, reason, candidates = self._should_trigger_agents(stage2_payload, state, session)
        self._save_status(
            "agent_trigger_evaluated",
            {
                "session": session.to_dict(),
                "trigger": {"decision": decision, "reason": reason, "candidate_count": len(candidates)},
            },
        )
        if not decision:
            print(f"AI agents not triggered: {reason}.")
            return

        order_state_path = getattr(self.config, "order_placement_state_path", None)
        if order_state_path is not None and not OrderPlacementStateService.is_allowed(order_state_path):
            print("AI agents not triggered: Dhan order placement is blocked.")
            return
        if not AITradingStateService.is_any_user_enabled(self.config.ai_trading_state_path):
            print("AI agents not triggered: AI trading state has no enabled user.")
            return

        if self._backend_is_busy():
            print("AI agents not triggered: backend is already running or waiting.")
            return

        request_payload = self._build_agent_request(reason)
        response = self._submit_agent_request(request_payload)
        if not response:
            print("AI agent trigger failed: backend unavailable.")
            return

        self._mark_agent_triggered(state, session, stage2_payload, candidates, reason, request_payload, response)
        print(f"AI agents triggered: {reason}.")

    def _should_trigger_agents(
        self,
        stage2_payload: Dict[str, Any],
        state: Dict[str, Any],
        session: MarketSessionStatus,
    ) -> Tuple[bool, str, List[Dict[str, Any]]]:
        candidates = self._candidate_pool(stage2_payload)
        if not candidates:
            return False, "no_stage2_candidates_or_near_misses", candidates

        day_state = state.setdefault("days", {}).setdefault(session.market_date, {})
        agent_state = day_state.setdefault("agents", {})
        last_trigger_at = self._parse_iso(agent_state.get("last_trigger_at_utc"))

        if last_trigger_at is None:
            return True, "first_stage2_result_of_day", candidates

        min_elapsed = (datetime.now(timezone.utc) - last_trigger_at).total_seconds()
        if min_elapsed < self.config.agent_min_run_interval_seconds:
            return False, "agent_min_interval_active", candidates

        evaluated = agent_state.setdefault("evaluated_candidates", {})
        top_candidate = candidates[0]
        previous_top = agent_state.get("last_top_security_id")
        top_security_id = str(top_candidate.get("security_id"))
        if previous_top and str(previous_top) != top_security_id:
            return True, "top_candidate_changed", candidates

        for candidate in candidates[: max(1, int(self.config.agent_trigger_top_n))]:
            security_id = str(candidate.get("security_id"))
            if not security_id:
                continue
            prior = evaluated.get(security_id)
            if not prior:
                return True, "new_candidate_entered_stage2_pool", candidates
            prior_time = self._parse_iso(prior.get("last_evaluated_at_utc"))
            if prior_time is None:
                return True, "candidate_missing_evaluation_timestamp", candidates
            candidate_age = (datetime.now(timezone.utc) - prior_time).total_seconds()
            if candidate_age < self.config.agent_security_cooldown_seconds:
                continue
            previous_score = self._float_or_none(prior.get("stage2_score"))
            current_score = self._float_or_none(candidate.get("stage2_score") or candidate.get("score"))
            if self._score_improved(previous_score, current_score):
                return True, "candidate_score_improved_materially", candidates

        if min_elapsed >= self.config.agent_periodic_refresh_seconds:
            return True, "periodic_candidate_refresh", candidates

        return False, "no_meaningful_stage2_change", candidates

    def _candidate_pool(self, stage2_payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        stocks = [dict(item) for item in stage2_payload.get("stocks") or [] if isinstance(item, dict)]
        stocks.sort(key=lambda row: float(row.get("stage2_score") or row.get("score") or 0.0), reverse=True)
        near_misses = [
            dict(item)
            for item in (stage2_payload.get("summary") or {}).get("near_misses") or []
            if isinstance(item, dict)
        ]
        combined: List[Dict[str, Any]] = []
        seen: set[int] = set()
        for row in stocks + near_misses:
            try:
                security_id = int(row.get("security_id"))
            except Exception:
                continue
            if security_id in seen:
                continue
            seen.add(security_id)
            combined.append(row)
            if len(combined) >= max(1, int(self.config.stock_agent_manual_scan_limit)):
                break
        return combined

    def _score_improved(self, previous_score: Optional[float], current_score: Optional[float]) -> bool:
        if current_score is None:
            return False
        if previous_score is None:
            return True
        absolute_delta = current_score - previous_score
        ratio_delta = absolute_delta / max(abs(previous_score), 1.0)
        return (
            absolute_delta >= self.config.agent_stage2_score_delta_threshold
            or ratio_delta >= self.config.agent_stage2_score_delta_ratio
        )

    def _build_agent_request(self, reason: str) -> Dict[str, Any]:
        user = self._enabled_user()
        trade_config = self._trade_config()
        return {
            "request_id": f"auto-{int(time.time() * 1000)}-{reason}",
            "action": "start",
            "user_id": user.get("user_id"),
            "email": user.get("email"),
            "requested_at_utc": self._now_utc(),
            "trade_mode": trade_config.get("trade_mode"),
            "trade_amount": trade_config.get("trade_amount"),
            "regime_analysis_enabled": trade_config.get("regime_analysis_enabled"),
            "trigger_source": "session_supervisor",
            "trigger_reason": reason,
        }

    def _enabled_user(self) -> Dict[str, Any]:
        state = AITradingStateService.load_state(self.config.ai_trading_state_path)
        enabled = state.get("enabled_user_ids") if isinstance(state.get("enabled_user_ids"), list) else []
        user_id = str(enabled[0]) if enabled else ""
        user_state = (state.get("user_states") or {}).get(user_id) if user_id else {}
        return {"user_id": user_id, "email": (user_state or {}).get("email")}

    def _trade_config(self) -> Dict[str, Any]:
        last_request = StorageService.load_snapshot(self.config.ai_trading_request_path) or {}
        trade_mode = os.getenv("SUPERVISOR_TRADE_MODE") or last_request.get("trade_mode") or "auto"
        raw_amount = os.getenv("SUPERVISOR_TRADE_AMOUNT")
        trade_amount = raw_amount if raw_amount not in (None, "") else last_request.get("trade_amount")
        try:
            trade_amount = float(trade_amount) if trade_amount not in (None, "") else None
        except Exception:
            trade_amount = None
        return {
            "trade_mode": str(trade_mode).strip().lower(),
            "trade_amount": trade_amount,
            "regime_analysis_enabled": False,
        }

    def _backend_is_busy(self) -> bool:
        status = self._backend_status()
        if not status:
            return False
        return str(status.get("status") or "").lower() in {"running", "waiting"}

    def _backend_status(self) -> Optional[Dict[str, Any]]:
        headers = self._headers()
        try:
            response = requests.get(f"{self.backend_url}/ai-trading/status", headers=headers, timeout=5)
            response.raise_for_status()
            return response.json()
        except Exception:
            return None

    def _submit_agent_request(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        headers = self._headers()
        try:
            response = requests.post(
                f"{self.backend_url}/ai-trading/start",
                headers=headers,
                json=payload,
                timeout=10,
            )
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            self._save_status("agent_trigger_failed", {"request": payload, "error": f"{type(exc).__name__}: {exc}"})
            return None

    def _mark_agent_triggered(
        self,
        state: Dict[str, Any],
        session: MarketSessionStatus,
        stage2_payload: Dict[str, Any],
        candidates: List[Dict[str, Any]],
        reason: str,
        request_payload: Dict[str, Any],
        response: Dict[str, Any],
    ) -> None:
        day_state = state.setdefault("days", {}).setdefault(session.market_date, {})
        agent_state = day_state.setdefault("agents", {})
        now = self._now_utc()
        evaluated = agent_state.setdefault("evaluated_candidates", {})
        for candidate in candidates[: max(1, int(self.config.stock_agent_manual_scan_limit))]:
            security_id = str(candidate.get("security_id"))
            if not security_id:
                continue
            evaluated[security_id] = {
                "last_evaluated_at_utc": now,
                "stage2_score": candidate.get("stage2_score") or candidate.get("score"),
                "stage2_reason": candidate.get("stage2_reason"),
                "display_name": candidate.get("display_name"),
                "symbol": candidate.get("symbol"),
            }
        agent_state["last_trigger_at_utc"] = now
        agent_state["last_trigger_reason"] = reason
        agent_state["last_request"] = request_payload
        agent_state["last_response"] = response
        if candidates:
            agent_state["last_top_security_id"] = candidates[0].get("security_id")
        history = list(agent_state.get("trigger_history") or [])
        history.append(
            {
                "triggered_at_utc": now,
                "reason": reason,
                "stage2_generated_at_utc": stage2_payload.get("generated_at_utc"),
                "request_id": request_payload.get("request_id"),
                "candidate_count": len(candidates),
            }
        )
        agent_state["trigger_history"] = history[-50:]
        self._save_state(state)
        self._save_status(
            "agent_triggered",
            {
                "session": session.to_dict(),
                "reason": reason,
                "request": request_payload,
                "response": response,
            },
        )

    def _stage2_signature(self, payload: Dict[str, Any]) -> str:
        rows = []
        for candidate in self._candidate_pool(payload)[: max(1, int(self.config.agent_trigger_top_n))]:
            rows.append(
                {
                    "security_id": candidate.get("security_id"),
                    "score": round(float(candidate.get("stage2_score") or candidate.get("score") or 0.0), 2),
                    "reason": candidate.get("stage2_reason"),
                    "rvol": candidate.get("time_of_day_rvol"),
                    "vwap": candidate.get("price_vs_vwap_percent"),
                    "orb": candidate.get("opening_range_breakout_percent"),
                    "accel": candidate.get("volume_acceleration_ratio"),
                }
            )
        return json.dumps(rows, sort_keys=True, ensure_ascii=True)

    def _stage1_snapshot_exists(self, market_date: str) -> bool:
        payload = StorageService.load_snapshot(self.config.stage1_daily_path(market_date))
        return StorageService.is_stage_snapshot_usable(
            payload,
            self.config.stage1_max_fetch_failure_ratio,
        )

    def _load_state(self) -> Dict[str, Any]:
        payload = StorageService.load_snapshot(self.config.session_supervisor_state_path)
        return payload if isinstance(payload, dict) else {"stage": "session_supervisor_state", "days": {}}

    def _save_state(self, state: Dict[str, Any]) -> None:
        state["generated_at_utc"] = self._now_utc()
        StorageService.save_snapshot(self.config.session_supervisor_state_path, state)

    def _save_status(self, status: str, details: Dict[str, Any]) -> None:
        payload = {
            "stage": "session_supervisor",
            "status": status,
            "generated_at_utc": self._now_utc(),
            "generated_at_ist": self.market_time.now().isoformat(),
            "details": details,
        }
        StorageService.save_snapshot(self.config.session_supervisor_status_path, payload)

    def _ensure_market_date_state(self, state: Dict[str, Any], market_date: str) -> Dict[str, Any]:
        state.setdefault("days", {}).setdefault(market_date, {})
        state["current_market_date"] = market_date
        self._save_state(state)
        return state

    def _compact_state(self, state: Dict[str, Any]) -> Dict[str, Any]:
        day_state = (state.get("days") or {}).get(state.get("current_market_date"), {})
        return {
            "current_market_date": state.get("current_market_date"),
            "stage1": day_state.get("stage1"),
            "stage2": day_state.get("stage2"),
            "agents": {
                key: value
                for key, value in (day_state.get("agents") or {}).items()
                if key != "evaluated_candidates"
            },
            "evaluated_candidate_count": len((day_state.get("agents") or {}).get("evaluated_candidates") or {}),
        }

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.backend_token:
            headers["Authorization"] = f"Bearer {self.backend_token}"
        return headers

    def _parse_hhmm(self, value: str) -> dt_time:
        hour, minute = str(value).split(":", 1)
        return dt_time(int(hour), int(minute))

    def _parse_iso(self, value: Any) -> Optional[datetime]:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def _float_or_none(self, value: Any) -> Optional[float]:
        try:
            if value in (None, ""):
                return None
            return float(value)
        except Exception:
            return None

    def _now_utc(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _as_bool(self, value: Any, default: bool = True) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "y", "on"}:
                return True
            if normalized in {"0", "false", "no", "n", "off"}:
                return False
        return default

    def _env_bool(self, key: str, default: bool) -> bool:
        value = os.getenv(key)
        if value is None:
            return default
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def main() -> None:
    SessionSupervisor().run_forever()


if __name__ == "__main__":
    main()
