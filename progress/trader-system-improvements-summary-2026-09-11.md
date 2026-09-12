# Trader system improvement record

Updated September 11, 2026.

This document consolidates the work discussed in seven Codex tasks, the implementation records already saved in this repository, the current Git history, and the September 7 through September 11 verification results. It records what changed, what the measurements support, and what remains open.

## Current position

The redesign kept the correct service boundaries and changed the work inside them.

- Universe Scanner builds a broad broker-tradable NSE/BSE equity universe and attaches historical profiles and intraday baselines.
- Intra-Finder consumes the Full Packet feed, maintains bounded live state, ranks unusual activity, and emits candidate events.
- The stock agent receives market evidence and independently chooses BUY, SELL, or no trade.
- Execution applies account capacity, affordability, freshness, broker-permission, and protected-order checks.

Before this document was added, the local repository was clean at commit `730bd49`, and `master` matched `origin/master`. The optimization, correctness, research, agent-policy, and session-review changes described below are committed. This documentation file is the only new untracked change. That does not prove that every current commit is running on Ubuntu. The last explicit production checks in the referenced tasks covered revision `bfd46e0` and later user-managed rebuilds. Production should be verified separately after deployment.

## Main improvements

### Universe Scanner

The scanner no longer tries to guess a small list of interesting stocks before the market opens. It publishes the full tradable universe, normally about 3,500 stocks, and leaves intraday selection to Intra-Finder.

Implemented changes include:

- Broad NSE/BSE universe construction with venue selection, instrument identity, historical profiles, and intraday volume baselines.
- A schema-versioned daily artifact and last-known-good fallback.
- Automatic 07:00 IST scheduling, a 07:30 premarket start cutoff, after-market recovery, a 90-minute runtime guard, weekend checks, and NSE cash-market holiday handling.
- Fail-closed behavior when the current-year market calendar is missing.
- Gateway-aware retries for temporary Dhan cooldown responses. A cooldown is no longer immediately recorded as missing history.
- Bounded worker submission. The scanner keeps a small number of requests in flight instead of creating thousands of futures at once.
- Dated historical-profile fallback. A failed refresh can retain an older validated profile instead of replacing it with unknown data.
- Venue preservation when a comparison is incomplete, so a temporary history failure does not silently switch exchanges.
- Bounded opening-range recovery with explicit failure reasons and no more than three retries per instrument.

The September 1 build published 3,535 stocks, 2,932 daily profiles, and 3,453 intraday baselines. All stocks remained in the universe even when a profile was unavailable.

### Intra-Finder architecture and correctness

The receive path was separated from expensive processing. A dedicated receiver owns the Dhan SDK loop and puts decoded packets into an ordered, bounded FIFO. One consumer owns stock-state mutation, which preserves per-stock ordering and prevents ranking or checkpoint work from stopping WebSocket reads.

Other changes include:

- An 8,192-entry bounded ingress queue with backpressure, high-water tracking, queue-full counts, and receive-to-process delay metrics.
- Stale queued observations still update state and recordings but cannot create fresh signals.
- Incremental rolling calculations and cached baseline compilation. The ranker no longer repeatedly scans every retained sample for every stock.
- Early rejection of stale or unobserved stocks before rolling-feature work.
- Bounded persistence with surfaced write failures. Completed background writes are checked instead of silently discarded.
- Smaller checkpoints that copy only retained tails and detach mutable setup state before background serialization.
- Session-aware restart and shutdown handling. An empty process can no longer overwrite a valid saved checkpoint or daily status.
- Daily event totals derived from durable records rather than one process's in-memory counter.
- Setup confirmation timers now reset when observation continuity breaks. A stock cannot leave the evaluated set for an hour and return with an old five-second timer still armed.
- Opening ranges remain unverified until the required opening-period coverage exists.
- Live-session state resets at 09:15 so pre-open samples do not contaminate the trading session.
- Selected candidates refresh acceleration, trend efficiency, and related local features before setup evaluation. `rank_as_of` and `derived_as_of` are stored separately.
- Minute bars retain the first packet's volume increment when the minute changes.

The working selection shape remains one broad feed, a top-60 working set, top-100 hysteresis reserve, and top-10 setup evaluation. Historical comparisons did not justify replacing the existing activity ranker or increasing the production setup cutoff.

### Non-AI latency and concurrency

The September 7 pass optimized the parts outside model inference:

- Mature 3,500-stock ranking improved from about 908 ms to 97 ms median in the controlled benchmark.
- A September 1 live warm rank measured 209 ms after stale-state work moved out of the expensive path.
- Two chart sets improved from 10.26 seconds to 5.71 seconds with optional spawned renderer processes.
- Chart rendering can use bounded isolated processes instead of unsafe Matplotlib threading. This remains opt-in because the target server has two physical CPU cores and shares resources with other applications.
- Independent user accounts can prepare concurrently while account-specific capacity reservations and placement checks remain serialized where required.
- Intra-Finder, scanner, persistence, chart, and request worker pools are bounded. The design avoids adding threads where the broker limit or two-core server is the real constraint.
- NIFTY snapshot data is detached under its state lock and written afterward, reducing time spent holding the lock.
- Dashboard WebSocket frames are built once for matching clients, and socket writes have bounded waits.

The result is much faster, but it has not met the tail-latency objective. The final sustained Linux replay processed and verified 420,000 packets from 3,500 synthetic stocks with no packet loss, queue-full waits, or persistence errors. Median delay was 0.51 ms, p99 was 554.03 ms, and maximum delay was 836.34 ms. The engineering objective remains p99 below 250 ms.

### Dhan requests, rate limits, and caching

Request coordination was tightened without weakening broker safety:

- Thread-local HTTP sessions reuse connections.
- Identical in-flight history reads are coalesced at the gateway. Failures are not cached as successes.
- Signal-cache prewarming also coalesces concurrent misses.
- The gateway bounds active POST requests.
- Scanner history work respects the existing conservative data-request rate.
- Linux fallback rate files are created while holding their locks.
- Option-chain spacing is synchronized.
- Optional Redis sliding-window admission coordinates data, quote, option-chain, order, and non-trading limits across processes. It uses account identity rather than access tokens, so token renewal does not reset the budget.
- Redis and process-based chart rendering remain explicit deployment options. They are not assumed active merely because their code and tests exist.

### Agent policy and execution

The scanner, agent, and execution responsibilities were separated more clearly.

- The agent input excludes detector direction, setup name, score, explanation, and legacy scanner indicator snapshots. The agent independently chooses BUY, SELL, or no trade.
- The execution layer no longer forces the scanner's proposed side.
- The numeric tool-call limit and protected-order attempt counter were removed.
- A price-drift rejection now returns the current price, quote and candle timestamps, recent candles, proposed levels, and rejection details. The agent can reassess or stop instead of receiving only a generic failure.
- Fresh current-state retrieval now starts after chart rendering and overlaps image uploads. This removes chart-render time from the initial quote age without adding a broker request.
- A just-fetched candle history can be reused instead of fetched again.
- Account capacity is checked and reserved before chart generation and model work, then checked again before placement.
- Capital tiers are three active trades below Rs 2,000, five from Rs 2,000 through Rs 5,000, and ten above Rs 5,000. Total account capital includes used margin. Manual allocation can lower the effective limit when funds cannot support the tier.
- Admission diagnostics now record positions, active orders, reservations, occupied instrument keys, pending parent IDs, and pending-order ages.

Pending accepted entries still occupy a slot until the broker reports a terminal state. This is deliberate. Ignoring an unfilled entry could allow a late fill to exceed the account limit.

## What the recorded sessions showed

The measurements changed several earlier assumptions.

- Intra-Finder does find moving stocks. On September 7 and 8, selected stocks had a median subsequent five-minute observed range near 0.9%.
- Detector direction was not reliable enough to control the trade. Fewer than half of those stocks finished five minutes later in the detector's direction. Keeping the agent independent is supported by the evidence.
- The existing activity ranker remained the best tested default. Eight formulas were compared across six days. On the untouched September 10 comparison, the existing ranker scored 22.52% on the defined sustained-move label. The closest alternative scored 22.42%.
- A simpler recent-turnover sorter found tighter spreads but less subsequent movement. It was a tradeoff, not a better replacement.
- Replaying 3.78 million August 28 packets after the continuity fix changed 86 events to 83 and reduced the longest confirmation interval from 31.93 seconds to 6.54 seconds.
- September 9 produced 660 signals across 118 stocks, 35 AI runs, and 26 submitted orders. Twenty-three entries filled and 22 closed. There were nine winners and 13 losers, totaling minus Rs 24.17 before fees and excluding open TCC exposure.
- Median signal-to-AI start was 26.3 seconds. Median first order attempt was about 100.4 seconds. On the 23 filled entries, median signal-to-fill delay was 129 seconds, and 14 had less subsequent 15-minute movement left at fill than at signal.
- Full trade slots, not poor ranking alone, blocked many candidates. Positions and pending entries explained 416 of 417 full-slot blocks in the September 10 admission audit. One MCL entry held a slot for 309 minutes and Jaykay held one for 193 minutes.
- Saved quotes were already 22.58 seconds old at context construction at the median before current-state retrieval was moved after chart rendering.
- All 26 AI-submitted Super Orders had correctly positioned target and stop-loss values matching Dhan records. Protection did not remain clean in every case. TCC had opposite positions on different exchanges with cancelled BSE protection, Graphite closed through a separate order after its protected exit failed to close it, and Pashupati was closed while linked legs still appeared pending.

These results describe observed price paths and broker records. They do not prove a profitable strategy. The sample includes development days, shadow-mode days, restarts, incomplete profiles, and only one untouched day for the final ranking comparison.

## Verification completed

Test counts grew as the work expanded. They are checkpoints, not numbers to add together.

- Trading policy pass: 207 tests and 15 subtests.
- Initial non-AI Linux optimization pass: 231 tests and 15 subtests.
- Live qualification pass: 235 Linux tests and 19 subtests.
- Observation-correctness pass: 257 Windows tests and 262 Linux tests, followed by focused checks for the final restart fix.
- September 11 final Windows pass: 278 tests, six environment-specific skips, and 19 subtests.
- September 11 isolated Linux and Redis pass: 284 tests and 19 subtests, with no skips.
- The real Dhan SDK WebSocket smoke test confirmed batched subscriptions, ordered packet delivery, and continued ping/pong processing while the consumer queue was full.
- Git diff validation and independent review of the production changes found no actionable correctness issue.

Tests cover feed ordering and backpressure, persistence failures, mature histories, setup continuity, opening coverage, restart behavior, temporal leakage, minute-volume conservation, cache fallback, Dhan admission, account isolation, tool retries, quote freshness, Redis coordination, and Windows/Linux behavior.

## Remaining work

The project is improved, but these items are still open:

1. Reduce sustained feed tail latency. The 554 ms Linux replay p99 still misses the 250 ms objective. Profile checkpoint construction, recording, status snapshots, and concurrent chart load on the target two-core host before adding more workers.
2. Define the pending-entry lifecycle. Decide when an unfilled entry expires, how cancellation is confirmed with Dhan, what to do with a late partial fill, and when a reserved slot can be released. Do not solve this by ignoring pending orders.
3. Reconcile protection failures. TCC, Graphite, and Pashupati require an explicit Super Order lifecycle audit and broker-state recovery policy.
4. Improve morning profile reliability. Dated fallback prevents data loss, but frequent scanner completion failures and large missing-profile counts still need operational diagnosis.
5. Measure live quote age and event-to-order timing after the latest preparation-order change. The code ordering is verified, but production improvement has not been measured.
6. Keep collecting untouched sessions. One holdout day is not enough to approve a ranking or detector change.
7. Verify the latest `master` on Ubuntu after deployment. Check the commit, container health, universe artifact, feed connection, ingress histograms, persistence status, shadow/live setting, Redis setting, and chart-worker setting.
8. Treat AI inference latency as a separate project. It was deliberately excluded from the non-AI optimization work, although the recorded signal-to-order delay shows that it matters to trade quality.

## Source tasks and records

| Task | Main contribution |
| --- | --- |
| `01a04f68-1c2e-7eb2-8421-250adfe75196`, Redesign IntraFinder architecture | Broad-universe architecture, scanner scheduling, setup engine, live deployment, and initial rank optimization. |
| `01a061ae-4495-7032-8be9-875c214d18aa`, Analyze Infra Finder data | Three-day and agent-funnel research, missing scanner-to-agent contract findings, latency and outcome analysis. |
| `01a07a37-d140-7aa1-8e21-ce4d91c287fb`, Update trade limits and agent access | Balance tiers, early capacity admission, unlimited tool calls, independent direction, and richer price-rejection evidence. |
| `01a07b8b-4e0c-7111-a83d-f3d708039864`, Optimize Dhan trading system | Full non-AI implementation, Dhan coordination, benchmarks, Linux tests, and live qualification. |
| `01a07b78-58f3-7ac1-9830-b7b4c6da4f26`, Update trade limits and agent access (2) | Non-AI bottleneck audit and target-server hardware constraints. |
| `01a07b85-fe6c-7b40-84f7-b379b8bcded6`, Update trade limits and agent access (4) | Duplicate audit context that confirmed feed, ranking, persistence, chart, and account-routing bottlenecks before implementation. |
| `01a081a9-2cd8-7712-abb9-81805d8c3949`, Analyze intra-finder improvements | Correctness implementation, six-day ranking research, September 9 trade review, admission audit, and final Windows/Linux verification. |

Detailed supporting records:

- [Non-AI latency implementation](non-ai-latency-implementation-2026-09-07.md)
- [Live qualification](live-qualification-2026-09-08.md)
- [Intra-Finder correctness implementation](intra-finder-implementation-2026-09-09.md)
- [Intra-Finder feed audit](intra-finder-feed-audit-2026-09-10.md)
- [Admission audit](admission-audit-2026-09-10.md)
- [Ranking research and changes](ranking-research-2026-09-10/findings-and-changes.md)
- [Final Linux verification](verification-2026-09-10/resume-verification-2026-09-11.md)
- [Trading agent policy](../docs/trading-agent-policy.md)
- [Intra-Finder v2 implementation](../docs/intra-finder-v2-implementation.md)
- [September 9 session findings](../september-09-session-review/findings.md)
