# Findings

The fixed Kalman/CUSUM combination did not demonstrate improved accuracy or a profitable edge. It lost less money in total because it took fewer trades. Its net trade win rate and loss per trade were worse than Kalman alone.

The original track plan froze three variants before outcomes were available. All 42 planned account replays completed across seven sessions and 12 fixed prior-universe stocks. The strict `recent_trade` gate produced zero trades for every variant. All active results below use the `receipt_proxy` sensitivity assumption, which does not verify quote age or missing freshness metadata.

| Rule, receipt sensitivity | Trades | Net profitable trades | Net trade win rate | Gross PnL after fill slippage | Fees | Net PnL | Mean net PnL per trade |
|---|---:|---:|---:|---:|---:|---:|---:|
| Kalman trend | 105 | 26 | 24.76% | -Rs 3,246.39 | Rs 7,471.42 | -Rs 10,717.81 | -Rs 102.07 |
| CUSUM continuation | 164 | 32 | 19.51% | -Rs 4,924.56 | Rs 12,715.76 | -Rs 17,640.32 | -Rs 107.56 |
| Same-direction AND combination | 59 | 10 | 16.95% | -Rs 2,714.89 | Rs 4,364.86 | -Rs 7,079.75 | -Rs 120.00 |

Each row represents a separate simulated account replay, with the same risk/fee/execution rules. Do not add these PnLs to infer an ensemble account. Signals, stocks and dates overlap.

| Rule, later four diagnostic sessions | Trades | Net trade win rate | Net PnL | Mean net PnL per trade |
|---|---:|---:|---:|---:|
| Kalman trend | 47 | 19.15% | -Rs 6,148.42 | -Rs 130.82 |
| CUSUM continuation | 91 | 15.38% | -Rs 10,064.20 | -Rs 110.60 |
| AND combination | 28 | 7.14% | -Rs 4,707.42 | -Rs 168.12 |

The later four sessions retain the shared program's validation/audit labels. They are previously inspected history, not a new holdout. These fixed models were not fitted or tuned on the first three sessions. The split is descriptive.

CUSUM hit the daily loss stop on all seven receipt-proxy sessions; Kalman did on three and the combination on one. A risk stop can truncate the trade sample and does not make the signal predictive. All three active variants had negative gross PnL before explicit fees as well as negative net PnL.

Net trade win rate counts realized trades whose PnL exceeds fees. It is not raw direction accuracy, probability calibration or an independent statistical estimate. No claim of a 24.76% price forecast accuracy follows from Kalman's 24.76% net trade win rate. A learned weighted ensemble was not tested in this track. The only combination here is the predeclared agreement gate.

Verification passed for every planned session and trade ledger, causal fill chronology, gross-minus-fees accounting, source snapshot digest, unchanged policy files, all seven normalized input hashes, frozen hypothesis/source-manifest hashes and seven pinned upstream files. Twelve focused tests passed for Kalman arithmetic/covariance, CUSUM thresholds/resets, completed-bar timing, quote/gap resets, per-instrument state, combination direction and future-prefix invariance.

`evidence-verification.json` and `trade-metrics.csv` contain the checked outcomes. `runs/initial-v1/plan.json` freezes the hypothesis and upstream-manifest hashes alongside the strategy/source and input hashes before the replay loop. Source review and formula choices appear in `sources.md`; pinned upstream code is inert text under `upstream`. `chronology.json` records observed filesystem timing and hashes. Filesystem times are descriptive evidence, not a tamper-proof registry.

No production trading code, orders or live AI agents changed. The evidence rejects promotion under the current assumptions. A larger untouched, timestamp-verified sample and stronger fill-capacity evidence would be needed before revisiting live claims. These results concern our fixed adaptations and local cohort. They do not assess all strategies or all models offered by the reviewed repositories.
