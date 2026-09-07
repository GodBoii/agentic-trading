"""Compare real chart rendering in threads and isolated spawned processes."""

import argparse
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
import json
import multiprocessing
from pathlib import Path
from tempfile import TemporaryDirectory
import time


def render(directory: str) -> dict:
    import numpy as np
    import pandas as pd
    from pipeline.services.charting_service import CandlestickChartService

    def frame(times):
        prices = 100 + np.arange(len(times)) * 0.01
        return pd.DataFrame({"timestamp": times, "open": prices, "high": prices + 0.2,
                             "low": prices - 0.2, "close": prices + 0.1, "volume": 1000})

    times = pd.date_range("2026-09-04 09:15", periods=375, freq="min", tz="Asia/Kolkata")
    times = times.append(pd.date_range("2026-09-07 09:15", periods=143, freq="min", tz="Asia/Kolkata"))
    daily = frame(pd.date_range("2025-06-01", "2026-09-06", freq="B", tz="Asia/Kolkata"))
    started = time.perf_counter()
    result = CandlestickChartService("Asia/Kolkata").build_intraday_chart_set(
        frame(times), "Benchmark", "2026-09-07", Path(directory), daily_frame=daily,
    )
    return {"seconds": time.perf_counter() - started, "charts": result["chart_count"],
            "bytes": sum(Path(path).stat().st_size for path in result["chart_paths_ordered"])}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("threads", "processes"), default="threads")
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args()
    executor_type = ThreadPoolExecutor if args.mode == "threads" else ProcessPoolExecutor
    kwargs = {} if args.mode == "threads" else {"mp_context": multiprocessing.get_context("spawn")}
    with TemporaryDirectory(prefix="chart-benchmark-", dir=Path(__file__).resolve().parents[3] / "progress") as directory:
        started = time.perf_counter()
        with executor_type(max_workers=args.workers, **kwargs) as executor:
            cold = list(executor.map(render, [str(Path(directory) / f"cold-{i}") for i in range(2)]))
            warm_started = time.perf_counter()
            warm = list(executor.map(render, [str(Path(directory) / f"warm-{i}") for i in range(2)]))
            warm_seconds = time.perf_counter() - warm_started
        print(json.dumps({"mode": args.mode, "workers": args.workers,
                          "total_seconds": time.perf_counter() - started,
                          "warm_pair_seconds": warm_seconds, "cold": cold, "warm": warm}, indent=2))


if __name__ == "__main__":
    main()
