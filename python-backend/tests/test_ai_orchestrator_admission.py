from __future__ import annotations

import unittest
from concurrent.futures import Future
from datetime import datetime, timedelta, timezone
from threading import BoundedSemaphore, Lock
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


class _Storage:
    @staticmethod
    def save_snapshot(_path, _payload):
        return None


class _HoldingExecutor:
    def __init__(self) -> None:
        self.futures = []

    def submit(self, _fn, _event):
        future = Future()
        self.futures.append(future)
        return future


def _event(event_id: str, *, created_at: str | None = None):
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
        "created_at": created_at or datetime.now(timezone.utc).isoformat(),
    }


class AIOrchestratorAdmissionTests(unittest.TestCase):
    def orchestrator(self):
        orchestrator = AITradingOrchestrator.__new__(AITradingOrchestrator)
        orchestrator.storage = _Storage
        orchestrator.event_state_path = "unused.json"
        orchestrator.event_state = {"events": {}}
        orchestrator.event_lock = Lock()
        orchestrator.event_capacity = BoundedSemaphore(1)
        orchestrator.event_executor = _HoldingExecutor()
        orchestrator._broadcast_event = lambda _payload: None
        return orchestrator

    def test_full_queue_rejects_instead_of_building_unbounded_backlog(self) -> None:
        orchestrator = self.orchestrator()
        first = orchestrator.submit_intra_finder_event(_event("first"))
        second = orchestrator.submit_intra_finder_event(_event("second"))
        self.assertTrue(first["accepted"])
        self.assertFalse(second["accepted"])
        self.assertTrue(second["queue_full"])
        self.assertNotIn("second", orchestrator.event_state["events"])

    def test_expired_event_is_not_sent_to_stock_agent(self) -> None:
        orchestrator = self.orchestrator()
        orchestrator.event_max_age_seconds = 300
        orchestrator.event_state["events"]["old"] = {"status": "queued"}
        orchestrator._run_intra_finder_event(
            _event(
                "old",
                created_at=(datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat(),
            )
        )
        self.assertEqual(orchestrator.event_state["events"]["old"]["status"], "expired")
        self.assertIn("event_expired_before_agent_start", orchestrator.event_state["events"]["old"]["error"])


if __name__ == "__main__":
    unittest.main()
