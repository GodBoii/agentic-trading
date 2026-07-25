# NIFTY Market Structure Monitor and Charts

This document records the monitor work completed in this conversation and the charting layer added on top of the saved NIFTY 200-depth data.

## Goal

The original monitor container was mostly a Stage 2 liquidity gate and did not give useful market-structure evidence. We changed the monitor into a NIFTY-focused recorder that captures what candles hide:

- 200-level resting order book depth for the front-month NIFTY future.
- Full-market packets containing LTP, LTQ, volume, OI, top-of-book depth, and buy/sell quantity fields.
- Latest JSON snapshots for agents.
- Raw NDJSON files for later chart reconstruction.
- Derived order-flow signals: CVD, imbalance snapshots, large-order wall events, and volume profile.
- Optional real-time NIFTY option feed for ATM-nearby contracts.
- Generated order-flow and liquidity charts for human review and LLM vision analysis.

## Why The Monitor Uses NIFTY Futures

NIFTY 50 itself is an index, not a tradeable order book. For market depth we record the front-month NIFTY futures contract. The recorder still resolves the NIFTY index as context, but the primary depth instrument is the front-month `FUTIDX` contract from the security master.

The Dhan SDK must subscribe this instrument on `NSE_FNO`. A previous issue subscribed the futures security id as `NSE_EQ`, which connected but produced no useful data. That has been fixed.

## Monitor Outputs

The monitor writes these files:

- `python-backend/nifty_market_depth_latest.json`
- `python-backend/nifty_market_depth/<market-date>/latest.json`
- `python-backend/nifty_market_depth/<market-date>/depth_200.ndjson`
- `python-backend/nifty_market_depth/<market-date>/full_market.ndjson`
- `python-backend/nifty_market_depth/<market-date>/trade_ticks.ndjson`
- `python-backend/nifty_market_depth/<market-date>/cvd_series.ndjson`
- `python-backend/nifty_market_depth/<market-date>/depth_imbalance_series.ndjson`
- `python-backend/nifty_market_depth/<market-date>/large_order_events.ndjson`
- `python-backend/nifty_market_depth/<market-date>/volume_profile.json`
- `python-backend/nifty_market_depth/<market-date>/options_feed.ndjson`
- `python-backend/nifty_market_depth/<market-date>/errors.ndjson`

The latest snapshot includes:

- Current stream states.
- Packet counters.
- Last full-market packet summary.
- Latest 200-depth bid/ask summaries.
- Top depth levels.
- Depth imbalance.

## Stability Fixes Implemented

The monitor now:

- Maps `NSE_FNO` correctly for NIFTY futures in both `MarketFeed.Full` and `FullDepth`.
- Uses a thread-local asyncio loop for the full-depth worker.
- Hides the full-depth WebSocket URL to avoid leaking access tokens.
- Reconnects if a stream connects but receives no packet within the configured timeout.
- Catches snapshot-write failures so observability errors do not kill recording.
- JSON-normalizes dates, datetimes, and paths.
- Keeps the old Stage 2 liquidity monitor disabled unless `MONITOR_LEGACY_LIQUIDITY_ENABLED=1`.

## Chart Outputs

The chart generator writes:

- `python-backend/nifty_market_depth_charts_latest.json`
- `python-backend/nifty_market_depth_charts/<market-date>/chart_summary.json`
- `python-backend/nifty_market_depth_charts/<market-date>/nifty_bookmap_heatmap.png`
- `python-backend/nifty_market_depth_charts/<market-date>/nifty_order_flow_footprint.png`
- `python-backend/nifty_market_depth_charts/<market-date>/nifty_dom_ladder.png`
- `python-backend/nifty_market_depth_charts/<market-date>/nifty_cvd_chart.png`
- `python-backend/nifty_market_depth_charts/<market-date>/nifty_futures_5m_candles.png`
- `python-backend/nifty_market_depth_charts/<market-date>/nifty_futures_15m_candles.png`
- `python-backend/nifty_market_depth_charts/<market-date>/nifty_volume_profile.png`
- `python-backend/nifty_market_depth_charts/<market-date>/nifty_option_chain_oi.png`

### 1. Bookmap-Style Liquidity Heatmap

This chart plots:

- Time on the x-axis.
- NIFTY futures price on the y-axis.
- Resting bid liquidity as cool colors.
- Resting ask liquidity as warm colors.
- Best bid and best ask traces.
- Trade-volume bubbles from full-market packets.

This is closest to the first reference image: it shows where liquidity is sitting behind the candle chart and where visible trades hit.

### 2. Order-Flow Footprint Approximation

This chart aggregates sampled full-market packets into small candle buckets. For each price bin it shows inferred sell-side and buy-side volume.

Aggressor classification uses:

1. LTP at or above best ask: aggressive buy.
2. LTP at or below best bid: aggressive sell.
3. Uptick or downtick fallback when bid/ask classification is not available.

The chart also renders candle bodies, per-candle delta, volume, and cumulative delta summary rows.

Important limitation: this is not yet exchange-grade footprint data because the current recorder samples raw full-market packets. For true footprint precision, the system should persist every trade tick with the best bid/ask at that exact moment.

### 3. DOM Ladder

This chart renders the latest bid and ask depth as a vertical price ladder:

- Bid resting quantity on the left.
- Ask resting quantity on the right.
- Price ladder in the center.
- Last traded price marker when available.
- Spread in the title when both sides are present.

This is closest to a DOM trader view and is useful for identifying immediate liquidity walls.

### 4. CVD Chart

This chart renders NIFTY futures price over cumulative volume delta. It highlights whether session price movement is supported by net aggressive buying/selling and flags simple price/CVD divergence.

### 5-6. NIFTY Futures Candles

The chart generator now attempts 5-minute and 15-minute NIFTY futures candle charts through the existing Dhan intraday-history path. These use the same candlestick rendering style as stock-analysis charts: VWAP, EMAs, Bollinger Bands, RSI, volume, and CVD proxy.

### 7. Volume Profile

The monitor accumulates traded volume by price bin from classified trade ticks and saves `volume_profile.json`. The chart renders horizontal price-level volume bars, point of control, and 70% value area.

### 8. Option Chain OI

The chart generator fetches the nearest NIFTY option-chain expiry through Dhan and renders put OI versus call OI around ATM. The live monitor also records an optional ATM-nearby options `MarketFeed.Full` stream into `options_feed.ndjson`.

## Agent-Readable Summary

`chart_summary.json` and `nifty_market_depth_charts_latest.json` provide structured data for agents:

- Chart paths in display order.
- Input row counts.
- Buy, sell, neutral, delta, and total classified volume.
- Heavy bid and ask liquidity levels by average quantity.
- Known limitations.

This allows an LLM agent to inspect the images and cross-check them with numeric evidence.

## Configuration

Relevant environment variables:

```text
NIFTY_DEPTH_MONITOR_ENABLED=1
NIFTY_DEPTH_LEVEL=200
NIFTY_DEPTH_LATEST_SAVE_SECONDS=5
NIFTY_DEPTH_RAW_WRITE_SECONDS=1
NIFTY_DEPTH_RECONNECT_SECONDS=5
NIFTY_DEPTH_FIRST_PACKET_TIMEOUT_SECONDS=20
NIFTY_DEPTH_IMBALANCE_SECONDS=30
NIFTY_LARGE_ORDER_THRESHOLD=300
NIFTY_VOLUME_PROFILE_SAVE_SECONDS=300
NIFTY_OPTIONS_FEED_ENABLED=1
NIFTY_OPTIONS_STRIKES_EACH_SIDE=2
NIFTY_DEPTH_CHARTS_ENABLED=1
NIFTY_DEPTH_CHART_INTERVAL_SECONDS=60
NIFTY_CHART_MAX_DEPTH_PACKETS=700
NIFTY_CHART_MAX_FULL_PACKETS=1800
NIFTY_CHART_MAX_CVD_ROWS=5000
NIFTY_CHART_PRICE_STEP=1
NIFTY_CHART_FOOTPRINT_MINUTES=1
NIFTY_CHART_DOM_LEVELS=48
NIFTY_OPTION_CHAIN_CHART_STRIKES_EACH_SIDE=5
MONITOR_LEGACY_LIQUIDITY_ENABLED=0
```

Manual chart rebuild:

```powershell
docker compose run --rm monitor python -m pipeline.runtime.run_nifty_depth_charts
```

For a specific recorded date:

```powershell
$env:NIFTY_CHART_MARKET_DATE="2026-06-23"
docker compose run --rm monitor python -m pipeline.runtime.run_nifty_depth_charts
```

## Next Improvements

The current version is stable and useful for visual inspection, but the next accuracy upgrades are:

- Persist every full-market packet or trade tick, not throttled samples, during market hours.
- Store the best bid/ask at the exact trade timestamp.
- Add imbalance-cluster detection, liquidity-wall persistence, absorption, spoofing/cancel detection, and sweep detection.
- Feed `nifty_market_depth_charts_latest.json` into the stock/risk/execution agents as a NIFTY market-regime input.
- Add a lightweight frontend viewer so the generated charts can be opened from the dashboard.

These charts improve market context, but they do not make prediction certain. They expose order-book pressure, absorption, and traded-volume behavior that candlesticks alone cannot show.
