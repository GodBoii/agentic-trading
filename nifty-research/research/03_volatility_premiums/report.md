# Volatility and option premium research

Research date: 1 October 2026. Offline observations from the recorded June through August archive. This study has no order placement or data-fetching capability.

Smoother intraday variance estimates outperform the very short rolling estimate in this archive. The evidence does not establish a profitable volatility strategy. The short straddle observations lose after estimated spreads and costs in every expiry-distance segment studied, even where option mid prices decline.

[All numerical results](artifacts/numerical-results.md) show every trial. The five-minute EWMA 0.94 forecast achieves QLIKE 0.6234 versus 0.7569 for the historical-mean baseline, across 1,056 forecasts on eight test dates. Its equal-day improvement interval spans -0.0525 to 0.3343. The thirty-minute log-Ridge model with regularisation 100 has pooled QLIKE 0.2706 versus 0.2830 for the baseline, but its equal-day improvement is negative. Every seemingly better method still needs additional dates.

The full study scores 2,749 horizon-labelled variance forecasts. The strict IV cohort contains 550 observations on thirteen dates, with median IV 9.792%. At least 2,215 of 2,766 eligible minute decisions fail the common-forward interval test. There are 1,430 priced fixed-contract premium observations. Their coverage restrictions are as important as their reported returns.

## What this folder tests

Thirty variance model and horizon comparisons use ten predictors at 5, 15 and 30 minutes. The predictors are the expanding prior-date historical mean, rolling 5/15/30/60-minute variance, EWMA decay 0.90/0.94/0.97, and two multiscale log-Ridge models with regularisation 10 and 100. Both Ridge models use past 5/15/60-minute mean squared returns. All trials remain in `artifacts/results.json` and `artifacts/variance_predictions.parquet`.

The option study tests two quote-age allowances, 2 and 5 seconds, and assumed continuously compounded discount rates of 0%, 5% and 10%. These rates are sensitivities, not measured historical rates. It also observes long and short fixed-strike straddles over three horizons, segmented by calendar days to expiry.

The RiskMetrics recursion is `v_t = lambda * v_(t-1) + (1-lambda) * r_t^2`. The familiar 0.94 value came from a daily RiskMetrics setting. Applying it to minutes is an experiment; it does not inherit the published daily calibration. [Original RiskMetrics document](https://www.msci.com/documents/10199/5915b101-4206-4ba0-aee2-3449d5c7e95a), [Federal Reserve evaluation](https://www.federalreserve.gov/pubs/ifdp/1997/600/ifdp600.pdf).

Corsi's HAR approach combines volatility at different horizons. The original uses substantially longer history. This folder tests an intraday approximation because sixteen uneven recording dates cannot support a credible daily/weekly/monthly HAR estimation. [Corsi original working paper](https://realvol.com/HVOLPaper.pdf), [published paper record](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1365738).

I inspected the public `arch` implementation of EWMA/HAR and `vollib` reference Black functions. I used explicit recursions and a bracketed IV solver here to keep the experiment small and avoid installing unreviewed trading repositories. The tests include the published `vollib` numerical benchmark. This is a local implementation informed by those references, not a run of the complete repositories. [arch source](https://github.com/bashtage/arch), [HAR implementation](https://github.com/bashtage/arch/blob/main/arch/univariate/mean.py), [vollib reference Black implementation](https://github.com/vollib/py_vollib/blob/master/py_vollib/ref_python/black/__init__.py).

## Forecast construction

The return is `10,000 * log(F_t/F_(t-1))`, in basis points. Realised variance is the sum of squared minute returns over the subsequent horizon. It measures recorded futures movement rather than spot variance. Different contracts never join into one return series.

The script resets history after an incomplete minute, missing minute, recording segment boundary, security change or day boundary. Every model uses the same 60-minute-history cohort for its horizon. Test dates use only labels completed before the test day begins. Training requires three previous usable dates and 100 labelled rows. Fitted transformations and log retransformation corrections use training data only.

The log models apply a training-residual smearing correction after exponentiation. Omitting this would predict a conditional geometric quantity while comparing it with arithmetic realised variance.

The principal loss is normalised QLIKE, `actual/forecast - log(actual/forecast) - 1`, with a numerical floor of 1e-8. Root-variance RMSE supplies a second view. Day-bootstrap intervals use 3,000 resamples and seed 20261001. Dates receive equal weight in those improvement intervals. Pooled headline loss gives longer recordings more weight. These different weighting schemes can disagree. The intervals are descriptive, do not correct for 30 comparisons, and involve only 5 to 8 test dates.

## Implied volatility assumptions

Nifty index options have European exercise and cash settlement, which supports European parity and pricing diagnostics. [NSE settlement rules](https://www.nseindia.com/static/products-services/equity-derivatives-settlement-mechanism). Black's formula describes discounted values using a same-expiry forward under its distributional assumptions. [Black original paper](https://doi.org/10.1016/0304-405X(76)90024-6).

Spot is absent in the archive. The monthly future is therefore not silently substituted for a weekly option's forward. The script uses backward-only CE/PE quote snapshots with at least two matched strikes at the nearest quoted expiry. CE and PE capture times must be within two seconds. At each strike, parity implies `F = K + (C-P)/discount`.

Bid and ask give a forward interval `K + (C_bid-P_ask)/discount` through `K + (C_ask-P_bid)/discount`. The study demands a nonempty intersection across the captured matched strikes. It takes the median midpoint-implied forward and clips it into that common interval. The closest strike to that forward supplies an OTM option whose IV is inverted by monotone bisection. Impossible Black prices are rejected. Expiry time is modelled as 15:30 IST on the recorded expiry date, with ACT/365 calendar time.

Capture-time synchronisation is imperfect. The archive lacks quote-origin timestamps, spot and quote sizes. Failure of the common parity interval often reflects asynchronous quotes, underlying movement, or data quality. It is not evidence of exploitable arbitrage. Conversely, passing the test does not establish executable arbitrage or fill capacity.

IV from these quotes is a risk-neutral pricing statistic. It is not a forecast of realised movement. CE and PE at the same strike linked through parity are not independent volatility measurements. The source lacks enough historical option surface information to estimate a robust skew or variance-swap rate.

The exported `iv_calendar_horizon_variance_bps2` is an explicitly mechanical scaling, `IV^2 * horizon_minutes/(365*1440) * 1e8`. Calendar time includes nights and weekends. Intraday variance has strong seasonality and receives a different share of total variance. The difference between this proxy and realised minute variance is not a measured volatility risk premium and cannot by itself justify selling options.

## Fixed-contract premium observations

At a decision minute the study chooses exact call and put IDs at one strike and expiry. Entry quotes are checked one second later. Exit quotes come from those same IDs at the chosen horizon, without rolling back to a new ATM strike. Long entry uses asks and long exit bids; short entry uses bids and short exit asks. Missing prices and paths are counted in the JSON output.

Net rupees assume one 65-unit lot, four executed orders, the existing research cost configuration, and 0.10 extra slippage points per leg transaction. That configuration includes brokerage, exchange/IPFT, SEBI fees, GST, option-sale STT and buy stamp duty. It is an estimated cost calculation. It does not model margin capital, rejected orders, queue priority, actual fills, exercise, financing, gamma hedging or execution size. [Dhan pricing](https://dhan.co/pricing/), [NSE STT](https://www.nseindia.com/static/products-services/equity-derivatives-securities-transaction-tax).

Observations overlap and intentionally probe every eligible minute. They are not independent trades and cannot be summed into portfolio returns. The coverage and parity filters select only part of the archive. Missing exits remain coverage failures rather than fabricated fills. Reported means describe the priced subset, not realised trading performance. Short straddles also have tail and margin exposures that this diagnostic cannot certify.

## Reproduce and inspect

From the Trader workspace:

```powershell
python nifty-research/research/03_volatility_premiums/study.py
python -m pytest --import-mode=importlib nifty-research/research/03_volatility_premiums/test_study.py -q
```

Dependencies are the root research environment's NumPy, pandas, PyArrow, scikit-learn and pytest. The study reads `research/01_depth_forecast_baseline/artifacts` and writes only its own `artifacts` directory. SHA-256 hashes for every option cache, the minute cache, and reused source modules are in `results.json`.

Eight tests check a published price benchmark, CE/PE parity, IV recovery, impossible prices, backward quote lookup, stale quotes, quote synchronisation, future-label alignment, gap resets and QLIKE identity.

## Architecture implication

An agent needs a separate physical variance forecast and option pricing context. A single IV number should not be treated as either. Smoother minute estimators are useful candidates for a forecast ensemble. They still need fresh dates, daypart modelling and a much longer regime sample.

The immediate data improvement is synchronised spot and same-expiry forward evidence alongside option bid/ask sizes and origin timestamps. After that, test variance forecasts against a rich option chain, build a held-out premium-selection policy, and measure actual hedging costs with the correct underlying contract. The current archive supports diagnosis; it does not support a claim that a naked short-premium system has an advantage.
