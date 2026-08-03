# Local NSE/BSE historical stock data

This directory is populated by `scripts/fetch_dhan_stock_history.py`.

Layout:

```text
stocks-data/
  manifest.json
  universe_changes.json
  download_state.sqlite3
  NSE/
    universe.csv
    universe.parquet
    <DHAN_SECURITY_ID>/
      metadata.json
      daily.parquet
      intraday_1m/
        2025.parquet
  BSE/
    ...
```

Only ordinary shares are included (`SEGMENT=E`, `INSTRUMENT=EQUITY`,
`INSTRUMENT_TYPE=ES`). Bonds, government securities, ETFs, and derivatives are
excluded.

Daily history is requested from 1900 to today, which Dhan documents as
available back to each scrip's inception. Intraday history stores the maximum
five years of 1-minute candles in yearly Parquet files. The 5, 15, 25, and
60-minute bars are intentionally not downloaded because they can be derived
losslessly from the 1-minute data.

Commands:

```powershell
python scripts/fetch_dhan_stock_history.py --mode universe --refresh-master
python scripts/fetch_dhan_stock_history.py --mode daily
python scripts/fetch_dhan_stock_history.py --mode all
```

The full run is resumable. Re-running the same command skips completed data
ranges. Credentials are read from `python-backend/.env` using
`DHAN_DATA_CLIENT_ID` and `DHAN_DATA_ACCESS_TOKEN`.

## Current refresh status

The security master was refreshed on 2026-07-27:

- NSE ordinary shares: 2,967 (previous snapshot: 2,809)
- BSE ordinary shares: 5,483 (previous snapshot: 5,287)

The configured Dhan token currently returns `DH-901 Invalid_Authentication`.
Renew `DHAN_DATA_ACCESS_TOKEN` before starting the candle backfill. A practical
sequence is to finish the smaller inception-to-date daily run first, then start
the much larger five-year 1-minute run:

```powershell
python scripts/fetch_dhan_stock_history.py --mode daily
python scripts/fetch_dhan_stock_history.py --mode intraday
```
