from __future__ import annotations

import json
import os
import base64
import hashlib
import re
import socket
import struct
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock, Thread
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, urlparse

from pipeline.config import PipelineConfig
from pipeline.runtime.run_stock_agent import MultiStockAgentRunner
from pipeline.services.ai_trading_state_service import AITradingStateService
from pipeline.services.storage_service import StorageService


class WebSocketBroadcaster:
    MAGIC_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

    def __init__(self) -> None:
        self.clients: list[socket.socket] = []
        self.lock = Lock()

    def accept(self, handler: BaseHTTPRequestHandler) -> bool:
        key = handler.headers.get("Sec-WebSocket-Key")
        if not key:
            return False
        accept_key = base64.b64encode(
            hashlib.sha1(f"{key}{self.MAGIC_GUID}".encode("ascii")).digest()
        ).decode("ascii")
        handler.send_response(101, "Switching Protocols")
        handler.send_header("Upgrade", "websocket")
        handler.send_header("Connection", "Upgrade")
        handler.send_header("Sec-WebSocket-Accept", accept_key)
        handler.end_headers()
        with self.lock:
            self.clients.append(handler.request)
        return True

    def remove(self, client: socket.socket) -> None:
        with self.lock:
            if client in self.clients:
                self.clients.remove(client)
        try:
            client.close()
        except Exception:
            pass

    def broadcast(self, payload: Dict[str, Any]) -> None:
        message = json.dumps(payload, ensure_ascii=True, default=str)
        with self.lock:
            clients = list(self.clients)
        stale: list[socket.socket] = []
        for client in clients:
            try:
                client.sendall(self._frame(message))
            except Exception:
                stale.append(client)
        for client in stale:
            self.remove(client)

    def send_one(self, client: socket.socket, payload: Dict[str, Any]) -> bool:
        try:
            client.sendall(self._frame(json.dumps(payload, ensure_ascii=True, default=str)))
            return True
        except Exception:
            self.remove(client)
            return False

    def _frame(self, message: str) -> bytes:
        body = message.encode("utf-8")
        length = len(body)
        if length < 126:
            header = struct.pack("!BB", 0x81, length)
        elif length < 65536:
            header = struct.pack("!BBH", 0x81, 126, length)
        else:
            header = struct.pack("!BBQ", 0x81, 127, length)
        return header + body


class AITradingOrchestrator:
    def __init__(self, config: Optional[PipelineConfig] = None) -> None:
        self.config = config or PipelineConfig()
        self.storage = StorageService
        self.stock_agent = MultiStockAgentRunner(self.config)
        self.last_request_id: Optional[str] = None
        self._boot_time_utc = datetime.now(timezone.utc)
        self.ws = WebSocketBroadcaster()
        self.event_executor = ThreadPoolExecutor(
            max_workers=max(1, self.config.intra_finder_agent_concurrency)
        )
        self.event_state_path = self.config.agents_results_dir / "event-dispatch-state.json"
        self.event_state = self.storage.load_snapshot(self.event_state_path) or {"events": {}}
        self.event_lock = Lock()

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

    def submit_intra_finder_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        required = {
            "event_id",
            "market_date",
            "universe_version",
            "isin",
            "exchange_segment",
            "security_id",
            "symbol",
            "direction",
            "setup_type",
            "setup_score",
        }
        missing = sorted(key for key in required if event.get(key) in (None, ""))
        if missing:
            raise ValueError(f"invalid_intra_finder_event_missing:{','.join(missing)}")
        event_id = str(event["event_id"])
        with self.event_lock:
            existing = (self.event_state.get("events") or {}).get(event_id)
            if existing:
                return {"accepted": False, "duplicate": True, "event_id": event_id}
            self.event_state.setdefault("events", {})[event_id] = {
                "status": "accepted",
                "accepted_at_utc": datetime.now(timezone.utc).isoformat(),
            }
            self.storage.save_snapshot(self.event_state_path, self.event_state)
        self.event_executor.submit(self._run_intra_finder_event, dict(event))
        return {"accepted": True, "duplicate": False, "event_id": event_id}

    def _run_intra_finder_event(self, event: Dict[str, Any]) -> None:
        event_id = str(event["event_id"])
        try:
            self._broadcast_event({"type": "intra_finder_event_accepted", "event": event})
            result = self.stock_agent.run_event(event, event_callback=self._broadcast_event)
            status = "completed"
            error = None
            decision = (result.get("results") or [{}])[0].get("decision")
        except Exception as exc:
            status = "failed"
            error = f"{type(exc).__name__}: {exc}"
            decision = None
        with self.event_lock:
            self.event_state.setdefault("events", {})[event_id] = {
                "status": status,
                "finished_at_utc": datetime.now(timezone.utc).isoformat(),
                "decision": decision,
                "error": error,
            }
            self.storage.save_snapshot(self.event_state_path, self.event_state)
        self._broadcast_event(
            {
                "type": "intra_finder_event_finished",
                "event_id": event_id,
                "status": status,
                "decision": decision,
                "error": error,
            }
        )

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
                "stock_agent": {"status": "pending", "summary": None, "details": None},
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
                if header == f"Bearer {auth_token}":
                    return True
                query_token = (parse_qs(urlparse(self.path).query).get("token") or [""])[0]
                return query_token == auth_token

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
                    parsed = urlparse(self.path)
                    if parsed.path == "/ai-trading/stream":
                        self._websocket_stream()
                        return
                    if parsed.path != "/ai-trading/status":
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
                    path = urlparse(self.path).path
                    if path == "/ai-trading/event":
                        result = orchestrator.submit_intra_finder_event(self._read_body())
                        self._json_response({"ok": True, **result}, status=202 if result["accepted"] else 200)
                        return
                    if path != "/ai-trading/start":
                        self._json_response({"error": "not_found"}, status=404)
                        return
                    request_payload = orchestrator.submit_start_request(self._read_body())
                    self._json_response({"ok": True, "request": request_payload})
                except Exception as exc:
                    self._json_response({"error": f"start_handler_error: {type(exc).__name__}: {exc}"}, status=500)

            def log_message(self, format: str, *args: Any) -> None:
                return

            def _websocket_stream(self) -> None:
                if self.headers.get("Upgrade", "").lower() != "websocket":
                    self._json_response({"error": "upgrade_required"}, status=426)
                    return
                if not orchestrator.ws.accept(self):
                    self._json_response({"error": "bad_websocket_handshake"}, status=400)
                    return
                client = self.request
                orchestrator.ws.send_one(
                    client,
                    {
                        "type": "status_snapshot",
                        "status": orchestrator.load_run_status(),
                        "sent_at_utc": datetime.now(timezone.utc).isoformat(),
                    },
                )
                try:
                    while True:
                        time.sleep(25)
                        if not orchestrator.ws.send_one(
                            client,
                            {"type": "heartbeat", "sent_at_utc": datetime.now(timezone.utc).isoformat()},
                        ):
                            break
                finally:
                    orchestrator.ws.remove(client)

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

        print(f"Arming event-driven AI trading for {user_id or 'unknown'}...")
        print(f"Trade mode: {trade_mode}, Trade amount: {trade_amount}")
        print(f"Regime analysis enabled: {regime_analysis_enabled}")
        outputs: Dict[str, Any] = {
            "stage2": self.storage.load_snapshot(self.config.stage2_latest_path)
            or {
                "generated_at_utc": None,
                "summary": {
                    "status": "waiting",
                    "message": "Intra-Finder has not published live state yet.",
                },
            },
        }
        self._save_status(
            "armed",
            "intra_finder",
            request,
            outputs=outputs,
            message="AI trading is armed. Agents now start only for qualified Intra-Finder events.",
        )
        print("AI trading armed; waiting for Intra-Finder events.")

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
                "stock_agent": self._stage_status("stock_agent", current_stage, outputs),
            },
        }
        self.storage.save_snapshot(self.config.ai_trading_run_status_path, payload)
        self._save_trade_session_snapshot(payload, outputs)
        self._broadcast_event({"type": "status_update", "status": payload})

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
        if stage == "stock_agent":
            results = output.get("results") or []
            return {
                "selected_symbols": (output.get("summary") or {}).get("selected_symbols"),
                "results": [
                    {
                        "rank": item.get("rank"),
                        "symbol": (item.get("candidate") or {}).get("symbol"),
                        "display_name": (item.get("candidate") or {}).get("display_name"),
                        "decision": item.get("decision"),
                        "attachments": item.get("attachments"),
                        "agent_metadata": item.get("agent_metadata"),
                        "analysis": self._truncate(item.get("analysis"), 20000),
                        "report_text": self._truncate(item.get("report_text"), 20000),
                    }
                    for item in results
                ],
                "decision": output.get("decision"),
                "report_text": self._truncate(output.get("report_text"), 20000),
            }
        return None

    def _truncate(self, value: Any, limit: int = 1400) -> str:
        text = str(value or "").strip()
        if len(text) <= limit:
            return text
        return f"{text[:limit].rstrip()}..."

    def _save_trade_session_snapshot(
        self,
        status_payload: Dict[str, Any],
        outputs: Optional[Dict[str, Any]],
    ) -> None:
        request = status_payload.get("request") if isinstance(status_payload.get("request"), dict) else {}
        request_id = str(request.get("request_id") or self.last_request_id or "").strip()
        if not request_id:
            return

        stock_output = (outputs or {}).get("stock_agent")
        agents = []
        if isinstance(stock_output, dict):
            for item in stock_output.get("results") or []:
                if not isinstance(item, dict):
                    continue
                candidate = item.get("candidate") or {}
                agents.append(
                    {
                        "rank": item.get("rank"),
                        "symbol": candidate.get("symbol"),
                        "display_name": candidate.get("display_name"),
                        "decision": item.get("decision"),
                        "attachments": item.get("attachments"),
                        "agent_metadata": item.get("agent_metadata"),
                        "analysis": item.get("analysis"),
                        "report_text": item.get("report_text"),
                    }
                )

        session_id = self._slugify_session_id(request_id)
        payload = {
            "session_id": session_id,
            "request_id": request_id,
            "title": self._session_title(status_payload, agents),
            "status": status_payload.get("status"),
            "created_at_utc": request.get("requested_at_utc"),
            "updated_at_utc": status_payload.get("updated_at_utc"),
            "request": request,
            "summary": ((stock_output or {}).get("summary") if isinstance(stock_output, dict) else None),
            "status_snapshot": status_payload,
            "agents": agents,
        }
        session_dir = self.config.ai_trading_sessions_dir / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        self.storage.save_snapshot(session_dir / "session.json", payload)

    def _slugify_session_id(self, value: str) -> str:
        slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-")
        return slug or f"session-{int(time.time() * 1000)}"

    def _session_title(self, status_payload: Dict[str, Any], agents: list[Dict[str, Any]]) -> str:
        request = status_payload.get("request") if isinstance(status_payload.get("request"), dict) else {}
        stock_names = [str(agent.get("display_name") or agent.get("symbol")) for agent in agents[:3] if agent.get("display_name") or agent.get("symbol")]
        if stock_names:
            return ", ".join(stock_names)
        requested_at = request.get("requested_at_utc") or status_payload.get("updated_at_utc") or "Trade session"
        return f"Trade session {requested_at}"

    def _broadcast_event(self, event: Dict[str, Any]) -> None:
        payload = dict(event)
        payload.setdefault("sent_at_utc", datetime.now(timezone.utc).isoformat())
        if self.last_request_id:
            payload.setdefault("request_id", self.last_request_id)
        self.ws.broadcast(payload)


def main() -> None:
    AITradingOrchestrator().run_forever()


if __name__ == "__main__":
    main()
