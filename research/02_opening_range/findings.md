# Initial opening-range findings

October 1, 2026. No opening-range candidate established an edge. Strict freshness permits no complete qualifying opening ranges. Receipt-proxy sensitivity loses after costs for every variant.

## What ran

Three frozen variants, seven sessions, two freshness modes produce 42 policy/session replays over the same 1,154,473 retained observations per variant. Dates and the twelve-stock prior ADV universe match the common experiment plan. Development, validation and audit dates are already inspected historical diagnostics. They are not an independent final holdout.

Ten behavioral tests pass. They cover complete causal range formation, frozen levels, one daily signal, late starts, gaps, invalid source quality, short entries, direction/VWAP filters, spread and timestamp ordering. Python compilation passes. Test output is saved in `test-results.txt`.

## Receipt-proxy sensitivity

All amounts are rupees. Each row sums separate daily accounts; it is not one compounded account. Timing and quality assumptions remain unverified.

| Hypothesis | Trades | Gross P&L | Fees | Net P&L | Positive sessions |
| --- | ---: | ---: | ---: | ---: | ---: |
| Fifteen-minute ORB | 15 | -363.73 | 1,235.80 | -1,599.53 | 0 |
| Thirty-minute ORB, opening direction | 13 | -755.72 | 1,074.47 | -1,830.19 | 0 |
| Fifteen-minute ORB, VWAP alignment | 15 | -363.73 | 1,235.80 | -1,599.53 | 0 |

The fifteen-minute baseline emits 21 signals. Fifteen fill; one expires, one fails the depth proxy and four fail drift/spread checks. Four trades stop, ten time out and one reaches its target. The thirty-minute rule emits fifteen signals and fills thirteen trades. Its six stops and seven time exits produce a loss before fees.

VWAP alignment changes no admitted trades or accounting in this sample. That result does not prove VWAP is useless; it says this filter adds no improvement to this particular eligible subset and exit configuration.

| Hypothesis | Development net | Diagnostic validation net | Historical audit net |
| --- | ---: | ---: | ---: |
| Fifteen-minute ORB | -123.92 | -1,329.61 | -146.00 |
| Thirty-minute direction | -786.54 | -1,043.65 | 0.00 |
| Fifteen-minute VWAP | -123.92 | -1,329.61 | -146.00 |

No trades occur on August 20, 21, 24 or September 1. The fifteen-minute rule rejects 788,925 observations as belonging to incomplete opening ranges; the thirty-minute rule rejects 810,822. These are repeated per-observation reasons, not counts of independent failed ranges. The largest marked drawdown across all proxy runs is Rs 1,338.81. Every replay finishes without unresolved positions or pending entries.

## Interpretation

The test is a deliberately limited opening-range adaptation. The reviewed [US paper](https://concretumgroup.com/wp-content/uploads/2026/02/A-Profitable-Day-Trading-Strategy-For-The-U.S.-Equity-Market.pdf) makes stock selection through relative opening volume central to its stronger result. Our experiment lacks that historical measurement and uses fixed short-horizon exits rather than its ATR stop and end-of-day exit. The result rejects these frozen local candidates for deployment; it does not falsify the paper's full strategy.

The slight positive development gross return of fifteen-minute ORB is smaller than fees. Validation is negative before fees. Selecting the least negative variant would still be a historical selection bias. The small trade count and seven sessions do not warrant a Sharpe or annual return claim.

## Evidence and next experiment

`runs/initial-v1/plan.json` saves parameters, input hashes, runtime and source snapshot. `comparison.csv` and session summaries retain every zero-trade and losing result. Trade files preserve actual simulated entry/exit observations. August 25 is repeated separately in `runs/repeat-check-v1`; exact comparison evidence is saved in `repeatability.json`.

Capture every received opening packet for the predefined cohort and label source quote age. Build fourteen prior-session opening-volume and daily ATR histories before attempting a faithful stocks-in-play adaptation. Preregister longer holding horizons separately and evaluate them on new dates. Do not alter these thresholds after seeing these results.
