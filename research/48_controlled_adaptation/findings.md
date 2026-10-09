# Adaptation results

The completed run found no reliable forecast improvement from these four fitting schedules. Every later-period method was worse than predicting zero return on both MAE and RMSE at all three horizons. The controlled gate accepted no updates.

The dataset has 277,704 shared opportunities across 12 stocks. Training uses 119,238 rows on 485 dates in 2022-2023. Validation uses 61,719 rows on 245 dates in 2024. The later diagnostic uses 96,747 rows on 384 dates in 2025-2026. This is an already available historical dataset, not an untouched holdout.

All methods use the same 21 shared causal price, volume, VWAP, peer and time-of-day features. Features belong to a completed minute, orders reserve capital at the decision time, and entry references occur a full minute later. Account exits occur 5, 15 or 30 minutes after entry. The account reserves up to INR100,000 per position with three slots, resets INR500,000 capital daily and stops opening positions after INR2,500 realized daily loss. Current NSE fees apply to all years as a counterfactual assumption. The primary fill penalty is 2bps per side; 5bps is the declared stress.

## Primary 15-minute results

These figures are for the combined 2025-2026 later diagnostic and the primary 2bps-per-side account assumption. Accuracy excludes observations with exactly zero realized return.

| Method | MAE bps | RMSE bps | Direction accuracy | Trades | Net PnL INR |
|---|---:|---:|---:|---:|---:|
| Zero return forecast | 21.5204 | 32.7006 | Undefined | 0 | 0 |
| Static ridge | 21.5639 | 32.7414 | 50.80% | 16 | -2,040.39 |
| Expanding monthly | 21.5453 | 32.7286 | 50.73% | 9 | 2,293.16 |
| Rolling 12 months | 21.5717 | 32.7370 | 50.10% | 43 | -4,101.11 |
| Recency, 90-date half-life | 21.5566 | 32.7282 | 50.42% | 29 | -43.18 |
| Controlled selector | 21.5639 | 32.7414 | 50.80% | 16 | -2,040.39 |

Expanding fitting improved MAE against static by only 0.0185bps, roughly 0.086%. It remained worse than zero-return forecasting. Its positive account result came from nine trades across 384 observed dates. At 5bps per side, its combined result was INR1.54 from four trades. That does not establish a reliable profitable predictor. The unchanged controlled method exactly matches static forecasts and trades.

## Additional horizons

The fixed four schedules also ran at 5 and 30 minutes. The controlled selector was predeclared only for the primary 15-minute horizon.

| Horizon | Method | Later MAE bps | Trades at 2bps | Net PnL INR |
|---|---|---:|---:|---:|
| 5 minutes | Static | 12.4250 | 1 | -602.43 |
| 5 minutes | Expanding | 12.4215 | 2 | -1,139.18 |
| 5 minutes | Rolling | 12.4307 | 33 | -1,198.88 |
| 5 minutes | Recency | 12.4254 | 24 | -2,348.81 |
| 30 minutes | Static | 30.4950 | 81 | -7,750.67 |
| 30 minutes | Expanding | 30.4605 | 41 | 2,449.87 |
| 30 minutes | Rolling | 30.5137 | 77 | -12,201.68 |
| 30 minutes | Recency | 30.4942 | 66 | -21,814.14 |

The corresponding zero-return MAEs are 12.3952bps and 30.4380bps. None of these forecasts beat them. The positive expanding 30-minute result weakened to INR570.46 from eight trades in the 5bps stress. Its primary 2026 result was negative INR1,082.93, so its positive trading result did not persist across both later years.

Higher assumed costs change which trades pass the net-edge entry gate. A better PnL in a higher-cost row can result from rejecting losing trades, not from a beneficial execution cost. These stress rows are different admitted trade sets, not the same trades repriced under higher costs.

## Update decisions

The controlled method audited 31 monthly boundaries. Three initial boundaries lacked 60 prior validation dates. All remaining 28 retained the original model because no challenger passed both the 1% MAE improvement and nonnegative account-utility gate. There were zero accepted switches.

This is a useful rejection result. An adapting system should be allowed to retain its model when the evidence for a change is weak. It does not show that controlled switching is profitable, because no actual update qualified here. Synthetic timing tests separately exercised acceptance followed by a waiting period until a new 60-date block was outside the deployed model's training history.

The actual incumbent's coefficient hash, its final training-label timestamp, every eligible validation block, every shadow-model hash and the account utility are in the saved monthly audit. No same-month labels update a deployed coefficient vector. Expanding, rolling and recency schedules update at monthly boundaries using only matured earlier labels. The controlled schedule would wait at least 60 new observed dates after a successful refit to preserve an honest incumbent comparison.

## Verification and limits

Seven focused tests pass. They cover label maturity rather than observation-date filtering alone, rolling-window dates, date-based recency weights, immutable coefficients, cost-sensitive gate rejection, actual-incumbent validation separation and future-label invariance. The verifier checked 403 recorded deployments, 357 saved model snapshots, all 31 controlled boundaries and 104 account evaluations. Daily ledgers reconcile to summary PnL; trade ledgers reconcile fees and delayed execution ordering.

The 104 account evaluations include repeated year slices, cost scenarios and methods over the same historical opportunities. They are not independent trials. The zero-return prediction's no-trade PnL is a control outcome, not an investment return benchmark.

Remaining limitations are the shared dataset's current survivor/download cohort, ex-post full-session eligibility, unverified corporate actions and candle labeling, absent bid/ask spreads and capacity, current fees applied to earlier years, overlapping horizon outcomes and many research comparisons. Account losses stop new admissions using realized PnL; intratrade drawdown and stop execution are not observable from scheduled candle references.

No neural adaptation, learned data transformation, meta-learning or full DoubleAdapt implementation ran here. The evidence supports rejecting live promotion of these simple monthly adaptation methods. Source/specification hashes and compact results are in `evidence/`; full local replay artifacts are in `runs/initial-v1/`.
