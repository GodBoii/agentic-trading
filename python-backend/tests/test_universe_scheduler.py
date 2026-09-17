from __future__ import annotations

import subprocess
import unittest
from datetime import datetime, time as dt_time
from types import SimpleNamespace
from unittest.mock import patch

from pipeline.runtime.run_universe_scanner import (
    _run_heavy_scan,
    _scan_timeout_seconds,
    _should_defer_heavy_scan,
)
from pipeline.config import PipelineConfig


class UniverseSchedulerTests(unittest.TestCase):
    def test_premarket_budget_ends_at_nine_even_after_late_start(self) -> None:
        config = PipelineConfig()
        session = SimpleNamespace(is_after_close=False)
        for clock, expected in (("06:00:00", 10800), ("07:00:00", 7200),
                                ("07:25:00", 5700), ("08:59:45", 15),
                                ("09:00:00", 0), ("12:00:00", 0)):
            with self.subTest(clock=clock):
                now = datetime.fromisoformat(f"2026-09-17T{clock}+05:30")
                self.assertEqual(_scan_timeout_seconds(now, config, session), expected)

    def test_after_close_run_keeps_full_budget(self) -> None:
        now = datetime.fromisoformat("2026-09-17T16:00:00+05:30")
        self.assertEqual(_scan_timeout_seconds(now, PipelineConfig(),
                         SimpleNamespace(is_after_close=True)), 10800)

    def test_child_timeout_does_not_extend_short_remaining_budget(self) -> None:
        with patch("pipeline.runtime.run_universe_scanner.subprocess.run") as run:
            run.return_value.returncode = 0
            self.assertEqual(_run_heavy_scan(15), 0)
            self.assertEqual(run.call_args.kwargs["timeout"], 15)

    def test_scan_can_start_before_cutoff(self) -> None:
        self.assertFalse(
            _should_defer_heavy_scan(
                dt_time(7, 10),
                dt_time(7, 30),
                SimpleNamespace(is_after_close=False),
            )
        )

    def test_missing_scan_is_deferred_during_live_day(self) -> None:
        self.assertTrue(
            _should_defer_heavy_scan(
                dt_time(10, 0),
                dt_time(7, 30),
                SimpleNamespace(is_after_close=False),
            )
        )

    def test_missing_scan_can_run_after_close(self) -> None:
        self.assertFalse(
            _should_defer_heavy_scan(
                dt_time(16, 0),
                dt_time(7, 30),
                SimpleNamespace(is_after_close=True),
            )
        )

    def test_hung_child_returns_timeout_exit_code(self) -> None:
        with patch(
            "pipeline.runtime.run_universe_scanner.subprocess.run",
            side_effect=subprocess.TimeoutExpired("scanner", 60),
        ):
            self.assertEqual(_run_heavy_scan(60), 124)


if __name__ == "__main__":
    unittest.main()
