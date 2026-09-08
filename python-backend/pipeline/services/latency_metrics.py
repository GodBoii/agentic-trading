"""Fixed-size histograms for pipeline delays without retaining packet data."""

from bisect import bisect_left
from threading import Lock
import time


class LatencyMetrics:
    bounds_ms = (0.1, 0.25, 0.5, 1, 2, 5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000)

    def __init__(self) -> None:
        self.lock = Lock()
        self.rows = {name: {"counts": [0] * (len(self.bounds_ms) + 1), "max_ms": 0.0,
                            "max_at_epoch": None, "last_ms": 0.0}
                     for name in ("ingress", "rank", "checkpoint_build", "status_build", "io_wait")}

    def observe(self, name: str, milliseconds: float) -> None:
        value = max(0.0, milliseconds)
        with self.lock:
            row = self.rows[name]
            row["counts"][bisect_left(self.bounds_ms, value)] += 1
            row["last_ms"] = value
            if value > row["max_ms"]:
                row["max_ms"], row["max_at_epoch"] = value, time.time()

    def snapshot(self) -> dict:
        with self.lock:
            rows = {name: {**row, "counts": list(row["counts"])} for name, row in self.rows.items()}
        for row in rows.values():
            count = sum(row["counts"])
            row["observations"] = count
            for label, fraction in (("p95_upper_ms", 0.95), ("p99_upper_ms", 0.99)):
                cumulative = 0
                row[label] = None
                for index, frequency in enumerate(row["counts"]):
                    cumulative += frequency
                    if count and cumulative >= count * fraction:
                        row[label] = self.bounds_ms[index] if index < len(self.bounds_ms) else None
                        break
        return {"bucket_upper_bounds_ms": [*self.bounds_ms, None], "operations": rows}
