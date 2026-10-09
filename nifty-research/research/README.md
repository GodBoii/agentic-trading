# Nifty research programme

Each topic has its own implementation, tests, source references, numerical artifacts and report. Shared readers and payoff utilities remain in `../nifty_lab`. The raw archives remain in python-backend and are read-only inputs.

The first experiment is preserved in `01_depth_forecast_baseline`, including its output and source snapshot. Twelve topics have now been completed. Three subagents worked in parallel with the primary agent, then took different topics and independent reviews. The runtime permits four active agents including the primary, so forty simultaneous agents are unavailable here.

| Study | Topic | Report |
|---|---|---|
| 01 | Initial forecast baseline and directional option replay | [Baseline](01_depth_forecast_baseline/artifacts/report.md) |
| 02 | OFI, queue imbalance, weighted midpoint and depth horizons | [Order-book study](02_orderbook_horizons/artifacts/report.md) |
| 03 | Realised variance, EWMA/HAR approximations, IV and premium decay | [Volatility study](03_volatility_premiums/report.md) |
| 04 | Spreads, premium structures, iron structures and synthetic hedging | [Hedging study](04_options_hedging/report.md) |
| 05 | Fixed RSI, Bollinger, EMA, Donchian, opening range and reversal rules | [Indicator study](05_indicator_patterns/report.md) |
| 06 | Observation dependence, multiple comparisons and search bias | [Evaluation study](06_dependence_and_selection/report.md) |
| 07 | AR, variance ratios, OU diagnostics and trained regimes | [Statistical models](07_statistical_regimes/report.md) |
| 08 | Time, stop, target and thesis exits | [Exit policies](08_exit_policies/report.md) |
| 09 | Persistent versus transient near-price liquidity | [Liquidity persistence](09_liquidity_persistence/artifacts/report.md) |
| 10 | Latency, quote freshness and slippage | [Execution sensitivity](10_execution_sensitivity/report.md) |
| 11 | One-minute depth forecasts translated into option trades | [Forecast transfer](11_one_minute_option_transfer/report.md) |
| 12 | Expiry-distance premium behaviour and bid/ask shape checks | [Premium mechanics](12_expiry_premium_mechanics/report.md) |

`program.json` is the registry. A topic marked in progress is not complete merely because its folder exists. [SUMMARY.md](SUMMARY.md) contains the completed cross-study assessment, review corrections and limitations.

## Reproduce

From nifty-research:

```powershell
python -m pytest -q
python run_program.py --studies 05 06 --workers 2
```

The runner uses the current Python interpreter, permits at most three concurrent research scripts, and records stdout, failures, duration and script hashes under local ignored artifacts. It returns a failure when any selected study fails. It never places orders or schedules ongoing jobs. No opaque online trading repository is installed or executed. The studies adapt specific documented methods into small locally reviewed implementations.

Each report identifies original papers and public repos, the formulas actually implemented, differences from the references, data exclusions and the number of configurations examined. A thirty-minute intraday approximation to HAR is not represented as a replication of daily HAR. Weighted midpoint is not represented as the fitted Stoikov microprice. Synthetic hedging paths are not mixed with empirical Nifty returns.

## Research rules

- The existing dates are development data once examined. Chronological folds help prevent future leakage, but do not undo selection after seeing results.
- Publish every tested configuration, negative results and unknown exits.
- Keep hypothesis tests, forecast errors, conditional trade P&L and synthetic diagnostics distinct.
- Correct comparisons within each declared family and disclose the larger search across families. No combined family-wide significance claim is currently available.
- Fix contract identities at entry; apply correct bid/ask sides, costs and receipt-time freshness.
- Keep unknown exits as exposure, never zero profit. Never use future coverage to decide an entry.
- Treat short margin, quote sizes, original exchange timestamps, jump events and partial fills as missing evidence.
- No study output authorises live execution.

## Prospective follow-up

`frozen-near-depth-hypothesis.json` preserves the original 1 October freeze. `frozen-near-depth-hypothesis-v2.json` records the reviewed 2 October revision, including shared feature-code hashes. Both contain the selected one-minute nearby-depth and price models as explicit numerical coefficients, with selection history disclosed and execution disabled. The exporter requires an explicit freeze date and a new output filename, and refuses to overwrite prior evidence. Its proposed fixed thirty-session follow-up is a collection budget, not a statistical-power guarantee. The exporter does not enable a collector. No refitting, feature changes or interim winner selection should occur in the follow-up, and session dates must be checked against the NSE calendar.
