# Prediction combinations on longer daily histories

This study tests whether mixing trend, reversal and nonlinear forecasts improves next-session intraday direction. Daily features are available only after the prior session has completed. Targets use the next recorded session's open-to-close return. This is a forecasting study and idealized bar-price cost sensitivity, not an executable intraday account replay.

Seven established stocks from the earlier quote cohort were fixed before viewing these outcomes: ICICI Bank, Infosys, Reliance, Bharti Airtel, SBI, TCS and Axis Bank. Their current-survivor selection is not a historical point-in-time universe. Original daily files remain read-only and receive SHA-256 fingerprints.

Models fit 19,089 stock-session rows across 2,727 dates from 2012 through 2022. Ensemble weights use a separate 3,465 rows on 495 dates in 2023-2024. The evaluation has 2,709 rows across 387 dates from January 1, 2025 through July 24, 2026. All stocks share the same eligible prediction rows. These historical dates are chronologically separated, without a claim that the broader project has never inspected them.

## Frozen comparison

- Momentum ridge uses five- and twenty-session returns and distance from the twenty-session average.
- Reversal ridge uses the latest return, candle body, closing location and relative volume.
- Joint ridge uses all nine inputs, including range and volatility.
- A shallow random forest tests nonlinear interactions across all nine inputs.
- Equal and inverse-calibration-MSE averages combine momentum, reversal and forest forecasts.
- The fixed training-mean forecast supplies a simple benchmark.

For member forecasts p and calibration outcomes y, MSE is the mean of `(p-y)^2`. Learned weights are `(1/MSE_i) / sum(1/MSE_j)`, nonnegative and summing to one. No evaluated outcome changes coefficients, normalization, weights, thresholds or stock selection. Exact settings are in specification.json. Prior invalid bars and historical price discontinuities reset feature history; future price jumps do not select which predictions are evaluated.

The diagnostic uses a predeclared 15 bps forecast threshold, up to five positions of Rs100,000 reference notional, both directions, reference open/close prices, the frozen fee function, and extra costs of 2, 5 or 10 bps per leg. These reference prices do not establish actual spread, capacity, broker flatten timing, shortability or intraday drawdown. Its outputs are not common-engine account results.

## Run

From the repository root:

```powershell
python -m unittest discover -s research/44_daily_forecasts/tests -v
python -m research.44_daily_forecasts.run --run-name new-version
python -m research.44_daily_forecasts.analyze --run-name new-version
```

Dependencies are Python, NumPy, pandas, pyarrow and scikit-learn. Existing run directories refuse overwriting. Each run preserves method/source snapshots, data manifests, fitted ridge/scaler parameters, complete forest trees, every prediction and all cost-scenario trade rows. The separate uncertainty analysis is explicitly posthoc and cannot select or alter models.

See findings.md and sources.md for results and reviewed formulas. Compact evidence is versioned under evidence; full predictions and run snapshots stay local under runs.
