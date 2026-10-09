# Findings from the supplied VWAP paper

Completed on 2026-10-09. The paper was read in full. Two local experiments finished, and neither established an edge. Adding the fixed momentum confirmation did not make the transferred candle strategy profitable.

## Minute data coverage

The whole saved minute dataset contains 327 parquet files and 21,723,341 rows. The audit found 60,399 instrument-days and 43,882 complete valid regular sessions across 73 instruments. The remaining 16,517 instrument-days fail the strict full-session rule. This is a data audit, not a backtest of all 73 stocks.

The candle backtest preselected the first six available folder IDs numerically before inspecting performance. None of the earlier fixed 12-stock quote cohort has a saved minute-data folder, so the candle experiment necessarily uses a different cohort.

| ID | Saved name | Accepted sessions |
|---|---|---:|
| 4 | Twentyfirst Century Management Svcs | 374 |
| 7 | Aarti Industries | 1,200 |
| 13 | ABB | 1,174 |
| 22 | ACC | 1,200 |
| 25 | Adani Enterprises | 1,201 |
| 34 | Ador Welding | 635 |

These sum to 5,784 instrument-days across 1,201 distinct dates, from 2021-07-26 through 2026-07-24. Eligibility requires exactly 375 unique minute buckets covering 09:15 through 15:29 IST, consistent positive OHLC, nonnegative volume and positive day volume. No gaps were filled. This uses future knowledge of full-session coverage to select days and creates selection bias. Timestamp seconds are floored, but the vendor's candle-labeling convention remains unverified. Having a valid candle does not prove that its opening price was executable at the assumed size.

## Candle rule and combination

VWAP uses the paper's formula, cumulative typical price times volume divided by cumulative volume. Direction after completed minute t is long above VWAP, short below and flat on equality or unknown cumulative VWAP. The position changes at minute t+1's open. The baseline reverses on a later completed crossover and exits at the final regular candle close.

The combination requires a same-direction five-minute price return of at least 8 bps, a strictly same-direction latest-minute return and path efficiency of at least 0.3. It uses only six already completed closes. It goes to cash when confirmation fails. These are fixed conditions, not learned weights or a calibrated probability forecast.

Each name starts an independent INR 100,000 fully collateralized sleeve, giving INR 600,000 total starting capital per scenario. Equity compounds through accepted dates. Fees use the existing frozen 2026 NSE intraday schedule on all years, an explicit current-cost stress assumption. The three adverse slippage assumptions were declared before evaluation.

| Variant | Per-side slippage | Gross PnL INR | Fees INR | Net PnL INR | Ending capital INR |
|---|---:|---:|---:|---:|---:|
| VWAP direction | 0 bps | -134,563.95 | 458,152.11 | -592,716.06 | 7,283.94 |
| VWAP + momentum confirmation | 0 bps | -62,881.68 | 530,141.62 | -593,023.30 | 6,976.70 |
| VWAP direction, primary case | 1 bps | -207,826.95 | 385,619.43 | -593,446.38 | 6,553.62 |
| VWAP + momentum, primary case | 1 bps | -145,405.56 | 448,112.29 | -593,517.85 | 6,482.15 |
| VWAP direction | 5 bps | -352,756.89 | 241,180.47 | -593,937.36 | 6,062.64 |
| VWAP + momentum confirmation | 5 bps | -315,759.43 | 278,543.58 | -594,303.01 | 5,696.99 |

The two variants and three cost scenarios produced 34,704 instrument-day ledger rows and 126,515 closed trades in total. Those totals include repeated evaluations of the same dates and should not be described as independent observations or 126,515 independent forecasts.

All six sleeves lost capital in the primary case. The baseline made 20,770 round trips; the combination made 23,780. Going to cash whenever confirmation failed increased trading costs enough to outweigh its smaller gross loss. The primary baseline lost 98.91% of combined starting capital; the confirmation variant lost 98.92%.

This is a rejection of these implementations on this cohort under these assumptions. It is not a statement that the original QQQ findings were reproduced or disproved, or that every possible VWAP extension must fail.

## Later dates do not rescue the result

The specification labels dates from 2025 onward a later diagnostic. There are 1,661 eligible instrument-days in this period, but the sleeves carry their depleted earlier capital into it. The primary baseline made no trades on 1,596 of those days; the combination made no trades on 1,549. Both had negative net PnL across the later period. This is not a freshly funded 2025-2026 evaluation. Zero trading after a sleeve becomes too small to buy a share cannot count as successful risk prediction.

No parameter tuning or restart with fresh capital followed these losses. A separately preregistered fresh-capital or fixed-notional study could answer a different question, but it was not included in these completed tests.

## Shared quote comparison

This separate experiment uses vendor VWAP and completed midpoint bars. It retains the shared comparison engine's fixed 30 bps target,15 bps stop,300-second horizon,600-second cooldown, fees, latency, position limits and account loss halt. Those exit rules differ materially from the paper.

| Variant | Freshness mode | Closed trades | Realized net PnL INR | Incomplete sessions |
|---|---|---:|---:|---:|
| VWAP direction | Recent trade required | 7 | -673.72 | 1 |
| VWAP + momentum | Recent trade required | 1 | -253.95 | 0 |
| VWAP direction | Receipt proxy sensitivity | 153 | -17,683.67 | 0 |
| VWAP + momentum | Receipt proxy sensitivity | 146 | -17,530.89 | 0 |

The strict direction run has two unresolved positions in one session, 2026-08-21. Its reported PnL is realized closed-trade PnL, not a complete portfolio outcome. The last usable marks for those positions were about 6,419 seconds old at the end of the tape, so a final-mark liquidation estimate cannot make that session reliable. Receipt-proxy results allow the unverified clock assumption and remain research sensitivities. A small reduction in loss in that mode does not establish better prediction accuracy or profitability.

## Verification and limits

Eleven focused tests pass. They cover completed-bar timing, rejection of incomplete/stale observations, VWAP equality, confirmation mathematics, future-candle invariance, next-minute-open execution, adverse short-side slippage and fee reconciliation. The saved 126,515-trade ledger independently reconciles to all 34,704 daily rows, sleeve capital continuity and the frozen code/specification hashes.

Remaining limits include survivorship in locally downloaded names, ex-post full-day availability, unverifiable candle timestamp semantics, current fees applied to earlier years, and missing quote spreads, depth, market impact and borrow restrictions. Several names can be illiquid, so full-equity candle fills can be unrealistic. No learned ensemble weights, neural model, reinforcement learning, live orders, or exact QQQ/TQQQ replication ran in this track.

The reproducible commands and outputs are listed in `README.md`. The exact original method and primary source references are in `sources.md`.
