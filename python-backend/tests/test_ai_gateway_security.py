from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import sys
import time
import types
import unittest
from unittest.mock import patch

if "dhanhq" not in sys.modules:
    fake_dhan = types.ModuleType("dhanhq")
    fake_dhan.MarketFeed = type("MarketFeed", (), {})
    fake_dhan.DhanContext = type("DhanContext", (), {})
    fake_dhan.HistoricalData = type("HistoricalData", (), {})
    fake_dhan.OptionChain = type("OptionChain", (), {})
    fake_dhan.FullDepth = type("FullDepth", (), {})
    fake_dhan.dhanhq = type("dhanhq", (), {})
    sys.modules["dhanhq"] = fake_dhan

from pipeline.runtime.run_ai_trading_orchestrator import (
    AITradingOrchestrator,
    WebSocketBroadcaster,
    WebSocketTicketValidator,
)


def _encode(value: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(value, separators=(",", ":")).encode()).decode().rstrip("=")


def _ticket(secret: str, *, user_id: str = "user-1", ticket_id: str = "ticket-1", lifetime: int = 45) -> str:
    now = int(time.time())
    header = _encode({"alg": "HS256", "typ": "JWT"})
    payload = _encode(
        {
            "iss": "polycognition-web",
            "aud": "ai-trading-websocket",
            "sub": user_id,
            "iat": now,
            "exp": now + lifetime,
            "jti": ticket_id,
        }
    )
    signing_input = f"{header}.{payload}"
    signature = base64.urlsafe_b64encode(
        hmac.new(secret.encode(), signing_input.encode("ascii"), hashlib.sha256).digest()
    ).decode().rstrip("=")
    return f"{signing_input}.{signature}"


class _FakeSocket:
    def __init__(self) -> None:
        self.frames: list[bytes] = []
        self.closed = False

    def sendall(self, frame: bytes) -> None:
        self.frames.append(frame)

    def close(self) -> None:
        self.closed = True


class AIGatewaySecurityTests(unittest.TestCase):
    def test_valid_ticket_is_user_scoped_and_one_time(self) -> None:
        validator = WebSocketTicketValidator("s" * 32)
        token = _ticket("s" * 32)
        claims = validator.validate(token)
        self.assertEqual(claims["sub"], "user-1")
        with self.assertRaisesRegex(ValueError, "replayed"):
            validator.validate(token)

    def test_tampered_ticket_is_rejected(self) -> None:
        validator = WebSocketTicketValidator("s" * 32)
        token = _ticket("s" * 32)
        header, payload, signature = token.split(".")
        tampered_payload = _encode(
            {
                "iss": "polycognition-web",
                "aud": "ai-trading-websocket",
                "sub": "other-user",
                "iat": int(time.time()),
                "exp": int(time.time()) + 45,
                "jti": "ticket-2",
            }
        )
        with self.assertRaisesRegex(ValueError, "signature"):
            validator.validate(f"{header}.{tampered_payload}.{signature}")

    def test_broadcast_reaches_only_matching_user(self) -> None:
        broadcaster = WebSocketBroadcaster()
        first = _FakeSocket()
        second = _FakeSocket()
        broadcaster.clients = {first: "user-1", second: "user-2"}  # type: ignore[dict-item]
        broadcaster.broadcast({"type": "private-event"}, "user-1")
        self.assertEqual(len(first.frames), 1)
        self.assertEqual(second.frames, [])

    def test_gateway_refuses_to_start_without_service_token(self) -> None:
        orchestrator = AITradingOrchestrator.__new__(AITradingOrchestrator)
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "AI_TRADING_BACKEND_TOKEN"):
                orchestrator._handler_class()


if __name__ == "__main__":
    unittest.main()
