# Non-AI latency audit and implementation plan

Prepared September 7, 2026, before application edits. Baseline commit `c9f3030`. Work stays in the current local checkout at `C:/Users/prajw/Downloads/Trader`. No deployment, broker orders, credential changes, or remote code changes are part of this pass.

## Context and scope

Read the local transcript for thread `01a07b78-58f3-7ac1-9830-b7b4c6da4f26`, `context.md`, the Dhan context documents, current runtime code, and the installed Dhan 2.2.0 feed implementation. The earlier thread used the `ed10` worktree. This session points to the main local checkout. The earlier hardware inspection reported an i3-6098P with two cores and four threads, about 12 GB RAM, a SATA SSD, and Intel HD 510 graphics, shared with other applications. These are inherited observations, not new measurements.

Exclude model inference and model selection. Include feed reception, rolling state, ranking, recording, history and quote requests, scanner scheduling, event routing, chart preparation, monitoring, persistence, and frontend delivery. Audit all these areas, but change an algorithm only when its behavior can be checked. Replacing every implementation without measurements would conflict with preserving trading behavior.

## Broker constraints verified against current documentation

| API | Documented ceiling | Engineering consequence |
| --- | --- | --- |
| Orders | 10/s, 250/min, 1,000/hour, 7,000/day; 25 modifications/order | Per-account placement coordination must survive concurrency. Never retry an ambiguous placement as a new order. |
| Data | 5/s and 100,000/day | Retain the current conservative 4/s default. More workers cannot increase this budget. |
| Quotes | 1 request/s, up to 1,000 instruments/request | Batch coverage checks. Share the quote budget across quote and OHLC callers. |
| Non-trading | 20/s | Account preparation needs bounded fanout, with account-scoped request coordination. |
| Option chain | 1 request per 3 seconds | Serialize admission across threads and processes. |

Source: [Dhan rate limits](https://dhanhq.co/docs/v2/) and [option chain](https://dhanhq.co/docs/v2/option-chain/).

Market feed allows five connections per user and 5,000 instruments per connection, with at most 100 subscriptions per JSON message. One Full feed covers this equity universe and supplies five-level depth. Dhan sends pings every ten seconds and disconnects after forty seconds without a response. The installed SDK only advances its asyncio loop when the caller runs it, so CPU work between reads also delays protocol work. Preserve binary decoding in the SDK and instrument the decoded-packet boundary. See [live market feed](https://dhanhq.co/docs/v2/live-market-feed/).

Dedicated depth differs from Full packets. Twenty-level depth supports fifty instruments per connection; two-hundred-level depth supports one. These endpoints cover NSE equity and derivatives. Do not expand deep-depth subscriptions to the whole universe or assume these sockets have an independently unlimited account budget. See [full market depth](https://dhanhq.co/docs/v2/full-market-depth/).

Daily history ends at a non-inclusive date. Intraday history supports 1, 5, 15, 25, and 60 minute intervals, up to five years of active-instrument history, in requests spanning at most ninety days. Locally retained candles reduce repeat requests. Historical candles cannot reconstruct every missed tick or order-book update. See [historical data](https://dhanhq.co/docs/v2/historical-data/) and [market quotes](https://dhanhq.co/docs/v2/market-quote/).

Order updates use a separate authenticated stream. Their lifecycle must remain distinct from the market-data subscription lifecycle. Token rotation must rebuild authenticated clients and invalidate any in-flight sharing keys. Expired-options data is a separate research endpoint, not a replacement for live equity history. See [order updates](https://dhanhq.co/docs/v2/order-update/), [authentication](https://dhanhq.co/docs/v2/authentication/), and [expired options](https://dhanhq.co/docs/v2/expired-options-data/).

## Audit findings

| Area and files | Finding | Change or required experiment |
| --- | --- | --- |
| `stages/intra_finder.py`, installed `dhanhq/marketfeed.py` | Receive, rank, snapshot, then receive again. | Dedicated loop owner and bounded FIFO; retain packet timestamps and ordered state updates. |
| `stages/live_state.py` | Repeated 900-sample walks, nested value-window loops, baseline parsing/sorting each rank. | Reverse bounded-window scans, one-pass window endpoints, cached compiled baseline points. Check parity on boundaries and resets. |
| `stages/activity_ranker.py` | Cross-sectional percentiles and hysteresis require a coherent universe. | Preserve score, tie order, eligibility and hysteresis. Measure mature histories, not only three samples. |
| `stages/intra_finder.py` | Unbounded persistence submission; completed exceptions discarded. | Bound pending writes, observe every completion, retain failed futures, expose errors in health. |
| `stages/live_state.py`, checkpoints | Copies large deques and serializes bars subsequently discarded for cold stocks. `setup_state` is a mutable reference. | Copy only retained tails and detach nested setup state at capture. Preserve checkpoint schema. |
| `services/dhan_service.py` | Shared Linux rate files exist; startup check/write can race. Local option gap is unsynchronized. | Atomic file creation under lock; condition-protected option admission and shared gap. Keep existing safety margin. |
| `runtime/run_market_data_gateway.py` | Each concurrent identical history request reaches Dhan separately. | Share only in-flight identical reads, bounded by active request concurrency; key by route, body, credential version and market date. No stale quote caching. |
| `stages/universe_scanner.py` | Thousands of futures queued immediately; daily and baseline pools already exist. | Keep a small multiple of worker count in flight, consume completion order, preserve result association. |
| `services/signal_data_cache.py` | Cache freshness exists, but concurrent misses can duplicate fetches. | Gateway in-flight sharing covers overlapping requests; later measure process-local cache hit and conversion costs. |
| `runtime/run_ai_trading_orchestrator.py` | Entire account runs serialize inside one event. | Bounded independent account tasks, preserve per-account admission and placement locks, deterministic result collection, isolate failures. |
| `services/charting_service.py`, `runtime/run_stock_agent.py` | Whole chart set under a global Matplotlib lock; uploads and context fetches already overlap. | Benchmark real chart sets before introducing spawned workers. Keep lock for thread safety. Worker memory, input copies, startup and two-core contention must be included. |
| `services/nifty_depth_monitor.py`, tick collector | Separate feed/reconnect and periodic persistence paths. | Inventory socket owners and record queue age on each before consolidating feeds. Preserve full-depth consumers and market-close release. |
| `services/storage_service.py`, Convex persistence | Atomic snapshots use fsync; remote writes and event rewrites can dominate tails. | Retain durability; measure bytes and time. Separate immutable event archive from periodic snapshots only with restart replay tests. |
| `convex`, `app/api`, dashboard delivery | Database queries and UI subscriptions are downstream of the market path. | Profile query rows, payload bytes, subscriber fanout and slow sockets. Preserve authorization and pagination contracts. Do not invent database indexes without query evidence. |
| Docker and runtime scheduling | Several worker pools share two physical cores. | Benchmark concurrent scanner/feed/chart load. Do not add GPU work or raise every pool. |

## Implementation sequence and acceptance checks

1. Establish baseline. Run local tests without starting broker-connected services. Save a reproducible 3,500-stock rank benchmark for 3, 300 and 900 samples, including realistic 75-bucket baselines. Record median and tail, interpreter and platform. Earlier transcript numbers are comparison context only. Initial unittest baseline: 194 passed.
2. Optimize rolling calculations. Compare results with a simple reference implementation over empty, sparse, mature, same-second and boundary histories. Preserve relative-strength ranking and stable ties. Cache baseline compilation with bounded memory and mutation-sensitive keys. Do not change retention lengths.
3. Reduce checkpoint construction. Select retained samples before allocating lists or converting bars. Deep-copy setup state so background writes cannot observe later mutation. Compare hot/cold serialized payloads with the previous schema.
4. Bound scanner submission. Submit at most twice the worker count, refill as completions arrive, and propagate exceptions. Test completion association and bounded input consumption. Leave the 4/s limiter in control.
5. Repair request coordination. Serialize option-chain slots; remove rate-file creation races; share identical in-flight history requests at the gateway. Test simultaneous success, failure, different venue, different interval and credential generation. Failed requests must be retryable. Do not cache positions, margin or order placement decisions.
6. Separate feed reception. One thread owns the connected SDK loop continuously; one consumer owns state mutation. Use an 8,192-entry FIFO by default, never overwrite ticks. When full, wait cooperatively so protocol tasks still run and TCP backpressure can propagate. Track high-water mark, full-queue waits and receive-to-process delay. Stop and join the receiver before disconnecting or reconnecting; surface receiver exceptions after draining accepted packets. Suppress new signals from stale queued observations while retaining state and recording.
7. Bound persistence. Admit at most a configurable small number of pending writes, with backpressure rather than silent data loss. Check errors before admitting more work. Expose pending count and failure state. Preserve buffers when submission fails. Verify drain and close behavior and that failed persistence prevents session-memory release.
8. Remove account head-of-line blocking. Extract one account task and execute independent accounts with a small bounded pool. Keep existing event admission, capacity reservation and immediate placement recheck. Verify a slow account cannot prevent a second account from preparing, and one failure does not hide another result. Model inference internals remain unchanged.
9. Run full regression and replay checks. Include Dhan resilience, trade-readiness, opportunity replay, indicator replay, admission, independent execution, chart causal cutoffs, persistence, credentials and closed-market lifecycle. Run compile checks and review the complete local diff. Update this file with actual measurements and incomplete experiments.
10. Qualify on target hardware before claiming end-to-end latency. Replay a mature 3,500-stock session with burst input, recording enabled, scanner cache misses and chart rendering. Measure ingress p50/p95/p99/max, ranking time, queue age/depth, memory, CPU, disk throughput and request wait. Require no ordering loss or unexplained signal differences. Initial engineering target: p99 receive-to-process below 250 ms in steady replay and recovery from bursts within the configured freshness window. This is a target, not a measured result.

## Follow-through experiments

Chart process isolation: benchmark one warmed spawned renderer first, then two; compare complete evidence sets and metadata. Bound submissions and shut the pool down on market close. Enable only if end-to-end chart-ready latency improves under feed load. Matplotlib is [not thread-safe](https://matplotlib.org/stable/users/faq.html).

Gateway admission and durable budgets: add per-account daily accounting and bounded HTTP admission once all direct SDK/request callers are classified. Linux coordination must be tested with actual independent processes, including clock jumps, process death and corrupt state. Preserve the fact that rejected/ambiguous orders cannot be blindly retried.

Recording journal: measure whether event-state rewrites dominate after checkpoint reductions. If so, append sequence-numbered events, periodically compact an atomic checkpoint, and replay only committed later records after restart. Require crash tests before replacing the current format.

Monitor and frontend delivery: measure slow-client blocking in `WebSocketBroadcaster.send_one`, quote/depth duplication, query scan counts and rendering frequency. Bound per-client queues with explicit resynchronization rather than dropping order updates. Any UI change requires browser verification.

## Research applied

- [Python executors](https://docs.python.org/3.13/library/concurrent.futures.html): bound pending work explicitly on this Python version; avoid waiting on a dependent task in the same saturated pool.
- [WebSocket buffers](https://websockets.readthedocs.io/en/stable/topics/memory.html): larger queues add latency under sustained overload; bounded buffering must carry backpressure through the application.
- [Requests sessions](https://requests.readthedocs.io/en/latest/user/advanced/): reuse connections with clear ownership; do not share mutable request state casually across workers.
- [Python profiling](https://docs.python.org/3.13/library/profile.html): use profiling to find work, and separate unprofiled timing for speed comparisons.

## Rollback and reporting

Keep each change local and independently reviewable. Do not change trading thresholds, event schemas, account identity, quote freshness or chart evidence requirements to improve a benchmark. Revert an optimization if parity fails. Report measured local gains separately from target-server performance, and leave unqualified experiments explicitly open.

Implementation status: plan saved; application implementation has not started at this point.

## Redis addition requested during implementation

Use Redis for cross-process broker admission first. Keep rolling stock state and feed FIFOs in process memory. Configure it explicitly with `DHAN_RATE_LIMIT_REDIS_URL`; every process using one account must use the same coordinator. Leave the existing file coordinator active when Redis is not configured.

1. Add a short atomic Lua script using Redis server time and sorted sets. Key by a hash of broker client ID and API category, never by token. Token renewal must not reset budgets.
2. Check every applicable window before reserving a request. Data retains 4/s and adds the documented daily ceiling as a conservative rolling 24-hour limit. Quotes retain 1.1-second spacing. Option-chain admission checks both data and 3.1-second spacing in one atomic operation. Orders check second, minute, hour and day windows. Non-trading reads check 20/s.
3. Set expiration only after the largest window; never reset counters during reconnect. Use unique request IDs to avoid collisions. Bound time waiting for admission and fail closed on Redis errors. Do not switch to independent local budgets during an outage.
4. Verify concurrent independent clients, shared token-rotation identity, category separation, expiration, compound option limits, restart and unavailable Redis using an actual isolated container. No application credentials or production volumes enter the test containers.
5. Use a dedicated Redis database/service with `noeviction` for correctness counters. A restarted empty Redis loses budget history; its operational recovery must pause affected request traffic for the longest lost window or restore persisted state before admission resumes. AOF persistence and startup readiness are deployment requirements, not claims of exactly-once behavior.
6. Keep Redis Streams as a later alternative for the durable event archive. Consumer groups require acknowledgments, retry ownership and idempotent consumers. Redis Pub/Sub is unsuitable for replayable order events. Measure local coordination latency before moving more work into Redis.

Sources: [atomic Lua execution](https://redis.io/docs/latest/develop/programmability/eval-intro/), [Redis rate limiting](https://redis.io/tutorials/howtos/ratelimiting/), [Streams delivery and recovery](https://redis.io/docs/latest/develop/data-types/streams/).

Docker Desktop became available during this task. Local Linux and Redis validation is authorized. These containers will run tests and synthetic replay, not the credentialed trading Compose stack.

## Implemented locally

| Step | Result |
| --- | --- |
| Rolling state | Incremental ordered price windows maintain extrema and path length, including replacement of the latest sample. Value-window endpoints use binary searches. Clock reversal falls back to full scans. Baselines compile once per distinct content and interval. Retained raw histories and checkpoint schema remain unchanged. |
| Startup | Restored rolling state warms before the market socket connects. Replay reports preparation time separately. |
| Feed | A dedicated thread continuously owns the SDK loop. The FIFO holds 8,192 packets plus at most one decoded packet waiting for space. Shutdown drains both. Receiver exceptions propagate; protocol ping/pong continues during consumer stalls. |
| Recovery | Background history and coverage workers enqueue results. The consumer applies state changes and discards results from an obsolete universe/session or connection generation. |
| Signal freshness | Live calls supply processing time for expiry/cutoff gates; stale queue observations cannot create new signals. State and recording still consume them in order. Replay calls retain explicit time control. |
| Recording | Pending write jobs are bounded at eight. Every completed exception is observed and failed futures remain visible. Buffers flush at 25,000 rows as well as the time threshold. Early row flushes avoid rewriting full checkpoints. Snapshot tails are selected before copying, and nested setup state is detached. |
| Scanner | Daily scans and baseline work maintain at most twice their worker count as submitted futures. Existing worker counts and Dhan's conservative data rate remain intact. |
| Requests | Gateway coalesces identical in-flight history reads only; signal-cache prewarm also coalesces misses. Gateway admits at most 32 active POST requests. Direct HTTP calls reuse thread-local sessions. |
| Broker limits | Linux fallback state files are created under their locks. Option-chain spacing is synchronized. Optional Redis admission reserves all applicable windows atomically, including data plus option-chain together. |
| Accounts | Two account tasks per event by default, configurable up to four. Failures are isolated and results retain configured account order. Event dictionaries, local chart paths, Agno session IDs and cloud image prefixes are account-specific. New session IDs gain a hashed account suffix; existing sessions remain readable. |
| Chart work | Reuse warmed indicator frames within a chart set. Optional spawned renderers isolate Matplotlib state and have bounded submission. The default remains the existing locked renderer until target-server qualification. |
| Dashboard transport | Each WebSocket frame is serialized per connection. Socket writes and lock acquisition have bounded waits. Broadcast builds a frame once for matching clients. Slow-client disconnection relies on existing reconnect/snapshot behavior. |
| NIFTY monitoring | Snapshot serialization captures detached data under the state lock, then performs durable disk writes outside it. A separate lock prevents overlapping snapshot writes. Failure remains visible and does not advance the success timestamp. |

The Redis integration does not centralize direct TypeScript Dhan API calls, external manual clients, or other tools using the same account. All broker traffic must be accounted for before enabling a shared production budget. Redis does not replace per-account capital reservations or placement rechecks.

## Measurements and what they establish

Windows rank benchmark uses Python 3.13.3, 3,500 eligible stocks, five timed warmed passes and 75 baseline buckets. Baseline source is loaded from Git revision `c9f3030` without changing the checkout.

| Retained samples per stock | Original median | Final warmed median |
| --- | --- | --- |
| 3 | 210.9 ms | 70.4 ms |
| 300 | 549.3 ms | 92.7 ms |
| 900 | 907.8 ms | 97.4 ms |

The mature-history median is about 9.3 times faster. Warm timings exclude initial cache construction, which is now performed before socket connection for restored state. This benchmark does not include network, recording, model execution or chart rendering.

Two real nine-image chart sets took 10.26 seconds in warmed threads and 5.71 seconds in two warmed spawned processes on the laptop. Both produced nine charts per set and 1,695,753 image bytes per set. This checks generated output existence and size, not pixel identity. Existing chart tests check causal date cutoffs and technical metadata. One-process application routing also passed the real nine-image test.

Linux tests use Docker Desktop on WSL2, Python 3.13 and a two-CPU quota with 4 GB memory. A CPU quota does not emulate the i3's clock speed, caches, SSD or other office-server applications.

Replay feeds 3,500 stocks with 900 retained samples through the actual `IntraFinder.process_packet`, ranker, setup evaluation in shadow mode, and Parquet writer. It verifies packet sequence and the raw Parquet row count. It substitutes a synthetic decoded feed and a fixed market clock; it does not run real orders, account workflows, scanner cache misses or LLM calls. The measured queue delay starts after decoding, so it excludes broker transit, SDK decode time and upstream socket buffers.

| Replay | Outcome |
| --- | --- |
| First 52,500-packet burst test, rank every second, flush every five seconds | All packets recorded, but p99 delay 4.38 s; queue filled. Failed latency target. |
| After indexed value windows, same burst load | All packets recorded; p99 1.31 s, peak queue 5,921, zero full-queue waits. |
| Paced input, normal five-second rank cadence, before incremental prices | All packets recorded; median 0.34 ms, p95 259 ms, p99 392 ms. |
| Incremental prices and preconnection preparation, paced input | All packets recorded; median 0.39 ms, p95 141 ms, p99 340 ms; no full-queue waits. Preparation 1.06 s. |
| Same paced input, 5,000-row recording limit experiment | p99 353 ms, no material gain. Keep the 25,000-row default to avoid unnecessary small files. |
| Final 210,000-packet, sixty-second paced replay | Every packet recorded in order; median 0.44 ms, p95 153 ms, p99 320 ms, maximum 437 ms. Peak queue 1,524 with zero full-queue waits. Peak RSS about 1,236 MiB. Includes raw recording and final drain. |

The 250 ms p99 target is not yet demonstrated under all tested conditions. The packet path is bounded and much faster, but ranking and checkpoint/status work still create latency spikes. No claim of fully optimized live-market behavior follows from these tests.

The real Dhan SDK was separately tested against a local WebSocket server with binary Full packets. It subscribed 250 instruments in batches of 100, 100 and 50, decoded twenty ordered five-level packets, and answered a server ping while a two-entry consumer queue was full. No Dhan credentials were used.

## Configuration and reproduction

Defaults apply without changing existing environment files:

- `INTRA_FINDER_INGRESS_CAPACITY=8192`
- `INTRA_FINDER_IO_PENDING_LIMIT=8`
- `INTRA_FINDER_RECORDING_ROW_LIMIT=25000`
- `ACCOUNT_EVENT_WORKERS=2`, maximum four per event; existing event admission still bounds the number of events.
- `CHART_RENDER_PROCESSES=0`, optional one or two. Keep zero until comparing complete feed-plus-chart load on the office server.
- `DHAN_RATE_LIMIT_REDIS_URL` unset. Set consistently for every Python process sharing an account when deliberately switching coordinators. Never run a mixture of independent Redis and file budgets for one broker identity.

Run from the repository root:

```powershell
$env:PYTHONPATH = 'python-backend'
& 'python-backend/trade/Scripts/python.exe' -m pytest python-backend/tests -q
& 'python-backend/trade/Scripts/python.exe' -m pipeline.research.latency_benchmark --baseline c9f3030
& 'python-backend/trade/Scripts/python.exe' -m pipeline.research.latency_benchmark
docker build -t trader-latency-test:local -f python-backend/Dockerfile .
docker compose -f docker-compose.validation.yml build tests
docker compose -f docker-compose.validation.yml run --rm tests
docker compose -f docker-compose.validation.yml down
docker run --rm --network none --cpus 2 --memory 4g trader-latency-validation:local python -m pipeline.research.feed_latency_replay --rounds 60 --paced --rank-interval 5 --flush-seconds 300
docker run --rm --network none trader-latency-validation:local python -m pipeline.research.dhan_feed_smoke
```

The validation Compose file is separate from the credentialed trading stack. Its Redis data is disposable, its network is internal, and it publishes no ports. Its Dockerfile copies only backend code/tests and the two UI contract fixtures needed by tests. The validation image was checked to contain no root/backend `.env` or runtime secret directory.

## Work still requiring separate evidence

1. Sustained real-feed qualification across the entire market session, including opening bursts, lunch, reconnect, universe refresh and close. Record exchange/LTT age independently from local queue delay.
2. Combined scanner, chart, remote persistence and feed load on the office hardware. Choose chart worker count from total event-to-chart-ready latency and feed p99, not chart throughput alone.
3. Inventory direct Dhan callers in `app/api/dhan`, other processes and external account tools before enabling Redis budgets. Decide account-scoped quotas for each endpoint and persist coordinator state through Redis restart. Test restored AOF behavior and rollout rollback with broker traffic paused.
4. NIFTY raw NDJSON writes remain synchronous. Before adding an asynchronous journal, record their latency and implement ordered append acknowledgments, drain on SIGTERM, disk-full behavior and chart-reader handling of the final partial line. Do not silently change tick capture completeness.
5. Event-state rewrites and full checkpoints remain the recovery format. A journal/compaction replacement needs crash/replay equivalence tests and a migration strategy. This pass reduced copying and bounded write work without changing that format.
6. Convex session-list queries already use the user/update index and a bounded take. Profile payload chunk replacement and remote session loads before changing queries. No database schema, remote function, auth policy or UI layout was changed.

These are open qualification and follow-through tasks, not completed optimizations.

## Final local verification

- Windows: 225 passed, 6 skipped, 15 subtests passed. The skips are the five real-Redis checks and one Linux file-lock check.
- Linux Docker with Redis, two CPUs and 4 GB RAM: 231 passed, 15 subtests passed. This includes independent-process Redis admission and first-use file-lock contention.
- Python compilation and `git diff --check` passed. Validation Compose configuration parsed successfully.
- Real SDK WebSocket smoke test passed using only localhost.
- The application chart-process route passed the real nine-image test with one worker on Windows and with two configured workers on Linux.
- The sixty-second replay recorded 210,000 of 210,000 packets with no ordering failure or persistence error. It did not reach the 250 ms p99 target.

All edits remain uncommitted in this local checkout. Nothing was deployed to the office server, no broker order was sent, and no credential file was changed. The isolated test Redis container and network are removed after validation; the local test images remain available for reproduction.
