# Stage 1: Universe Scanner

## The simple idea

Universe Scanner builds today's list of stocks worth watching. It does not ask
whether a stock is breaking out now. It asks whether the stock is a valid,
ordinary, sufficiently active and historically suitable Indian equity.

It only uses completed historical information. Today's unfinished candle and
live LTP are deliberately excluded.

## Processing order

1. Download Dhan's detailed instrument master.
2. Validate its columns and size.
3. Keep ordinary NSE `EQ` and BSE `A`, `B` and `X` equities.
4. Remove rows with invalid ISIN/security IDs or disabled trading.
5. Remove every row whose combined ASM/GSM flag is not `N`.
6. Group listings by ISIN.
7. Fetch each eligible NSE/BSE venue's completed daily history.
8. Select the venue with better historical liquidity.
9. Apply price, traded-value, ATR, history and activity filters.
10. Build previous-session intraday volume baselines for survivors.
11. Atomically publish the universe and explanation files.

## Why ISIN deduplication matters

NSE and BSE assign different Dhan security IDs to the same share. Treating both
rows as different stocks would duplicate analysis and could trigger two agents
for the same economic position. Grouping by ISIN prevents that.

Venue selection uses the median of `close × volume` for the last 20 sessions.
Median means the middle normal day; it is less easily distorted by one enormous
trade day. Active-day ratio and median volume break ties. A new venue must be at
least 20% better before replacing yesterday's selected venue, which prevents
small daily fluctuations from switching the system repeatedly.

## Historical filters

- Previous completed close: ₹100 to ₹3,000.
- Average traded value over exactly 20 sessions: at least ₹10 crore.
- Fourteen-session ATR percentage: at least 1.5%.
- At least 21 valid completed sessions.
- At least 90% of the last 20 sessions have non-zero volume.

ATR describes the stock's typical daily movement, including gaps. ATR percentage
divides that movement by price so a ₹120 stock and a ₹2,000 stock can be compared.

Insufficient history is an intentional exclusion, not an API failure. The report
keeps these reasons separate:

- `INSUFFICIENT_HISTORY`
- `HISTORICAL_FETCH_FAILED`
- `PRICE_RANGE`
- `ADV_20`
- `ATR_PERCENT`
- `INACTIVE_SESSIONS`
- `ASM_GSM`

## Outputs

Each date directory contains:

- `universe.json` and `universe.parquet`
- `exclusions.json`
- `venue-comparison.parquet`
- `run-report.json`

`results/stage1/latest.json` changes only after a successful, non-degraded run.
If Dhan's current master cannot be trusted, diagnostics are retained but the
official latest universe is not replaced.
