"""Offline burst replay through the real IntraFinder and persistence code."""

import argparse
import asyncio
from dataclasses import replace
from datetime import datetime, timedelta
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import time
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pyarrow.parquet as pq

from pipeline.config import PipelineConfig
from pipeline.services.feed_receiver import FeedReceiver
from pipeline.stages.intra_finder import IntraFinder
from pipeline.stages.live_state import LiveStockState, OHLCV


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stocks", type=int, default=3500)
    parser.add_argument("--rounds", type=int, default=15)
    parser.add_argument("--samples", type=int, default=900)
    parser.add_argument("--bars-per-stock", type=int, default=0, choices=range(421), metavar="0..420")
    parser.add_argument("--rank-interval", type=int, default=1)
    parser.add_argument("--flush-seconds", type=int, default=5)
    parser.add_argument("--paced", action="store_true", help="Spread each round across one second")
    args = parser.parse_args()
    base = datetime.fromisoformat("2026-09-07T10:00:00+05:30")
    with TemporaryDirectory(prefix="feed-replay-", dir=Path(__file__).resolve().parents[3] / "progress") as temporary:
        root = Path(temporary)
        config = replace(PipelineConfig(), results_dir=root, stage2_results_dir=root / "stage2",
                         stage2_latest_path=root / "stage2/latest.json",
                         intra_finder_shadow_mode=True, intra_finder_record_all_raw_packets=True,
                         intra_finder_flush_seconds=args.flush_seconds,
                         intra_finder_status_seconds=max(5, args.flush_seconds),
                         intra_finder_rank_interval_seconds=args.rank_interval)
        with patch("pipeline.stages.intra_finder.DhanService", return_value=None):
            finder = IntraFinder(config)
        started = time.monotonic()
        clock = SimpleNamespace(now=lambda: base + timedelta(seconds=time.monotonic() - started),
                                market_date_str=lambda: base.date().isoformat())
        finder.market_time = clock
        finder.connection_state = "CONNECTED"
        finder.connected_at = base - timedelta(seconds=60)
        finder.universe_version = "offline-replay"
        finder.event_state = {"events": {}}
        finder.shadow_mode = True
        finder.record_all_raw = True
        depth = [{"bid_price": 99.99 - i * 0.01, "ask_price": 100.01 + i * 0.01,
                  "bid_quantity": 1000, "ask_quantity": 1000, "bid_orders": 10, "ask_orders": 10}
                 for i in range(5)]
        baseline = {f"{minute // 60:02d}:{minute % 60:02d}": float((minute - 550) * 1000)
                    for minute in range(555, 930, 5)}
        for index in range(args.stocks):
            stock = {"exchange_segment": "NSE_EQ", "security_id": index + 1,
                     "symbol": f"S{index}", "isin": f"I{index}"}
            state = LiveStockState.from_stock(stock)
            state.median_cumulative_volume = baseline
            state.latest_price = 100
            state.last_packet_at = state.last_trade_at = base.isoformat()
            state.depth = depth
            state.spread_percent = 0.02
            state.session_live_started = True
            state.cumulative_volume = state.previous_cumulative_volume = 100000
            state.cumulative_value = 10000000
            state.price_samples.extend((base.timestamp() - args.samples + i, 100 + i % 7 * 0.001)
                                       for i in range(args.samples))
            state.value_samples.extend((base.timestamp() - args.samples + i, 10000000 - (args.samples - i) * 1000)
                                       for i in range(args.samples))
            state.minute_bars.extend(
                OHLCV((base - timedelta(minutes=args.bars_per_stock - i)).isoformat(),
                      100.0, 100.1, 99.9, 100.0, 1000.0, 100.0)
                for i in range(args.bars_per_stock)
            )
            finder.stocks[state.key] = stock
            finder.states[state.key] = state
        emitted = 0
        preparation_started = time.perf_counter()
        for state in finder.states.values():
            state.refresh_derived(base)
        preparation_ms = (time.perf_counter() - preparation_started) * 1000
        started = time.monotonic()

        async def receive():
            nonlocal emitted
            if emitted >= args.stocks * args.rounds:
                await asyncio.Event().wait()
            round_number, index = divmod(emitted, args.stocks)
            due = round_number + (index / args.stocks if args.paced else 0)
            wait = started + due - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            emitted += 1
            return {"sequence": emitted, "security_id": index + 1, "exchange_segment": 1,
                    "LTP": 100 + (round_number % 7) * 0.001, "volume": 100000 + round_number * 10,
                    "LTT": clock.now().isoformat(), "depth": depth, "avg_price": 100}

        loop = asyncio.new_event_loop()
        feed = SimpleNamespace(loop=loop, get_instrument_data=receive)
        receiver = FeedReceiver(feed, clock.now)
        delays, ranks = [], []
        receiver.start()
        try:
            for expected in range(1, args.stocks * args.rounds + 1):
                item = receiver.get(10)
                if item.packet["sequence"] != expected:
                    raise AssertionError("packet order changed")
                delay = (time.monotonic() - item.received_monotonic) * 1000
                delays.append(delay)
                previous_rank = finder.last_rank_at
                finder.process_packet(item.packet, received_at=item.received_at,
                                      decision_at=clock.now(), allow_signals=delay < 10000)
                if finder.last_rank_at != previous_rank:
                    ranks.append(finder.last_rank_duration_ms)
        finally:
            receiver.stop()
            finder.close()
            loop.close()
        written = sum(pq.read_metadata(path).num_rows for path in root.glob("stage2/*/raw-depth/**/*.parquet"))
        if written != len(delays):
            raise AssertionError(f"raw recording mismatch: {written} != {len(delays)}")
        try:
            import resource
            peak_rss_mib = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
        except ImportError:
            peak_rss_mib = None
        print(json.dumps({"stocks": args.stocks, "samples": args.samples, "packets": len(delays),
                          "bars_per_stock": args.bars_per_stock,
                          "peak_rss_mib_linux": peak_rss_mib,
                          "paced": args.paced, "rank_interval": args.rank_interval,
                          "flush_seconds": args.flush_seconds,
                          "preconnection_preparation_ms": preparation_ms,
                          "recorded_packets": written, "elapsed_seconds": time.monotonic() - started,
                          "ingress_ms": dict(zip(("p50", "p95", "p99", "max"), np.percentile(delays, [50, 95, 99, 100]).tolist())),
                          "ranking_ms": ranks, "queue_high_water": receiver.high_water,
                          "queue_full_waits": receiver.full_waits, "persistence_error": finder.persistence_error}, indent=2))


if __name__ == "__main__":
    main()
