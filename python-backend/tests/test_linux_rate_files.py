"""Exercise the fallback coordinator with actual Linux file locks."""

from concurrent.futures import ProcessPoolExecutor
import multiprocessing
from pathlib import Path
from tempfile import TemporaryDirectory
import time
from types import SimpleNamespace
import unittest

from pipeline.services.dhan_service import DhanService, fcntl


def _shared_slot(path: str) -> float:
    service = object.__new__(DhanService)
    service.config = SimpleNamespace(dhan_rate_limit_state_path=Path(path),
                                     shared_rate_limit_window_seconds=0.1,
                                     shared_rate_limit_poll_seconds=0.001,
                                     historical_rate_limit_per_sec=2)
    service._acquire_shared_data_slot()
    return time.time()


@unittest.skipIf(fcntl is None, "Linux file locks are not available")
class LinuxRateFileTests(unittest.TestCase):
    def test_simultaneous_first_use_does_not_reset_another_process_reservation(self):
        with TemporaryDirectory() as directory:
            path = str(Path(directory) / "rate.json")
            with ProcessPoolExecutor(max_workers=4, mp_context=multiprocessing.get_context("spawn")) as pool:
                timestamps = sorted(pool.map(_shared_slot, [path] * 12))
            for index in range(2, len(timestamps)):
                self.assertGreaterEqual(timestamps[index] - timestamps[index - 2], 0.095)
