# Findings from the frozen daily-history comparison

Weighted averaging did not establish a useful prediction improvement. Across 2,709 later stock-session rows on 387 dates, the momentum specialist had slightly smaller forecast error than either ensemble. Learned weights were almost equal, so weighting changed very little.

| Forecast | Direction accuracy, excluding 9 flat outcomes | RMSE, bps | R2 relative to training-mean forecast |
|---|---:|---:|---:|
| Training mean | 52.481% | 122.502312 | 0.000000 |
| Momentum ridge | 52.778% | 122.422533 | 0.001302 |
| Reversal ridge | 52.704% | 122.575451 | -0.001194 |
| Joint ridge | 51.037% | 122.489879 | 0.000203 |
| Random forest | 51.259% | 122.471311 | 0.000506 |
| Equal ensemble | 52.593% | 122.463469 | 0.000634 |
| Weighted ensemble | 52.593% | 122.463463 | 0.000634 |

Training-mean direction accuracy is the relevant directional control. Comparing the ensemble only against 50% would hide the sample's positive-return imbalance. Row counts include correlated stocks and dates. R2 of 0.000634 means a 0.0634% reduction in mean squared error relative to that benchmark, not a 6.34% gain or investment return.

Inverse calibration-MSE weights were 33.3457% momentum, 33.3321% reversal and 33.3222% forest. They use only 2023-2024 forecast errors from base models fitted through 2022. No 2025-2026 evaluation result enters the weights.

A separate, explicitly posthoc five-session moving-block analysis resampled daily mean paired loss differences, keeping stocks together. The weighted-minus-training-mean squared-error difference was -9.517 bps squared, with a descriptive 95% interval from -33.563 to +14.640. Weighted-minus-momentum was +10.023, interval -14.635 to +35.435. Weighted-minus-equal was -0.001613, interval -0.007354 to +0.004267. All intervals include zero. These are descriptive uncertainty estimates with unverified stationarity/block-length assumptions, not corrected hypothesis tests or evidence of independent replication.

## Cost sensitivity

The predeclared 15 bps gate admitted only two ensemble positions. Both equal and learned ensembles used the same positions. Their total reference-price net result was +Rs67.16 with 2 bps extra cost per leg, -Rs52.17 with 5 bps, and -Rs251.05 with 10 bps. Two positions cannot estimate a reliable edge. Momentum admitted none. Reversal and joint ridge each admitted eleven positions with positive diagnostic totals, while the forest admitted thirteen and lost money. These sparse results do not justify selecting a different model after inspecting the outputs.

Daily open/close execution is idealized, including close prices that do not implement the actual broker's earlier intraday square-off. No spread, depth, latency, margin, failed order, shortability or intraday stop evidence is available. Consequently these totals are bar-price sensitivities, not common-engine account backtests or verified achievable returns.

## Verification and limits

Six focused tests pass for feature prefix causality, next-session labels, invalid-history resets, convex weights, cost direction and aligned metric cohorts. Another agent independently checked prior-day feature timing, chronological splits and fee directions. It rebuilt all 2,709 forecasts from saved ridge/scaler and forest-tree JSON. Ridge forecasts reproduced exactly; forest maximum difference was 2.13e-14 bps with float32 traversal. Actual-data feature prefix invariance through December 31, 2024 passed for every stock.

Input manifests contain zero invalid source rows in the seven selected daily files. One historical large-price discontinuity reset Reliance's rolling history. Corporate-action adjustment provenance remains unknown. The selected stocks are current survivors, not a historical point-in-time universe. A small input-validation limitation remains: the helper rejects duplicate timestamps but does not separately reject different timestamps on the same date or missing target sessions across long gaps. The actual evaluated cohort had no relevant duplicate/gap issue; future data should receive those checks before reuse.

The evidence supports retaining simple benchmarks and collecting broader point-in-time data, not deploying the blend or searching these evaluation dates for a more attractive threshold. No production strategy, broker order or live setting changed.
