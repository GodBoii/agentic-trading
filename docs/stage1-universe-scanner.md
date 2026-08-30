# Stage 1: Universe Scanner

## Purpose

Universe Scanner builds the broad broker-tradable cash-equity universe. It no
longer attempts to predict which stocks will be active today. Live sorting is an
Intra-Finder responsibility.

The normal output is roughly 3,500 to 4,000 unique ordinary NSE/BSE equities and
fits inside one Dhan market-feed connection.

## Processing order

1. Download and validate Dhan's detailed instrument master.
2. Keep ordinary NSE `EQ` and BSE `A`, `B` and `X` cash equities.
3. Remove invalid identities, disabled instruments and disallowed ASM/GSM rows.
4. Group NSE/BSE listings by ISIN.
5. Select the historically more liquid venue when history is available.
6. Otherwise retain the prior venue, then prefer NSE as a deterministic fallback.
7. Attach daily historical profiles and cached intraday baselines.
8. Fetch deterministic NSE and BSE corporate-action calendars.
9. Publish the complete tradable universe atomically.

Price, ADV, ATR and active-session thresholds remain available behind
`stage1_apply_opportunity_filters`, but the production default is `False`.
Missing or short history marks a profile as unavailable and does not remove a
tradable stock.

## Historical profile

Dhan daily OHLCV provides previous close, ADV, ATR, activity ratio and venue
liquidity. Dhan intraday candles provide median same-time cumulative volume and
range baselines. Intraday profiles are cached for seven days so the daily scan
does not refetch thousands of unchanged histories.

The first broad build can take longer because the profile cache is empty.
Intra-Finder accepts a completed last-known-good universe up to four calendar
days old, so a slow profile refresh cannot prevent market-open collection.

## Corporate actions

`CorporateActionService` downloads the NSE calendar and BSE's bulk corporate
action data without AI. Split, bonus, rights, merger and demerger records mark
previous-price references as unsafe. Every ex-date action disables gap setups
for that stock while still allowing live-only activity setups.

An unavailable action source is reported in the run summary. It does not make
the instrument master unusable. Gap detection also rejects unexplained price
discontinuities above the configured historical-volatility guard.

## Identity

ISIN identifies the economic security across venues. Runtime state uses
`(exchange_segment, security_id)`. A bare security ID is not a safe cross-exchange
key.

## Outputs

Each date directory contains:

- `universe.json` and `universe.parquet`
- `exclusions.json`
- `venue-comparison.parquet`
- `run-report.json`

The summary separates master eligibility, historical-profile coverage,
intraday-baseline coverage and corporate-action source health.

The broad-universe contract uses baseline schema version 3. Deployment forces
one new Stage 1 publication instead of mistaking an older filtered universe for
the new contract.
