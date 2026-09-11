# Why good signals missed analysis, and what changed

This review follows every one of the 118 September 9 stock charts, all 660
signals, actual AI runs and fills, and six broad recorded market sessions.
The code changes are local. Nothing was deployed, no orders were cancelled,
and account risk limits and independent AI decisions are unchanged.

## The main finding

Several late entries followed a large move and then consolidated. That pattern
is visible in AGI, Excelsoft, Orient Green Power, Menon, Innovision, Pashupati and
TCC. But it does not follow that the ranker generally preferred sideways stocks.
At signal time, AI-selected stocks had more subsequent movement overall than
skipped stocks, even within half-hour comparison groups.

Two separate problems explain much of the gap between a good signal and a good
entry: capacity was already committed, and the market could change substantially
before preparation and analysis finished.

## Where the capacity went

Of 659 dispatched signals, 417 were blocked by the trade limit, 114 by analysis
capacity, and 64 by authorization/IP checks. Only 35 started AI analysis.

M Tek Copper's unfilled short order occupied a slot for **308.95 minutes**.
Jaykay's unfilled short occupied another for **193.28 minutes**. MCL was pending
during 406 of the 417 full-slot blocks; Jaykay during 251. Pashupati's filled
position remained open during 415. These overlapping counts must not be added.

Broker submission, cancellation and fill intervals explain five occupied slots
at 416 of the 417 blocked signal timestamps. The remaining case occurred three
seconds before the MCL submission and is consistent with an in-flight reservation.
The evidence does not demonstrate a false-cap bug. Ignoring pending orders could
let a delayed fill exceed the account limit.

Good missed signals were often already high-ranked. Texmo was rank 1 and Mangalam
rank 1 when capacity blocked them. Responsive's afternoon move and Novartis's
morning move were also missed. The detector sometimes emitted opposite directions
around the same rally, reinforcing the decision to leave BUY/SELL/no-trade to AI.

The next execution change should define when an unfilled entry expires, how to
confirm broker cancellation, and how to handle an ambiguous response or late
partial fill. That policy is not silently introduced by this research pass.
No profitable replacement-trade simulation is claimed; freeing a slot does not
tell us what an unseen AI run would decide or how long a new position would last.

## Entry timing

On the 23 filled entries, using the next observed minute open as a comparison
price, median absolute subsequent 15-minute displacement was **0.784% from
signal time** and **0.506% from fill time**. Fourteen of 23 had less displacement
remaining at the later point. Median signal-to-fill delay was **129 seconds**,
maximum **346 seconds**.

This result depends on the horizon: five-minute displacement did not deteriorate
overall. These are paired descriptive price paths, not executable returns or
proof that delay caused the losses. Graphite moved substantially after entry in
the opposite direction; that is a decision/protection problem, not a quiet stock.

Saved quote timestamps also show a preventable freshness problem: quotes were
already **22.58 seconds old at AI context creation at the median**, up to **76.49
seconds**, because the current-state request completed before chart rendering
and uploads. The implementation moves that existing request after chart rendering
and overlaps it with uploads, retaining the same request, charts and tools.
It does not impose an AI reasoning deadline or claim inference is faster.

## Eight formulas tested across six days

The experiment compares ten selections from the same fresh top-100 recorded
activity population at five-minute boundaries. A sustained-move label requires
absolute next-five-minute close displacement of at least 0.5% and a close-path
efficiency of at least 0.6. Direction is not assumed known. This is a discovery
label, not a strategy win rate.

| Selection rule | Sep 2 | Sep 3 | Sep 7 | Sep 8 | Sep 9 | Sep 10 holdout |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Existing activity rank | 18.97% | 21.14% | 21.27% | 22.61% | 18.72% | **22.52%** |
| Latest-minute range | 16.91% | 19.80% | 18.34% | 21.72% | 20.43% | 22.42% |
| Fresh share of recent range | 14.95% | 15.73% | 17.24% | 20.25% | 16.26% | 17.28% |
| Renewed volume | 11.91% | 13.83% | 13.48% | 20.68% | 18.40% | 19.45% |
| Efficient recent movement | 13.08% | 14.78% | 17.46% | 22.91% | 16.96% | 18.94% |
| Volume renewal + range | 12.09% | 14.19% | 15.21% | 18.21% | 15.94% | 18.74% |
| Expansion after compression | 10.41% | 11.56% | 14.04% | 14.72% | 13.74% | 13.92% |
| Recent traded value | 13.11% | 15.13% | 16.82% | 16.47% | 12.61% | 18.36% |

The latest-minute range rule helped on September 9 but not consistently. A simple
efficiency filter can exclude an emerging reversal or expansion before its path
looks clean. A volume burst can describe an exhausted move rather than the start
of one. The attractive compression examples in Responsive and Texmo did not make
the tested compression formula a useful replacement across days.

On September 10, subtracting entry spread from the absolute move gave **20.94%**
for existing activity versus **20.16%** for latest-minute range. This allowance is
not a complete model of fees, impact, slippage or exit costs. No tested replacement
justifies changing the production formula or top-10 cutoff.

September 2/3 were development dates, September 7 validation, and September 8/9
already-inspected confirmation dates. September 10's completed tape was exported
after the rules were frozen, and used once as an untouched comparison in this
task. One untouched day is not proof of a general trading edge.

Inputs total roughly 4.88 million observed instrument-minutes. All pre-decision
features use completed minutes. Missing minutes are not interpolated. A cumulative
volume reset invalidates the affected renewal windows instead of inventing a
quiet minute. Future-price/volume/rank mutation tests verify earlier selections
do not change. Results retain missing-label selections in selection counts.

Recorded rank values can predate their observation row because older tapes do
not store a rank-calculation timestamp. The comparison is a snapshot shortlist
experiment, not a tick-perfect production replay. Each policy has different
label coverage; exact counts, phase splits and source manifests are retained.
The first ten opening minutes are excluded from this experiment.

## Local implementation

1. Selected stocks refresh local acceleration, efficiency and related features
   once per observed second before setup checks. Cross-sectional ranking remains
   on its existing cadence. Recording exposes separate `derived_as_of` and
   `rank_as_of`, so an old rank is no longer disguised as a fresh calculation.
   The offline opportunity replay follows the same refresh behavior.
2. Minute bars preserve the volume increment arriving in the first packet of a
   new minute. Initial cumulative volume remains excluded. Attribution follows
   received packet time; exact exchange-minute attribution is unavailable across
   missing packets.
3. Admission records categorized occupancy, pending parent IDs and observed ages
   from the broker responses it already fetched. An unlinked ordinary order is
   explicitly not a confirmed entry parent. There are no extra broker requests
   and no changes to the capacity decision.
4. AI current-state retrieval is moved closer to model startup and overlaps chart
   uploads. Technical charts can still reflect the earlier candle frame; their
   timestamps remain explicit. Execution rechecks are preserved.

## Verification and remaining limits

The final Windows suite passed with **278 tests and 19 subtests**; six
platform/service-specific checks were skipped. Compilation and whitespace checks
passed. New tests cover temporal leakage,
volume resets, source identity, candidate freshness, minute-volume conservation,
pending-order diagnostics and replay/live refresh parity.

Quote preparation tests confirm chart rendering finishes before the one initial
current-state fetch, that this fetch overlaps uploads, and that context construction
waits for both. Upload errors and snapshot-error behavior remain unchanged. A
controlled timing example reduced quote age from 161.1 ms to 40.6 ms without
changing total preparation time. That proves ordering, not production latency.

Both successful 4,000-stock replays recorded all 32,000 packets. Their p99 values
varied from 365 ms to 191 ms, so no latency gain is claimed from that short
comparison. Candidate feature refresh measured about 14.8 microseconds per call.
An intervening Windows atomic-file replacement failed once and passed on retry;
the file-lock cause remains unproven and is documented.

Verification resumed on September 11 after the usage-limit interruption.
Windows again passed 278 tests and 19 subtests, with six environment-specific
skips. Docker's Linux engine was available, and the isolated Linux suite with
Redis passed all 284 tests and 19 subtests without skips. Independent review of
the production changes found no actionable correctness issues.

The saved sustained Linux replay covered 3,500 stocks and 420,000 packets over
121.62 seconds. All packet sequences were verified in storage, with no queue-full
waits or persistence errors. Processing delay was 0.51 ms at the median, 554.03 ms
at p99, and 836.34 ms at the maximum. This still misses the 250 ms objective.
The replay used synthetic packets and does not establish production latency.
See [resume verification](../verification-2026-09-10/resume-verification-2026-09-11.md).

Remaining feed stalls, quote age during slow uploads, pending-entry lifecycle
management, and occasional morning scanner completion failures require further
work. These results do not mean every pipeline path is now fully optimized.

## Artifacts

- [Every stock, with visual notes](chart-review/stock-coverage.csv)
- [All 660 signal measurements](chart-review/signal-audit.csv)
- [Chart-pattern review](chart-review/findings.md)
- [Six-day formula comparison](ranking-comparison.csv)
- [Full metrics and phase splits](ranking-comparison.json)
- [Signal-to-fill comparisons](signal-to-fill-decay.json)
- [Admission investigation](../admission-audit-2026-09-10.md)
- [Feature and volume fixes](../intra-finder-feed-audit-2026-09-10.md)
- [Frozen experiment specification](experiment-spec.md)

The ten `chart-review/charts-*.png` contact sheets cover all 118 stocks. The raw
minute data and selection rows stay in the ignored backend research directory.

For research context, order-flow imbalance has documented short-horizon price
relationships, but contemporaneous impact is not evidence that our sampled depth
predicts a future rally. Event-level quote changes are needed to test that claim;
five-level snapshots do not identify who is trading or reliably reconstruct all
cancellations. [Cont, Kukanov and Stoikov](https://arxiv.org/abs/1011.6402)
