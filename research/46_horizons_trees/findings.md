# Findings

The bounded study froze no-trade in all nine model/horizon groups. Several learned candidates made positive validation PnL but had fewer than the predeclared 100 validation trades. Those sparse positives are recorded below. They were not silently promoted or described as losses.

The strongest positive validation example was 15-minute histogram boosting with a 10 bps net entry threshold. It produced Rs 29,278.11 across 91 trades. The specification required at least 100 trades before a candidate could compete against no-trade. That rule was declared before running these outcomes, so it was retained. Positive PnL on 91 selected validation trades does not establish repeatable performance, particularly after searching thresholds and horizons.

Twelve stocks selected using 2022 traded-value history supplied 277,704 admitted decision rows. All three horizons used the same rows. Models trained on 119,238 rows across 485 sessions in 2022-2023. Validation used 61,719 rows across 245 sessions in 2024. Test used 96,747 rows across 384 sessions from 2025-01-01 through 2026-07-24. Each row represents one instrument and one completed-minute decision; rows within a date and overlapping horizons are dependent.

| Family | Horizon | Best active validation candidate by total net PnL | Trades | Net PnL | Selection outcome |
|---|---:|---|---:|---:|---|
| Momentum | 5 minutes | Lookback 5, net threshold 20 bps | 3,544 | -Rs 484,265.43 | Lost against no-trade |
| Momentum | 15 minutes | Lookback 5, net threshold 20 bps | 2,906 | -Rs 400,091.66 | Lost against no-trade |
| Momentum | 30 minutes | Lookback 5, net threshold 20 bps | 2,411 | -Rs 315,770.36 | Lost against no-trade |
| Ridge | 5 minutes | Net threshold 10 bps | 2 | Rs 1,776.69 | Fewer than 100 trades |
| Ridge | 15 minutes | Net threshold 30 bps | 1 | Rs 2,089.98 | Fewer than 100 trades |
| Ridge | 30 minutes | Net threshold 20 bps | 8 | Rs 2,981.15 | Fewer than 100 trades |
| Boosting | 5 minutes | Net threshold 30 bps | 13 | Rs 10,205.96 | Fewer than 100 trades |
| Boosting | 15 minutes | Net threshold 10 bps | 91 | Rs 29,278.11 | Fewer than 100 trades |
| Boosting | 30 minutes | Net threshold 20 bps | 70 | -Rs 20,263.72 | Fewer than 100 trades; lost |

The eligible 30-minute boosting candidate used a 10 bps threshold, made 187 trades and lost Rs 43,104.81. The table lists the highest-PnL active candidate per family/horizon, including candidates that fail minimum-trade admission. Every actual trial, including the others, appears in `runs/initial-v1/validation-trials.json`. Thresholds apply after estimated round-trip fees and two 2 bps adverse-cost legs.

These PnLs sum independent daily-reset Rs 500,000 account simulations across validation sessions. They are not a continuously compounded equity curve or a portfolio combining candidate rows. Common slot, cash reservation, exclusive-instrument and realized-loss rules apply to each separate replay. The losses above should not be added together as one traded portfolio.

After the durable policy freeze, all nine selected policies abstained on test. Their 18 test account replays at 2 and 5 bps adverse cost per leg produced zero trades and zero PnL. This is a selected abstention outcome, not evidence that trained models have perfect risk control or that future edge is impossible.

Raw forecasts were still evaluated independently of the abstention policy on the common test cohort:

| Horizon | Ridge direction accuracy | Boosting direction accuracy | Ridge RMSE, bps | Boosting RMSE, bps | Boosting R2 versus training-mean forecast |
|---|---:|---:|---:|---:|---:|
| 5 minutes | 50.25% | 50.99% | 18.7835 | 18.7805 | -0.002049 |
| 15 minutes | 50.79% | 51.34% | 32.7413 | 32.7359 | -0.001977 |
| 30 minutes | 51.12% | 51.94% | 46.0257 | 46.0057 | -0.000264 |

Boosting improved descriptive direction accuracy over ridge, but all test R2 values were negative against the frozen training-mean benchmark. A slight direction hit-rate difference does not establish an actionable after-cost forecast. Direction metrics omit exactly zero target returns, leaving 92,578, 94,391 and 95,155 direction rows for the three horizons. They are not profit probabilities or calibration measures, and no independent-sample significance claim is made.

A separately marked posthoc descriptive check applied the direction of each horizon's already frozen training-mean forecast. That constant negative sign achieved 51.91%, 51.80% and 52.35% test direction accuracy at 5, 15 and 30 minutes. It beat both learned families on this direction metric. Therefore the boosted model's roughly 51-52% hit rate cannot be presented as improvement over this simple frozen direction baseline. No selection or model changed during the check. The same `chronology-and-controls.json` records that the selection freeze predates the first test prediction file. Filesystem times are descriptive evidence, not a tamper-proof registration system.

There were six fitted models, 36 active validation entry trials, nine selection-group no-trade comparators backed by three distinct control replays, and 18 test policy/cost replays. That is 57 distinct account replays. Do not count the same three validation controls as nine extra executions.

Twelve focused tests passed before fitting. They cover fixed-grid counting, no-trade/negative/zero selection, sparse-positive rejection, deterministic ties, date-group and label-interval purging, forecast cohort validation, real shared-account capacity/timing/nonoverlap/cost behavior and independent saved boosted-tree inference. Independent review of this track's selection and fitting path found no material causal bug. The shared dataset smoke checks recomputed all delayed labels and verified future-prefix invariance on two actual stock sessions. `dataset-review.json` records that scope.

`verify.py` checks frozen source/dataset/model/selection hashes, independently reconstructs ridge and numeric boosted-tree forecasts from safe saved state, and checks every account's ledgers, causal fill chronology, capacity, exclusive-instrument intervals and gross-minus-fees accounting. Its final result is saved in `evidence-verification.json` and `verification-log.txt`.

The study remains conditional on a current locally available stock universe and ex-post full-session admission. A prior close may be the prior eligible complete session, not necessarily the immediately preceding exchange session. Candle timestamps, corporate actions, actual spreads, depth, margin and shortability remain unverified. The shared engine uses scheduled delayed candle references and a counterfactual fee schedule, with no intratrade marks. No live code or orders changed, and no candidate was promoted.
