from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from pipeline.config import PipelineConfig
from pipeline.runtime.run_executioner import ExecutionerRunner
from pipeline.runtime.run_sorting import wait_for_current_stage2_snapshot
from pipeline.runtime.run_stock_analyzer import MultiStockAnalyzerRunner
from pipeline.services.ai_trading_state_service import AITradingStateService
from pipeline.services.storage_service import StorageService


class AITradingOrchestrator:
    def __init__(self, config: Optional[PipelineConfig] = None) -> None:
        self.config = config or PipelineConfig()
        self.storage = StorageService
        self.stock_analyzer = MultiStockAnalyzerRunner(self.config)
        self.executioner = ExecutionerRunner(self.config)
        self.last_request_id: Optional[str] = None
        self._boot_time_utc = datetime.now(timezone.utc)

    def run_forever(self) -> None:
        print("=" * 60)
        print("AI TRADING ORCHESTRATOR")
        print("=" * 60)
        print("Waiting for user start requests...")
        self._start_http_gateway()

        while True:
            try:
                request = self._load_pending_request()
                if request:
                    self._run_request(request)
                else:
                    time.sleep(2)
            except Exception as exc:  # pragma: no cover - runtime safety
                print(f"AI trading orchestrator error: {type(exc).__name__}: {exc}")
                self._save_status("failed", "orchestrator", error=str(exc))
                time.sleep(5)

    def _load_pending_request(self) -> Optional[Dict[str, Any]]:
        request = self.storage.load_snapshot(self.config.ai_trading_request_path)
        if not isinstance(request, dict):
            return None
        request_id = str(request.get("request_id") or "")
        if not request_id or request_id == self.last_request_id:
            return None
        if request.get("action") != "start":
            return None
        # Ignore stale requests from before this container booted
        requested_at = request.get("requested_at_utc")
        if requested_at:
            try:
                req_dt = datetime.fromisoformat(str(requested_at).replace("Z", "+00:00"))
                if req_dt < self._boot_time_utc:
                    self.last_request_id = request_id  # Mark as seen so we don't log repeatedly
                    return None
            except (ValueError, TypeError):
                pass
        return request

    def submit_start_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        request_payload = {
            "request_id": str(request.get("request_id") or f"{int(time.time() * 1000)}-backend"),
            "action": "start",
            "user_id": request.get("user_id"),
            "email": request.get("email"),
            "requested_at_utc": request.get("requested_at_utc") or datetime.now(timezone.utc).isoformat(),
            "trade_mode": request.get("trade_mode") or "auto",
            "trade_amount": request.get("trade_amount"),
            "regime_analysis_enabled": self._as_bool(request.get("regime_analysis_enabled"), default=True),
        }
        self.storage.save_snapshot(self.config.ai_trading_request_path, request_payload)
        return request_payload

    def load_run_status(self) -> Dict[str, Any]:
        status = self.storage.load_snapshot(self.config.ai_trading_run_status_path)
        if isinstance(status, dict):
            if self._is_stale_running_status(status):
                stale_status = self._stale_status(status)
                self.storage.save_snapshot(self.config.ai_trading_run_status_path, stale_status)
                return stale_status
            return status
        return {
            "status": "idle",
            "current_stage": "idle",
            "message": None,
            "stages": {
                "stage2": {"status": "pending", "summary": None, "details": None},
                "stock_analyzer": {"status": "pending", "summary": None, "details": None},
                "executioner": {"status": "pending", "summary": None, "details": None},
            },
        }

    def _is_stale_running_status(self, status: Dict[str, Any]) -> bool:
        if status.get("status") != "running":
            return False
        updated_at = status.get("updated_at_utc")
        if not updated_at:
            return True
        try:
            updated_dt = datetime.fromisoformat(str(updated_at).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return True
        return updated_dt < self._boot_time_utc

    def _stale_status(self, status: Dict[str, Any]) -> Dict[str, Any]:
        payload = dict(status)
        stages = dict(payload.get("stages") or {})
        current_stage = str(payload.get("current_stage") or "")
        if current_stage and current_stage in stages:
            stage_payload = dict(stages.get(current_stage) or {})
            if stage_payload.get("status") == "running":
                stage_payload["status"] = "stale"
                stages[current_stage] = stage_payload
        payload["status"] = "stale"
        payload["current_stage"] = "idle"
        payload["updated_at_utc"] = datetime.now(timezone.utc).isoformat()
        payload["message"] = "Previous AI trading run was interrupted before completion. Start a new run when ready."
        payload["stale_previous_stage"] = current_stage
        payload["stages"] = stages
        return payload

    def _start_http_gateway(self) -> None:
        server = ThreadingHTTPServer(
            (self.config.ai_trading_gateway_host, self.config.ai_trading_gateway_port),
            self._handler_class(),
        )
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        print(f"AI trading gateway listening on port {self.config.ai_trading_gateway_port}.")

    def _handler_class(self):
        orchestrator = self
        auth_token = os.getenv("AI_TRADING_BACKEND_TOKEN")

        class AITradingGatewayHandler(BaseHTTPRequestHandler):
            def _authorized(self) -> bool:
                if not auth_token:
                    return True
                header = self.headers.get("authorization", "")
                return header == f"Bearer {auth_token}"

            def _json_response(self, payload: Dict[str, Any], status: int = 200) -> None:
                body = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _read_body(self) -> Dict[str, Any]:
                length = int(self.headers.get("content-length") or 0)
                if length <= 0:
                    return {}
                try:
                    return json.loads(self.rfile.read(length).decode("utf-8"))
                except Exception:
                    return {}

            def do_GET(self) -> None:
                try:
                    if not self._authorized():
                        self._json_response({"error": "unauthorized"}, status=401)
                        return
                    if urlparse(self.path).path != "/ai-trading/status":
                        self._json_response({"error": "not_found"}, status=404)
                        return
                    self._json_response(orchestrator.load_run_status())
                except Exception as exc:
                    self._json_response({"error": f"status_handler_error: {type(exc).__name__}: {exc}"}, status=500)

            def do_POST(self) -> None:
                try:
                    if not self._authorized():
                        self._json_response({"error": "unauthorized"}, status=401)
                        return
                    if urlparse(self.path).path != "/ai-trading/start":
                        self._json_response({"error": "not_found"}, status=404)
                        return
                    request_payload = orchestrator.submit_start_request(self._read_body())
                    self._json_response({"ok": True, "request": request_payload})
                except Exception as exc:
                    self._json_response({"error": f"start_handler_error: {type(exc).__name__}: {exc}"}, status=500)

            def log_message(self, format: str, *args: Any) -> None:
                return

        return AITradingGatewayHandler

    def _run_request(self, request: Dict[str, Any]) -> None:
        self.last_request_id = str(request.get("request_id"))
        user_id = str(request.get("user_id") or "")
        trade_mode = str(request.get("trade_mode") or "auto").strip().lower()
        trade_amount = request.get("trade_amount")
        regime_analysis_enabled = self._as_bool(request.get("regime_analysis_enabled"), default=True)

        if not AITradingStateService.is_any_user_enabled(self.config.ai_trading_state_path):
            self._save_status("blocked", "requested", request, "AI trading is not enabled for any user.")
            return

        print(f"Starting AI trading run {self.last_request_id} for user {user_id or 'unknown'}...")
        print(f"Trade mode: {trade_mode}, Trade amount: {trade_amount}")
        print(f"Regime analysis enabled: {regime_analysis_enabled}")
        self._save_status(
            "waiting",
            "stage2",
            request,
            message="Waiting for Stage 2 momentum results before starting trading agents.",
        )
        market_date = wait_for_current_stage2_snapshot(self.config, poll_seconds=10)
        outputs: Dict[str, Any] = {
            "stage2": self.storage.load_snapshot(self.config.stage2_daily_path(market_date))
            or self.storage.load_snapshot(self.config.stage2_latest_path)
            or {"generated_at_utc": None, "summary": {"status": "ready", "market_date": market_date}},
        }

        trade_config = {
            "trade_mode": trade_mode,
            "trade_amount": float(trade_amount) if trade_amount else None,
            "regime_analysis_enabled": regime_analysis_enabled,
        }

        stages = [
            (
                "stock_analyzer",
                lambda force: self.stock_analyzer.run_cycle(
                    force=force,
                    trade_config=trade_config,
                    use_regime_analysis=regime_analysis_enabled,
                ),
            ),
            ("executioner", lambda force: self.executioner.run_cycle(force=force, trade_config=trade_config)),
        ]

        for stage_name, runner in stages:
            self._save_status("running", stage_name, request, outputs=outputs)
            print(f"Running {stage_name}...")
            outputs[stage_name] = runner(force=True)

        self._save_status("completed", "completed", request, outputs=outputs)
        print(f"Completed AI trading run {self.last_request_id}.")

    def _save_status(
        self,
        status: str,
        current_stage: str,
        request: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        outputs: Optional[Dict[str, Any]] = None,
        message: Optional[str] = None,
    ) -> None:
        payload = {
            "status": status,
            "current_stage": current_stage,
            "request": request or {},
            "updated_at_utc": datetime.now(timezone.utc).isoformat(),
            "error": error,
            "message": message,
            "stages": {
                "stage2": self._stage_status("stage2", current_stage, outputs),
                "stock_analyzer": self._stage_status("stock_analyzer", current_stage, outputs),
                "executioner": self._stage_status("executioner", current_stage, outputs),
            },
        }
        self.storage.save_snapshot(self.config.ai_trading_run_status_path, payload)

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

    def _stage_status(self, stage: str, current_stage: str, outputs: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        output = (outputs or {}).get(stage)
        if output is not None:
            return {
                "status": "completed",
                "generated_at_utc": output.get("generated_at_utc") if isinstance(output, dict) else None,
                "summary": output.get("summary") if isinstance(output, dict) else None,
                "details": self._stage_details(stage, output),
            }
        if current_stage == stage:
            return {"status": "running", "generated_at_utc": None, "summary": None, "details": None}
        return {"status": "pending", "generated_at_utc": None, "summary": None, "details": None}

    def _stage_details(self, stage: str, output: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(output, dict):
            return None
        if stage == "stock_analyzer":
            reports = output.get("reports") or []
            return {
                "selected_symbols": (output.get("summary") or {}).get("selected_symbols"),
                "reports": [
                    {
                        "rank": report.get("rank"),
                        "symbol": (report.get("candidate") or {}).get("symbol"),
                        "display_name": (report.get("candidate") or {}).get("display_name"),
                        "analysis": self._truncate(report.get("analysis")),
                    }
                    for report in reports
                ],
            }
        if stage == "executioner":
            return {
                "decision": output.get("decision"),
                "results": [
                    {
                        "rank": item.get("rank"),
                        "display_name": (item.get("selected_stock") or {}).get("display_name"),
                        "decision": item.get("decision"),
                        "report_text": self._truncate(item.get("report_text")),
                    }
                    for item in (output.get("results") or [])
                ],
                "report_text": self._truncate(output.get("report_text")),
            }
        return None

    def _truncate(self, value: Any, limit: int = 1400) -> str:
        text = str(value or "").strip()
        if len(text) <= limit:
            return text
        return f"{text[:limit].rstrip()}..."


def main() -> None:
    AITradingOrchestrator().run_forever()


if __name__ == "__main__":
    main()
