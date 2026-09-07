"""Optional bounded process pool for Matplotlib's process-wide rendering state."""

import atexit
from concurrent.futures import ProcessPoolExecutor
import multiprocessing
from threading import BoundedSemaphore, Lock
from typing import Any

_lock = Lock()
_pool: ProcessPoolExecutor | None = None
_slots: BoundedSemaphore | None = None
_workers = 0


def _render(timezone: str, market_open: tuple, market_close: tuple, arguments: dict) -> dict:
    from pipeline.services.charting_service import CandlestickChartService

    service = CandlestickChartService(timezone, market_open, market_close)
    return service._build_intraday_chart_set(**arguments)


def render_in_process(service: Any, arguments: dict, *, workers: int) -> dict:
    global _pool, _slots, _workers
    with _lock:
        if _pool is None:
            _workers = workers
            _pool = ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context("spawn"))
            _slots = BoundedSemaphore(workers * 2)
        if workers != _workers:
            raise RuntimeError("Chart worker count cannot change while the pool is running")
        pool, slots = _pool, _slots
        slots.acquire()
        try:
            future = pool.submit(_render, service.market_timezone, service.market_open, service.market_close, arguments)
        except BaseException:
            slots.release()
            raise
    try:
        return future.result()
    finally:
        slots.release()


def close_chart_workers() -> None:
    global _pool, _slots
    with _lock:
        if _pool is not None:
            _pool.shutdown(wait=True, cancel_futures=False)
        _pool = None
        _slots = None


atexit.register(close_chart_workers)
