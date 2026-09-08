# Live qualification, September 8

Read-only inspection began around 14:01 IST. Ubuntu runs commit `1afec3f7065678f1dc675c62e65999543099201c`, matching the local checkout. Runtime files are modified by the running services. This task does not change those files or enable trading.

## Evidence so far

- Feed connected since 09:10 IST, zero reconnects, zero full-queue waits, no persistence error. About 13.3 million packets processed by 14:03.
- 3,510 requested instruments, 3,499 observed at least once, 3,369 observed with usable price/full-packet state. Receiving a previous-close packet is not proof of a usable live Full feed.
- Intra-Finder uses about 1.33 GiB RAM and roughly one CPU core. Host has about 7.8 GiB available RAM and little swap use.
- One-minute health sample, 120 observations, no HTTP failures: median sampled ingress delay 0.787 ms, p95 sample 1,179 ms, maximum sample 1,896 ms. Session maximum is 9,792 ms and did not increase during sampling. These are health observations, not packet-weighted latency percentiles.
- Recent ranking snapshots usually show 60–72 ms. Opening logs contain several hundreds-of-milliseconds ranks. The historical maximum cannot be attributed to a cause because per-operation timings were not recorded.
- Runtime checkpoint is approximately 38.8 MB; status snapshot about 5.8 MB. Locally serializing a copied checkpoint without indentation reduced 38.5 MB to 19.6 MB, but only reduced median serialization from 443 ms to 406 ms. Disk savings are established; a large CPU gain is not.
- Historical profiles: 2,151 ready, 122 partial, 1,237 unavailable. Venue-comparison errors include 2,919 DH-905 Input_Exception responses, 147 insufficient-history cases, eight DH-907 responses. These counts include alternate venues. They are not evidence of a rate-limit failure or an order-IP rejection.
- NIFTY collector disabled. Agent dispatch in shadow mode. Chart processes and Redis coordination unset. Those optional paths cannot be qualified as active from today's run.

## Local follow-through before deployment

1. Measure checkpoint construction with actual retained bars, which the earlier synthetic replay did not include.
2. Reduce repeated dataclass conversion and snapshot bytes while preserving the exact JSON data and atomic fsync/replace behavior.
3. Add bounded per-operation latency counters, including checkpoint construction and recording submission waits, so a future queue spike can be attributed rather than guessed.
4. Test representative failed historical requests through the existing gateway. Preserve rate coordination and do not start another WebSocket or alter trading controls.
5. Run regression tests and record which changes need deployment. Do not claim that local fixes have changed the currently running process.

Live sample observations are in `live-health-samples-2026-09-08.json`. A copied market-state checkpoint used for local experiments is under ignored `python-backend/results/live-audit`, not in the report or commits.

## Implemented after measurement

The copied checkpoint contains 3,510 stock states and 67,998 retained minute bars. Reconstructing compact checkpoints locally took a median 181 ms before the change and 66 ms after replacing recursive dataclass conversion with an explicit record for immutable OHLCV bars. Field-for-field parity is tested. Compact JSON cuts snapshot bytes by about 49%; atomic file replacement and fsync remain in place.

Added fixed-size histograms for every live ingress observation, each rank, checkpoint construction, status construction and I/O admission wait. Histograms report bucket upper bounds, observation counts, maximum delay and when that maximum occurred. They are process-lifetime statistics, not a sliding-window percentile. They require deployment to observe future live spikes.

Read-only probes through the existing gateway succeeded for two stocks whose morning profiles were unavailable, security IDs 890228 and 513303 on BSE. Both the 30-day and original 60-day ranges succeeded. The 60-day requests returned 31 and 42 bars. This proves some earlier failures were transient; it does not prove every missing profile will recover. Historical daily/intraday reads now retry DH-905 Input_Exception once within the existing attempt budget and shared rate limits. Order retries, placement controls, and the existing historical circuit breaker are unchanged.

Twenty-five of the 120 live health observations exceeded 250 ms. Queue spikes occurred even with no full-queue waits. The broad feed remains operational, but the live latency target is not met consistently. No claim of a complete live qualification is warranted.

Disabled paths remain unqualified on this server: NIFTY monitoring, agent routing/execution, spawned chart workers and Redis. Redis must not be pointed at the unrelated `aios-redis` instance without a deliberate isolated configuration and restart/recovery policy. Missing morning profiles require a bounded recovery run and publication strategy; this task did not rerun the entire universe or replace active-session state.

## Verification and deployment boundary

- Windows regression: 229 passed, six environment-specific skips, 19 subtests passed.
- Isolated Linux Docker with real Redis: 235 passed, 19 subtests passed.
- Python compilation and whitespace checks passed.
- Final server health check remained healthy and connected, with zero reconnects, zero queue-full waits and no persistence error. Last queue delay was 85 ms; the lifetime maximum remained 9,792 ms.

New changes are local and uncommitted. The current server was inspected, not restarted or modified. Applying the new snapshot and metrics code requires restarting Intra-Finder; activating the bounded history retry requires restarting the gateway. Both can retain current shadow mode. The earlier user constraint requires code modifications to stay local, so deployment needs an explicit scope update before proceeding.

After deployment, collect the packet-weighted histograms across multiple checkpoint intervals. Check that snapshot byte reduction and checkpoint-build timings improve on Ubuntu, and correlate remaining ingress maxima with operation maxima. Do not confuse this future measurement with the health samples already collected. Keep the existing whole-session maximum in the report even if a process restart resets its counter.
