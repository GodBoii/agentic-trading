from __future__ import annotations

from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from pipeline.runtime.run_stock_agent import MultiStockAgentRunner


MODULE = "pipeline.runtime.run_stock_agent"


class ContextReady(Exception):
    """Stop the test before creating a model or making an order."""


class AgentSnapshotFreshnessTests(TestCase):
    def run_preparation(self, build_charts, fetch_state, upload, build_context):
        runner = MultiStockAgentRunner.__new__(MultiStockAgentRunner)
        runner.config = SimpleNamespace(
            stock_analyzer_artifacts_dir=Path("unused"), stock_agent_max_leverage=5,
            stock_agent_max_risk_fraction_per_slot=.02, stock_agent_max_concurrent_trades=5,
            stock_agent_final_quote_max_age_seconds=5, stock_agent_final_candle_max_age_seconds=120,
            stock_agent_max_entry_drift_risk_fraction=.25,
        )
        runner.market_time = SimpleNamespace(now=lambda: datetime.now(timezone.utc))
        runner.signal_cache = SimpleNamespace(load_frame=lambda **_: SimpleNamespace(empty=False))
        runner.execution_helper = Mock()
        runner.execution_helper._normalize_selected_stock.return_value = {}
        runner.user_dhan = Mock()
        runner.dhan = Mock()
        runner.charting = SimpleNamespace(REQUIRED_AGENT_CHARTS={"one"}, build_intraday_chart_set=build_charts)
        runner._resolve_margin_budget = lambda *_: 500
        runner._fetch_daily_chart_history = lambda *_: None
        runner._upload_chart_images = upload
        runner._emit = Mock()
        runner._chart_image_cards = lambda *_: []
        runner._build_stock_agent_timing_context = lambda *_: {}
        market = Mock()
        market.current_stock_state_payload.side_effect = fetch_state
        with ExitStack() as stack:
            stack.enter_context(patch(f"{MODULE}.CloudPersistenceService.validate_agno_db"))
            stack.enter_context(patch(f"{MODULE}.StockMarketDataToolkit", return_value=market))
            stack.enter_context(patch(f"{MODULE}.StockAccountToolkit"))
            stack.enter_context(patch(f"{MODULE}.StockTechnicalToolkit"))
            stack.enter_context(patch(f"{MODULE}.StockExecutionToolkit"))
            stack.enter_context(patch(f"{MODULE}.StockDecisionContextBuilder.build", side_effect=build_context))
            runner._run_admitted_stock_agent(
                0, {"security_id": 1, "exchange_segment": "NSE_EQ", "market_date": "2026-09-09",
                    "display_name": "Test", "event_id": "test"}, {"user_id": "test"},
            )

    @staticmethod
    def bundle():
        return {"charts": {"one": {"path": "one.png"}}, "chart_paths_ordered": ["one.png"]}

    def test_snapshot_runs_after_render_and_overlaps_upload_before_context(self):
        rendered, fetching, uploaded = Event(), Event(), Event()
        calls = []

        def render(**_):
            self.assertFalse(fetching.is_set())
            rendered.set()
            return self.bundle()

        def fetch(**kwargs):
            self.assertTrue(rendered.is_set())
            calls.append(kwargs)
            fetching.set()
            self.assertTrue(uploaded.wait(2), "upload must overlap the snapshot request")
            return {"quote": {"last_price": 101}}

        def upload(*_):
            self.assertTrue(fetching.wait(2))
            uploaded.set()
            return ["one.png"]

        def context(**kwargs):
            self.assertTrue(uploaded.is_set())
            self.assertEqual(kwargs["current_state"], {"quote": {"last_price": 101}})
            raise ContextReady

        with self.assertRaises(ContextReady):
            self.run_preparation(render, fetch, upload, context)
        self.assertEqual(calls, [{"force_refresh": True}])

    def test_upload_error_prevents_context_and_waits_for_snapshot(self):
        completed = Event()

        def fetch(**_):
            completed.set()
            return {}

        context = Mock()
        with self.assertRaisesRegex(RuntimeError, "upload failed"):
            self.run_preparation(lambda **_: self.bundle(), fetch,
                                 Mock(side_effect=RuntimeError("upload failed")), context)
        self.assertTrue(completed.is_set())
        context.assert_not_called()

    def test_snapshot_error_keeps_existing_partial_context_behavior(self):
        def context(**kwargs):
            self.assertEqual(kwargs["current_state"]["status"], "error")
            self.assertIn("snapshot unavailable", str(kwargs["current_state"]))
            raise ContextReady

        with self.assertRaises(ContextReady):
            self.run_preparation(lambda **_: self.bundle(),
                                 Mock(side_effect=RuntimeError("snapshot unavailable")),
                                 lambda *_: ["one.png"], context)
