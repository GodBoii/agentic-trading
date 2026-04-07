# Dhan Latest Data APIs

This document captures the latest Dhan data API understanding used in this project as of April 7, 2026.

It is focused on the practical data features we verified in code:

- Real-time price
- Historical data for 5 years
- 20 market depth
- Option chain
- Full market depth
- Expired options data

## SDK Version Used

The project virtual environment was updated to:

```text
dhanhq==2.2.0rc1
```

This is important because older `dhanhq` versions exposed older-style APIs and did not cleanly expose the latest depth helpers we needed.

Latest stable on PyPI was `2.0.2`, but the newer pre-release `2.2.0rc1` adds newer classes like:

- `DhanContext`
- `MarketFeed`
- `FullDepth`
- `OptionChain`
- `HistoricalData`

## Authentication Model

For this project, data access is using:

- `DHAN_DATA_CLIENT_ID`
- `DHAN_DATA_ACCESS_TOKEN`

These are loaded from `python-backend/.env`.

App credentials can still exist in root `.env`:

- `DHAN_APP_ID`
- `DHAN_APP_SECRET`

Those are mainly useful for auth/token generation flows, but they are not required for basic data fetching once a valid access token already exists.

## New SDK Initialization Style

Latest SDK style:

```python
from dhanhq import DhanContext, dhanhq

dhan_context = DhanContext(client_id, access_token)
dhan = dhanhq(dhan_context)
```

This replaces the older direct initialization style:

```python
dhan = dhanhq(client_id, access_token)
```

## Test Instrument Used

The main equity instrument used in our tests is:

- `security_id = 1333`
- `exchange_segment = NSE_EQ`
- `instrument_type = EQUITY`

This is the same sample security commonly used in Dhan examples and is treated in this repo as the base equity test instrument.

For option chain, the underlying used is:

- `under_security_id = 13`
- `under_exchange_segment = IDX_I`

This corresponds to the Nifty index underlying used by Dhan examples.

## 1. Real-time Price

This checks live last traded price.

API used:

```python
dhan.ticker_data({"NSE_EQ": [1333]})
```

What it gives:

- Latest traded price
- Real-time snapshot style response

Use this when:

- You only need current price quickly
- You do not need depth, OHLC, or full quote details

## 2. Historical Data for 5 Years

This checks long-range daily historical candles.

API used:

```python
from dhanhq import HistoricalData

historical_api = HistoricalData(dhan_context)
historical_api.historical_daily_data(
    security_id="1333",
    exchange_segment="NSE_EQ",
    instrument_type="EQUITY",
    from_date="2021-04-08",
    to_date="2026-04-07",
)
```

What it gives:

- Open
- High
- Low
- Close
- Volume
- Timestamps

In our live run, this returned more than 1200 daily candles, confirming that multi-year daily history is working.

## 3. 20 Market Depth

This is not the same thing as a regular quote.

20 market depth means:

- 20 bid levels
- 20 ask levels
- price, quantity, and order count for each level

This is useful when we want to see a deeper order book instead of only the top 5 levels.

Correct API path:

- Dedicated websocket feed
- `FullDepth(depth_level=20)`

Code pattern:

```python
from dhanhq import FullDepth

feed = FullDepth(dhan_context, [(FullDepth.NSE, "1333")], depth_level=20)
feed.run_forever()
```

Important:

- This is a special depth websocket
- It is not the same as calling `quote_data()`
- It is not the same as regular `MarketFeed.Full`

In our live verification, this successfully returned:

- 20 bid levels
- 20 ask levels

## 4. Option Chain

This gives chain-level option data for an underlying, across strikes for a chosen expiry.

Correct API class:

```python
from dhanhq import OptionChain

option_chain_api = OptionChain(dhan_context)
```

Flow:

1. Get valid expiries
2. Pick an expiry
3. Fetch the option chain

Code pattern:

```python
exp_resp = option_chain_api.expiry_list(13, "IDX_I")
chain_resp = option_chain_api.option_chain(13, "IDX_I", expiry)
```

Important fix we made:

- `UnderlyingScrip` must be sent as an integer, not a string

Earlier, the request used `"13"` as a string and returned:

```text
814 Invalid Request
```

After switching to integer `13`, option chain started working.

## 5. Full Market Depth

This name is easy to misunderstand, because Dhan uses two different ideas:

### A. Regular `MarketFeed Full`

This is the normal live market feed full packet:

```python
from dhanhq import MarketFeed

feed = MarketFeed(dhan_context, [(MarketFeed.NSE, "1333", MarketFeed.Full)], version="v2")
```

This typically gives:

- LTP
- LTQ
- OHLC
- volume
- OI
- other quote-style fields
- usually only 5 depth levels in the packet

### B. Dedicated `FullDepth`

This is the newer depth product for deeper market book access.

It supports:

- `depth_level=20`
- `depth_level=200`

Code pattern:

```python
feed = FullDepth(dhan_context, [(FullDepth.NSE, "1333")], depth_level=200)
```

For 200-level depth, the docs use a dedicated websocket endpoint.

In our live verification, this successfully returned:

- 200 bid levels
- 200 ask levels

So in practical project terms:

- `MarketFeed.Full` = regular rich quote packet
- `FullDepth(20)` = actual 20-level depth
- `FullDepth(200)` = latest deep full-depth order book

## 6. Expired Options Data

Latest SDK exposes a dedicated helper for expired options:

```python
historical_api.expired_options_data(...)
```

Signature used by current SDK:

```python
expired_options_data(
    security_id,
    exchange_segment,
    instrument_type,
    expiry_flag,
    expiry_code,
    strike,
    drv_option_type,
    required_data,
    from_date,
    to_date,
    interval=1,
)
```

This is different from ordinary equity historical data because expired options need derivative-specific context like:

- strike
- option type (`CALL` / `PUT`)
- expiry code
- derivative instrument identity

In our current project, this test is still pending because we have not yet supplied a valid expired option security id and related option metadata in `.env`.

## Practical Summary

If the project needs:

- current price: use `ticker_data`
- daily candles: use `HistoricalData.historical_daily_data`
- option expiries and strikes: use `OptionChain`
- regular rich live feed: use `MarketFeed`
- true 20-level or 200-level order book: use `FullDepth`
- old expired derivative candles: use `HistoricalData.expired_options_data`

## Project File That Uses This

The current validation script is:

- `python-backend/dhan-data-api-test.py`

That script now uses the latest SDK-style objects and verifies the currently working Dhan data capabilities for this repo.

## Verified Outcome In This Project

After upgrading the SDK and fixing the implementation:

- Real-time Price: working
- Historical Data for 5 Years: working
- 20 Market Depth: working
- Option Chain: working
- Full Market Depth: working
- Expired Options Data: not yet configured with valid expired option instrument inputs

## Notes

- Dhan rate limits can affect quote/depth style endpoints if hit too quickly.
- Websocket connections should be closed cleanly after tests.
- Tokens should never be printed into logs or saved into docs.
