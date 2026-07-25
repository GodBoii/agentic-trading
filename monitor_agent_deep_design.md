# Monitor Pipeline: Complete Redesign & Agent Design Blueprint
*Deep Analysis — June 27, 2026 | Full codebase read, all Dhan API constraints verified*

---

## PART 1: CORRECTING THE ARCHITECTURE UNDERSTANDING

### The Two Completely Independent Pipelines

Your codebase has **two separate, independent Docker pipelines** that share the filesystem but never call each other:

```
Pipeline 1: SORTING + STOCK TRADING
─────────────────────────────────────────────────────────
sorting service (SessionSupervisor)
   → Stage 1: BSE 5000 stocks → ~165 pass (price, ADV, ATR)
   → Stage 2: 165 stocks → RVOL + VWAP + ORB + volume accel → top ~8
   → Triggers ai-trading-agents service via HTTP POST

ai-trading-agents service (MultiStockAgentRunner)
   → Loads Stage 2 candidates
   → Filters by capital budget (margin check via Dhan API, up to 30 stocks)
   → For EACH stock that fits budget: fetch candles, build charts, run LLM agent
   → Agent decides: trade this stock or skip
   → If trade: place order via DhanExecutionToolkit


Pipeline 2: MONITOR (INDEPENDENT, PRE-SELECTED INSTRUMENT)
─────────────────────────────────────────────────────────
monitor service (NiftyDepthMonitor)
   → ONE pre-selected instrument: NIFTY front-month futures
   → Keeps 2 WebSocket connections open ALL market hours:
       • MarketFeed.Full → full market packets (LTP, volume, OI, 5-level depth)
       • FullDepth → 200-level order book depth
   → Saves EVERY packet to NDJSON files on disk
   → Generates 3 charts every 60 seconds: bookmap, footprint, DOM ladder
   → Currently: NO agent consuming this data for trading
```

### Why You Pre-Select ONE Instrument for the Monitor

This is the key constraint that drives everything:

**Dhan's 200-level depth WebSocket**: `wss://full-depth-api.dhan.co/twohundreddepth`
- **Exactly 1 instrument per connection**
- **Maximum 5 WebSocket connections total** across all feed types
- **NO historical API** — market depth is LIVE-ONLY

If you're not connected at 9:15 AM, you have no data from 9:15 AM. There is no way to go back and fetch the order book from 30 minutes ago. **This is why you must pre-select and keep the connection alive the entire session.** You're building your own historical depth dataset, packet by packet, saved to NDJSON files.

**This is also why individual stocks don't work as the monitor instrument:**
- A stock might have perfect conditions on Monday, nothing on Tuesday
- You'd be recording depth data all day for an instrument that ends up not trading
- Index instruments (futures) are ALWAYS moving, ALWAYS relevant, EVERY trading day

---

## PART 2: INSTRUMENT SELECTION — WITH ACCURATE 2026 FACTS

### The Landscape Has Changed (Critical 2025-2026 SEBI Reforms)

| Instrument | Lot Size (June 2026) | Weekly Expiry | Expiry Day | Notes |
|---|---|---|---|---|
| **NIFTY 50 Options** | **65 units** | ✅ Yes (weekly) | **Tuesday** | Changed from Thursday in Sep 2025 |
| **Bank Nifty Options** | 30 units | ❌ Monthly only | Last Wednesday | Lost weekly in Oct 2024 |
| **FinNifty Options** | 60 units | ❌ Monthly only | Last Tuesday | Lost weekly in Nov 2024 |
| **MidCap Nifty** | 75 units | ✅ Yes (weekly) | Monday | Less liquid than NIFTY |
| **SENSEX Options** | 10 units | ✅ Yes (weekly) | Tuesday | BSE; Dhan 200-level NOT supported |

### Why NIFTY 50 Wins on Every Criteria

**1. The 200-level depth constraint forces an NSE_FNO instrument:**
- Dhan confirmed: 200-level depth works ONLY for `NSE_EQ` and `NSE_FNO`
- BSE instruments (SENSEX) → ❌ No 200-level depth on Dhan
- NSE_FNO instruments (NIFTY futures, Bank Nifty futures, FinNifty futures) → ✅ All supported

**2. The monitor instrument must be tradeable every single day:**
- NIFTY spot moves every trading day, without exception
- The NIFTY futures contract (used for depth monitoring) is always active

**3. The weekly options constraint:**
- After SEBI Oct 2024 reforms, **only NIFTY 50 has weekly options on NSE**
- Bank Nifty: monthly only
- FinNifty: monthly only
- **NIFTY 50 is the only index on NSE with weekly expiry**
- This matters because weekly options are CHEAPER than monthly (less time value)

**4. Capital efficiency — cheapest viable option for testing:**
- NIFTY 50 lot size: **65 units** (as of Jan 2026)
- NIFTY weekly expiry: **Tuesday**
- ATM option, 0–2 DTE: ₹80–150/unit × 65 = **₹5,200–9,750 per lot**
- 100pt OTM, 0–1 DTE: ₹30–70/unit × 65 = **₹1,950–4,550 per lot**

**Decision: NIFTY 50 front-month futures for monitoring (already built), NIFTY 50 weekly options for trading**

---

## PART 3: WHAT THE MONITOR CURRENTLY COLLECTS (AND WHAT'S MISSING)

### Currently Saved to Disk

```
nifty_market_depth/{date}/
├── full_market.ndjson    → Raw full market packets (LTP, volume, OI, 5-level depth)
├── trade_ticks.ndjson   → Classified trade ticks (buy/sell/neutral, volume_delta)
├── depth_200.ndjson     → 200-level bid + ask depth updates (price, qty, orders)
├── errors.ndjson        → Stream errors
└── latest.json          → Rolling snapshot (refreshed every 5 seconds)
```

### What Is NOT Being Captured (but Should Be)

The current system records raw events but doesn't compute any derived analytical signals. Here's what's missing:

**Missing Signal 1: Cumulative Volume Delta (CVD)**
CVD = running total of (buy_volume - sell_volume). The MOST important order flow indicator.
- When CVD rises while price rises: genuine buying, trend is strong
- When CVD falls while price rises: price moving up on weakness, likely to reverse
- Divergence between CVD and price = the single strongest reversal warning

**Missing Signal 2: Large Order Threshold Events**
When a NEW bid/ask appears in the 200-level book with quantity > threshold (e.g., 300+ contracts at one level), this is likely an institutional order. These events should be logged as timestamped "wall_appeared" events. Similarly, when a large level disappears (cancelled), log "wall_removed".

**Missing Signal 3: Absorption Detection**
When price tries to fall through a large bid level but fails (bid absorbs the selling), then price bounces — this is the most reliable buy signal in order flow. Current code detects aggressor side per tick but doesn't track if a large bid HELD against multiple sell ticks.

**Missing Signal 4: Depth Imbalance Time Series**
The `latest.json` computes depth_imbalance at each 5-second snapshot. But this is NOT being saved to a time series file. Over time, you want to see: "for the last 10 minutes, bid side has consistently had 60%+ of total quantity" → strong buying pressure. This is currently lost.

**Missing Signal 5: Price-Level Volume Profile**
As trades happen, accumulate volume at each price level throughout the day. By 12:00 PM you have a clear picture of where most business happened — these become support/resistance zones with real data behind them.

**Missing Signal 6: Option Chain Real-Time Tracking**
The monitor currently has no awareness of options at all. What CE and PE OI is building/unwinding at each strike? This is critical for knowing where institutional sellers are positioned (= price magnets).

---

## PART 4: IMPROVED DATA COLLECTION ARCHITECTURE

### WebSocket Connection Plan (4 of 5 connections used)

```
Connection 1: FullDepth (200-level)
  → Instrument: NIFTY front-month futures (NSE_FNO)
  → Already implemented in NiftyDepthMonitor._depth_200_worker()
  → Saves: depth_200.ndjson (every bid/ask update, all 200 levels)

Connection 2: MarketFeed.Full (full market packets)
  → Instrument: NIFTY front-month futures (NSE_FNO)
  → Already implemented in NiftyDepthMonitor._full_market_worker()
  → Saves: full_market.ndjson, trade_ticks.ndjson

Connection 3: MarketFeed.Full (options real-time monitoring)
  → Instruments (updated weekly when strikes change):
      • NIFTY ATM Call (CE) — 1 strike
      • NIFTY ATM Put (PE) — 1 strike
      • NIFTY 1-OTM Call — 1 strike
      • NIFTY 1-OTM Put — 1 strike
      • NIFTY 2-OTM Call + Put — 2 strikes
      • India VIX — 1 instrument
      • Total: ~7 instruments (well within 5,000 limit)
  → Gives: real-time LTP, OI, OI day high/low, 5-level depth per option
  → NEW: saves options_feed.ndjson

Connection 4: MarketFeed.Full (macro context)
  → Instruments: NIFTY index (spot proxy), Bank Nifty, FinNifty, Sensex
  → Gives context for correlation and breadth
  → NEW: saves macro_feed.ndjson

Connection 5: RESERVED (for emergency reconnect or future use)
```

### New Files to Add

```
nifty_market_depth/{date}/
├── full_market.ndjson        ← existing
├── depth_200.ndjson          ← existing
├── trade_ticks.ndjson        ← existing
├── errors.ndjson             ← existing
│
├── cvd_series.ndjson         ← NEW: cumulative volume delta, one entry per tick
├── depth_imbalance_series.ndjson ← NEW: bid/ask imbalance % every 30 seconds
├── large_order_events.ndjson ← NEW: walls appearing/disappearing (>300 contracts)
├── absorption_events.ndjson  ← NEW: detected absorption patterns
├── volume_profile.json       ← NEW: updated every 5 min, price→volume accumulation
├── options_feed.ndjson       ← NEW: real-time option LTP + OI updates
└── macro_feed.ndjson         ← NEW: Bank Nifty, FinNifty, VIX ticks
```

### CVD Time Series Record (most important new addition)

```python
# Saved to cvd_series.ndjson on every classified trade tick
{
  "type": "cvd_update",
  "timestamp_ist": "2026-06-27T09:47:23+05:30",
  "ltp": 24850.0,
  "aggressor": "buy",           # from existing Lee-Ready classification
  "tick_volume": 25,            # volume delta for this tick
  "cumulative_buy_volume": 45230,   # running total since session start
  "cumulative_sell_volume": 42100,
  "cumulative_neutral_volume": 1200,
  "cvd": 3130,                  # = cum_buy - cum_sell (positive = net buyers)
  "cvd_5min": 450,              # CVD change over last 5 minutes
  "cvd_ma_20": 2800,            # 20-tick moving average of CVD
  "event_sequence": 1247
}
```

### Depth Imbalance Time Series Record

```python
# Saved to depth_imbalance_series.ndjson every 30 seconds
{
  "type": "depth_imbalance_snapshot",
  "timestamp_ist": "2026-06-27T09:47:00+05:30",
  "ltp": 24850.0,
  "bid_total_qty": 52000,       # total quantity across all 200 bid levels
  "ask_total_qty": 38000,       # total quantity across all 200 ask levels
  "imbalance": 0.154,           # (bid-ask)/(bid+ask): positive = bid heavy
  "bid_top5_qty": 8500,         # top 5 bid levels quantity
  "ask_top5_qty": 5200,         # top 5 ask levels quantity
  "top5_imbalance": 0.239,      # top 5 imbalance (more sensitive)
  "largest_bid": {"price": 24845, "qty": 890, "orders": 2},
  "largest_ask": {"price": 24855, "qty": 650, "orders": 3},
  "bid_levels_above_avg": 45,   # how many bid levels have > average qty
  "ask_levels_above_avg": 31
}
```

### Large Order Event Record

```python
# Saved to large_order_events.ndjson when new level > threshold
{
  "type": "large_order_appeared",  # or "large_order_removed"
  "timestamp_ist": "...",
  "side": "bid",                   # "bid" or "ask"
  "price": 24800.0,
  "quantity": 850,
  "orders": 2,
  "ltp_at_event": 24850.0,
  "distance_from_ltp": -50.0,      # price - ltp, negative = below LTP (support)
  "distance_percent": -0.201       # as % of LTP
}
```

---

## PART 5: CHARTS FOR THE MONITOR AGENT — COMPLETE SPECIFICATION

The monitor agent (designed in Part 6) will receive these chart images. Currently 3 charts exist. We need 8 total.

### Existing Charts (keep, already generated by NiftyDepthChartGenerator)

**Chart 1: Bookmap Liquidity Heatmap**
- X-axis: Time, Y-axis: Price, Color: Resting quantity (bids=blue/cool, asks=red/warm)
- Best bid/ask traces, trade volume bubbles
- Shows WHERE institutions have been parking orders over time

**Chart 2: Order Flow Footprint**
- 1-minute candle buckets, per candle: sell volume (left) vs buy volume (right) per price bin
- Cumulative delta per candle shown at bottom
- Shows WHO is winning at each price level — buyers or sellers

**Chart 3: DOM Ladder**
- Current snapshot of 200-level depth (48 levels shown)
- Bids left (blue bars), asks right (red bars), LTP marker (yellow)
- Shows current resting order imbalance RIGHT NOW

### New Charts to Build

**Chart 4: Cumulative Volume Delta (CVD) Chart** ← most important new chart

```python
# Layout: 2-panel figure
# Top panel: NIFTY futures price (line) + VWAP (dashed)
# Bottom panel: CVD line (green=positive, red=negative) + CVD 20-tick MA
# Annotations: 
#   - Divergence zones (price up, CVD down → bearish signal)
#   - Zero line for CVD (below = net sellers winning the day)
#   - Session CVD high and low markers
# Time range: Full current session (9:15 AM to now)
# Update: Every 60 seconds (same cadence as other charts)
```

This chart answers: "Are buyers or sellers in control TODAY, and is the trend in control strengthening or weakening?"

**Chart 5: NIFTY Futures Candlestick — 5 Minute** ← technical backbone

Already possible with existing `CandlestickChartService` but currently only generates charts for BSE equity stocks. Needs adaptation for `FUTIDX` instrument type on `NSE_FNO`.

```python
# Uses existing charting_service.py
# Indicators: EMA9, EMA21, VWAP, Bollinger Bands, RSI, ATR
# Overlays: Opening range (9:15-9:30 shaded), key S/R from previous day
# Special additions for futures:
#   - OI change bar chart at bottom (rising OI = new money entering)
#   - VWAP bands (±1 ATR from VWAP)
# Data source: DhanService.fetch_intraday_history(interval="1") → aggregate to 5m
#   (Dhan provides 1m and 5m, 15m, 25m, 60m intervals directly)
#   History available: up to 5 YEARS via REST API (not live-only like depth!)
```

**Chart 6: NIFTY Futures Candlestick — 15 Minute** ← trend direction

Same as Chart 5 but 15-minute timeframe. Shows the larger structure and where we are in the trend.

**Chart 7: Volume Profile (Horizontal)**

```python
# Layout: Horizontal bar chart
# Y-axis: Price levels (binned by 25 or 50 points)
# X-axis: Total volume traded at each price level (from trade_ticks.ndjson)
# Color: Where CVD was positive → green bars, negative → red bars
# Special markers:
#   - Point of Control (POC): price with most volume = strongest S/R
#   - Value Area High (VAH): top of 70% of total volume zone
#   - Value Area Low (VAL): bottom of 70% of total volume zone
# Use case: POC acts as magnet for price. VAH/VAL are likely reversal zones.
```

**Chart 8: Option Chain OI Distribution**

```python
# Layout: Back-to-back horizontal bar chart
# Center: Strike prices (ATM ±5 strikes = 10 strikes total, 50pt intervals)
# Left side: Put OI (green bars) at each strike
# Right side: Call OI (red bars) at each strike
# Special markers:
#   - ATM strike: highlighted with different color
#   - Max Call OI (resistance): annotated as "CALL WALL"
#   - Max Put OI (support): annotated as "PUT WALL"
#   - Max Pain level: dashed vertical line
# Overlaid as inset: PCR value + interpretation text
# Data source: DhanService.fetch_option_chain() (already built)
#              + options_feed.ndjson for real-time OI changes
```

### Chart Summary Table

| # | Chart | Already Built? | Data Source | Update Cadence | Agent Value |
|---|---|---|---|---|---|
| 1 | Bookmap Heatmap | ✅ Yes | depth_200.ndjson | 60s | Where has money been sitting |
| 2 | Footprint Chart | ✅ Yes | trade_ticks.ndjson | 60s | Who's winning at each price |
| 3 | DOM Ladder | ✅ Yes | latest_depth_sides | 60s | Current order book snapshot |
| 4 | CVD Chart | ❌ Build | cvd_series.ndjson | 60s | Net buying/selling pressure |
| 5 | 5m Candlestick | ❌ Adapt | Dhan historical API | Per-request | Technical setup confirmation |
| 6 | 15m Candlestick | ❌ Adapt | Dhan historical API | Per-request | Higher timeframe trend |
| 7 | Volume Profile | ❌ Build | trade_ticks.ndjson | 5 min | Key S/R from volume data |
| 8 | Option Chain OI | ❌ Build | Dhan option chain API | Per-request | Institutional positioning map |

---

## PART 6: THE MONITOR AGENT — COMPLETE DESIGN

### Agent Identity

```
Name:        SIGMA (Signal Intelligence & Gamma-Aware Monitor Agent)
Role:        NIFTY 50 Options Intraday Trader
Scope:       ENTRY ONLY in v1. Uses DhanExecutionToolkit.
Model:       Vision-capable multimodal LLM (same as stock agent)
Context:     All 8 charts + structured JSON packet
Max trades:  1 lot per trigger, maximum 2 trades per day
Instrument:  NIFTY weekly options (buying only — CE or PE)
Expiry:      Current week's Tuesday contract
```

### Agent Trigger (when does SIGMA run?)

SIGMA runs on a SCHEDULE, not event-driven like the stock pipeline. It doesn't wait for Stage 2 or any other pipeline. It runs based on market time windows:

```python
SIGMA_RUN_SCHEDULE = [
    # Window 1: Opening momentum (most important)
    {"name": "opening_momentum", "run_at": "09:32", "reason": "Opening range formed, first signal"},
    {"name": "opening_confirm", "run_at": "09:45", "reason": "Confirm opening direction"},
    
    # Window 2: Mid-morning continuation
    {"name": "mid_morning", "run_at": "10:30", "reason": "Consolidation breakout window"},
    
    # Window 3: Afternoon momentum
    {"name": "afternoon_1", "run_at": "13:30", "reason": "Post-dead-zone directional move"},
    {"name": "afternoon_2", "run_at": "14:15", "reason": "Final directional window"},
    
    # NEVER run:
    # 12:00–13:30 → dead zone (theta decay fastest, lowest volume)
    # After 15:05 → no new entries
]

# Additional trigger: If open position exists, SIGMA does NOT run (1 position at a time)
# Additional trigger: Regime = choppy or event_driven → skip all windows
# Additional trigger: VIX > 22 → skip (options too expensive to buy)
```

### Complete Input Packet to SIGMA

```json
{
  "agent": "SIGMA",
  "generated_at_ist": "2026-06-27T09:47:00+05:30",
  
  "timing": {
    "current_ist": "09:47:00",
    "session_window": "opening_momentum",
    "minutes_since_open": 32,
    "minutes_to_entry_cutoff": 438,
    "minutes_to_time_stop": 438,
    "days_to_weekly_expiry": 1,
    "expiry_day": "Tuesday",
    "is_expiry_week_final_day": false
  },

  "regime": {
    "market_regime": "trend_up",
    "index_regime": "trend_up",
    "breadth_regime": "strong_breadth",
    "volatility_regime": "normal_volatility",
    "confidence": 78.5,
    "new_trade_permission": "allowed",
    "preferred_style": "trend_following",
    "position_size_multiplier": 1.0,
    "risk_flags": [],
    "reasoning_summary": "Strong opening with price above VWAP, most sectors positive"
  },

  "nifty_futures_state": {
    "security_id": "41453",
    "ltp": 24850.0,
    "day_open": 24700.0,
    "day_high": 24875.0,
    "day_low": 24680.0,
    "vwap": 24780.0,
    "distance_from_vwap_percent": 0.28,
    "price_vs_vwap": "above",
    "opening_range": {
      "high": 24810.0,
      "low": 24680.0,
      "range_size_points": 130,
      "current_status": "broken_above",
      "breakout_percent": 0.31
    },
    "volume_today": 1234567,
    "oi_today": 9876543,
    "oi_change_today": 123456,
    "oi_buildup": "long_buildup"
  },

  "order_flow_summary": {
    "data_freshness_seconds": 8,
    "cvd_session": 3130,
    "cvd_5min": 450,
    "cvd_trend": "rising",
    "cvd_price_divergence": false,
    "depth_imbalance_current": 0.154,
    "depth_imbalance_5min_avg": 0.128,
    "depth_imbalance_trend": "strengthening",
    "largest_bid": {"price": 24800.0, "qty": 890, "orders": 2, "distance_from_ltp": -50.0},
    "largest_ask": {"price": 24950.0, "qty": 650, "orders": 3, "distance_from_ltp": 100.0},
    "large_bid_walls": [
      {"price": 24800, "qty": 890, "first_seen": "09:32:15", "held_for_minutes": 15}
    ],
    "large_ask_walls": [
      {"price": 24950, "qty": 650, "first_seen": "09:45:00", "held_for_minutes": 2}
    ],
    "absorption_events_last_30min": [
      {"time": "09:38:00", "side": "bid", "price": 24780, "description": "Bid at 24780 absorbed 3 sell waves, price held"}
    ],
    "aggressor_ratio_5min": {"buy": 0.62, "sell": 0.31, "neutral": 0.07},
    "volume_profile_poc": 24760.0,
    "value_area_high": 24840.0,
    "value_area_low": 24700.0
  },

  "options_market": {
    "vix_level": 13.2,
    "vix_change_intraday_percent": -1.5,
    "vix_regime": "low",
    "atm_strike": 24850,
    "call_atm_ltp": 145.0,
    "put_atm_ltp": 105.0,
    "pcr_oi": 1.12,
    "pcr_volume": 0.98,
    "pcr_interpretation": "slightly_bullish_contrarian",
    "atm_iv_call": 13.1,
    "atm_iv_put": 13.4,
    "iv_skew": "balanced",
    "options_expensive": false,
    "max_pain": 24700,
    "largest_call_oi_wall": {"strike": 25000, "oi": 8500000},
    "largest_put_oi_wall": {"strike": 24500, "oi": 9200000}
  },

  "account_state": {
    "available_margin": 75000.0,
    "today_realized_pnl": 0.0,
    "today_unrealized_pnl": 0.0,
    "daily_loss_limit": -4500.0,
    "daily_loss_consumed_percent": 0.0,
    "open_positions": [],
    "trades_today": 0,
    "max_trades_today": 2
  },

  "trade_config": {
    "max_premium_budget_inr": 12000.0,
    "lot_size": 65,
    "max_lots": 1,
    "expiry": "2026-07-01",
    "strike_selection": "atm_or_1otm",
    "order_type": "LIMIT",
    "slippage_allowance_points": 2.0
  },

  "charts_provided": [
    "bookmap_heatmap.png",
    "footprint_chart.png",
    "dom_ladder.png",
    "cvd_chart.png",
    "nifty_5m_candles.png",
    "nifty_15m_candles.png",
    "volume_profile.png",
    "option_chain_oi.png"
  ]
}
```

### SIGMA Agent System Prompt

```
You are SIGMA, an expert intraday NIFTY 50 options trader specializing in
order flow analysis. You make exactly ONE decision per run: BUY CALL,
BUY PUT, or WAIT.

Your edge is reading the NIFTY futures order book — the 200-level depth data
that shows where large institutional players have placed their orders BEFORE
price moves. When you see large resting bids absorbing selling pressure
without the price falling, institutions are accumulating long positions.
When you see large offers repeatedly defending a level, institutions are
distributing and price will likely fall.

You trade NIFTY weekly options (buying only). This means:
- Maximum loss on any trade = the premium you pay (clearly defined)
- No margin calls, no unlimited risk
- You need NIFTY to move FAST and FAR enough to overcome theta decay
- The typical hold time is 30 minutes to 3 hours — not overnight, not days

═══════════════════════════════════════════
READ THE CHARTS IN THIS ORDER:
═══════════════════════════════════════════

1. CHART 6 (15m Candles): What is the MACRO TREND? Up, down, sideways?
   Where is price relative to VWAP? Previous day's high/low?
   This sets the direction bias. Do NOT fight this trend.

2. CHART 5 (5m Candles): What is the MICRO SETUP?
   Is there a pullback to VWAP in an uptrend (buy signal)?
   Is there a rejection from VWAP in a downtrend (sell signal)?
   Where is RSI? (Avoid buying calls when RSI > 75, avoid puts when RSI < 25)

3. CHART 7 (Volume Profile): Where is the Point of Control (POC)?
   Where is the Value Area? Price tends to return to POC.
   If price is far above VAH → possible mean reversion. Below VAL → possible bounce.

4. CHART 4 (CVD Chart): Is CVD CONFIRMING the price move?
   - Price rising AND CVD rising = genuine move, buy calls
   - Price rising BUT CVD flat or falling = weak move, DON'T buy calls
   - CVD diverging from price = the MOST POWERFUL reversal signal

5. CHART 1 (Bookmap): WHERE has the heaviest liquidity been sitting?
   Large blue clusters (bids) = strong support floors.
   Large red clusters (asks) = resistance ceilings.
   Is price approaching a heavy ask wall? Reduce confidence on calls.
   Is price near a heavy bid wall? Increase confidence on calls.

6. CHART 2 (Footprint): WHO is winning at EACH price level?
   Green (buy volume) > pink (sell volume) at recent prices = buyers in control.
   Per-candle delta positive and growing = momentum strengthening.

7. CHART 3 (DOM Ladder): What does the CURRENT order book look like RIGHT NOW?
   Large bid cluster immediately below LTP = institutional support.
   Large ask cluster immediately above LTP = institutional resistance.
   If bid side >> ask side in quantity → bullish near-term.

8. CHART 8 (Option Chain OI): Where are the MAGNETIC levels?
   Largest PUT wall = strong support (large sellers there protect their short puts)
   Largest CALL wall = strong resistance (call writers will defend)
   Is today's price between these walls? Likely range-bound.
   Has price broken above the call wall? Very bullish — sellers are panicking.

═══════════════════════════════════════════
HARD RULES — VIOLATION MEANS IMMEDIATE WAIT:
═══════════════════════════════════════════

RULE 1: Regime check
  IF regime.new_trade_permission == "blocked" → OUTPUT WAIT
  IF regime.market_regime == "choppy" → OUTPUT WAIT
  IF regime.market_regime == "event_driven" → OUTPUT WAIT

RULE 2: Volatility check
  IF vix_level > 22 → OUTPUT WAIT (options overpriced, expect to lose premium)
  IF vix_change_intraday_percent > +10 → OUTPUT WAIT (sudden fear spike, unstable)

RULE 3: Time check
  IF timing.session_window == "dead_zone" → OUTPUT WAIT
  IF timing.minutes_to_entry_cutoff < 30 → OUTPUT WAIT (too close to cutoff)

RULE 4: Position check
  IF account_state.open_positions is not empty → OUTPUT WAIT (1 position at a time)
  IF account_state.trades_today >= account_state.max_trades_today → OUTPUT WAIT

RULE 5: P&L check
  IF account_state.today_realized_pnl < (daily_loss_limit * 0.60) → OUTPUT WAIT
  (Stop when 60% of daily loss limit is consumed, not 100%)

RULE 6: Capital check
  IF 1 lot of ATM option costs more than trade_config.max_premium_budget_inr → OUTPUT WAIT

RULE 7: Data freshness
  IF order_flow_summary.data_freshness_seconds > 120 → OUTPUT WAIT (stale depth data)

RULE 8: CVD-price divergence
  IF you are about to BUY CALL but cvd_price_divergence == true → OUTPUT WAIT
  (Price rising but CVD falling is the most dangerous time to buy calls)

RULE 9: Option pricing
  IF options_market.options_expensive == true AND atm_iv > 20 → OUTPUT WAIT
  (VIX may be low but specific option IV can still be inflated)

═══════════════════════════════════════════
VALID TRADE CONDITIONS:
═══════════════════════════════════════════

BUY CALL when ALL of these are true:
  ✓ regime = trend_up OR (mean_reversion AND price below VWAP about to reclaim)
  ✓ 15m chart: price above VWAP and trend is up
  ✓ CVD: rising or recently turned positive from below
  ✓ Depth imbalance: bid side dominant (positive imbalance > 0.10)
  ✓ No large ask wall within 50 points above current price
  ✓ Volume profile: price above POC or POC is nearby support
  ✓ PCR: not extremely low (> 0.75 preferred for call buying)
  ✓ VIX: below 18 preferred, acceptable up to 22

BUY PUT when ALL of these are true:
  ✓ regime = trend_down OR (mean_reversion AND price above VWAP about to reject)
  ✓ 15m chart: price below VWAP and trend is down
  ✓ CVD: falling or recently turned negative from above
  ✓ Depth imbalance: ask side dominant (negative imbalance < -0.10)
  ✓ No large bid wall within 50 points below current price
  ✓ Volume profile: price below POC or POC is nearby resistance
  ✓ PCR: not extremely high (< 1.4 preferred for put buying)

WAIT when ANY of the following:
  - Regime is choppy, event-driven, or blocked
  - Charts are contradicting each other (e.g., 15m up but CVD falling hard)
  - VIX is elevated (> 22) making options too expensive
  - We're in the 12:00–13:30 dead zone
  - An open position already exists
  - Not enough conviction — "WAIT" is the most common correct answer

═══════════════════════════════════════════
MANDATORY OUTPUT FORMAT:
═══════════════════════════════════════════

## Decision: [BUY CALL | BUY PUT | WAIT]
## Option Type: [CE | PE | N/A]
## Strike: [e.g., 24900 | N/A]
## Security ID: [from security master CSV — you must provide this | N/A]
## Expiry: [YYYY-MM-DD | N/A]
## Quantity: [65 | N/A]
## Order Type: [LIMIT | N/A]
## Limit Price: [₹XX.XX per unit | N/A]
## Reasoning: 
   [3-4 sentences: what the charts specifically showed, why this direction, 
    what would immediately invalidate this trade]
## Key Risk: [Single most important thing that could make this trade wrong]
## Stop Level: [₹XX.XX premium (= entry × 0.65) | N/A]
## Target Level: [₹XX.XX premium (= entry × 1.45) | N/A]
## Correlation ID: [UUID | N/A]
## Execution Status: [Attempted | Skipped — reason]
```

### Tools Available to SIGMA

```python
# INFORMATION TOOLS (always available)
get_account_snapshot()                          # funds, positions, holdings
get_order_book()                                # all today's orders
get_super_order_list()                          # check for existing bracket orders
get_kill_switch_status()                        # is emergency halt active?

# CALCULATION TOOLS (always available)
calculate_margin_requirement(                   # pre-validate before placing
    security_id, exchange_segment,
    transaction_type, quantity,
    price, product_type, order_type
)

# EXECUTION TOOLS (require EXECUTIONER_ALLOW_LIVE_ORDERS=1)
place_intraday_equity_order(                    # for buying NIFTY options
    security_id="49081",                        # NIFTY CE security ID
    exchange_segment="NSE_FNO",
    transaction_type="BUY",
    quantity=65,                                # 1 lot
    order_type="LIMIT",
    price=145.50,                               # ATM call limit price
    product_type="INTRADAY",
    correlation_id="sigma-20260627-001"
)

# NIFTY options are placed as equity orders on NSE_FNO
# The security_id for each NIFTY strike+expiry+type must come from security_id_list.csv
```

---

## PART 7: TRADE MONITOR — F&O VERSION

The post-entry monitor is the MOST CRITICAL missing piece. Once SIGMA places an option buy order, the monitor must watch it every 30 seconds and exit via deterministic rules (no LLM delay for exits).

### Why Options Need a Different Monitor than Stocks

| | Stock (current approach) | NIFTY Option (needed) |
|---|---|---|
| Main enemy | Price moves against position | **TIME** (theta decay) + price + IV change |
| Stop-loss basis | Price of the stock | **Premium** of the option (% from entry) |
| Time urgency | Low (CNC can hold overnight) | **Extreme** (must exit by 3:15 PM) |
| "Price goes sideways" result | Flat P&L | **Loss** — premium decays even without movement |
| VIX spike impact | Indirect | Direct — IV changes premium price immediately |

### F&O Monitor Deterministic Rules (fire in 30-second loop)

```python
# Priority 0 (Highest — fires immediately, overrides everything)
RULE_0 = {
    "name": "daily_kill_switch",
    "condition": "today_realized_pnl + unrealized_pnl < daily_loss_limit",
    "action": "EXIT_ALL_POSITIONS_AND_HALT_TRADING_TODAY",
    "severity": "CRITICAL"
}

# Priority 1 (Fire immediately, no LLM consultation)
RULE_1 = {
    "name": "stop_loss_triggered",
    "condition": "current_premium <= entry_premium * 0.65",
    "action": "EXIT_IMMEDIATELY",
    "message": "Stop-loss hit: premium fell 35% from entry"
}

RULE_2 = {
    "name": "target_hit",
    "condition": "current_premium >= entry_premium * 1.45",
    "action": "EXIT_IMMEDIATELY",
    "message": "Target hit: premium rose 45% from entry"
}

RULE_3 = {
    "name": "hard_time_stop",
    "condition": "current_ist_time >= '15:05:00'",
    "action": "EXIT_IMMEDIATELY",
    "message": "Hard time-stop: 15:05 IST — must exit before exchange square-off"
}

RULE_4 = {
    "name": "expiry_day_time_stop",
    "condition": "days_to_expiry == 0 AND current_ist_time >= '14:30:00'",
    "action": "EXIT_IMMEDIATELY",
    "message": "Expiry day: premiums go parabolic or zero after 2:30 PM, exiting"
}

# Priority 2 (Fire immediately, clear conditions)
RULE_5 = {
    "name": "vix_spike",
    "condition": "vix_intraday_change_percent >= +15",
    "action": "EXIT_IMMEDIATELY",
    "message": "Sudden VIX spike: event risk or circuit breaker, exiting"
}

RULE_6 = {
    "name": "regime_flipped_to_blocked",
    "condition": "regime.new_trade_permission == 'blocked' AND position_age_minutes < 30",
    "action": "EXIT_IMMEDIATELY",
    "message": "Regime changed to blocked within 30 min of entry"
}

RULE_7 = {
    "name": "dead_zone_bleeding",
    "condition": (
        "current_ist between 12:00 and 13:30"
        " AND current_premium < entry_premium * 0.85"
    ),
    "action": "EXIT_IMMEDIATELY",
    "message": "In dead zone with declining premium — theta accelerating"
}

# Priority 3 (Escalate to LLM advisory before action)
RULE_8 = {
    "name": "stale_market_data",
    "condition": "depth_data_age_seconds > 180 OR quote_age_seconds > 60",
    "action": "REQUEST_LLM_ADVISORY",
    "escalation": "LLM decides: exit_review or hold"
}

RULE_9 = {
    "name": "direction_reversal_signal",
    "condition": (
        "cvd_5min < -200 AND position_is_call"
        " AND current_premium < entry_premium"
    ),
    "action": "REQUEST_LLM_ADVISORY",
    "escalation": "CVD turning against call position — escalate"
}
```

### LLM Advisory for Monitor (runs every 5 minutes on active position)

```
Model: xiaomi/mimo-v2.5-pro (existing regime model — no new model needed)

Receives:
  - Current position: entry premium, current premium, unrealized P&L, % from stop, % from target
  - Time context: position age, minutes to time-stop, days to expiry
  - NIFTY state: LTP, VWAP position, distance moved since entry
  - Order flow: current DOM ladder (Chart 3), CVD last 10 min (from cvd_series.ndjson)
  - VIX level + change since entry

Returns one of:
  - HOLD: Thesis intact, depth supportive, adequate time remaining
  - TIGHTEN: Tighten stop to -20% (from -35%) — take partial protection
  - EXIT_REVIEW: Something changed — escalate to deterministic check
  - NO_OPINION_STALE_DATA: Data too old to form view

CANNOT return: Execute order. Place trade. Modify existing order.
```

### Monitor Snapshot Schema (F&O)

```json
{
  "stage": "fo_trade_monitor",
  "generated_at_ist": "2026-06-27T10:15:00+05:30",
  "monitor_state": "observing",
  "position": {
    "instrument": "NIFTY01JUL2026CE24900",
    "security_id": "49081",
    "exchange_segment": "NSE_FNO",
    "direction": "CE",
    "quantity": 65,
    "entry_premium_per_unit": 145.0,
    "entry_total_cost": 9425.0,
    "entry_time_ist": "09:47:23",
    "entry_order_id": "123456",
    "current_premium": 178.0,
    "unrealized_pnl_per_unit": 33.0,
    "unrealized_pnl_inr": 2145.0,
    "unrealized_pnl_percent": 22.76,
    "stop_loss_premium": 94.25,
    "target_premium": 210.25,
    "time_since_entry_minutes": 28,
    "time_to_time_stop_minutes": 318,
    "days_to_expiry": 1
  },
  "deterministic_checks_run": 9,
  "deterministic_triggers_fired": 0,
  "llm_advisory": {
    "model": "xiaomi/mimo-v2.5-pro",
    "opinion": "HOLD",
    "reasoning": "CVD positive and rising. DOM shows strong bids at 24850. Thesis intact.",
    "ran_at_ist": "2026-06-27T10:15:00+05:30"
  },
  "data_quality": {
    "depth_data_age_seconds": 5,
    "quote_age_seconds": 2,
    "regime_age_minutes": 18
  }
}
```

---

## PART 8: CAPITAL REQUIREMENTS & POSITION SIZING

### Starting Capital for Testing

| Phase | Capital | What You Can Test | Risk Per Trade |
|---|---|---|---|
| Phase 0 (Validation) | ₹20,000 | 1 lot, deep OTM options 0-1 DTE (₹30-60/unit = ₹1,950-3,900/lot) | ₹680-1,365 max loss at -35% |
| Phase 1 (Live testing) | ₹50,000 | 1 lot, ATM options 1-2 DTE (₹80-150/unit = ₹5,200-9,750/lot) | ₹1,820-3,413 max loss |
| Phase 2 (Growth) | ₹1,00,000 | 1-2 lots, ATM any DTE | ₹3,413-6,825 max loss |

### Position Sizing Formula

```python
def calculate_nifty_option_lots(
    available_margin: float,
    atm_premium_per_unit: float,
    lot_size: int = 65,           # current NIFTY lot size (June 2026)
    max_capital_per_trade: float = 0.20,  # never more than 20% on one option
    stop_loss_pct: float = 0.35   # exit if premium falls 35%
) -> dict:
    
    # Never risk more than 7% of total capital on a single trade
    # (because stop at -35% means effective risk = lot_cost * 0.35)
    max_loss_acceptable = available_margin * 0.07
    
    # Work backwards: if stop is at -35%, what premium can we afford?
    max_premium_total = max_loss_acceptable / stop_loss_pct
    
    # Hard cap: never more than 20% of capital in one option position
    hard_cap = available_margin * max_capital_per_trade
    
    one_lot_cost = atm_premium_per_unit * lot_size
    
    effective_budget = min(max_premium_total, hard_cap)
    
    if one_lot_cost <= effective_budget:
        return {
            "lots": 1,
            "cost": one_lot_cost,
            "max_loss": one_lot_cost * stop_loss_pct,
            "target_gain": one_lot_cost * 0.45
        }
    else:
        return {"lots": 0, "reason": "atm_premium_exceeds_risk_budget"}
```

### Daily Risk Controls

```
Daily loss limit:      -7% of available capital (e.g., -₹3,500 on ₹50,000)
Weekly loss limit:     -12% of available capital
Monthly loss limit:    -18% of available capital → halt for the rest of month

Daily loss consumed 60% → SIGMA stops running for the day
Daily loss consumed 100% → Kill switch fires, exit all positions

Max trades per day: 2
Max consecutive losses before mandatory system review: 3
```

---

## PART 9: SECURITY ID RESOLUTION

The most practical challenge: NIFTY options have a different Dhan security ID for every strike and expiry. The `security_id_list.csv` already exists in the project root. SIGMA needs a tool to look up the correct ID.

```python
# New tool: get_nifty_option_security_id()
# Input: strike (e.g., 24900), option_type ("CE" or "PE"), expiry ("2026-07-01")
# Output: security_id from security_id_list.csv
# 
# The CSV has columns: SEM_SMST_SECURITY_ID, SEM_TRADING_SYMBOL, ...
# NIFTY options look like: NIFTY01JUL26C24900 (CE) or NIFTY01JUL26P24900 (PE)
# Parse with: pd.read_csv("security_id_list.csv") + filter by trading symbol pattern

# This should be a Python tool SIGMA can call before placing an order:
# security_id = get_nifty_option_security_id(24900, "CE", "2026-07-01")
# Then: place_intraday_equity_order(security_id=security_id, ...)
```

---

## PART 10: IMPLEMENTATION SEQUENCE

### Phase 0: Data Collection Improvements (Week 1)
**No agent changes. Just improve what gets saved.**

1. Add CVD computation to `NiftyDepthMonitor._record_full_packet()` → save to `cvd_series.ndjson`
2. Add depth imbalance time series → save to `depth_imbalance_series.ndjson` every 30s
3. Add large order detection in `_record_depth_packet()` → save to `large_order_events.ndjson`
4. Add options real-time feed (Connection 3) for ATM strikes → save to `options_feed.ndjson`
5. Run for 5 trading days and verify data quality

**Deliverable:** Rich dataset that didn't exist before.

### Phase 1: New Charts (Week 2)
**Build the missing 5 charts.**

1. `CVDChartGenerator` → reads `cvd_series.ndjson` → produces `nifty_cvd_chart.png`
2. `VolumeProfileGenerator` → reads `trade_ticks.ndjson` → produces `nifty_volume_profile.png`
3. `OptionChainChartGenerator` → calls `DhanService.fetch_option_chain()` → produces `nifty_option_chain_oi.png`
4. Adapt `CandlestickChartService` for `FUTIDX` on `NSE_FNO` → produces 5m and 15m candle charts
5. Add all new chart paths to `nifty_depth_charts_latest.json`

**Deliverable:** Agent now has 8 charts instead of 3.

### Phase 2: SIGMA Agent (Week 3)
**Build the monitor agent. Paper mode only.**

1. `pipeline/monitor/fo_packet_builder.py` → assembles the complete JSON packet
2. `pipeline/monitor/fo_security_resolver.py` → reads `security_id_list.csv`, resolves strike → security_id
3. `pipeline/monitor/sigma_agent.py` → the SIGMA trading agent
4. `pipeline/runtime/run_sigma_agent.py` → entry point, schedule-based trigger
5. Set `EXECUTIONER_ALLOW_LIVE_ORDERS=0` → paper mode
6. Run for 2-3 weeks, log all decisions, measure directional accuracy

**Deliverable:** Agent making real decisions logged to files but no live orders.

### Phase 3: F&O Monitor (Week 4)
**The post-trade safety net.**

1. `pipeline/monitor/fo_trade_monitor.py` → 9 deterministic rules + LLM advisory
2. `pipeline/runtime/run_fo_monitor.py` → entry point, 30-second loop
3. Test with paper trades (manually create fake position in state file, watch monitor)

**Deliverable:** Monitor correctly detecting and logging what it would do on each trigger.

### Phase 4: Integration & Live Testing (Week 5+)
1. Connect SIGMA → FoTradeMonitor handoff via shared state file
2. Add `monitor-agent` Docker service to `docker-compose.yml`
3. Set `EXECUTIONER_ALLOW_LIVE_ORDERS=1`
4. First live trade: max ₹2,000 premium (deep OTM, expiry day options)
5. Evaluate after 10 live trades: is expectancy positive?

---

## APPENDIX: FILES CREATED / MODIFIED

### New Files
```
python-backend/pipeline/monitor/
├── __init__.py
├── fo_packet_builder.py          # Assembles complete SIGMA input packet
├── fo_security_resolver.py       # NIFTY strike → Dhan security_id lookup
├── fo_trade_monitor.py           # Post-trade monitor (9 rules + LLM advisory)
├── sigma_agent.py                # SIGMA trading agent
├── cvd_chart_generator.py        # CVD + price chart
├── volume_profile_generator.py   # Volume profile horizontal chart
└── option_chain_chart_generator.py  # OI distribution + IV skew chart

python-backend/pipeline/runtime/
├── run_sigma_agent.py            # SIGMA agent loop (schedule-based)
└── run_fo_monitor.py             # F&O trade monitor loop

python-backend/pipeline/services/
└── nifty_candle_chart_service.py # Adapts charting_service for NSE_FNO futures
```

### Modified Files
```
nifty_depth_monitor.py            # Add CVD tracking, depth imbalance series,
                                  # large order detection, options feed connection

nifty_depth_charting.py           # Add CVD chart, volume profile chart generation

docker-compose.yml                # Add monitor-agent service for SIGMA
                                  # Add fo-monitor service for FoTradeMonitor

config.py                         # Add paths for new NDJSON files and chart outputs
```

### Unchanged Files (Use As-Is)
```
nifty_depth_monitor.py (base WebSocket logic)    ← 200-level already perfect
dhan_execution_toolkit.py                         ← All tools already built
dhan_service.py                                   ← fetch_option_chain() already there
regime_analyzer.py                                ← PCR, VIX, option chain already there
market_reference_service.py                       ← Security master CSV reader
charting_service.py                               ← Candle charts, will adapt not replace
```
