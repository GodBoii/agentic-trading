# Feed and feature audit

Changes are local. No broker requests or production changes were made.

## Confirmed and fixed

`IntraFinder.process_packet` updated price/depth on every packet, but the local derived metrics used by momentum setup conditions were only refreshed by ranking. After 09:30 that meant up to five seconds of old trend efficiency and volume acceleration, alongside current prices. Excluded stocks could retain older derived values indefinitely. One-second recordings gave those mixed-age values only the packet timestamp.

Selected candidates now refresh their derived features once per observed second, before recording and detector evaluation. Other stocks retain the existing ranking cadence. Snapshots include separate `derived_as_of` and `rank_as_of` timestamps. Percentiles remain cross-sectional snapshots. This avoids reranking the universe or recalculating every recorded stock every second. A second packet within the same second deliberately shares the derived calculation, with its precise calculation time recorded.

The minute builder also lost cumulative volume increments on the first packet of each new minute. A cumulative-volume sequence 1000, 1100, 1120, 1200, 1250 previously omitted the 20 and 50 increments at minute boundaries. New minutes start with the previous packet's cumulative total. The initial observed total remains excluded, and a lower cumulative total starts at that lower value. The delta belongs to the packet's received minute; without intervening trades the exact exchange-minute allocation cannot be reconstructed.

## Checks

35 tests passed across feature freshness, observation integrity, indicator flow, and the existing 4,000-stock performance test. New cases cover current candidate metrics, unchanged cold-stock calculation epochs, same-second refresh limits, restore invalidation, and minute-volume conservation.

Offline replay command, run from `python-backend`:

```text
python -m pipeline.research.feed_latency_replay --stocks 4000 --rounds 8 --samples 900 --bars-per-stock 120 --rank-interval 5 --paced
```

Both successful runs preserved all 32,000 packets and finished without persistence errors. Baseline p99 was 365 ms, maximum 415 ms, rank calls 131/168 ms. Changed run p99 was 191 ms, maximum 252 ms, rank calls 132/139 ms. These short, noisy runs do not establish a latency improvement. An isolated 10,000-iteration sample/refresh measurement averaged 14.8 microseconds per candidate refresh.

One intervening run failed when Windows denied replacement of the runtime-state file at shutdown. Repeating the same command passed. The cause of that file lock is unproven; shared storage code was not changed.

## Remaining observations

- Recording/status/checkpoint work still runs in part on the packet consumer. The replay still shows pauses, and these changes do not solve the 250 ms worst-case objective.
- When a universe version changes, `load_universe` retains existing stock-state objects by identity. Updated historical profiles and baselines are not copied onto them. This matters if Stage 1 refreshes missing data during the session. It is a confirmed code path, but not established as a cause of the September 9 selection outcomes.
- Historical derived rows have no calculation epoch. Do not interpret their packet timestamp as proof that every metric was recalculated then.
