# One-minute option transfer

This study asks whether study02's chronological one-minute futures forecasts transfer to nearby options after execution-side prices and estimated charges. It extends the earlier five-minute replay with the actually tested one-minute horizon.

It registers 18 configurations together. Three policies use price-only regression, price plus nearby depth regression and one-minute momentum. Each uses absolute forecast thresholds of 0.5, 1 and 2 bps, and either a long call/put or a 50-point directional debit spread. There is a separate zero-position, zero-cost no-trade reference.

Contracts come from decision-time quotes, with one-second entry latency. The scheduled exit is at decision plus 60 seconds, matching the forecast horizon, so exposure lasts 59 seconds. Every quote lookup is backward-only and limited to a two-second recorded quote age. Entry and exit both require unchanged security ID, expiry, strike and option type. Unknown exits block re-entry until the next date.

No parameter or threshold is selected as a winner. Study02's one-minute nearby-depth result was already examined when this hypothesis was created. Its saved prediction file also includes only rows with known future underlying labels. This is exploratory work on that preselected coverage cohort.

## Inputs and outputs

Inputs are the one-minute subset of `research/02_orderbook_horizons/artifacts/predictions.parquet` and the validated session option caches from study01. Output `results.json` includes all configurations, dates, coverage counters, cost assumptions and source hashes. `ledger.json` preserves every entered position, including unknown exits. `report.md` gives the numerical results.

The forecast target uses sampled futures midpoints. The option replay uses recorded bid/ask prices. Missing size and exchange quote timing mean that even one-lot fills remain conditional. This is not a live fill backtest or a return-on-capital estimate.

```powershell
python research/11_one_minute_option_transfer/study.py
python -m pytest research/11_one_minute_option_transfer/test_study.py -q
```

## Primary sources checked October 2, 2026

- [Dhan Full feed documentation](https://dhanhq.co/docs/v2/live-market-feed/) specifies last-trade time and five-level quote fields. Our retained option cache has prices and receipt time but lacks saved executable size. Last-trade time does not establish quote freshness.
- [Dhan pricing](https://dhan.co/pricing/) specifies Rs20 per executed F&O order. A single option round trip has two orders; a two-leg spread round trip has four. Estimated GST, SEBI and stamp rates use the common lab configuration. Contract-note rounding is not modelled.
- [NSE fee circular effective March 1, 2026](https://nsearchives.nseindia.com/content/circulars/FA73061.pdf) gives Rs3,553 per crore of option premium for combined transaction and IPFT charges. The archive falls after that date.
- [NSE STT schedule](https://www.nseindia.com/static/products-services/equity-derivatives-securities-transaction-tax) specifies 0.15% of sold option premium from April 1, 2026. Positions here are scheduled to close before expiry settlement.
- [HftBacktest fill-model documentation](https://hftbacktest.readthedocs.io/en/latest/order_fill.html) explains replay's market-impact and liquidity-taking limitations. This study does not use its queue models or claim a replication of its exchange simulation.

Study02's primary papers motivate queue/depth forecasting. This study adds an economic translation test, not a replication of their US-equity results. Sources ground definitions and costs; they do not establish Nifty profitability.
