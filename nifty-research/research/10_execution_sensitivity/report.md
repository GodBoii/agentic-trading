# Execution sensitivity

24 conditional quote replays, each valued at three extra-slippage settings. Entry identities are fixed at decision time. Five-minute holding period; quote ages 2 and 5 seconds; latencies 1, 3 and 5 seconds.

| Policy / structure | Quote age | Latency | Priced / unknown | Gross INR | Net, 0.10 slip | Net, 0.50 slip | Net, 1.00 slip |
|---|---:|---:|---:|---:|---:|---:|---:|
| momentum / single | 2 | 1 | 202 / 7 | -1599.00 | -16506.10 | -27010.10 | -40140.10 |
| momentum / single | 2 | 3 | 204 / 6 | -724.75 | -15784.62 | -26392.62 | -39652.62 |
| momentum / single | 2 | 5 | 205 / 5 | -1654.25 | -16787.82 | -27447.82 | -40772.82 |
| momentum / vertical | 2 | 1 | 180 / 5 | -3331.25 | -29180.60 | -47900.60 | -71300.60 |
| momentum / vertical | 2 | 3 | 180 / 5 | -3152.50 | -29003.07 | -47723.07 | -71123.07 |
| momentum / vertical | 2 | 5 | 181 / 4 | -3760.25 | -29756.59 | -48580.59 | -72110.59 |
| price_near_depth / single | 2 | 1 | 7 / 1 | -910.00 | -1366.24 | -1730.24 | -2185.24 |
| price_near_depth / single | 2 | 3 | 7 / 1 | -919.75 | -1375.87 | -1739.87 | -2194.87 |
| price_near_depth / single | 2 | 5 | 7 / 1 | -932.75 | -1389.04 | -1753.04 | -2208.04 |
| price_near_depth / vertical | 2 | 1 | 7 / 1 | -162.50 | -1062.97 | -1790.97 | -2700.97 |
| price_near_depth / vertical | 2 | 3 | 7 / 1 | -126.75 | -1027.07 | -1755.07 | -2665.07 |
| price_near_depth / vertical | 2 | 5 | 7 / 1 | -113.75 | -1014.38 | -1742.38 | -2652.38 |
| momentum / single | 5 | 1 | 204 / 6 | -1160.25 | -16220.50 | -26828.50 | -40088.50 |
| momentum / single | 5 | 3 | 204 / 6 | -724.75 | -15784.62 | -26392.62 | -39652.62 |
| momentum / single | 5 | 5 | 205 / 5 | -1654.25 | -16787.82 | -27447.82 | -40772.82 |
| momentum / vertical | 5 | 1 | 181 / 4 | -3324.75 | -29319.40 | -48143.40 | -71673.40 |
| momentum / vertical | 5 | 3 | 180 / 5 | -3152.50 | -29003.07 | -47723.07 | -71123.07 |
| momentum / vertical | 5 | 5 | 181 / 4 | -3760.25 | -29756.59 | -48580.59 | -72110.59 |
| price_near_depth / single | 5 | 1 | 7 / 1 | -910.00 | -1366.24 | -1730.24 | -2185.24 |
| price_near_depth / single | 5 | 3 | 7 / 1 | -919.75 | -1375.87 | -1739.87 | -2194.87 |
| price_near_depth / single | 5 | 5 | 7 / 1 | -932.75 | -1389.04 | -1753.04 | -2208.04 |
| price_near_depth / vertical | 5 | 1 | 7 / 1 | -162.50 | -1062.97 | -1790.97 | -2700.97 |
| price_near_depth / vertical | 5 | 3 | 7 / 1 | -126.75 | -1027.07 | -1755.07 | -2665.07 |
| price_near_depth / vertical | 5 | 5 | 7 / 1 | -113.75 | -1014.38 | -1742.38 | -2652.38 |

Bid/ask spread is already deducted through the execution-side quotes. The half-spread diagnostic measures the difference from hypothetical midpoint fills; it must not be deducted again. Extra slippage is INR points per unit per transaction. Estimated charges use current lab assumptions applicable to these archive dates.

Increasing slippage always reduces P&L on the same ledger. Latency need not have a monotone effect in a small sample. Apparent improvement when allowing older quotes is an execution-assumption change, not new alpha.

## Sources

[HftBacktest primary repository](https://github.com/nkaz001/hftbacktest) and [fill-model documentation](https://hftbacktest.readthedocs.io/en/latest/order_fill.html) show the role of queue position, feed latency and incomplete fill evidence. This study uses only a conditional aggressive-quote model because queue position and sizes are unavailable. The repo's crypto examples are not Nifty validations.

[Dhan Full feed format](https://dhanhq.co/docs/v2/live-market-feed/) distinguishes last-trade time from quote receipt time. [NSE fee circular](https://nsearchives.nseindia.com/content/circulars/FA73061.pdf) grounds lab transaction-charge assumptions.

Run `python research/10_execution_sensitivity/study.py` from nifty-research.
