"""Incremental extrema and path length for ordered, replaceable price samples."""

from bisect import bisect_left, insort
from collections import deque


class PriceWindow:
    def __init__(self, seconds: int, samples=()) -> None:
        self.seconds = seconds
        rows = list(samples)[-900:]
        self.samples: deque[tuple[float, float]] = deque(rows)
        self.ordered = sorted(value for _, value in rows)
        self.path = sum(abs(current[1] - previous[1]) for previous, current in zip(rows, rows[1:]))

    def expire(self, now: float) -> None:
        while self.samples and self.samples[0][0] < now - self.seconds:
            _, value = self.samples.popleft()
            del self.ordered[bisect_left(self.ordered, value)]
            if self.samples:
                self.path -= abs(self.samples[0][1] - value)
        if len(self.samples) < 2:
            self.path = 0.0

    def append(self, timestamp: float, price: float, *, replace: bool = False) -> None:
        if replace and self.samples:
            _, previous = self.samples.pop()
            del self.ordered[bisect_left(self.ordered, previous)]
            if self.samples:
                self.path -= abs(previous - self.samples[-1][1])
        self.expire(timestamp)
        if len(self.samples) >= 900:
            _, value = self.samples.popleft()
            del self.ordered[bisect_left(self.ordered, value)]
            self.path -= abs(self.samples[0][1] - value)
        if self.samples:
            self.path += abs(price - self.samples[-1][1])
        self.samples.append((timestamp, price))
        insort(self.ordered, price)


class RollingPrices:
    def __init__(self, samples, now: float) -> None:
        self.five = PriceWindow(300, (row for row in samples if row[0] >= now - 300))
        self.one = PriceWindow(60, (row for row in self.five.samples if row[0] >= now - 60))
        self.now = now

    def append(self, timestamp: float, price: float, *, replace: bool) -> None:
        self.five.append(timestamp, price, replace=replace)
        self.one.append(timestamp, price, replace=replace)
        self.now = timestamp

    def expire(self, now: float) -> None:
        self.five.expire(now)
        self.one.expire(now)
        self.now = now
