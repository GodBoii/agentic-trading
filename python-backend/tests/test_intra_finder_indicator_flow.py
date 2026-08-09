from __future__ import annotations

import unittest
from datetime import datetime, timedelta
import sys
import types

if "dhanhq" not in sys.modules:
    fake_dhan = types.ModuleType("dhanhq")
    fake_dhan.MarketFeed = type(
        "MarketFeed", (), {"NSE": "NSE", "BSE": "BSE", "Full": "Full"}
    )
    fake_dhan.DhanContext = type("DhanContext", (), {})
    fake_dhan.HistoricalData = type("HistoricalData", (), {})
    fake_dhan.OptionChain = type("OptionChain", (), {})
    fake_dhan.FullDepth = type("FullDepth", (), {})
    fake_dhan.dhanhq = type("dhanhq", (), {})
    sys.modules["dhanhq"] = fake_dhan

from pipeline.config import PipelineConfig
from pipeline.stages.indicator_event_engine import IndicatorEventEngine
from pipeline.stages.intra_finder import IntraFinder


class IntraFinderIndicatorFlowTests(unittest.TestCase):
    def finder(self) -> IntraFinder:
        finder = IntraFinder.__new__(IntraFinder)
        finder.config = PipelineConfig()
        finder.indicator_aggregation_seconds = 60
        finder.stock_agent_cooldown_seconds = 1200
        finder.pending_indicator_deadlines = []
        finder.pending_agent_events = []
        finder.agent_queue_max_age_seconds = 120
        finder.agent_queue_expired = 0
        finder.indicator_events_detected = 0
        finder.indicator_aggregates_formed = 0
        finder.shadow_mode = True
        finder.events_suppressed = 0
        finder.gate_failure_counts = __import__("collections").Counter()
        finder.event_state = {"events": {}, "last_stock_event_at": {}}
        state = {"security_id": 1, "latest_features": {}}
        state.update(IndicatorEventEngine.state_fields())
        finder.states = {1: state}
        finder.stocks_by_security_id = {1: {"security_id": 1, "symbol": "TEST"}}
        finder._log = lambda message: None
        return finder

    @staticmethod
    def evidence(event_type: str, direction: str, at: datetime):
        return {
            "event_type": event_type,
            "direction": direction,
            "detected_at": at.isoformat(),
            "bar_start": (at - timedelta(minutes=1)).replace(second=0, microsecond=0).isoformat(),
        }

    def test_events_for_one_stock_are_merged_before_one_emit(self) -> None:
        finder = self.finder()
        now = datetime.fromisoformat("2026-08-03T10:00:01+05:30")
        state = finder.states[1]
        finder._queue_indicator_evidence(
            1,
            state,
            [
                self.evidence("EMA_BULLISH_CROSS", "LONG", now),
                self.evidence("BULLISH_ENGULFING", "LONG", now),
            ],
            now,
        )
        captured = []
        finder._indicator_safety_gates = lambda *args: ([], 0.01)

        def create_event(stock, local_state, features, events, direction, score, emitted_at):
            captured.append((events, direction, score))
            return {"event_id": "one-event"}

        finder._create_indicator_event = create_event
        self.assertEqual(finder._flush_due_indicator_events(now + timedelta(seconds=30)), [])
        emitted = finder._flush_due_indicator_events(now + timedelta(seconds=61))
        self.assertEqual(len(emitted), 1)
        self.assertEqual(len(captured[0][0]), 2)
        self.assertEqual(captured[0][1], "LONG")

    def test_mixed_indicator_directions_are_preserved_for_agent_reasoning(self) -> None:
        now = datetime.fromisoformat("2026-08-03T10:00:01+05:30")
        events = [
            self.evidence("RSI_EXITED_OVERSOLD", "LONG", now),
            self.evidence("SHOOTING_STAR", "SHORT", now),
        ]
        self.assertEqual(IntraFinder._indicator_direction(events), "MIXED")

    def test_basic_safety_gates_do_not_require_rvol_or_predictive_score(self) -> None:
        finder = self.finder()
        now = datetime.fromisoformat("2026-08-03T10:05:00+05:30")
        finder._estimated_slippage = lambda *args, **kwargs: 0.01
        state = finder.states[1]
        features = {
            "received_at": now.isoformat(),
            "last_price": 100.0,
            "depth": [{} for _ in range(5)],
            "spread_percent": 0.03,
            "connection_warm": True,
            "upper_circuit": 120.0,
            "lower_circuit": 80.0,
            "relative_volume": None,
        }
        failures, slippage = finder._indicator_safety_gates(
            state, features, "NEUTRAL", now
        )
        self.assertEqual(failures, [])
        self.assertEqual(slippage, 0.01)

    def test_agent_queue_discards_stale_evidence_before_dispatch(self) -> None:
        finder = self.finder()
        now = datetime.fromisoformat("2026-08-03T10:10:00+05:30")
        finder.market_time = type("Clock", (), {"now": lambda self: now})()
        finder.pending_agent_events = [
            {
                "event_id": "stale",
                "created_at": (now - timedelta(minutes=5)).isoformat(),
                "setup_score": 100,
            },
            {
                "event_id": "fresh",
                "created_at": (now - timedelta(seconds=30)).isoformat(),
                "setup_score": 50,
            },
        ]
        event = finder._next_fresh_agent_event_locked()
        self.assertEqual(event["event_id"], "fresh")
        self.assertEqual(finder.agent_queue_expired, 1)


if __name__ == "__main__":
    unittest.main()
