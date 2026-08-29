from __future__ import annotations

import unittest
from datetime import datetime, timedelta
from threading import Event, RLock
from types import SimpleNamespace
from unittest.mock import Mock, patch
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
        finder.agent_threads = set()
        finder.dispatch_lock = RLock()
        finder.events_triggered = 0
        finder.agent_dispatch_successes = 0
        finder.agent_dispatch_failures = 0
        finder.indicator_events_detected = 0
        finder.indicator_aggregates_formed = 0
        finder.readiness_evaluations = 0
        finder.readiness_passed = 0
        finder.readiness_rechecks = 0
        finder.readiness_threshold = 75.0
        finder.readiness_direction_margin = 10.0
        finder.readiness_min_completed_bars = 45
        finder.readiness_min_room_atr = 0.55
        finder.readiness_max_last_trade_age_seconds = 90
        finder.readiness_observation_seconds = 600
        finder.readiness_reevaluation_seconds = 60
        finder.readiness_min_confirmation_seconds = 300
        finder.readiness_max_entry_drift_atr = 0.80
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

        def create_event(stock, local_state, features, events, direction, readiness, score, emitted_at):
            captured.append((events, direction, readiness["score"], score))
            return {"event_id": "one-event"}

        finder._create_indicator_event = create_event
        self.assertEqual(finder._flush_due_indicator_events(now + timedelta(seconds=30)), [])
        with patch(
            "pipeline.stages.intra_finder.evaluate_trade_readiness",
            return_value={
                "ready": True,
                "direction": "LONG",
                "score": 82.0,
                "components": {},
                "failures": [],
            },
        ):
            emitted = finder._flush_due_indicator_events(now + timedelta(seconds=61))
        self.assertEqual(len(emitted), 1)
        self.assertEqual(len(captured[0][0]), 2)
        self.assertEqual(captured[0][1], "LONG")
        self.assertEqual(captured[0][2], 82.0)

    def test_indicator_activity_does_not_speculatively_fetch_history(self) -> None:
        finder = self.finder()
        finder.signal_cache = SimpleNamespace(prewarm=Mock())
        now = datetime.fromisoformat("2026-08-03T10:00:01+05:30")
        state = finder.states[1]

        finder._queue_indicator_evidence(
            1,
            state,
            [self.evidence("EMA_BULLISH_CROSS", "LONG", now)],
            now,
        )
        finder._reschedule_readiness_evaluation(
            1,
            state,
            list(state["pending_indicator_events"]),
            now,
        )

        finder.signal_cache.prewarm.assert_not_called()

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

    def test_weak_evidence_is_rejected_before_agent_readiness(self) -> None:
        finder = self.finder()
        self.assertTrue(
            finder._weak_indicator_evidence_only(
                [
                    {"event_type": "DOJI"},
                    {"event_type": "VOLUME_SURGE"},
                ]
            )
        )
        self.assertFalse(
            finder._weak_indicator_evidence_only(
                [
                    {"event_type": "DOJI"},
                    {"event_type": "EMA_BULLISH_CROSS"},
                ]
            )
        )

    def test_each_agent_event_starts_immediately_without_a_waiting_queue(self) -> None:
        finder = self.finder()
        both_started = Event()
        release = Event()
        started: list[str] = []

        def post(event):
            started.append(event["event_id"])
            if len(started) == 2:
                both_started.set()
            release.wait(2)

        finder._post_agent_event = post
        finder._dispatch_event({"event_id": "first"})
        finder._dispatch_event({"event_id": "second"})

        self.assertTrue(both_started.wait(2))
        self.assertCountEqual(started, ["first", "second"])
        self.assertEqual(finder.events_triggered, 2)
        self.assertEqual(len(finder.agent_threads), 2)
        self.assertFalse(hasattr(finder, "pending_agent_events"))

        threads = list(finder.agent_threads)
        release.set()
        for thread in threads:
            thread.join(timeout=2)
        self.assertEqual(finder.agent_dispatch_successes, 2)
        self.assertEqual(finder.agent_dispatch_failures, 0)
        self.assertEqual(finder.agent_threads, set())


if __name__ == "__main__":
    unittest.main()
