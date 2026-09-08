# Intra-Finder implementation, September 9

Work began at local revision `bfd46e0`. Changes are local and uncommitted.
Ubuntu was used only to read and analyze historical files. No production code,
configuration, containers, orders, credentials or AI policy were changed.

## Implemented

- Pending setup confirmations reset after rank exits, stale processing,
  reconnects, restarts or gaps above five seconds. Existing cooldowns remain.
- Opening ranges track observed minutes and gaps. Historical recovery validates
  all 15 candles, records failure reasons, prioritizes observed hot stocks and
  retries within a bounded eight-request queue. Pre-open time no longer satisfies
  the opening-drive observation period.
- Daily profile refresh failures retain dated validated history up to seven days
  old. Successful-fetch metadata replaces modification-time freshness. Partial
  refreshes cannot overwrite a usable fallback, and incomplete comparisons
  cannot force a venue switch.
- Day-level event counts recover from the event archive, with a separate count
  of acknowledged writes. Run manifests identify source/configuration. Midnight
  finalization keeps the correct session date, and an empty after-close restart
  cannot erase the completed report. Torn archive tails remain inspectable and
  are separated from subsequent appends.
- Depth-window lookup skips expired ordered samples. An unordered restored
  history retains the reference scan. The value matches across all 3,510 states
  in the copied production checkpoint.
- Added a reusable offline shortlist comparison and a retained-candle option
  for the feed load test. Ranking formulas and the top-10 limit remain unchanged.

## Historical comparison

Read broad one-second data from September 2, 3, 7 and 8 on Ubuntu. Each policy
uses information recorded before a five-minute decision boundary. Labels use
the following five observed minutes, with entry and endpoint freshness checks.
The comparison includes recorded rank cutoffs at 10/30/60 and a simpler sorter
using recent traded value and price range. The latter fills up to its limit;
recorded ranks can have fewer eligible observations. Exact counts are saved.

| Date | Current top-10 median next-five-minute range | Simpler top-10 range | Current/simpler median spread |
| --- | ---: | ---: | ---: |
| September 2 | 0.798% | 0.701% | 0.075% / 0.053% |
| September 3 | 0.757% | 0.637% | 0.086% / 0.054% |
| September 7 | 0.862% | 0.724% | 0.090% / 0.060% |
| September 8 | 0.845% | 0.796% | 0.076% / 0.058% |

The simpler sorter selects more liquid stocks with tighter spreads, but less
subsequent movement. Expanding the recorded cutoff to 60 captures roughly
20–24% of eligible stock/time windows with at least a 0.5% future range, versus
roughly 6% for the top 10. It also consumes about six times the attention slots,
and the fraction of selections that move falls. This does not justify expanding
automatic dispatch or replacing the existing ranker.

These are descriptive selection results, not executable profits. They use
recorded ranks and quote summaries rather than every production book gate.
Missing future minutes are excluded, and September 8 has only 62 usable decision
times versus 68 on the other dates. Dates were previously inspected and are
not untouched holdouts. Source paths, sizes and modification times are recorded
and checked for changes during the run.

In a separate before/after replay of all 3,781,457 August 28 raw packets, without
time bucketing, the old detector emitted 86 events and the updated detector 83.
The longest armed-to-trigger interval fell from 31.93 to 6.54 seconds; intervals
over 30 seconds fell from one to zero. Both versions read the same universe and
tape. These are detector outputs before production safety/dispatch gates, not
the events originally emitted on August 28. The tape starts late and does not
qualify opening behavior. Replay runtime was 353 versus 357 seconds, showing
no material processing-speed improvement in this experiment.

## Verification and performance limits

- Initial Windows baseline: 229 passed, six environment-specific skips,
  19 subtests passed.
- Final Windows suite: 257 passed, six skips, 19 subtests passed.
- Isolated Linux suite with Redis: 262 passed, 19 subtests passed. The final
  daily-cache metadata adjustment also passed all five relevant tests on both
  platforms. The final empty-process shutdown fix also passed the Linux
  observation-integrity and lifecycle tests. The temporary Redis container/network
  was removed afterward.
- Python compilation and repository whitespace checks passed.
- A 105,000-packet Windows replay recorded all packets in order, without full
  queues or persistence failures. p99 delay was 261 ms. It used mature rolling
  samples but no retained candles.
- A stronger two-CPU Linux replay included 70,000 retained candles and wrote
  checkpoints every five seconds. All 210,000 packets were recorded in order;
  no full-queue waits or persistence error occurred. p99 delay was 570 ms,
  maximum 724 ms, peak RSS about 1,256 MiB. This stresses checkpoint frequency
  more than production and does not meet the 250 ms target.
- The depth lookup microbenchmark improved from 0.543 to 0.317 seconds for
  100,000 mature-window calculations. Full production-checkpoint status capture
  remained about 26 ms locally; compact checkpoint capture changed from about
  72 to 75 ms after adding coverage fields. No overall latency win is claimed.

## Deployment and next evidence

The correctness fixes are tested locally. Production still needs the user's
normal deployment process. A first deployment during a running session will
mark legacy opening ranges unverified and recover them within the shared
history budget; a premarket deployment avoids that mid-session transition.

Keep current selection and AI independence. Collect untouched complete sessions
with the new continuity/coverage metadata before changing shortlist size or
repetition policy. Remaining latency work needs measurements across real
checkpoint intervals and combined chart/feed load. Optional chart workers,
NIFTY monitoring and Redis production coordination are not qualified by this
offline test suite.

## Reproduction and artifacts

From the repository root, with `PYTHONPATH=python-backend`:

```powershell
python -m pipeline.research.selection_comparison --root python-backend/results/stage2 --dates 2026-09-02 2026-09-03 2026-09-07 2026-09-08 --output progress/selection-comparison-2026-09-09.json
python -m pipeline.research.feed_latency_replay --rounds 60 --paced --rank-interval 5 --flush-seconds 5 --bars-per-stock 20
python -m pytest python-backend/tests -q
```

The latest four-day data resides on Ubuntu; the comparison module can also run
from stdin there without installing or modifying application code. Results:

- `selection-comparison-2026-09-09.json`, including source manifest.
- `observation-replay-2026-09-09.json`, including raw-tape manifest and counts.
- `production-checkpoint-comparison-2026-09-09.json`.
- `feed-replay-2026-09-09.txt` and `feed-replay-linux-bars-2026-09-09.txt`.
