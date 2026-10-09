# Nifty archive chart explorer

Interactive charts built from the actual futures and option recordings. The generated `artifacts/index.html` includes Plotly and chart data, so it opens offline without an account, server or API key. Candlesticks use recorded futures LTP, not spot index prices.

```powershell
python -m pip install -r nifty-research/charts/requirements.txt
python nifty-research/charts/build.py
python -m pytest -q nifty-research/charts/test_charts.py
```

Default sessions are July 28, August 20 and August 21, 2026. Use `--dates 2026-08-03 2026-08-19` for other dates, or `--all` for every available weekday recording. Repeat `--source-root PATH` to use other archive roots. Each session uses one recording directory, chosen by the largest market-packet file. It never joins overlapping recordings from separate directories.

Select a date and chart in the explorer. Search filters the chart library. Legends isolate or hide series; drag zooms and double-click resets. Export the selected chart as PNG or its plotted data as CSV. Mobile uses a native chart selector.

The gallery includes price representations, trend/momentum indicators, realised volatility, volume/flow estimates, OI, spread, microprice, deep-book liquidity and captured-contract options views. Availability depends on valid data for the selected session. The page lists chart families that require inputs missing from this archive.

## Data handling

- Files are read only. Before/after sizes and modification times detect changing inputs; SHA-256 hashes and rejected-record counts accompany every session.
- Only weekday 09:15–15:30 IST captures on the named date are accepted. This is a normal-session filter, not a full exchange calendar.
- Price candles use actual sampled LTP OHLC. The first cumulative-volume difference after a gap, reset or contract switch is unknown and contributes zero. Reset events inside a candle make that candle ambiguous, so it is omitted.
- Full-grid missing minutes stay blank. Indicators restart after gaps and incomplete candles. Complete requires packets within two seconds of each minute boundary.
- Volume profile and VWAP allocate each reported interval's volume to the latest sampled price. They are labelled proxies. Signed flow uses quote/tick rules with unclassified volume retained.
- Book sides must be uncrossed, refer to the same security ID, and be at most one second old. Each minute retains its last valid pair. Depth snapshots must also match a market packet's instrument within two seconds.
- Option quotes are sampled backward within two seconds of each cutoff. Contract identities and strikes stay fixed. The nearest captured expiry is shown. Missing quotes are blank, never carried forward indefinitely. Captured-basket PCR requires every captured contract to be fresh at a common cutoff.
- Payoffs are hypothetical expiry scenarios per option unit using fresh same-cutoff quotes, buys at ask and sells at bid. They exclude costs, margin and intraday risk. They are not historical strategy returns.

Generated data and HTML stay in the ignored `artifacts` directory. Rebuilds reuse session caches only while source file metadata and builder code match. `--rebuild` forces another read. The manifest lists available dates that were not built.

The gallery does not alter the existing research studies, production app, collectors or broker state.

Reference formats: [Dhan full feed](https://dhanhq.co/docs/v2/live-market-feed/), [Dhan full depth](https://dhanhq.co/docs/v2/full-market-depth/), [Plotly candlesticks](https://plotly.com/python/candlestick-charts/).
