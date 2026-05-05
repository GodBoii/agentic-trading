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
from pipeline.runtime.run_risk_analyzer import RiskAnalyzerRunner
from pipeline.runtime.run_sorting import wait_for_current_stage2_snapshot
from pipeline.runtime.run_stock_analyzer import MultiStockAnalyzerRunner
from pipeline.services.ai_trading_state_service import AITradingStateService
from pipeline.services.storage_service import StorageService


class AITradingOrchestrator:
    def __init__(self, config: Optional[PipelineConfig] = None) -> None:
        self.config = config or PipelineConfig()
        self.storage = StorageService
        self.stock_analyzer = MultiStockAnalyzerRunner(self.config)
        self.risk_analyzer = RiskAnalyzerRunner(self.config)
        self.executioner = ExecutionerRunner(self.config)
        self.last_request_id: Optional[str] = None

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
        return request

    def submit_start_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        request_payload = {
            "request_id": str(request.get("request_id") or f"{int(time.time() * 1000)}-backend"),
            "action": "start",
            "user_id": request.get("user_id"),
            "email": request.get("email"),
            "requested_at_utc": request.get("requested_at_utc") or datetime.now(timezone.utc).isoformat(),
        }
        self.storage.save_snapshot(self.config.ai_trading_request_path, request_payload)
        return request_payload

    def load_run_status(self) -> Dict[str, Any]:
        status = self.storage.load_snapshot(self.config.ai_trading_run_status_path)
        if isinstance(status, dict):
            return status
        return {
            "status": "idle",
            "current_stage": "idle",
            "message": None,
            "stages": {
                "stage2": {"status": "pending", "summary": None, "details": None},
                "stock_analyzer": {"status": "pending", "summary": None, "details": None},
                "risk_analyzer": {"status": "pending", "summary": None, "details": None},
                "executioner": {"status": "pending", "summary": None, "details": None},
            },
        }

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
                if not self._authorized():
                    self._json_response({"error": "unauthorized"}, status=401)
                    return
                if urlparse(self.path).path != "/ai-trading/status":
                    self._json_response({"error": "not_found"}, status=404)
                    return
                self._json_response(orchestrator.load_run_status())

            def do_POST(self) -> None:
                if not self._authorized():
                    self._json_response({"error": "unauthorized"}, status=401)
                    return
                if urlparse(self.path).path != "/ai-trading/start":
                    self._json_response({"error": "not_found"}, status=404)
                    return
                request_payload = orchestrator.submit_start_request(self._read_body())
                self._json_response({"ok": True, "request": request_payload})

            def log_message(self, format: str, *args: Any) -> None:
                return

        return AITradingGatewayHandler

    def _run_request(self, request: Dict[str, Any]) -> None:
        self.last_request_id = str(request.get("request_id"))
        user_id = str(request.get("user_id") or "")

        if not AITradingStateService.is_any_user_enabled(self.config.ai_trading_state_path):
            self._save_status("blocked", "requested", request, "AI trading is not enabled for any user.")
            return

        print(f"Starting AI trading run {self.last_request_id} for user {user_id or 'unknown'}...")
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

        stages = [
            ("stock_analyzer", self.stock_analyzer.run_cycle),
            ("risk_analyzer", self.risk_analyzer.run_cycle),
            ("executioner", self.executioner.run_cycle),
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
                "risk_analyzer": self._stage_status("risk_analyzer", current_stage, outputs),
                "executioner": self._stage_status("executioner", current_stage, outputs),
            },
        }
        self.storage.save_snapshot(self.config.ai_trading_run_status_path, payload)

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
        if stage == "risk_analyzer":
            return {
                "decision": output.get("decision"),
                "report_text": self._truncate(output.get("report_text")),
            }
        if stage == "executioner":
            return {
                "decision": output.get("decision"),
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
