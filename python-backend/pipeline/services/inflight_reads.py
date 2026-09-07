"""Share concurrent identical reads without retaining stale responses."""

from concurrent.futures import Future
from threading import Lock
from typing import Callable, Hashable, TypeVar

T = TypeVar("T")


class InflightReads:
    def __init__(self) -> None:
        self._lock = Lock()
        self._pending: dict[Hashable, Future] = {}

    def run(self, key: Hashable, fetch: Callable[[], T]) -> T:
        with self._lock:
            future = self._pending.get(key)
            owner = future is None
            if owner:
                future = Future()
                self._pending[key] = future
        if not owner:
            return future.result()
        try:
            result = fetch()
            future.set_result(result)
            return result
        except BaseException as exc:
            future.set_exception(exc)
            raise
        finally:
            with self._lock:
                self._pending.pop(key, None)
