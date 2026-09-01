from __future__ import annotations

import json
import os
import base64
import hashlib
import hmac
import re
import secrets
import socket
import struct
import time
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock, Thread, current_thread
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, urlparse

import requests

from pipeline.config import PipelineConfig
from pipeline.runtime.run_stock_agent import MultiStockAgentRunner
from pipeline.services.ai_trading_state_service import AITradingStateService
from pipeline.services.dhan_service import DhanService
from pipeline.services.market_calendar_service import MarketCalendarService
from pipeline.services.order_placement_gate import (
    DH905_INVALID_IP,
    OrderPlacementGate,
    OrderPlacementState,
    OrderPlacementStateService,
)
from pipeline.services.process_memory_service import release_unused_process_memory
from pipeline.services.trading_amount_service import TradingAmountService
from pipeline.services.storage_service import StorageService


class WebSocketBroadcaster:
    MAGIC_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

    def __init__(self) -> None:
        self.clients: dict[socket.socket, str] = {}
        self.lock = Lock()

    def accept(self, handler: BaseHTTPRequestHandler, user_id: str) -> bool:
        key = handler.headers.get("Sec-WebSocket-Key")
        if not key or not user_id:
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
            self.clients[handler.request] = user_id
        return True

    def remove(self, client: socket.socket) -> None:
        with self.lock:
            self.clients.pop(client, None)
        try:
            client.close()
        except Exception:
            pass

    def broadcast(self, payload: Dict[str, Any], user_id: str) -> None:
        if not user_id:
            return
        message = json.dumps(payload, ensure_ascii=True, default=str)
        with self.lock:
            clients = [client for client, client_user_id in self.clients.items() if client_user_id == user_id]
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


class WebSocketTicketValidator:
    """Issue and validate short-lived, one-time HS256 WebSocket tickets."""

    AUDIENCE = "ai-trading-websocket"
    ISSUER = "polycognition-web"

    def __init__(self, secret: str, max_lifetime_seconds: int = 120) -> None:
        self.secret = secret.encode("utf-8")
        self.max_lifetime_seconds = max_lifetime_seconds
        self.used_ticket_ids: dict[str, int] = {}
        self.lock = Lock()

    def issue(self, user_id: str, lifetime_seconds: int = 45) -> Dict[str, Any]:
        if not self.secret:
            raise ValueError("websocket_ticket_signing_secret_missing")
        normalized_user_id = str(user_id or "").strip()
        if not normalized_user_id:
            raise ValueError("websocket_ticket_identity_invalid")
        lifetime = max(15, min(int(lifetime_seconds), self.max_lifetime_seconds))
        issued_at = int(time.time())
        expires_at = issued_at + lifetime
        header = self._encode_segment({"alg": "HS256", "typ": "JWT"})
        payload = self._encode_segment(
            {
                "iss": self.ISSUER,
                "aud": self.AUDIENCE,
                "sub": normalized_user_id,
                "iat": issued_at,
                "exp": expires_at,
                "jti": secrets.token_urlsafe(24),
            }
        )
        signing_input = f"{header}.{payload}"
        signature = base64.urlsafe_b64encode(
            hmac.new(self.secret, signing_input.encode("ascii"), hashlib.sha256).digest()
        ).decode("ascii").rstrip("=")
        return {
            "ticket": f"{signing_input}.{signature}",
            "expires_at": datetime.fromtimestamp(expires_at, timezone.utc).isoformat(),
        }

    @staticmethod
    def _encode_segment(value: Dict[str, Any]) -> str:
        return base64.urlsafe_b64encode(
            json.dumps(value, separators=(",", ":")).encode("utf-8")
        ).decode("ascii").rstrip("=")

    @staticmethod
    def _decode_segment(value: str) -> bytes:
        padding = "=" * ((4 - len(value) % 4) % 4)
        return base64.urlsafe_b64decode(f"{value}{padding}".encode("ascii"))

    def validate(self, token: str) -> Dict[str, Any]:
        if not self.secret:
            raise ValueError("websocket_ticket_signing_secret_missing")
        parts = token.split(".")
        if len(parts) != 3:
            raise ValueError("websocket_ticket_format_invalid")
        header_segment, payload_segment, signature_segment = parts
        signing_input = f"{header_segment}.{payload_segment}".encode("ascii")
        expected_signature = hmac.new(self.secret, signing_input, hashlib.sha256).digest()
        try:
            supplied_signature = self._decode_segment(signature_segment)
        except Exception as exc:
            raise ValueError("websocket_ticket_signature_invalid") from exc
        if not hmac.compare_digest(expected_signature, supplied_signature):
            raise ValueError("websocket_ticket_signature_invalid")
        try:
            header = json.loads(self._decode_segment(header_segment).decode("utf-8"))
            claims = json.loads(self._decode_segment(payload_segment).decode("utf-8"))
        except Exception as exc:
            raise ValueError("websocket_ticket_payload_invalid") from exc
        if header.get("alg") != "HS256" or header.get("typ") != "JWT":
            raise ValueError("websocket_ticket_algorithm_invalid")
        if claims.get("aud") != self.AUDIENCE or claims.get("iss") != self.ISSUER:
            raise ValueError("websocket_ticket_scope_invalid")
        user_id = str(claims.get("sub") or "").strip()
        ticket_id = str(claims.get("jti") or "").strip()
        try:
            issued_at = int(claims.get("iat"))
            expires_at = int(claims.get("exp"))
        except (TypeError, ValueError) as exc:
            raise ValueError("websocket_ticket_time_invalid") from exc
        now = int(time.time())
        if not user_id or not ticket_id:
            raise ValueError("websocket_ticket_identity_invalid")
        if issued_at > now + 30 or expires_at <= now:
            raise ValueError("websocket_ticket_expired")
        if expires_at <= issued_at or expires_at - issued_at > self.max_lifetime_seconds:
            raise ValueError("websocket_ticket_lifetime_invalid")
        with self.lock:
            self.used_ticket_ids = {
                used_id: used_expiry
                for used_id, used_expiry in self.used_ticket_ids.items()
                if used_expiry > now
            }
            if ticket_id in self.used_ticket_ids:
                raise ValueError("websocket_ticket_replayed")
            self.used_ticket_ids[ticket_id] = expires_at
        return claims


class SupabaseUserVerifier:
    """Resolve a Supabase access token to its authoritative user identity."""

    def __init__(
        self,
        supabase_url: str,
        anon_key: str,
        *,
        timeout_seconds: float = 5.0,
        cache_seconds: int = 30,
    ) -> None:
        self.supabase_url = supabase_url.strip().rstrip("/")
        self.anon_key = anon_key.strip()
        self.timeout_seconds = timeout_seconds
        self.cache_seconds = max(0, cache_seconds)
        self.cache: dict[str, tuple[float, Dict[str, Any]]] = {}
        self.lock = Lock()

    def verify(self, access_token: str) -> Dict[str, Any]:
        token = str(access_token or "").strip()
        if not token:
            raise ValueError("supabase_token_missing")
        if not self.supabase_url or not self.anon_key:
            raise RuntimeError("supabase_auth_not_configured")
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        now = time.monotonic()
        with self.lock:
            cached = self.cache.get(token_hash)
            if cached and cached[0] > now:
                return dict(cached[1])
            if cached:
                self.cache.pop(token_hash, None)
        try:
            response = requests.get(
                f"{self.supabase_url}/auth/v1/user",
                headers={
                    "Authorization": f"Bearer {token}",
                    "apikey": self.anon_key,
                },
                timeout=self.timeout_seconds,
            )
        except requests.RequestException as exc:
            raise RuntimeError("supabase_auth_unavailable") from exc
        if response.status_code in {401, 403}:
            raise ValueError("supabase_token_invalid")
        if not response.ok:
            raise RuntimeError(f"supabase_auth_failed_{response.status_code}")
        try:
            user = response.json()
        except ValueError as exc:
            raise RuntimeError("supabase_auth_response_invalid") from exc
        user_id = str(user.get("id") or "").strip()
        if not user_id:
            raise ValueError("supabase_user_missing")
        identity = {"id": user_id, "email": user.get("email")}
        with self.lock:
            self.cache[token_hash] = (now + self.cache_seconds, identity)
        return dict(identity)


class AITradingOrchestrator:
    def __init__(self, config: Optional[PipelineConfig] = None) -> None:
        self.config = config or PipelineConfig()
        self.storage = StorageService
        self.stock_agent: Optional[MultiStockAgentRunner] = None
        self.stock_agent_lock = Lock()
        self.order_placement_gate = OrderPlacementGate(
            DhanService(self.config),
            self.config.order_placement_state_path,
        )
        self.market_calendar = MarketCalendarService(self.config)
        self.released_session_key: Optional[str] = None
        self.last_request_id: Optional[str] = None
        self._boot_time_utc = datetime.now(timezone.utc)
        self.ws = WebSocketBroadcaster()
        self.event_state_path = self.config.agents_results_dir / "event-dispatch-state.json"
        self.event_decision_archive_path = (
            self.config.agents_results_dir / "event-decision-archive.ndjson"
        )
        self.event_state = self.storage.load_snapshot(self.event_state_path) or {"events": {}}
        self.event_lock = Lock()
        self.event_threads: set[Thread] = set()
        with self.event_lock:
            if self._compact_event_state_locked():
                self.storage.save_snapshot(self.event_state_path, self.event_state)
                release_unused_process_memory()
        websocket_signing_secret = (
            os.getenv("AI_TRADING_WS_SIGNING_SECRET", "").strip()
            or os.getenv("AI_TRADING_BACKEND_TOKEN", "").strip()
        )
        self.ws_ticket_validator = WebSocketTicketValidator(websocket_signing_secret)
        supabase_url = (
            os.getenv("SUPABASE_URL", "").strip()
            or os.getenv("NEXT_PUBLIC_SUPABASE_URL", "").strip()
        )
        supabase_anon_key = (
            os.getenv("SUPABASE_ANON_KEY", "").strip()
            or os.getenv("NEXT_PUBLIC_SUPABASE_ANON_KEY", "").strip()
        )
        self.supabase_user_verifier = SupabaseUserVerifier(
            supabase_url,
            supabase_anon_key,
            timeout_seconds=float(os.getenv("SUPABASE_AUTH_TIMEOUT_SECONDS", "5")),
            cache_seconds=int(os.getenv("SUPABASE_AUTH_CACHE_SECONDS", "30")),
        )
        self.ws_ticket_ttl_seconds = int(os.getenv("AI_TRADING_WS_TICKET_TTL_SECONDS", "45"))
        self.allowed_websocket_origins = {
            origin.strip().rstrip("/")
            for origin in os.getenv("AI_TRADING_ALLOWED_ORIGINS", "http://localhost:3000").split(",")
            if origin.strip()
        }

    @staticmethod
    def audit_event(
        event: str,
        *,
        request_id: str,
        user_id: str = "",
        detail: str = "",
    ) -> None:
        fields = [f"event={event}", f"request_id={request_id}"]
        if user_id:
            fields.append(f"user_id={user_id}")
        if detail:
            fields.append(f"detail={detail}")
        print("[AI Gateway] " + " ".join(fields), flush=True)

    def run_forever(self) -> None:
        print("=" * 60)
        print("AI TRADING ORCHESTRATOR")
        print("=" * 60)
        print("Continuous detector routing is active; no manual start request is required.")
        self._apply_market_lifecycle()
        self.order_placement_gate.start_periodic_verification(
            verify_now=True,
            on_verified=self._handle_order_placement_verification,
        )
        self._start_http_gateway()
        Thread(
            target=self._market_lifecycle_loop,
            name="ai-market-lifecycle",
            daemon=True,
        ).start()

        while True:
            try:
                time.sleep(2)
            except Exception as exc:  # pragma: no cover - runtime safety
                print(f"AI trading orchestrator error: {type(exc).__name__}: {exc}")
                self._save_status("failed", "orchestrator", error=str(exc))
                time.sleep(5)

    def _get_stock_agent(self) -> MultiStockAgentRunner:
        with self.stock_agent_lock:
            if self.stock_agent is None:
                runner = MultiStockAgentRunner(self.config)
                runner.order_placement_gate = self.order_placement_gate
                self.stock_agent = runner
            return self.stock_agent

    def _compact_event_state_locked(self) -> bool:
        raw_events = self.event_state.get("events") or {}
        if not isinstance(raw_events, dict):
            self.event_state = {"events": {}}
            return True

        compact_fields = (
            "status",
            "market_date",
            "accepted_at_utc",
            "started_at_utc",
            "finished_at_utc",
            "status_code",
            "reason",
            "error",
            "configured_user_count",
            "decision_archive",
            "decision_archive_error",
        )
        compact_events: Dict[str, Dict[str, Any]] = {}
        changed = False
        for event_id, raw_record in raw_events.items():
            if not isinstance(raw_record, dict):
                changed = True
                continue
            record = {
                field: raw_record[field]
                for field in compact_fields
                if raw_record.get(field) is not None
            }
            if raw_record.get("decision") is not None:
                try:
                    self._archive_event_decision(str(event_id), raw_record)
                    record["decision_archive"] = str(
                        self.event_decision_archive_path
                    )
                except Exception as exc:
                    record["decision"] = raw_record["decision"]
                    record["decision_archive_error"] = (
                        f"{type(exc).__name__}: {exc}"
                    )
            compact_events[str(event_id)] = record
            changed = changed or record != raw_record

        max_records = max(
            100,
            int(os.getenv("AI_TRADING_EVENT_STATE_MAX_RECORDS", "10000")),
        )
        if len(compact_events) > max_records:
            protected = {
                event_id: record
                for event_id, record in compact_events.items()
                if record.get("decision") is not None
            }
            ordered = sorted(
                (
                    item
                    for item in compact_events.items()
                    if item[0] not in protected
                ),
                key=lambda item: str(
                    item[1].get("finished_at_utc")
                    or item[1].get("started_at_utc")
                    or item[1].get("accepted_at_utc")
                    or ""
                ),
                reverse=True,
            )
            available_slots = max(0, max_records - len(protected))
            compact_events = {
                **protected,
                **dict(ordered[:available_slots]),
            }
            changed = True

        if changed:
            self.event_state = {"events": compact_events}
        return changed

    def _archive_event_decision(
        self,
        event_id: str,
        record: Dict[str, Any],
    ) -> None:
        self.storage.append_json_line(
            self.event_decision_archive_path,
            {
                "event_id": event_id,
                "status": record.get("status"),
                "market_date": record.get("market_date"),
                "accepted_at_utc": record.get("accepted_at_utc"),
                "started_at_utc": record.get("started_at_utc"),
                "finished_at_utc": record.get("finished_at_utc"),
                "decision": record.get("decision"),
                "error": record.get("error"),
            },
        )

    def _release_closed_market_memory(self, session_key: str) -> None:
        with self.stock_agent_lock:
            self.stock_agent = None
        with self.event_lock:
            changed = self._compact_event_state_locked()
            if changed:
                self.storage.save_snapshot(self.event_state_path, self.event_state)
        release_unused_process_memory()
        self.released_session_key = session_key
        print(
            f"[AI Gateway] market workers released; session={session_key}",
            flush=True,
        )

    def _apply_market_lifecycle(self) -> None:
        session = self.market_calendar.session_status()
        if session.is_market_hours:
            self.released_session_key = None
            return
        session_key = f"{session.market_date}:{session.reason}"
        if self.released_session_key != session_key:
            self._release_closed_market_memory(session_key)

    def _market_lifecycle_loop(self) -> None:
        while True:
            try:
                self._apply_market_lifecycle()
            except Exception as exc:
                print(
                    f"[AI Gateway] market lifecycle check failed: "
                    f"{type(exc).__name__}: {exc}",
                    flush=True,
                )
            time.sleep(60)

    def _handle_order_placement_verification(self, state: OrderPlacementState) -> None:
        """Restore users disabled by the retired DH-905 guard after Dhan verifies recovery."""
        if not state.allowed:
            return
        trading_state = AITradingStateService.load_state(self.config.ai_trading_state_path)
        for user_id, entry in (trading_state.get("user_states") or {}).items():
            if not isinstance(entry, dict):
                continue
            if entry.get("enabled") or entry.get("status_code") != DH905_INVALID_IP:
                continue
            trade_mode = str(entry.get("trade_mode") or "auto").lower()
            AITradingStateService.set_user_state(
                self.config.ai_trading_state_path,
                str(user_id),
                True,
                {
                    "status_code": "manual_amount" if trade_mode == "manual" else "automatic_balance",
                },
            )
            print(
                f"[Order Gate] restored AI trading for user {user_id} after successful verification.",
                flush=True,
            )

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
            # Regime analysis is deprecated. Keep the response field for older
            # clients, but never allow a request to re-enable the retired lane.
            "regime_analysis_enabled": False,
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
        expires_at = event.get("expires_at")
        if expires_at:
            try:
                expiry = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
                if expiry.tzinfo is None:
                    expiry = expiry.replace(tzinfo=timezone.utc)
            except (TypeError, ValueError) as exc:
                raise ValueError("invalid_intra_finder_event_expiry") from exc
            if datetime.now(timezone.utc) >= expiry.astimezone(timezone.utc):
                return self._block_intra_finder_event(
                    event_id,
                    "EVENT_EXPIRED",
                    "Event expired before agent admission.",
                )
        gate = getattr(self, "order_placement_gate", None)
        if gate is not None:
            order_state = gate.refresh_from_store()
            if not order_state.allowed:
                with self.event_lock:
                    self.event_state.setdefault("events", {})[event_id] = {
                        "status": "blocked",
                        "accepted_at_utc": datetime.now(timezone.utc).isoformat(),
                        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
                        "status_code": order_state.status_code,
                        "reason": order_state.reason,
                    }
                    self.storage.save_snapshot(self.event_state_path, self.event_state)
                return {
                    "accepted": False,
                    "duplicate": False,
                    "blocked": True,
                    "event_id": event_id,
                    "status_code": order_state.status_code,
                }
            load_slots = getattr(gate, "current_active_trade_slots", None)
            if callable(load_slots):
                active_slots = load_slots()
                if active_slots is None:
                    return self._block_intra_finder_event(
                        event_id,
                        "TRADE_CAPACITY_UNAVAILABLE",
                        "Broker positions and active orders could not be verified.",
                    )
                if len(active_slots) >= self.config.stock_agent_max_concurrent_trades:
                    return self._block_intra_finder_event(
                        event_id,
                        "MAX_ACTIVE_TRADES",
                        "The configured live trade slots are occupied.",
                        active_trade_count=len(active_slots),
                    )
        with self.event_lock:
            existing = (self.event_state.get("events") or {}).get(event_id)
            if existing:
                return {"accepted": False, "duplicate": True, "event_id": event_id}
            self.event_state.setdefault("events", {})[event_id] = {
                "status": "starting",
                "market_date": str(event["market_date"]),
                "accepted_at_utc": datetime.now(timezone.utc).isoformat(),
            }
            try:
                self.storage.save_snapshot(self.event_state_path, self.event_state)
            except Exception:
                self.event_state.setdefault("events", {}).pop(event_id, None)
                raise
        thread = Thread(
            target=self._run_intra_finder_event_thread,
            args=(dict(event),),
            name=f"stock-agent-{event_id[:12]}",
            daemon=True,
        )
        with self.event_lock:
            self.event_threads = {
                thread
                for thread in getattr(self, "event_threads", set())
                if getattr(thread, "is_alive", lambda: False)()
            }
            configured_limit = int(
                getattr(getattr(self, "config", None), "stock_agent_max_concurrent_trades", 3)
            )
            if len(self.event_threads) >= configured_limit:
                self.event_state.setdefault("events", {})[event_id].update(
                    {
                        "status": "blocked",
                        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
                        "status_code": "AGENT_CAPACITY",
                        "reason": "The three live trade-analysis slots are occupied.",
                    }
                )
                self.storage.save_snapshot(self.event_state_path, self.event_state)
                return {
                    "accepted": False,
                    "duplicate": False,
                    "blocked": True,
                    "event_id": event_id,
                    "status_code": "AGENT_CAPACITY",
                }
            self.event_threads.add(thread)
        try:
            thread.start()
        except Exception as exc:
            with self.event_lock:
                self.event_threads.discard(thread)
                existing = dict((self.event_state.get("events") or {}).get(event_id) or {})
                existing.update(
                    {
                        "status": "failed",
                        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
                        "error": f"agent_thread_start_failed:{type(exc).__name__}",
                    }
                )
                self.event_state.setdefault("events", {})[event_id] = existing
                self.storage.save_snapshot(self.event_state_path, self.event_state)
            raise
        return {
            "accepted": True,
            "duplicate": False,
            "event_id": event_id,
        }

    def _block_intra_finder_event(
        self,
        event_id: str,
        status_code: str,
        reason: str,
        **details: Any,
    ) -> Dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        with self.event_lock:
            self.event_state.setdefault("events", {})[event_id] = {
                "status": "blocked",
                "accepted_at_utc": now,
                "finished_at_utc": now,
                "status_code": status_code,
                "reason": reason,
                **details,
            }
            self.storage.save_snapshot(self.event_state_path, self.event_state)
        return {
            "accepted": False,
            "duplicate": False,
            "blocked": True,
            "event_id": event_id,
            "status_code": status_code,
            **details,
        }

    def _run_intra_finder_event_thread(self, event: Dict[str, Any]) -> None:
        try:
            self._run_intra_finder_event(event)
        finally:
            with self.event_lock:
                self.event_threads.discard(current_thread())

    def save_user_config(self, request: Dict[str, Any]) -> Dict[str, Any]:
        user_id = str(request.get("user_id") or "").strip()
        raw_amount = request.get("trade_amount")
        amount = TradingAmountService.parse(raw_amount)
        trade_mode = "auto" if raw_amount in (None, "") else "manual"
        if not user_id:
            raise ValueError("user_id_required")
        if trade_mode == "manual" and amount is None:
            raise ValueError("trade_amount_must_be_a_positive_finite_number")
        now = datetime.now(timezone.utc).isoformat()
        state = AITradingStateService.set_user_state(
            self.config.ai_trading_state_path,
            user_id,
            True,
            {
                "email": request.get("email"),
                "trade_mode": trade_mode,
                "trade_amount": amount,
                "amount_updated_at_utc": now,
                "status_code": "automatic_balance" if trade_mode == "auto" else "manual_amount",
            },
        )
        return {"user_id": user_id, "trade_mode": trade_mode, "trade_amount": amount, "amount_updated_at_utc": now, "enabled": True, "generated_at_utc": state.get("generated_at_utc")}

    def set_user_enabled(self, request: Dict[str, Any]) -> Dict[str, Any]:
        user_id = str(request.get("user_id") or "").strip()
        if not user_id:
            raise ValueError("user_id_required")
        enabled = bool(request.get("enabled"))
        previous_state = AITradingStateService.load_state(self.config.ai_trading_state_path)
        previous_user_states = previous_state.get("user_states")
        previous_entry = (
            previous_user_states.get(user_id, {})
            if isinstance(previous_user_states, dict)
            else {}
        )
        previous_enabled = bool(
            previous_entry.get("enabled") if isinstance(previous_entry, dict) else False
        )
        state = AITradingStateService.set_user_state(
            self.config.ai_trading_state_path,
            user_id,
            enabled,
            {"email": request.get("email")},
        )
        start_request = self.submit_start_request(request) if enabled else None
        return {
            "user_id": user_id,
            "enabled": enabled,
            "previous_enabled": previous_enabled,
            "enabled_user_ids": state.get("enabled_user_ids", []),
            "request": start_request,
        }

    def load_user_config(self, user_id: str) -> Dict[str, Any]:
        entry = (AITradingStateService.load_state(self.config.ai_trading_state_path).get("user_states") or {}).get(user_id) or {}
        max_age = float(os.getenv("TRADING_AMOUNT_MAX_AGE_SECONDS", str(30 * 24 * 60 * 60)))
        status = TradingAmountService.status(entry, max_age_seconds=max_age)
        return {"user_id": user_id, "trade_mode": status.get("trade_mode"), "trade_amount": entry.get("trade_amount"), "amount_updated_at_utc": entry.get("amount_updated_at_utc"), "enabled": bool(entry.get("enabled")), **status}

    def _run_intra_finder_event(self, event: Dict[str, Any]) -> None:
        event_id = str(event["event_id"])
        gate = getattr(self, "order_placement_gate", None)
        if gate is not None and not gate.allowed:
            with self.event_lock:
                existing = dict((self.event_state.get("events") or {}).get(event_id) or {})
                existing.update(
                    {
                        "status": "blocked",
                        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
                        "status_code": gate.state.status_code,
                        "reason": gate.state.reason,
                    }
                )
                self.event_state.setdefault("events", {})[event_id] = existing
                self.storage.save_snapshot(self.event_state_path, self.event_state)
            return
        started_at = datetime.now(timezone.utc)
        with self.event_lock:
            existing = dict((self.event_state.get("events") or {}).get(event_id) or {})
            existing.update(
                {
                    "status": "started",
                    "started_at_utc": started_at.isoformat(),
                }
            )
            self.event_state.setdefault("events", {})[event_id] = existing
            self.storage.save_snapshot(self.event_state_path, self.event_state)
        users: list[Dict[str, Any]] = []
        user_results: list[Dict[str, Any]] = []
        try:
            stock_agent = self._get_stock_agent()
            max_age = float(os.getenv("TRADING_AMOUNT_MAX_AGE_SECONDS", str(30 * 24 * 60 * 60)))
            users = AITradingStateService.configured_users(self.config.ai_trading_state_path, max_age_seconds=max_age)
            for user in users:
                if gate is not None and not gate.allowed:
                    break
                user_id = str(user.get("user_id") or "").strip()
                if not user_id:
                    continue
                self._broadcast_event(
                    {
                        "type": "intra_finder_event_accepted",
                        "event": event,
                        "request_id": event_id,
                    },
                    user_id=user_id,
                )
                resolved = stock_agent.resolve_user_trade_config(user)
                if not resolved.get("eligible"):
                    user_results.append(resolved)
                    continue
                routed = stock_agent.prepare_user_event(event, resolved)
                if not routed.get("eligible"):
                    user_results.append(routed)
                    continue
                result = stock_agent.run_event(
                    routed["event"],
                    user_id=user_id,
                    trade_config={
                        "trade_mode": resolved["trade_mode"],
                        "trade_amount": resolved["trade_amount"],
                        "amount_source": resolved["amount_source"],
                        "account_margin_capacity": resolved.get("account_margin_capacity"),
                        "max_concurrent_trades": resolved["max_concurrent_trades"],
                        "regime_analysis_enabled": False,
                    },
                    event_callback=lambda payload, scoped_user_id=user_id: self._broadcast_event(
                        {**payload, "request_id": event_id},
                        user_id=scoped_user_id,
                    ),
                )
                user_results.append({"user_id": user_id, "eligible": True, "result": result})
            status = "completed"
            error = None
        except Exception as exc:
            status = "failed"
            error = f"{type(exc).__name__}: {exc}"
        with self.event_lock:
            existing = dict((self.event_state.get("events") or {}).get(event_id) or {})
            archive_error = None
            try:
                self._archive_event_decision(
                    event_id,
                    {
                        **existing,
                        "status": status,
                        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
                        "decision": {
                            "user_results": user_results,
                            "configured_user_count": len(users),
                        },
                        "error": error,
                    },
                )
            except Exception as exc:
                archive_error = f"{type(exc).__name__}: {exc}"
            existing.update({
                "status": status,
                "finished_at_utc": datetime.now(timezone.utc).isoformat(),
                "configured_user_count": len(users),
                "decision_archive": str(self.event_decision_archive_path),
                "error": error,
            })
            if archive_error:
                existing["decision"] = {
                    "user_results": user_results,
                    "configured_user_count": len(users),
                }
                existing["decision_archive_error"] = archive_error
            self.event_state.setdefault("events", {})[event_id] = existing
            self.storage.save_snapshot(self.event_state_path, self.event_state)
        result_by_user = {
            str(result.get("user_id") or ""): result
            for result in user_results
            if isinstance(result, dict) and result.get("user_id")
        }
        for user in users:
            user_id = str(user.get("user_id") or "").strip()
            if not user_id:
                continue
            self._broadcast_event(
                {
                    "type": "intra_finder_event_finished",
                    "event_id": event_id,
                    "request_id": event_id,
                    "status": status,
                    "decision": result_by_user.get(user_id),
                    "error": error,
                },
                user_id=user_id,
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

    def load_run_status_for_user(self, user_id: str) -> Dict[str, Any]:
        status = self.load_run_status()
        request = status.get("request") if isinstance(status.get("request"), dict) else {}
        status_user_id = str(request.get("user_id") or "").strip()
        if status_user_id and status_user_id == user_id:
            return status
        return {
            "status": "idle",
            "current_stage": "idle",
            "message": None,
            "updated_at_utc": status.get("updated_at_utc"),
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
        auth_token = os.getenv("AI_TRADING_BACKEND_TOKEN", "").strip()
        if not auth_token or auth_token.startswith("replace_with_"):
            raise RuntimeError(
                "AI_TRADING_BACKEND_TOKEN is required; refusing to start the public AI trading gateway."
            )
        if (
            len(orchestrator.ws_ticket_validator.secret) < 32
            or orchestrator.ws_ticket_validator.secret.startswith(b"replace_with_")
        ):
            raise RuntimeError(
                "The WebSocket signing key must contain at least 32 characters. "
                "Set a strong AI_TRADING_BACKEND_TOKEN or override it with "
                "AI_TRADING_WS_SIGNING_SECRET."
            )
        if not orchestrator.allowed_websocket_origins:
            raise RuntimeError("AI_TRADING_ALLOWED_ORIGINS must contain at least one trusted origin.")
        if (
            not orchestrator.supabase_user_verifier.supabase_url
            or not orchestrator.supabase_user_verifier.anon_key
        ):
            raise RuntimeError(
                "SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY are required "
                "to authenticate public AI trading requests."
            )

        class AITradingGatewayHandler(BaseHTTPRequestHandler):
            def _request_id(self) -> str:
                existing = getattr(self, "_gateway_request_id", "")
                if existing:
                    return existing
                supplied = self.headers.get("x-request-id", "").strip()
                if not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", supplied):
                    supplied = str(uuid.uuid4())
                self._gateway_request_id = supplied
                return supplied

            def _bearer_token(self) -> str:
                header = self.headers.get("authorization", "").strip()
                if not header.lower().startswith("bearer "):
                    return ""
                return header[7:].strip()

            def _internal_authorized(self, token: str) -> bool:
                return bool(token) and hmac.compare_digest(token, auth_token)

            def _authenticate(self, *, allow_internal: bool) -> Optional[Dict[str, Any]]:
                request_id = self._request_id()
                token = self._bearer_token()
                if allow_internal and self._internal_authorized(token):
                    orchestrator.audit_event(
                        "auth_success",
                        request_id=request_id,
                        detail="internal_service",
                    )
                    return {"kind": "internal"}
                try:
                    user = orchestrator.supabase_user_verifier.verify(token)
                except ValueError as exc:
                    orchestrator.audit_event(
                        "auth_denied",
                        request_id=request_id,
                        detail=str(exc),
                    )
                    self._json_response({"error": "unauthorized"}, status=401)
                    return None
                except RuntimeError as exc:
                    orchestrator.audit_event(
                        "auth_unavailable",
                        request_id=request_id,
                        detail=str(exc),
                    )
                    self._json_response({"error": "authentication_unavailable"}, status=503)
                    return None
                user_id = str(user["id"])
                orchestrator.audit_event(
                    "auth_success",
                    request_id=request_id,
                    user_id=user_id,
                    detail="supabase_user",
                )
                return {"kind": "user", "user": user}

            def _json_response(self, payload: Dict[str, Any], status: int = 200) -> None:
                body = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(body)))
                self.send_header("cache-control", "no-store")
                self.send_header("x-content-type-options", "nosniff")
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
                    parsed = urlparse(self.path)
                    if parsed.path == "/health":
                        self._json_response({"status": "ok"})
                        return
                    if parsed.path == "/ai-trading/stream":
                        self._websocket_stream(parsed)
                        return
                    if parsed.path not in {"/ai-trading/config", "/ai-trading/status"}:
                        self._json_response({"error": "not_found"}, status=404)
                        return
                    request_id = self._request_id()
                    orchestrator.audit_event(
                        "request_received",
                        request_id=request_id,
                        detail=f"GET {parsed.path}",
                    )
                    identity = self._authenticate(allow_internal=True)
                    if not identity:
                        return
                    if identity["kind"] == "user":
                        user_id = str(identity["user"]["id"])
                    else:
                        user_id = (parse_qs(parsed.query).get("user_id") or [""])[0]
                        if not user_id:
                            self._json_response({"error": "user_id_required"}, status=400)
                            return
                    if parsed.path == "/ai-trading/config":
                        self._json_response(orchestrator.load_user_config(user_id))
                        orchestrator.audit_event(
                            "request_completed",
                            request_id=request_id,
                            user_id=user_id,
                            detail="GET /ai-trading/config status=200",
                        )
                        return
                    self._json_response(orchestrator.load_run_status_for_user(user_id))
                    orchestrator.audit_event(
                        "request_completed",
                        request_id=request_id,
                        user_id=user_id,
                        detail="GET /ai-trading/status status=200",
                    )
                except Exception as exc:
                    self._json_response({"error": f"status_handler_error: {type(exc).__name__}: {exc}"}, status=500)

            def do_POST(self) -> None:
                try:
                    path = urlparse(self.path).path
                    if path not in {
                        "/ai-trading/event",
                        "/ai-trading/config",
                        "/ai-trading/start",
                        "/ai-trading/toggle",
                        "/ai-trading/ws-ticket",
                    }:
                        self._json_response({"error": "not_found"}, status=404)
                        return
                    request_id = self._request_id()
                    orchestrator.audit_event(
                        "request_received",
                        request_id=request_id,
                        detail=f"POST {path}",
                    )
                    identity = self._authenticate(allow_internal=path != "/ai-trading/ws-ticket")
                    if not identity:
                        return
                    if path == "/ai-trading/event":
                        if identity["kind"] != "internal":
                            orchestrator.audit_event(
                                "request_denied",
                                request_id=request_id,
                                user_id=str(identity["user"]["id"]),
                                detail="internal_endpoint",
                            )
                            self._json_response({"error": "forbidden"}, status=403)
                            return
                        result = orchestrator.submit_intra_finder_event(self._read_body())
                        self._json_response(
                            {"ok": bool(result["accepted"]), **result},
                            status=202 if result["accepted"] else 200,
                        )
                        return
                    if path == "/ai-trading/ws-ticket":
                        user_id = str(identity["user"]["id"])
                        ticket = orchestrator.ws_ticket_validator.issue(
                            user_id,
                            orchestrator.ws_ticket_ttl_seconds,
                        )
                        self._json_response(ticket)
                        orchestrator.audit_event(
                            "websocket_ticket_issued",
                            request_id=request_id,
                            user_id=user_id,
                        )
                        return
                    payload = self._read_body()
                    if identity["kind"] == "user":
                        user = identity["user"]
                        payload["user_id"] = str(user["id"])
                        payload["email"] = user.get("email")
                    user_id = str(payload.get("user_id") or "")
                    if not user_id:
                        self._json_response({"error": "user_id_required"}, status=400)
                        return
                    if path == "/ai-trading/config":
                        result = orchestrator.save_user_config(payload)
                        self._json_response({"ok": True, "config": result})
                        orchestrator.audit_event(
                            "request_completed",
                            request_id=request_id,
                            user_id=user_id,
                            detail="POST /ai-trading/config status=200",
                        )
                        return
                    if path == "/ai-trading/toggle":
                        result = orchestrator.set_user_enabled(payload)
                        self._json_response({"ok": True, **result})
                        orchestrator.audit_event(
                            "request_completed",
                            request_id=request_id,
                            user_id=user_id,
                            detail="POST /ai-trading/toggle status=200",
                        )
                        return
                    request_payload = orchestrator.submit_start_request(payload)
                    self._json_response({"ok": True, "request": request_payload})
                    orchestrator.audit_event(
                        "request_completed",
                        request_id=request_id,
                        user_id=user_id,
                        detail="POST /ai-trading/start status=200",
                    )
                except Exception as exc:
                    self._json_response({"error": f"start_handler_error: {type(exc).__name__}: {exc}"}, status=500)

            def log_message(self, format: str, *args: Any) -> None:
                return

            def _websocket_stream(self, parsed) -> None:
                if self.headers.get("Upgrade", "").lower() != "websocket":
                    self._json_response({"error": "upgrade_required"}, status=426)
                    return
                origin = self.headers.get("Origin", "").strip().rstrip("/")
                if origin not in orchestrator.allowed_websocket_origins:
                    orchestrator.audit_event(
                        "client_connection_denied",
                        request_id=self._request_id(),
                        detail="origin_forbidden",
                    )
                    self._json_response({"error": "websocket_origin_forbidden"}, status=403)
                    return
                ticket = (parse_qs(parsed.query).get("ticket") or [""])[0]
                try:
                    claims = orchestrator.ws_ticket_validator.validate(ticket)
                except ValueError as exc:
                    orchestrator.audit_event(
                        "client_connection_denied",
                        request_id=self._request_id(),
                        detail=str(exc),
                    )
                    self._json_response({"error": str(exc)}, status=401)
                    return
                user_id = str(claims["sub"])
                if not orchestrator.ws.accept(self, user_id):
                    self._json_response({"error": "bad_websocket_handshake"}, status=400)
                    return
                client = self.request
                orchestrator.audit_event(
                    "client_connected",
                    request_id=self._request_id(),
                    user_id=user_id,
                    detail="websocket",
                )
                orchestrator.ws.send_one(
                    client,
                    {
                        "type": "status_snapshot",
                        "status": orchestrator.load_run_status_for_user(user_id),
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
                    orchestrator.audit_event(
                        "client_disconnected",
                        request_id=self._request_id(),
                        user_id=user_id,
                        detail="websocket",
                    )

        return AITradingGatewayHandler

    def _run_request(self, request: Dict[str, Any]) -> None:
        self.last_request_id = str(request.get("request_id"))
        user_id = str(request.get("user_id") or "")
        trade_mode = str(request.get("trade_mode") or "auto").strip().lower()
        trade_amount = request.get("trade_amount")
        regime_analysis_enabled = False

        if not OrderPlacementStateService.is_allowed(self.config.order_placement_state_path):
            self._save_status("blocked", "requested", request, "Dhan order placement is blocked.")
            return
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
        user_id = str((request or {}).get("user_id") or "").strip()
        self._broadcast_event(
            {
                "type": "status_update",
                "status": payload,
                "request_id": str((request or {}).get("request_id") or ""),
            },
            user_id=user_id,
        )

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

    def _broadcast_event(self, event: Dict[str, Any], user_id: str) -> None:
        if not user_id:
            return
        payload = dict(event)
        payload["user_id"] = user_id
        payload.setdefault("sent_at_utc", datetime.now(timezone.utc).isoformat())
        self.ws.broadcast(payload, user_id)


def main() -> None:
    AITradingOrchestrator().run_forever()


if __name__ == "__main__":
    main()
