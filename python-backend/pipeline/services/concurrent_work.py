"""Completion-order iteration without submitting an entire universe at once."""

from concurrent.futures import FIRST_COMPLETED, Executor, wait
from typing import Callable, Iterable, Iterator, TypeVar

T = TypeVar("T")
R = TypeVar("R")


def bounded_results(
    executor: Executor, function: Callable[[T], R], items: Iterable[T], *, limit: int
) -> Iterator[tuple[T, R]]:
    if limit < 1:
        raise ValueError("pending work limit must be positive")
    iterator = iter(items)
    pending = {}

    def refill() -> None:
        while len(pending) < limit:
            try:
                item = next(iterator)
            except StopIteration:
                return
            pending[executor.submit(function, item)] = item

    try:
        refill()
        while pending:
            completed, _ = wait(pending, return_when=FIRST_COMPLETED)
            for future in completed:
                item = pending.pop(future)
                yield item, future.result()
            refill()
    finally:
        for future in pending:
            future.cancel()
