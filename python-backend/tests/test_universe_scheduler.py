from __future__ import annotations

import subprocess
import unittest
from datetime import time as dt_time
from types import SimpleNamespace
from unittest.mock import patch

from pipeline.runtime.run_universe_scanner import (
    _run_heavy_scan,
    _should_defer_heavy_scan,
)


class UniverseSchedulerTests(unittest.TestCase):
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
