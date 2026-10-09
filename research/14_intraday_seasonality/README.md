# Same-time-of-day continuation

This is a short-history adaptation of a published intraday periodicity hypothesis. It asks whether a stock's returns in a fixed 30-minute interval on three prior sessions predict direction in that interval on later sessions. Seven already inspected recordings cannot reproduce a finding that persists across 40 trading days.

Run `python -m research.14_intraday_seasonality.run` from the repository root. The command refuses to overwrite frozen model evidence. Run focused tests with `python -m unittest discover -s research/14_intraday_seasonality/tests -v`.

## Sources

- [Heston, Korajczyk and Sadka, intraday patterns in the cross-section of stock returns](https://arxiv.org/abs/1005.3535) and [full paper](https://arxiv.org/html/1005.3535v1). The study uses 1,715 NYSE firms during 2001–2005, half-hour cross-sectional regressions and winner/loser deciles. Daily-frequency continuation differs from short-lag reversal. This experiment instead uses twelve NSE cash instruments, three training days and own-stock slot estimates. It does not estimate the paper's regression, decile spread or 40-day persistence.
- [LEAN official TradeBarConsolidator implementation](https://github.com/QuantConnect/Lean/blob/master/Common/Data/Consolidators/TradeBarConsolidator.cs). Reviewed for explicit timed aggregation and completed-bar semantics. Our locally written slot collector consumes quote midpoints, not trade bars. No external code was downloaded or run, and the library's existence is not a trading-profit claim.

## Frozen specification

Training is exactly August19,20,21 using the fixed prior-August18 top-12 ADV universe. Evaluate August24,25,31 and September1 without updating the model. Every evaluation date must follow the latest training date. Training input hashes and all fitted slot values live both in `models/initial-v1` and the replay plan's parameters.

Anchor 30-minute slots to 09:15 IST. The training collector excludes the partial final 15-minute interval. Require at least 60 actual observations per training interval, a first quote no later than 10 seconds after its start, a last quote in its final 10 seconds, every adjacent gap no larger than 15 seconds and every observation usable under the specified freshness mode. All three sessions must provide a complete instrument/slot return; no fallback imputes missing values.

Define `r[d,i,s] = 10000 * (last_midpoint / first_midpoint - 1)` and `mean[i,s] = sum(r[d,i,s]) / 3`. The two frozen variants are:

| Variant | Direction |
| --- | --- |
| Same-slot mean | Follow the sign of the three-session mean if its absolute magnitude reaches 10 bps. |
| Same-slot unanimous sign | Apply the same mean threshold and require all three prior slot returns to share that direction. |

At most one signal attempt per instrument/slot, on the first received observation within its first 10 seconds. Only slots1–10, 09:45 through14:15 starts, admit signals. The first slot starts before common account entry hours; the14:45 slot would approach common entry cutoff/flatten. Those excluded slots stay in training diagnostics but do not trade.

Use common account/fees and next-observation aggressive fills with a30bps target,20bps stop,1790second maximum horizon,1800second cooldown,5bps maximum spread and cost-room gate. Stops and targets can exit before slot end. This controlled trading adaptation differs from the source paper's full half-hour portfolios.

Strict mode requires known freshness flags and recent trade age in training and evaluation. Receipt-proxy mode is an explicitly unverified sensitivity, not repaired freshness. Source quote age, full exchange ticks and calibrated impact remain unavailable. All variants remain ineligible for promotion; four later sessions are historical diagnostics, not pristine holdouts.
