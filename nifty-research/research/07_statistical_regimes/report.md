# Statistical regimes and return dependence

Research date: 1 October 2026. Revised 2 October 2026 after correcting index alignment in equal-day metrics. This separate study tests whether simple autoregression, short-window reversion diagnostics and train-only mixture regimes improve Nifty futures return forecasts. It uses the existing minute cache, changes no raw archives, and has no execution API.

Thirty-nine comparisons cover thirteen methods at 1, 5 and 15 minutes. Every result, fold and fitted regime diagnostic remains in [results.json](artifacts/results.json), [numerical-results.md](artifacts/numerical-results.md) and [predictions.parquet](artifacts/predictions.parquet). A forecast comparison does not establish option profitability.

Zero return has the lowest pooled RMSE at every horizon. This is a useful rejection of these specific simple formulas, not a proof that Nifty is inherently unpredictable.

| Horizon minutes | Scored rows | Test dates | Zero RMSE bps | Best alternative | Alternative RMSE bps |
|---:|---:|---:|---:|---|---:|
| 1 | 1,092 | 8 | 1.4819 | Historical mean | 1.4839 |
| 5 | 1,056 | 8 | 3.3824 | Historical mean | 3.4054 |
| 15 | 887 | 6 | 5.2911 | Capped OU-like fit | 5.3047 |

The study emits 3,188 horizon-labelled predictions and scores 3,035. Missing outcomes remain visible. For example, the 15-minute GMM2 has corrected equal-day MSE improvement -3.2791 bps squared, with descriptive interval -6.4315 to -0.5877. Its pooled RMSE is 5.3696 versus 5.2911 for zero. A more elaborate regime label did not improve this forecasting task.

The original equal-day calculation created a fresh loss Series with a consecutive index, then grouped it by the scored dates whose indices contained gaps after missing labels were removed. Pandas aligned the indices and silently misassigned or discarded losses. The corrected Series retains the scored row indices. This changes 36 nonzero-model equal-day means and their intervals. All 39 pooled RMSE values are unchanged, and the regenerated predictions file is byte-identical. The conclusion that zero has the lowest pooled RMSE at every horizon remains unchanged. Original outputs, code, tests and report are preserved in [pre-index-fix](artifacts/revisions/pre-index-fix/).

There are 1,523 rolling diagnostics on eleven dates. About 96.0% produce fitted phi between zero and one, with a conditional median half-life of 6.98 minutes. Yet the OU-like forecast does not beat zero at any horizon. That disconnect is exactly why a fitted half-life is not enough evidence for a reversion strategy. Median descriptive variance ratio is 0.9363, with 5th and 95th percentiles 0.5354 and 1.5943. Neither threshold policy improves pooled RMSE.

## Methods tested

- Zero return and a historical mean from previous dates.
- Five-minute momentum and its reversal, scaled by forecast horizon divided by five.
- Direct AR1 and AR5 return regressions, with Ridge regularisation 10 and 100.
- Two fixed variance-ratio rules. Ratios below 0.8 or 0.9 select reversal, above 1.2 or 1.1 select trend, and between the thresholds select zero. Signal size is the same scaled five-minute return.
- Two- and three-component Gaussian mixtures of past log five-minute variance and past five-minute return. Training responsibilities weight training target means. Test probabilities combine those means.
- A 60-minute rolling AR1 fit to log price levels, producing an OU-like forecast only when fitted phi lies between zero and one. Its forecast is capped at three times the trailing root variance for the horizon.

The mixture uses full covariance, 1e-4 covariance regularisation, three initialisations, up to 500 EM iterations and random seed 20261001. Nonconvergence stops the run instead of quietly presenting a model. No hyperparameter search selects a best variant after seeing test outcomes. All listed variants are retained.

The conditional mixture is a simple regime approximation, not Hamilton's Markov transition model. It has no transition matrix and never uses smoothed state probabilities that depend on future observations. This deliberate simpler comparison fits the small archive. The static Gaussian-mixture implementation comes from scikit-learn's primary repository. [Gaussian mixture source](https://github.com/scikit-learn/scikit-learn/blob/main/sklearn/mixture/_gaussian_mixture.py).

Hamilton's original work estimates discrete changes with a nonlinear filter. The public statsmodels example clearly distinguishes estimated regimes and smoothed probabilities. Those plots are useful retrospective descriptions, but feeding full-series smoothed probabilities into a past trading decision would leak future data. I reviewed that example; the experiment here does not claim to reproduce its Markov model. [Hamilton original paper](https://doi.org/10.2307/1912559), [statsmodels primary example](https://www.statsmodels.org/stable/examples/notebooks/generated/markov_regression.html), [source notebook](https://github.com/statsmodels/statsmodels/blob/main/examples/notebooks/markov_regression.ipynb).

## What the diagnostics mean

The descriptive variance ratio is `var(log_price[t]-log_price[t-q]) / (q * var(one-minute log return))`, with q=5 and 61 observed price levels. It uses overlapping returns. It omits Lo-MacKinlay finite-sample bias and heteroskedastic variance corrections, so it supplies no formal test statistic or p-value. The rules test whether this simple descriptor has predictive utility instead.

Lo and MacKinlay compare variances at different sampling frequencies. Their original paper also explicitly cautions that rejection of a random walk does not establish mean reversion. Their weekly US equity results cannot be assumed to apply to this minute Nifty sample. [Original author abstract](https://web.mit.edu/~alo/www/Papers/lo-mackinlay-88.html), [primary arch variance-ratio implementation reviewed](https://github.com/bashtage/arch/blob/main/arch/unitroot/unitroot.py).

An OU process has a restoring drift. Here a rolling AR1 coefficient gives an OU-like descriptive half-life `-log(2)/log(phi)` when 0<phi<1. A random walk fitted on a short finite window can also return phi below one. This fit does not prove stationarity, an equilibrium value, or a tradable reversion level. The estimated intercept and equilibrium can drift severely. The cap is an explicit research rule, not a solution to identification. [Uhlenbeck and Ornstein original paper](https://journals.aps.org/pr/abstract/10.1103/PhysRev.36.823).

## Chronology and coverage

Every day, futures security and original recording segment remains separate. Incomplete and missing minutes reset feature history. Returns use log futures prices in basis points. Labels use exact future endpoints within the same contiguous complete-minute run. Sixty minutes of valid history define the common cohort. Models train on at least three earlier usable dates and 100 earlier labelled examples. Every training label finishes before the earliest test decision.

AR and GMM standardisers fit earlier dates only. Test prices supply causal features at each decision, never later prices. Mixture target means also come from earlier dates. Forecasts are emitted even when their later outcome is missing, and scored-row counts are separate from prediction counts.

Root mean square error and mean absolute error compare forecasts to zero return. Equal-day MSE improvement uses 3,000 date resamples and seed 20261001. Positive values favour the alternative. These intervals are descriptive with very few dates and no correction for thirty-nine comparisons. Pooled loss and equal-day loss use different weights and can disagree. Direction accuracy includes zero predictions as wrong on nonflat labels; it must not be confused with an active-trades win rate.

## Reproduce

From the Trader workspace:

```powershell
python nifty-research/research/07_statistical_regimes/study.py
python -m pytest --import-mode=importlib nifty-research/research/07_statistical_regimes/test_study.py -q
```

Seven tests pass. They verify future prices do not alter earlier features, future test labels do not alter any earlier forecast, missing minutes block labels and reset history, mixture fitting ignores test labels, scalers use training rows, the variance ratio behaves correctly on a long independent-return simulation, and OU parameters recover a known stationary simulation. The missing-label regression removes interior and end-of-session labels, independently recomputes every model's per-date losses, and checks that all scored rows and dates contribute to the reported mean. The simulation checks numerical behaviour, not stationarity of Nifty.

The next experiment should use new dates, compare return dependence after realistic execution costs, and decide whether regimes improve calibration or candidate strategy selection. None of these forecast-only trials certifies a hedge, short-premium position, or option fill.
