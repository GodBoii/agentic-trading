# Findings from the first run

Ran October 1, 2026, using the existing archives and study 01 cache. Parsed 216,083 accepted Full quote packets and checked raw-file hashes against the earlier manifest. No invalid top quotes were found in this pass. Tests passed, 9 of 9.

The experiment ran 32 fitted model and horizon configurations plus 8 baseline configurations. It fit 288 day models across 9 chronological held-out dates and scored 6,401 horizon-rows. Some timestamps contribute to several horizons and overlapping return windows, so 6,401 is not the independent sample count. Each horizon uses its own common finite-feature cohort.

| Horizon, minutes | Zero-return RMSE | Price-only RMSE | Price + nearby depth RMSE | Price + deep depth RMSE | Price + observed OFI RMSE |
|---:|---:|---:|---:|---:|---:|
| 1 | 1.5259 | 1.5340 | 1.4927 | 1.5328 | 1.5352 |
| 3 | 2.6392 | 2.6791 | 2.6389 | 2.7209 | 2.6848 |
| 5 | 3.3699 | 3.4321 | 3.4156 | 3.5394 | 3.4426 |
| 10 | 4.6758 | 4.7747 | 4.7794 | 4.9425 | 4.7877 |

Errors are basis points of futures midpoint returns. These figures are forecasting errors, not strategy returns.

Nearby depth has its clearest result at one minute. Its RMSE falls about 2.7% versus price-only and about 2.2% versus zero return. It improves all nine held-out dates. The equal-day MSE improvement over price-only is 0.1149 squared basis points, with a descriptive 95% day-bootstrap interval of 0.0921 to 0.1380. Its Holm-adjusted one-sided day sign-flip p-value is 0.0547 across 28 comparisons. No added-feature comparison passes the family threshold of 0.05. Date independence and sign-flip symmetry remain unverified.

There is also a resolution limit. With nine dates, the smallest exact one-sided sign-flip p-value is 1/512. The first Holm comparison multiplies it by 28, giving 0.0547. This experiment cannot pass the 0.05 family threshold even with improvement on every date. That is a limitation of the amount of history, not evidence that the nearby-depth effect is zero. Frozen new dates are needed.

The practical observation is horizon decay. Nearby depth helps the fitted price model at one and three minutes, adds little at five, and worsens the ten-minute result. Adding deeper depth does not create a convincing additional benefit. Sampled top-quote OFI and weighted-midpoint/queue features worsen price-only RMSE at nearly every horizon. Aggregate-pressure persistence does not clearly beat the simpler nearby-depth model.

The one-minute nearby-depth observation deserves a prospective, frozen follow-up. It does not justify selecting a profitable option strategy. At a futures price near 24,000, one basis point is about 2.4 points. Forecast-error improvements of this size can disappear through spread, latency and derivatives costs. Costs were not simulated here, so no profitability conclusion is available.

The literature also needs careful interpretation. Cont et al. estimate concurrent order-flow price impact; the current study asks about later returns. Gould and Bonart study the next price change in event-level Nasdaq data. Our broker-recorded minute outcomes are a different setting. The quantity called microprice in the original cache is a weighted midpoint; it does not implement Stoikov's transition-fitted estimator.

Full results, fold dates, row counts, all feature groups, date-level errors and source audits are in the ignored local artifacts. The complete table is in `artifacts/report.md`; the machine-readable record is `artifacts/results.json`. No archive or live service was changed.

Run again from the Trader directory:

```powershell
python nifty-research/research/02_orderbook_horizons/study.py
python -m pytest --import-mode=importlib nifty-research/research/02_orderbook_horizons/test_study.py -q
```
