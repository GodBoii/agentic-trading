from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock, RLock
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from pipeline.runtime.run_ai_trading_orchestrator import AITradingOrchestrator
from pipeline.runtime.run_nifty_50_market_depth import _enabled
from pipeline.runtime.run_universe_scanner import _artifact_complete
from pipeline.stages.intra_finder import IntraFinder


class ClosedMarketMemoryLifecycleTests(TestCase):
    def test_nifty_collector_gate_is_disabled_by_zero(self) -> None:
        with patch.dict(os.environ, {"NIFTY_DEPTH_MONITOR_ENABLED": "0"}):
            self.assertFalse(_enabled())

    def test_universe_artifact_requires_current_baseline(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "universe.json"
            path.write_text(
                json.dumps(
                    {
                        "summary": {
                            "status": "completed",
                            "market_date": "2026-08-24",
                            "baseline_schema_version": 3,
                        }
                    }
                ),
                encoding="utf-8",
            )

            self.assertTrue(_artifact_complete(path, "2026-08-24"))
            self.assertFalse(_artifact_complete(path, "2026-08-25"))

    def test_intra_finder_clears_only_after_final_io_succeeds(self) -> None:
        finder = IntraFinder.__new__(IntraFinder)
        finder.released_session_date = None
        finder._mark_session_ended = Mock()
        finder._wait_for_pending_io = Mock(return_value=False)
        finder._release_session_memory = Mock()

        finder._finalize_and_release_session("2026-08-24")

        finder._mark_session_ended.assert_called_once_with("2026-08-24")
        finder._release_session_memory.assert_not_called()

    def test_intra_finder_releases_large_session_collections(self) -> None:
        finder = IntraFinder.__new__(IntraFinder)
        finder.state_lock = RLock()
        finder.states = {1: {"minute_bars": [1, 2, 3]}}
        finder.stocks_by_security_id = {1: {"symbol": "TEST"}}
        finder.universe_payload = {"stocks": [{"security_id": 1}]}
        finder.universe_version = "v1"
        finder.raw_buffer = [{"packet": 1}]
        finder.derived_buffer = [{"snapshot": 1}]
        finder.pending_indicator_deadlines = [(1.0, 1, 1)]
        finder.event_state = {"events": {"one": {}}}
        finder.received_security_ids = {1}
        finder.full_packet_security_ids = {1}
        finder.quote_verified_security_ids = {1}
        finder.coverage_milestones_logged = {100}
        finder.gate_failure_counts = {"gate": 1}
        finder.recovery_futures = set()
        finder.coverage_verification_future = object()
        finder.opening_range_recovery_started = True
        finder.last_global_packet_at = object()
        finder.connected_at = object()

        with patch(
            "pipeline.stages.intra_finder.release_unused_process_memory"
        ) as release_memory:
            released = finder._release_session_memory("2026-08-24")

        self.assertEqual(released, 1)
        self.assertEqual(finder.states, {})
        self.assertEqual(finder.stocks_by_security_id, {})
        self.assertEqual(finder.raw_buffer, [])
        self.assertEqual(finder.derived_buffer, [])
        self.assertEqual(finder.released_session_date, "2026-08-24")
        release_memory.assert_called_once_with()

    def test_ai_event_compaction_archives_decisions(self) -> None:
        orchestrator = AITradingOrchestrator.__new__(AITradingOrchestrator)
        orchestrator.event_state = {
            "events": {
                "event-1": {
                    "status": "completed",
                    "finished_at_utc": "2026-08-24T10:00:00+00:00",
                    "decision": {"large": [1, 2, 3]},
                }
            }
        }
        orchestrator.event_decision_archive_path = Path("archive.ndjson")
        orchestrator._archive_event_decision = Mock()

        changed = orchestrator._compact_event_state_locked()

        self.assertTrue(changed)
        record = orchestrator.event_state["events"]["event-1"]
        self.assertNotIn("decision", record)
        self.assertEqual(record["decision_archive"], "archive.ndjson")
        orchestrator._archive_event_decision.assert_called_once()

    def test_ai_worker_is_created_lazily_and_reuses_shared_gate(self) -> None:
        orchestrator = AITradingOrchestrator.__new__(AITradingOrchestrator)
        orchestrator.stock_agent = None
        orchestrator.stock_agent_lock = Lock()
        orchestrator.config = SimpleNamespace()
        orchestrator.order_placement_gate = object()
        runner = SimpleNamespace(order_placement_gate=object())

        with patch(
            "pipeline.runtime.run_ai_trading_orchestrator.MultiStockAgentRunner",
            return_value=runner,
        ) as runner_type:
            first = orchestrator._get_stock_agent()
            second = orchestrator._get_stock_agent()

        self.assertIs(first, second)
        self.assertIs(runner.order_placement_gate, orchestrator.order_placement_gate)
        runner_type.assert_called_once_with(orchestrator.config)
