# First research cycle

Completed 30 September 2026. Source archives and Ubuntu services were left intact.

## What was built and run

The lab processed the recorded futures, depth and option streams into 3,007 causal minute rows. Of these, 2,518 have a valid five-minute future label inside a continuous session segment. Comparable feature coverage leaves 2,627 decision rows. Expanding chronological training produces 1,678 predictions, with 1,602 scored labels across nine test dates, August 4 through August 21.

All original streams remain in their existing directories. Derived artifacts occupy about 27 MB. Per-stream SHA-256 hashes, quarantine counts, session resets, runtime dependency versions and code hashes are retained. Re-running the complete pipeline uses per-session caches. The regression suite has 18 passing tests, including future-data invariance, label boundaries, quote precision, chronological training, payoff risk, cost sides, session-close limits and unresolved exposure.

## Forecast results

| Model | Five-minute return RMSE, bps | Direction accuracy |
|---|---:|---:|
| Zero-return reference | 3.363 | Not directional |
| Five-minute momentum | 4.753 | 46.9% |
| Price-only Ridge | 3.425 | 50.9% |
| Price plus nearby depth | 3.410 | 53.3% |
| Price plus all depth | 3.475 | 51.5% |
| Price, depth and estimated flow | 3.468 | 50.7% |

Nearby depth improves daily MSE on eight of nine test dates. The paired day-bootstrap interval for its mean improvement is -0.334 to +0.482 bps squared. It includes zero. The deeper-book and estimated-flow additions worsen overall RMSE. Every fitted model has worse overall RMSE than the zero-return reference.

These are overlapping sampled-quote labels from a small collection of dates. The directional accuracy does not establish a profitable trade or an independent-observation significance result. Several models were compared without multiple-testing correction.

## Conditional option replay

The fixed policy opens when the predicted absolute five-minute return exceeds two basis points. It selects identities before entry, assumes a one-second execution delay, uses bid/ask prices and closes after five minutes. It skips entries whose planned exit reaches market close. Long calls/puts and debit spreads are tested separately at one assumed lot.

Every priced policy is loss-making after estimated costs. The nearby-depth single-option policy has seven priced trades with conditional net P&L of -INR 1,366.24 and one unresolved exit. Its debit-spread version has seven priced trades with -INR 1,062.97 and one unresolved exit. The momentum single-option policy has 202 priced trades with -INR 16,506.10 and seven unresolved exits.

Unresolved exits cannot be valued from sufficiently fresh saved quotes. They remain in the ledger and stop that policy for the rest of the date. The reported amounts exclude those unknown liquidation outcomes. Missing quote sizes prevent a fill/capacity claim. No account-return, intratrade drawdown, live-profit or margin claim is made.

## Architectural decision

No model or policy is promoted to live or agent execution. Keep nearby, distance-weighted liquidity as a hypothesis. Do not assume that more depth is better. Separate numerical forecasts from economic strategy valuation: a slightly better directional signal did not cover the tested options' costs and adverse movement.

The historical agent bundle contains only decision-time features, trained forecasts, valid contract candidates and source timestamps. It excludes future labels and realized P&L. Its permitted actions are no trade or recording a research hypothesis. Execution is unavailable.

## Next research decisions

1. Add synchronous spot, option sizes, IV and Greeks before fitting a strategy selector.
2. Forecast realised movement and volatility, and compare them with option-implied pricing. Preserve the first experiment as a failed directional benchmark.
3. Measure liquidity persistence near the market and test how its usefulness changes with horizon, expiry and volatility regime. Treat any work on existing dates as exploratory.
4. Add path-risk and emergency liquidation analysis. Closed-trade P&L cannot describe short-gamma or legging risk.
5. Reserve fresh, untouched sessions for confirmation. Do not optimize the two-basis-point threshold or holding time on these results and label that confirmation.

Detailed machine results, individual folds, conditional trade prices and plots are in `artifacts/v1/report.md` and the adjacent JSON/Parquet files.
