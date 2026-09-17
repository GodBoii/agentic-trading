# Live verification and bounded follow-up, September 17, 2026

## Scope and access boundary

Work started at 09:05:10 IST in the isolated worktree
`/home/arun/apps/trader-live-verification-2026-09-17` on branch
`codex/live-verification-2026-09-17`. The live checkout was inspected read-only.
It was not edited, cleaned, rebuilt, restarted, or deployed. No broker order or
credential mutation was performed.

The scheduled Codex sandbox could not connect to `/var/run/docker.sock`, use
non-interactive sudo, reach host loopback, or use systemd's service bus. Runtime
artifacts were visible by name and metadata, but their protected contents were
not readable inside that sandbox. A later direct read-only SSH check supplied
the live health measurements in the post-run section below.

## Startup checks

| Check | Observation |
| --- | --- |
| Local time | 2026-09-17 09:05:10 IST at start; before the 09:15 cash-market open. |
| NSE calendar | September 17 is a Thursday and is not in the NSE 2026 cash-market holiday list. NSE lists September 14 as Ganesh Chaturthi and normal market open as 09:15. Source: [NSE market timings and holidays](https://www.nseindia.com/resources/exchange-communication-holidays). |
| Production Git | `/home/arun/apps/trader` was on `master` at `730bd498cb5ea2394dc92320536bd02b61a50bb9`. The worktree was based on `bd4e331c99caf24a33ce67a782429dfd6f148465`; production was one UI/backend-stream-replay commit behind, but the production and worktree-HEAD blobs for `intra_finder.py` and `live_state.py` were identical. |
| Calendar artifact | Cache file refreshed at 00:00:18 IST. The official NSE calendar independently confirmed a trading day. |
| Auth health | Sanitized health file refreshed at 09:00:12, 09:15:13, and 09:30:21. This proved the health writer was active, not that credentials were valid, because its payload was unreadable in the scheduled sandbox. |
| Scanner artifact | `stage1/latest.json` was 30,042,781 bytes and last changed September 15 at 08:23:35. There were no September 16 or 17 Stage 1 artifact directories. Intra-Finder's configured fallback window is four days. |
| Feed/service activity | September 17 Stage 2 runtime and status files appeared at 09:10:14, five minutes before open. Raw-depth and one-second batches then persisted repeatedly. This is actual file-level data activity rather than a container-health inference. |
| Mode | Effective Compose interpolation was `INTRA_FINDER_SHADOW_MODE=0`, live dispatch mode. No mode was changed. |
| Redis | `DHAN_RATE_LIMIT_REDIS_URL` was absent from both production env files. Cross-process Redis admission was disabled. No Redis endpoint was probed. |
| Chart workers | `CHART_RENDER_PROCESSES` was unset, so the code default was zero spawned chart processes. |

## Live Full Packet observation

The observer started before the configured 09:10 feed start and ended at
10:16:22 IST, covering the complete first regular-session hour:

- The daily runtime/status files appeared at 09:10:14.
- At 09:15:15 the runtime checkpoint, setup-event archive, and agent dispatch
  state changed together. Auth health refreshed at 09:15:13.
- From 09:15 through 10:15, 120 raw-depth batches totaling 16,994,082 bytes
  were written from 09:15:14.492 through 10:15:37.114. Inter-batch gap median
  was 31.421 seconds, p95 35.512 seconds, and maximum 37.458 seconds.
- The same window produced 120 one-second batches totaling 339,880,760 bytes
  from 09:15:14.913 through 10:15:37.636. Inter-batch gap median was 31.205
  seconds, p95 36.923 seconds, and maximum 39.637 seconds.
- Twelve runtime checkpoints completed from 09:15:15 through 10:12:49. The
  11 checkpoint gaps were 307, 325, 322, 309, 334, 301, 304, 328, 304, 315,
  and 305 seconds. Median was 309 seconds and maximum was 334 seconds.
- The compact latest-state file continued changing approximately once per
  minute. It changed again at 10:16:45. Setup-event and dispatch-state files
  advanced together through 10:16:13, shortly after the measured hour.

These facts support active feed ingestion, detection, persistence, and event
handoff at file granularity, with no persisted-batch gap above 40 seconds. They
do not prove packet completeness or low latency.

## Post-run direct health check

A direct read-only SSH check at 13:08 IST confirmed that Intra-Finder was
healthy, connected, and in live-dispatch mode:

- Universe source date: September 15, with 3,532 expected and 3,154 observed
  instruments.
- Hot instruments: 62.
- Current rank duration: 71.002 ms.
- Current ingress delay: 1.081 ms.
- Ingress queue depth: zero; high-water mark: 4,581; full waits: zero.
- Reconnect count: one.
- Persistence pending: one; persistence error: none.
- Long-running process ingress histogram: p95 upper bucket 2,500 ms, p99 upper
  bucket 5,000 ms, maximum 15,987.959 ms across 51,569,630 observations.
- Rank histogram: p95 and p99 upper buckets 1,000 ms, maximum 4,265.646 ms.
- Checkpoint build maximum: 1,901.041 ms. Status build maximum: 2,720.535 ms.

The histograms cover the long-running process, not only September 17. They show
that current processing can be fast while tail delays remain unresolved.

## Most important confirmed problem

The September 17 scanner ran but missed publication at the 90-minute guard:

- 4,892 daily-profile cache files changed from 07:00:17 through 08:23:34.
- The scanner completed daily history for all 3,520 eligible ISINs.
- Baseline generation reached 1,500 of 3,520 stocks by 08:29:43, with 1,496
  ready.
- The parent terminated the child at the 5,400-second limit with exit code 124.
- No September 17 Stage 1 artifact directory or new `latest.json` followed.
- The scanner deferred further attempts after the premarket cutoff and used the
  last-known-good universe.

The final baseline work occurred at the hard deadline, leaving no time for the
summary, 30 MB JSON artifact, comparison files, and atomic latest publication.
Production's scanner container was unhealthy after this timeout.

A direct scanner remediation requires an operational policy choice. Safe
options have different consequences: start before 07:00, increase the 90-minute
guard, or reserve publication time by stopping baseline refresh early and
publishing lower or stale coverage. The existing records intentionally define
the 07:00 schedule, 90-minute guard, and seven-day baseline freshness, so this
work did not change them without user direction.

## Bounded code fix

The safe policy-defined correctness issue fixed in the isolated worktree was
the scanner reference refresh path. `IntraFinder.load_universe()` previously
retained an existing `LiveStockState` object without copying refreshed
historical profile, intraday baseline, corporate-action, symbol, or circuit
fields. It could therefore keep stale reference inputs after scanner recovery.

The fix adds `LiveStockState.refresh_reference_data()` and applies it to every
matching state on universe reload, including a same-day reload whose
`universe_version` is unchanged. Accumulated packets, bars, setup state, ranks,
and other live state remain on the same object. The derived-second cache is
invalidated and observed states are recalculated. New and removed instruments
retain the existing behavior. Scanner and rank formulas, top-10 admission,
detector direction, AI independence, tool access, account limits, broker
safety, and persistence/event formats are unchanged.

In a 3,500-state direct timing check, reference refresh took 35.979 ms. This is
not a live latency claim.

## Verification on Ubuntu

- `git diff --check`: passed.
- Python compilation of the two changed modules and test file: passed.
- Direct reference refresh checks: passed, including identity mismatch fail
  closed and preservation of packet/setup history.
- Targeted regression tests: two passed. The existing recent-universe fallback
  test and the new same-version reload/reference-refresh test ran against the
  real pipeline code, with import-only stubs for unavailable pandas and dotenv
  packages.
- Full pytest was not run there because host Python lacked pytest, pandas,
  NumPy, Dhan, and dotenv, while the scheduled sandbox could not access Docker.

## Remaining risks and required verification

1. Choose the scanner overrun policy: earlier start, longer guard, or bounded
   lower/stale baseline publication. Do not silently alter baseline freshness.
2. Run the complete suite and a proportionate replay before deployment.
3. After deployment, verify a same-day scanner refresh or reconnect updates
   reference fields while preserving live samples.
4. Continue reducing feed tail latency. Current latency can be low, but the
   long-running histograms still contain multi-second stalls.
5. Measure event-to-agent/current-quote timing and duplication from readable
   event and agent records.
6. Validate Dhan credentials, protected orders, and pending parents through the
   existing read-only broker path. No expiry, cancellation, or capacity-release
   policy was invented.

No production deployment, restart, broker mutation, or live configuration
change was performed during this work.
