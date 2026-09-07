from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock
from unittest.mock import patch
import sys
import types

if "dhanhq" not in sys.modules:
    fake_dhan = types.ModuleType("dhanhq")
    fake_dhan.MarketFeed = type("MarketFeed", (), {})
    fake_dhan.DhanContext = type("DhanContext", (), {})
    fake_dhan.HistoricalData = type("HistoricalData", (), {})
    fake_dhan.OptionChain = type("OptionChain", (), {})
    fake_dhan.FullDepth = type("FullDepth", (), {})
    fake_dhan.dhanhq = type("dhanhq", (), {})
    sys.modules["dhanhq"] = fake_dhan

from pipeline.runtime.run_ai_trading_orchestrator import AITradingOrchestrator
from pipeline.services.ai_trading_state_service import AITradingStateService
from pipeline.services.convex_service import ConvexService
from pipeline.services.order_placement_gate import OrderPlacementState


class _Storage:
    @staticmethod
    def save_snapshot(_path, _payload):
        return None


class _ImmediateThread:
    names: list[str] = []

    def __init__(self, *, target, args=(), name=None, daemon=None) -> None:
        self.target = target
        self.args = args
        self.name = name
        self.daemon = daemon

    def start(self) -> None:
        self.names.append(self.name)
        self.target(*self.args)


class _AliveThread:
    @staticmethod
    def is_alive() -> bool:
        return True


def _event(event_id: str):
    return {
        "event_id": event_id,
        "market_date": "2026-08-10",
        "universe_version": "test",
        "isin": "INE1",
        "exchange_segment": "NSE_EQ",
        "security_id": 1,
        "symbol": "TEST",
        "direction": "LONG",
        "setup_type": "INDICATOR_EVENT",
        "setup_score": 80.0,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


class AIOrchestratorAdmissionTests(unittest.TestCase):
    def orchestrator(self):
        orchestrator = AITradingOrchestrator.__new__(AITradingOrchestrator)
        orchestrator.storage = _Storage
        orchestrator.event_state_path = "unused.json"
        orchestrator.event_state = {"events": {}}
        orchestrator.event_lock = Lock()
        orchestrator._broadcast_event = lambda _payload: None
        return orchestrator

    def setUp(self) -> None:
        _ImmediateThread.names = []

    def test_every_distinct_signal_starts_an_agent_immediately(self) -> None:
        orchestrator = self.orchestrator()
        started: list[str] = []
        orchestrator._run_intra_finder_event = lambda event: started.append(event["event_id"])

        with patch(
            "pipeline.runtime.run_ai_trading_orchestrator.Thread",
            _ImmediateThread,
        ):
            first = orchestrator.submit_intra_finder_event(_event("first"))
            second = orchestrator.submit_intra_finder_event(_event("second"))

        self.assertTrue(first["accepted"])
        self.assertTrue(second["accepted"])
        self.assertEqual(started, ["first", "second"])
        self.assertEqual(len(_ImmediateThread.names), 2)
        self.assertNotIn("queue_full", first)
        self.assertNotIn("queue_full", second)

    def test_duplicate_event_is_suppressed_without_starting_another_agent(self) -> None:
        orchestrator = self.orchestrator()
        started: list[str] = []
        orchestrator._run_intra_finder_event = lambda event: started.append(event["event_id"])

        with patch(
            "pipeline.runtime.run_ai_trading_orchestrator.Thread",
            _ImmediateThread,
        ):
            first = orchestrator.submit_intra_finder_event(_event("same"))
            duplicate = orchestrator.submit_intra_finder_event(_event("same"))

        self.assertTrue(first["accepted"])
        self.assertFalse(duplicate["accepted"])
        self.assertTrue(duplicate["duplicate"])
        self.assertEqual(started, ["same"])
        self.assertEqual(len(_ImmediateThread.names), 1)

    def test_blocked_order_placement_does_not_start_agent_thread(self) -> None:
        orchestrator = self.orchestrator()
        blocked_state = types.SimpleNamespace(
            allowed=False,
            status_code="DH-905_INVALID_IP",
            reason="dhan_rejected_order_source_ip",
        )
        orchestrator.order_placement_gate = types.SimpleNamespace(
            refresh_from_store=lambda: blocked_state,
        )

        result = orchestrator.submit_intra_finder_event(_event("blocked"))

        self.assertFalse(result["accepted"])
        self.assertTrue(result["blocked"])
        self.assertEqual(result["status_code"], "DH-905_INVALID_IP")
        self.assertEqual(_ImmediateThread.names, [])

    def test_expired_event_never_starts_agent(self) -> None:
        orchestrator = self.orchestrator()
        event = _event("expired")
        event["expires_at"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()

        result = orchestrator.submit_intra_finder_event(event)

        self.assertFalse(result["accepted"])
        self.assertTrue(result["blocked"])
        self.assertEqual(result["status_code"], "EVENT_EXPIRED")
        self.assertEqual(_ImmediateThread.names, [])

    def test_fourth_concurrent_event_is_not_queued(self) -> None:
        orchestrator = self.orchestrator()
        orchestrator.config = types.SimpleNamespace(stock_agent_max_concurrent_events=3)
        orchestrator.event_threads = {_AliveThread(), _AliveThread(), _AliveThread()}

        result = orchestrator.submit_intra_finder_event(_event("fourth"))

        self.assertFalse(result["accepted"])
        self.assertTrue(result["blocked"])
        self.assertEqual(result["status_code"], "AGENT_CAPACITY")

    def test_shared_account_capacity_does_not_block_other_users(self) -> None:
        orchestrator = self.orchestrator()
        orchestrator.order_placement_gate = types.SimpleNamespace(
            refresh_from_store=lambda: types.SimpleNamespace(allowed=True),
            current_active_trade_slots=lambda: {"1", "2", "3"},
        )
        orchestrator._run_intra_finder_event = lambda event: None
        with patch("pipeline.runtime.run_ai_trading_orchestrator.Thread", _ImmediateThread):
            result = orchestrator.submit_intra_finder_event(_event("slots-full"))
        self.assertTrue(result["accepted"])

    def test_successful_verification_restores_user_disabled_by_old_guard(self) -> None:
        with (
            TemporaryDirectory() as directory,
            patch.object(ConvexService, "configured", return_value=False),
            patch.object(ConvexService, "required", return_value=False),
        ):
            state_path = Path(directory) / "ai-state.json"
            AITradingStateService.set_user_state(
                state_path,
                "user-1",
                False,
                {"trade_mode": "auto", "status_code": "DH-905_INVALID_IP"},
            )
            orchestrator = AITradingOrchestrator.__new__(AITradingOrchestrator)
            orchestrator.config = types.SimpleNamespace(ai_trading_state_path=state_path)
            verified = OrderPlacementState(
                allowed=True,
                status_code="ORDER_PLACEMENT_ALLOWED",
                reason="dhan_order_placement_verified",
                verified_at=datetime.now(timezone.utc).isoformat(),
                next_verification_at=datetime.now(timezone.utc).isoformat(),
                detected_ip="1.2.3.4",
                primary_ip="1.2.3.4",
                orders_allowed=True,
            )

            orchestrator._handle_order_placement_verification(verified)

            restored = AITradingStateService.load_state(state_path)
            self.assertTrue(restored["user_states"]["user-1"]["enabled"])
            self.assertEqual(
                restored["user_states"]["user-1"]["status_code"],
                "automatic_balance",
            )


if __name__ == "__main__":
    unittest.main()
