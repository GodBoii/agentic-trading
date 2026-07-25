# F&O Trading System: Deep Analysis & Complete Design Blueprint

*Authored after full codebase analysis — June 27, 2026*

---

## PART 1: WHAT YOU ALREADY HAVE (DON'T REBUILD IT)

Before designing anything new, it is critical to understand that **the infrastructure for exactly what you want is already 70% built inside this codebase.** Most people would start from scratch. You should not.

### What Already Exists and Works

| Component | File | Status | Relevance to F&O |
|---|---|---|---|
| NIFTY 200-level depth recorder | `nifty_depth_monitor.py` | ✅ Built & running | **Core signal source** |
| Bookmap heatmap chart | `nifty_depth_charting.py` | ✅ Built & generating | Feed to LLM vision |
| Footprint chart | `nifty_depth_charting.py` | ✅ Built & generating | Feed to LLM vision |
| DOM ladder chart | `nifty_depth_charting.py` | ✅ Built & generating | Feed to LLM vision |
| Option chain fetch | `dhan_service.py` | ✅ Built | PCR, ATM IV, OI |
| PCR calculation | `regime_analyzer.py` | ✅ Built | Regime input |
| India VIX tracking | `regime_analyzer.py` | ✅ Built | Volatility regime |
| Candlestick chart service | `charting_service.py` | ✅ Built | Can chart NIFTY futures |
| Place Super Order (entry + SL + target) | `dhan_execution_toolkit.py` | ✅ Built | Protected trade entry |
| Kill switch | `dhan_execution_toolkit.py` | ✅ Built | Emergency brake |
| Margin calculator | `dhan_execution_toolkit.py` | ✅ Built | Pre-trade check |
| Regime classifier | `regime_analysis_agent.py` | ✅ Built | Market context |
| Session supervisor | `run_session_supervisor.py` | ✅ Built | Orchestration layer |

**The critical observation: the monitoring infrastructure for NIFTY is already built. The piece that does not yet exist is the F&O agent that consumes all this data and places option trades instead of stock trades.**

---

## PART 2: INSTRUMENT SELECTION — THE FULL REASONING

### Why NOT these instruments

**BSE Equity Stocks (current approach):**
- Problem: the system scans 5,000+ stocks to find the "best one" — enormous compute and API quota consumption
- 200-level depth data is wasted because you can only monitor 1 stock at a time, and you don't know WHICH stock until Stage 2 runs
- Small capital problem: ₹399 trade amount (seen in live run) is too small for meaningful equity positions
- Edge is thin: retail has no information advantage in random BSE mid-caps

**NIFTY Futures:**
- Requires ₹60,000–70,000 for intraday margin (MIS)
- Gap risk causes margin calls
- Not suitable for capital under ₹1 lakh

**Bank Nifty Options:**
- SEBI October 2024 reform: Bank Nifty now has **monthly-only** expiry (no weekly)
- ATM premium per lot (30 units): ₹28,000–35,000 — too expensive for small capital
- Spreads are wider than NIFTY

**Option Selling (any instrument):**
- Requires ₹1.2–1.5 lakh margin per lot minimum
- Unlimited loss potential — catastrophic for small accounts

### The Right Instrument: NIFTY 50 Weekly Options (Buying Only)

**Why this is the correct choice — step by step reasoning:**

**1. Capital Efficiency:**
- Lot size: 75 units (effective Jan 2025)
- ATM premium 2–3 days to expiry: ₹100–180 per unit = **₹7,500–13,500 per lot**
- This is affordable on ₹30,000–50,000 capital
- Max loss = premium paid. No margin calls. Ever.

**2. The 200-Level Depth Advantage is PERFECTLY aligned:**
- Your system already captures NIFTY **futures** 200-level depth
- NIFTY futures order book is where ALL institutional activity happens — banks, FIIs, option market makers delta-hedging
- This order book is the single best leading indicator for where NIFTY spot will move next
- You use futures depth as the SIGNAL SOURCE and weekly options as the EXECUTION INSTRUMENT
- This is called "reading the futures tape to trade options" — it's a professional technique

**3. You're trading ONE instrument:**
- No need to scan 5,000 stocks
- No Stage 1/Stage 2 filtering needed
- All your data depth goes onto one thing: NIFTY
- The 200-level connection (1 instrument limit) is a perfect fit — you only ever need NIFTY futures

**4. Liquidity is unmatched:**
- NIFTY 50 weekly options are among the most liquid derivatives contracts in the world
- ATM strike bid-ask spread: ₹1–2 per unit in normal conditions
- Fills at mid-price are almost always achievable with limit orders
- No slippage problems that plague small-cap stock trading

**5. Edge from order flow is highest here:**
- When a large FII is buying the market, their futures orders appear in the 200-level book as large resting bids with few order counts (iceberg)
- This is a 30–90 second leading signal before price moves
- NIFTY options respond within seconds of a futures move
- You read the futures book → trade the options

**6. Defined trading schedule:**
- Unlike stock scanning which must run 6.25 hours, NIFTY options have clear high-edge windows:
  - 9:20–10:15 AM: Opening momentum window (highest volume, highest edge)
  - 1:30–3:00 PM: Afternoon directional window
  - Avoid 12:00–1:30 PM completely (dead zone, theta eats you alive)

---

## PART 3: THE STRATEGY — ORDER FLOW + OPTIONS

### Core Strategy: "Futures Tape → Options Execution"

This is not a technical indicator strategy. It is an **order flow reading strategy** where you use what the futures market SHOWS (resting institutional orders) to predict where price will go, then buy cheap options to profit from that move.

### Three Specific Setups

**Setup 1: Absorption Breakout (Trend Days)**

*Condition:* Regime is classified as `trend_up` or `trend_down`, VIX stable (<14)

*Trigger:* NIFTY futures holds a price level with repeated large buy absorption (large qty, few orders in depth, not fleeting) WHILE price is above VWAP. After 2–3 minutes of absorption, price begins breaking to new session high.

*Trade:* Buy 1 lot NIFTY ATM Call (CE), same week's expiry, 1–2 DTE preferred
*Exit:* +40% premium gain OR -30% premium loss OR 3:05 PM time-stop

**Setup 2: VWAP Reclaim (Mean-Reversion Days)**

*Condition:* Regime is `mean_reversion`, NIFTY has moved >0.5% away from VWAP

*Trigger:* Footprint chart shows selling exhaustion (sell volume decreasing at lows, buy delta improving). Depth shows large bids appearing at a key support zone below VWAP.

*Trade:* Buy 1 lot NIFTY ATM Put (PE) or Call (CE) in the direction of VWAP return
*Exit:* When NIFTY reaches VWAP OR -25% premium loss OR 2:45 PM time-stop

**Setup 3: Opening Range Breakout + Order Flow Confirm (All Trend Days)**

*Condition:* First 15 minutes (9:15–9:30) establishes opening range. Regime is `trend_up` or `trend_down`.

*Trigger:* NIFTY breaks outside the opening range with strong volume acceleration AND the 200-level depth shows NO significant resistance wall above (for breakout) or support below (for breakdown). PCR <0.9 for bullish breakout, >1.1 for bearish breakdown.

*Trade:* Buy 1 lot NIFTY ATM or 1-strike OTM option in breakout direction
*Exit:* +50% premium gain OR -35% premium loss OR if price re-enters opening range

### What NOT to Trade
- Event days (RBI policy, budget, election) → regime will show `event_driven` → skip ALL trades
- Choppy days (regime `choppy`) → no setup will work → 0 trades is correct output
- After 3:05 PM → too close to expiry square-off → force-exit anything open

---

## PART 4: AGENT DESIGN — COMPLETE SPECIFICATION

### Architecture Change: From "Stock Scanner" to "NIFTY Intelligence Loop"

**Current system:** Stage1 (5000 stocks → 165) → Stage2 (165 → 8) → StockAgent (analyzes 8 stocks)

**New F&O system:** NIFTY Monitor (always running) → Regime (always running) → F&O Agent (triggered on schedule or signal)

The F&O agent is simpler to trigger (no scanning) but requires MORE data depth on a single instrument. Here is the complete design:

---

### Agent Identity

```
Name:   CHRONOS-FNO
Role:   NIFTY 50 Options Intraday Trader
Model:  Vision-capable multimodal LLM (GPT-4o / Gemini 1.5 Pro / Groq vision)
Scope:  Entry only. No position management. No exit orders.
        (The trade monitor handles exits via deterministic rules)
```

---

### Data Inputs to the Agent (in order of importance)

**Tier 1 — Core Signal Data (must always be fresh, reject if stale >2 min)**

| Input | Source | Format | Why It Matters |
|---|---|---|---|
| **Bookmap heatmap** (last 30–60 min) | `nifty_depth_charting.py` | PNG image | Shows WHERE institutional bids/asks have been clustering over time |
| **Footprint chart** (1m candles) | `nifty_depth_charting.py` | PNG image | Shows BUY vs SELL volume at each price — reveals absorption vs. distribution |
| **DOM ladder** (current snapshot) | `nifty_depth_charting.py` | PNG image | Shows current resting order imbalance — which side has more commitment |
| **NIFTY futures 5m chart** | `charting_service.py` (adapted) | PNG image | Price structure, VWAP, EMAs, support/resistance |
| **NIFTY futures 15m chart** | `charting_service.py` (adapted) | PNG image | Higher timeframe trend direction |

**Tier 2 — Market Context (regime + options chain)**

| Input | Source | Format | Why It Matters |
|---|---|---|---|
| **Regime report** | `regime_latest.json` | JSON | Trade permission, market style (trend/mean-revert/choppy), position size multiplier |
| **PCR (OI-based)** | `regime_analyzer.py` option chain | Number + trend | Contrarian sentiment. >1.3 = bullish. <0.7 = bearish. |
| **India VIX level + intraday change** | `regime_analyzer.py` | Number | >20 = reduce size. >25 = no new entries. VIX dropping = good for option buyers. |
| **ATM IV (implied volatility)** | Option chain fetch | Number | Determines if options are cheap or expensive. High IV = options overpriced = don't buy. |
| **Option chain OI distribution** | Dhan option chain API | JSON table | Where max pain is. Where large OI walls exist (magnets for price). |
| **FII/DII provisional flow** | NSE API | JSON | Net buying or selling by institutions today — background context. |

**Tier 3 — Account & Risk Context**

| Input | Source | Format | Why It Matters |
|---|---|---|---|
| **Available funds** | `dhan_execution_toolkit.get_account_snapshot()` | JSON | How much capital is available for trading |
| **Current positions** | Dhan positions API | JSON | Prevents double-entry on same instrument |
| **Today's P&L** | Dhan positions API | Number | Has daily loss limit been hit? |
| **Market time** | `market_time_service.py` | IST timestamp | Is it a high-edge window? Close to time-stop? |
| **Opening range** | Computed from first 15m candle data | High/Low prices | Is price outside the range? By how much? |

---

### Prompt Structure for the F&O Agent

```
[SECTION 1: TIMING CONTEXT]
- Current IST time: {time}
- Market session open: 09:15 IST
- New entry cutoff: 15:05 IST (no new trades after this)
- Minutes since open: {N}
- Current trading window: [Opening Momentum / Mid-Day / Afternoon / Dead Zone / AVOID]
- Days to weekly expiry (Thursday): {N}

[SECTION 2: REGIME CONTEXT]
- Market regime: {trend_up | trend_down | mean_reversion | choppy | event_driven}
- Regime confidence: {%}
- Trade permission: {allowed | reduced | blocked}
- Preferred style: {trend_following | mean_reversion | observer_only}
- Position size multiplier: {0.0 – 1.0}
- Risk flags: {list}

[SECTION 3: VOLATILITY & OPTIONS MARKET CONTEXT]
- India VIX: {level} (change today: {+/-}%)
- VIX regime: {low <12 | normal 12-18 | elevated 18-25 | extreme >25}
- NIFTY Futures current price: {price}
- NIFTY VWAP: {price}
- Distance from VWAP: {+/-}%
- PCR (OI): {value} — {interpretation: bullish/bearish/neutral contrarian}
- ATM implied volatility: {%} — options are [cheap / fair / expensive]
- Max pain level: {price}
- Largest OI call wall: {strike} ({qty} contracts)
- Largest OI put wall: {strike} ({qty} contracts)

[SECTION 4: CHARTS — READ THESE CAREFULLY]
Chart 1: NIFTY Futures 15m candlestick (trend direction)
Chart 2: NIFTY Futures 5m candlestick (setup confirmation)
Chart 3: Bookmap Heatmap (last 30–60 min) — WHERE is liquidity clustering?
Chart 4: Footprint Chart — WHO is winning at each price? Buyers or sellers?
Chart 5: DOM Ladder — WHAT does the current order book look like RIGHT NOW?

[SECTION 5: ORDER FLOW OBSERVATIONS — PRE-COMPUTED]
- Current bid-ask imbalance (200-level): {buy%} bids vs {sell%} asks by quantity
- Largest resting bid (price, qty, orders): {data}
- Largest resting ask (price, qty, orders): {data}
- Depth absorption detected: {yes/no} at price {price}
- Spoofing alert: {yes/no} (large orders appearing and vanishing rapidly)
- Recent delta: {+/-} (net buyer/seller aggression last 5 minutes)

[SECTION 6: OPENING RANGE]
- Opening range high: {price} (set at 9:30 AM)
- Opening range low: {price}
- Current status: {inside range | broken above | broken below}
- Range expansion: {+/-}%

[SECTION 7: ACCOUNT STATE]
- Available margin: ₹{amount}
- Today's P&L: ₹{+/-}
- Daily loss limit: ₹{limit} — [{X}% consumed]
- Open positions: {list or "none"}
- Recent trades today: {count}

[SECTION 8: TRADE CONFIGURATION]
- Trade mode: {auto | manual}
- Max premium per lot budget: ₹{amount}
- Max lots: {1 | 2}
- Allowed option types: [CALL | PUT | BOTH]
- Expiry preference: {current week | next week}
```

---

### Tools the Agent Has Access To

```python
# INFORMATION TOOLS (read-only)
get_account_snapshot()           # funds, positions, holdings
get_order_book()                 # all today's orders
get_nifty_option_chain()         # fetches fresh option chain snapshot
get_nifty_atm_strike()           # computes current ATM strike from NIFTY price
get_super_order_list()           # existing super orders (open)

# CALCULATION TOOLS
calculate_margin_requirement(    # pre-validates if order will be accepted
    security_id, exchange_segment,
    transaction_type, quantity,
    price, product_type, order_type
)
calculate_option_lot_quantity(   # NEW: option-specific qty calculator
    budget_inr, atm_premium, max_lots
)

# EXECUTION TOOLS (require EXECUTIONER_ALLOW_LIVE_ORDERS=1)
place_intraday_equity_order(     # for limit/market option buy
    security_id, exchange_segment,
    transaction_type, quantity,
    order_type, price,
    product_type="INTRADAY",
    correlation_id=generated_uuid
)

# SAFETY TOOLS
get_kill_switch_status()         # is kill switch active?
activate_kill_switch()           # emergency halt (only if daily loss breached)
```

**Note:** NIFTY options are placed as equity orders on NSE_FNO segment. The `security_id` for the specific strike+expiry+type must be looked up from the Dhan security master CSV.

---

### Agent Instructions (System Prompt Core Rules)

```
You are CHRONOS-FNO, an intraday NIFTY 50 options trader.

CORE MISSION: Look at the charts and data provided. Decide whether to buy
1 lot of a NIFTY weekly option (Call or Put), or to WAIT. Never rush.

YOUR EDGE: You read the NIFTY futures order book to detect where large
institutions are placing orders before price moves. When you see genuine
absorption (large resting bids being consumed slowly without price falling),
it means buyers are in control. When you see iceberg selling (large offers
refilling at the same level), it means sellers are capping the move.

HARD RULES — NEVER VIOLATE:
1. If regime = choppy or event_driven → OUTPUT "WAIT". No analysis needed.
2. If VIX > 22 → OUTPUT "WAIT" (options are too expensive to buy).
3. If time is after 15:05 IST → OUTPUT "WAIT" (too late for new entries).
4. If time is between 12:00–13:30 IST → OUTPUT "WAIT" (dead zone).
5. If today's P&L loss already exceeds 60% of daily limit → OUTPUT "WAIT".
6. If an open position in NIFTY already exists → OUTPUT "WAIT" (1 position at a time).
7. If the account snapshot shows insufficient funds → OUTPUT "WAIT".
8. If depth data is stale (>3 minutes old) → OUTPUT "WAIT".
9. Never place a SELL order (no naked selling, no shorting options).
10. Maximum 1 lot per trade. Never 2 lots unless explicitly configured.

BEFORE ENTERING:
- Read Chart 1 (15m): What is the trend? Up, down, or sideways?
- Read Chart 2 (5m): Where is VWAP? Is price holding above or below?
- Read Chart 3 (Bookmap): Where has the most liquidity been sitting? Any walls?
- Read Chart 4 (Footprint): Are buyers or sellers winning at recent price levels?
- Read Chart 5 (DOM Ladder): What does the current order book look like right now?
- Check regime: Does the order flow story match the regime classification?
- Check PCR: If buying a call, PCR should not be extreme low (<0.6).
- Check ATM IV: Is it below 15%? Good. Above 20%? Be careful. Above 25%? Don't buy.

VALID DECISIONS:
- BUY CALL: Strong buy absorption in depth + price above VWAP + trend_up regime
- BUY PUT: Strong selling pressure in depth + price below VWAP + trend_down regime  
- WAIT: When the above conditions are not clearly met. WAIT is the most common output.

OUTPUT FORMAT (mandatory headers):
## Decision: [BUY CALL | BUY PUT | WAIT]
## Strike: [e.g., 25000CE | 25000PE | N/A]
## Security ID: [Dhan security ID from master CSV | N/A]
## Quantity: [75 | N/A]
## Order Type: [LIMIT | MARKET]
## Limit Price: [₹XX per unit | N/A]
## Reasoning: [3-5 sentences on what the charts showed and why]
## Risk: [What would invalidate this trade immediately?]
## Correlation ID: [UUID | N/A]
## Execution Status: [Attempted | Skipped]
```

---

## PART 5: THE MONITOR SYSTEM — F&O SPECIFIC REDESIGN

This is the most important improvement asked for. The current `trade_monitor_system.md` was designed for equity stocks. Options require a fundamentally different monitor because **time is an active enemy** in options — every minute you hold, theta decay costs you money even if price doesn't move.

### What Makes Options Monitoring Different from Equity Monitoring

| Factor | Equity Stock | NIFTY Option |
|---|---|---|
| Main risk | Price moves against you | Price doesn't move fast enough AND time decays premium |
| Stop-loss trigger | Price-based (below SL level) | Premium-based (below X% of entry) + time-based |
| Target trigger | Price-based | Premium-based (+X% gain) |
| Time sensitivity | Low (can hold overnight CNC) | Extreme (must exit by 3:20 PM, accelerating decay after 3 PM) |
| Volatility risk | Low | High — VIX spike can change option price without NIFTY moving |
| Delta changes | N/A | Near expiry, option moves more per point of NIFTY (gamma risk) |
| Theta schedule | None | ~Parabolic — accelerates as expiry approaches |

### F&O Monitor Architecture

```
fo_trade_monitor.py (new file)

States:
  idle          → No open option positions
  observing     → Position open, conditions normal
  theta_warning → Time decay accelerating (< 45 min left in session)
  pnl_warning   → Premium at 60% of entry (approaching stop)
  action_required → Deterministic exit trigger fired
  exiting       → Exit order placed
  resolved      → Position closed (with full P&L record)
  failed_safe   → Could not exit — escalate immediately
```

### Deterministic Exit Rules (fires immediately, no LLM consultation needed)

```python
DETERMINISTIC_EXIT_TRIGGERS = [
    # Rule 1: Stop-loss trigger
    {
        "name": "premium_stop_loss",
        "condition": "current_premium <= entry_premium * 0.65",  # -35% loss
        "action": "EXIT_IMMEDIATELY",
        "priority": 1
    },

    # Rule 2: Target trigger  
    {
        "name": "premium_target",
        "condition": "current_premium >= entry_premium * 1.45",  # +45% gain
        "action": "EXIT_IMMEDIATELY",
        "priority": 1
    },

    # Rule 3: Hard time stop — non-negotiable
    {
        "name": "eod_time_stop",
        "condition": "current_ist_time >= '15:05'",
        "action": "EXIT_IMMEDIATELY",
        "priority": 1,
        "reason": "Must be out before 3:20 PM exchange square-off. 15 min buffer."
    },

    # Rule 4: VIX spike during position
    {
        "name": "vix_spike_exit",
        "condition": "vix_intraday_change_percent >= +15",
        "action": "EXIT_IMMEDIATELY",
        "reason": "Sudden VIX spike indicates event risk — option premium going haywire"
    },

    # Rule 5: Regime flip
    {
        "name": "regime_flip_to_blocked",
        "condition": "regime.new_trade_permission == 'blocked' AND we_entered_on_allowed",
        "action": "EXIT_REVIEW",
        "reason": "Market conditions changed against our position"
    },

    # Rule 6: NIFTY direction reversal (for directional trades)
    {
        "name": "direction_reversal",
        "condition": "nifty_crossed_vwap_against_position AND premium_below_entry",
        "action": "EXIT_REVIEW",
        "priority": 2
    },

    # Rule 7: Stale data — protective mode
    {
        "name": "stale_market_data",
        "condition": "depth_data_age_seconds > 180 AND quote_age_seconds > 60",
        "action": "EXIT_REVIEW",
        "reason": "Cannot monitor position without fresh data — uncertainty too high"
    },

    # Rule 8: Dead zone entry (if somehow we entered during 12-1:30)
    {
        "name": "dead_zone_liquidation",
        "condition": "current_ist_time between '12:00' and '13:30' AND premium_below_entry",
        "action": "EXIT_REVIEW",
        "reason": "Premium being eaten by theta in dead zone"
    },

    # Rule 9: Daily P&L kill switch
    {
        "name": "daily_loss_kill_switch",
        "condition": "daily_realized_pnl <= -(capital * 0.03)",
        "action": "EXIT_ALL_AND_HALT",
        "priority": 0,  # Highest priority
        "reason": "Daily loss limit breached. No more trading today."
    },
]
```

### LLM Monitor Role (Advisory Only)

The LLM monitor runs every 5 minutes on an active position and answers:

```
Given the current charts and position state, classify as:
- HOLD: Thesis intact, depth still supportive, time is adequate
- TIGHTEN: Tighten stop-loss (premium stop from -35% to -20%), take partial profits
- EXIT_REVIEW: Something has changed — escalate for deterministic review
- NO_OPINION_STALE_DATA: Data too old to opine

Inputs to LLM monitor:
- Entry price, current premium, unrealized P&L, % from target, % from stop
- Time since entry, time remaining in session
- Current DOM ladder (chart)
- Current footprint (last 10 min) (chart)
- NIFTY price vs VWAP
- VIX level
- Regime status
```

### Monitor Snapshot Schema (F&O version)

```json
{
  "stage": "fo_trade_monitor",
  "generated_at_utc": "2026-06-27T09:45:00Z",
  "generated_at_ist": "2026-06-27T15:15:00+05:30",
  "position": {
    "instrument": "NIFTY27JUN2025CE25000",
    "security_id": "12345678",
    "exchange_segment": "NSE_FNO",
    "direction": "CE",
    "quantity": 75,
    "entry_premium": 180.0,
    "entry_time_ist": "09:47:23",
    "entry_order_id": "xxx",
    "current_premium": 220.0,
    "unrealized_pnl_inr": 3000.0,
    "unrealized_pnl_percent": 22.2,
    "stop_loss_premium": 117.0,
    "target_premium": 261.0,
    "time_since_entry_minutes": 18,
    "time_to_monitor_exit_minutes": 77,
    "days_to_expiry": 2
  },
  "greek_estimates": {
    "delta_approx": 0.52,
    "theta_per_hour_inr": -150,
    "vix_level": 14.2,
    "iv_percent": 13.8
  },
  "monitor_state": "observing",
  "deterministic_triggers_checked": 9,
  "deterministic_triggers_fired": 0,
  "llm_advisory": {
    "model": "gemini-1.5-pro",
    "opinion": "HOLD",
    "reasoning": "Depth still shows buy absorption above 24950. Footprint delta positive. NIFTY above VWAP. Thesis intact."
  },
  "data_quality": {
    "depth_data_age_seconds": 12,
    "quote_age_seconds": 4,
    "regime_age_minutes": 23
  }
}
```

---

## PART 6: SYSTEM REDESIGN — THE NEW ARCHITECTURE

### What Changes, What Stays

**KEEP (unchanged):**
- `NiftyDepthMonitor` (runs in `monitor` Docker service) — already perfectly designed
- `MarketRegimeAnalyzer` (runs in `regime` Docker service) — already works
- `SessionSupervisor` (runs in `sorting` Docker service) — keep as orchestrator
- `DhanService` — all data fetching is reusable
- `CandlestickChartService` — reuse for NIFTY futures charts
- `NiftyDepthChartGenerator` — already generates the 3 key charts
- `DhanExecutionToolkit` — already has all needed tools

**REMOVE (for F&O pipeline):**
- `Stage1Sanitation` — not needed (no stock scanning)
- `Stage2MomentumIgnition` — not needed  
- `Stage2LiquidityGate` — not needed
- `TickCollector` — not needed (NIFTY depth monitor replaces this)

**BUILD NEW:**
- `FoStockPacketBuilder` — builds the F&O specific data packet (options chain, regime, depth summary)
- `FoTradingAgent` — the new CHRONOS-FNO agent
- `FoTradeMonitor` — the options-specific post-entry monitor
- `FoOptionChartService` — option chain visualization (OI distribution chart)
- `FoSecurityResolver` — looks up the correct security_id for a given NIFTY strike/expiry

**ADAPT:**
- `SessionSupervisor` → add F&O mode: instead of triggering on Stage 2 changes, trigger on a timed schedule (every 30 min during trading hours, at 9:32 and 13:30 specifically)
- `run_session_supervisor.py` → add `fo_mode` env var to switch pipeline mode

### New Docker Service Layout

```yaml
services:
  # Unchanged services
  market-data-gateway:  # Dhan data proxy, port 8010
  regime:               # Regime analyzer, runs on schedule
  
  # Changed services
  monitor:              # Now ONLY runs NiftyDepthMonitor (already done)
                        # No more TickCollector or LiquidityGate

  sorting:              # Now runs FO Session Supervisor
                        # In FO mode: triggers FoTradingAgent on schedule
                        # In equity mode: runs existing Stage1/2 supervisor

  ai-trading-agents:    # Now runs FoTradingAgent OR StockAgent based on mode
                        # Port 8020, same HTTP gateway API

  fo-monitor:           # NEW service
                        # Runs FoTradeMonitor
                        # Polls positions, checks deterministic rules, runs LLM advisory
                        # Saves fo_trade_monitor_latest.json
```

### New Data Flow

```
09:15 AM: NiftyDepthMonitor starts recording (already running)
09:15 AM: RegimeAnalyzer starts collecting data

09:32 AM: FO Session Supervisor wakes up (opening range has formed)
          → Checks if conditions warrant agent run:
            - regime.new_trade_permission != 'blocked'
            - VIX < 22
            - Market is in opening momentum window
            - No open positions currently
          → If yes: POST /ai-trading/start to FoTradingAgent

FoTradingAgent.run_cycle():
  → Load regime_latest.json (staleness check)
  → Load nifty_depth_charts_latest.json (get chart paths)
  → Fetch fresh NIFTY futures 5m + 15m candlestick charts
  → Fetch fresh NIFTY option chain (ATM ±5 strikes, compute PCR, ATM IV)
  → Fetch account snapshot (funds, positions, P&L)
  → Compute order flow summary from nifty_market_depth_latest.json
  → Compute opening range from first-15m of futures candles
  → Build complete fo_packet.json
  → Call CHRONOS-FNO agent with 5 chart images + fo_packet text
  → Parse agent output (Decision, Strike, Security ID, etc.)
  → If Decision = BUY CALL/PUT:
      → calculate_margin_requirement() — pre-validate
      → place_intraday_equity_order() on NSE_FNO
      → Record trade in fo_session.json
      → Signal FoTradeMonitor to start watching

FoTradeMonitor (continuous loop every 30 seconds):
  → Check if any option positions exist
  → If yes: fetch current LTP of position
  → Run 9 deterministic trigger checks
  → If trigger fires: place exit order immediately, log trigger
  → Else: run LLM advisory (every 5 min)
  → Update fo_trade_monitor_latest.json

13:30 PM: Afternoon session — FO Session Supervisor checks again
          → Same conditions check → potentially triggers agent again
          (only if morning trade was resolved and no open position)

15:05 PM: Hard time-stop — FoTradeMonitor exits any remaining position
15:30 PM: Market close — FoTradeMonitor enters idle, saves daily summary
```

---

## PART 7: THE OPTION CHAIN CHART — NEW VISUALIZATION

The current system is missing one critical chart: the **option chain OI visualization**. This shows the agent where large OI is building (institutional positioning) which acts as magnetic price levels.

### What to Build: `fo_option_chain_charting.py`

```python
class FoOptionChainChartService:
    """
    Generates 2 charts from NIFTY option chain data:
    
    Chart 1: OI Distribution Bar Chart
      - X axis: Strike prices (ATM ± 10 strikes)
      - Y axis: Open Interest (in thousands of contracts)
      - Calls: Red bars (right side of ATM, shown as negative)
      - Puts: Green bars (left side of ATM, shown as positive)
      - Largest call wall: annotated (resistance)
      - Largest put wall: annotated (support)
      - ATM strike: highlighted with vertical line
      - Max pain level: highlighted with dashed line
    
    Chart 2: IV Smile / Skew Chart
      - X axis: Strike prices (ATM ± 10 strikes)
      - Y axis: Implied Volatility (%)
      - Calls: Red line
      - Puts: Blue line
      - Helps identify if market is pricing in upside or downside risk
      - Steep skew = fear; flat skew = complacency
    """
```

**Why this matters for the agent:** The agent can see visually that 25,200 CE has 50 lakh contracts of OI while 25,000 PE has 80 lakh contracts. This tells it: market makers have a HUGE put position, which means they are delta-hedged LONG futures → natural floor support around 24,800–25,000. The agent can fade a breakdown below this zone.

---

## PART 8: CAPITAL REQUIREMENTS & RISK MANAGEMENT

### Starting Capital Recommendation

| Capital Level | What's Possible | Risk Level |
|---|---|---|
| ₹10,000 | 1 lot only if buying OTM (<₹133/unit, 2–3 DTE). Almost no room for error. | 🔴 Very high |
| ₹25,000 | 1 lot ATM (1–2 DTE). Can sustain 2–3 consecutive losses. | 🟡 Manageable |
| ₹50,000 | 1 lot ATM (new week, more time value). 4–5 losing trades before stopping. | 🟢 Recommended minimum |
| ₹1,00,000 | 1–2 lots, more flexibility on strike selection and timing. | 🟢 Good starting point |

**Recommended starting capital: ₹50,000**

This allows:
- 1 lot of ATM NIFTY CE or PE at ₹130–180 per unit = ₹9,750–13,500 per lot
- Risk per trade: ₹3,500–5,000 (at -35% stop)
- Capital reserved for: 7–10 losing trades before forced pause
- Monthly target: 4–6 winning trades at +45% premium gain = ₹18,000–36,000 gross

### Position Sizing Formula

```python
def calculate_option_position_size(
    available_capital: float,
    atm_premium_per_unit: float,
    lot_size: int = 75,
    max_risk_per_trade_pct: float = 0.08,  # 8% of capital per trade
    stop_loss_pct: float = 0.35             # -35% of premium
) -> dict:
    
    # How much are we willing to lose on this trade?
    max_loss_inr = available_capital * max_risk_per_trade_pct
    
    # If we stop at -35%, the max premium we can buy is:
    # max_loss = premium_paid * 0.35
    # premium_paid = max_loss / 0.35
    max_affordable_premium = max_loss_inr / stop_loss_pct
    
    # Cost for 1 lot
    one_lot_cost = atm_premium_per_unit * lot_size
    
    # Never spend more than 25% of capital on a single option position
    hard_cap = available_capital * 0.25
    
    if one_lot_cost <= min(max_affordable_premium, hard_cap):
        return {"lots": 1, "total_premium": one_lot_cost, "max_loss": one_lot_cost * stop_loss_pct}
    else:
        return {"lots": 0, "reason": "premium_too_high_for_risk_budget"}
```

### Daily Risk Controls

```
Daily loss limit: -₹3,000 (6% of ₹50,000 capital)
→ When hit: kill switch fires, all positions closed, no new entries today

Weekly loss limit: -₹5,000 (10% of capital)
→ When hit: reduce size to 50% for 1 week

Monthly loss limit: -₹7,500 (15% of capital)
→ When hit: stop trading for rest of month, review system

Max trades per day: 2
Max consecutive losses before mandatory review: 3

Minimum required P&L target (per trade): ₹2,500 (at +45% on ₹5,500 premium)
Minimum R:R ratio: 1.3:1 (for options, lower than equity because premium decay limits loss)
```

---

## PART 9: IMPLEMENTATION SEQUENCE

Given your existing codebase, here is the exact sequence of work. Each phase is self-contained and testable.

### Phase 1: Data Foundation (Week 1) — No code changes needed for data

**Already done:**
- NIFTY depth monitor running → depth charts generating
- Regime analyzer running → PCR, VIX, option chain summary
- Candlestick chart service working

**Do:**
- Verify NIFTY futures security ID is correctly set in depth monitor
- Run the system one full market day and inspect:
  - `nifty_market_depth_charts/` → do charts look correct?
  - `regime_latest.json` → is PCR, VIX, option chain data populated?
- Build `fo_option_chain_charting.py` — the OI distribution + IV skew chart
- Adapt `charting_service.py` to generate candlestick charts for NIFTY futures specifically (it's designed for stocks currently)

### Phase 2: F&O Agent (Week 2) — The core build

- Build `FoStockPacketBuilder` — assembles fo_packet.json with all agent inputs
- Build `FoSecurityResolver` — given NIFTY + strike + expiry + CE/PE, returns security_id from Dhan master CSV
- Build `CHRONOS_FNO_Agent` (new `pipeline/fo/fo_agent.py`) — the trading agent
- **Run in paper mode first** (EXECUTIONER_ALLOW_LIVE_ORDERS=0):
  - Agent makes decisions, logs them, but places NO real orders
  - Run for 2 weeks minimum, log every decision and the outcome
  - Did the agent pick the right direction? Did the premium move as expected?

### Phase 3: F&O Monitor (Week 3)

- Build `FoTradeMonitor` (`pipeline/fo/fo_trade_monitor.py`)
- Implement all 9 deterministic exit rules
- Implement LLM advisory (reuse `mimo-v2.5-pro` or `gemini-1.5-pro`)
- Test with paper positions: manually create a fake position entry, watch monitor's behavior

### Phase 4: Integration & Live Testing (Week 4+)

- Connect FoTradingAgent → FoTradeMonitor handoff
- Update SessionSupervisor to support `FO_MODE=1` env var
- Start with 1 lot, ₹500 premium options (very cheap, 0-1 DTE on Thursday expiry)
- Run 20 paper trades → measure expectancy → only go live with positive paper expectancy
- Enable live orders (`EXECUTIONER_ALLOW_LIVE_ORDERS=1`)
- First live trade: ₹500 premium max, 1 lot (₹37,500 max cost, ₹13,125 max loss at -35%)

---

## PART 10: KEY DECISIONS SUMMARY

### What instrument?
**NIFTY 50 weekly options (buying only), traded on NSE_FNO segment via Dhan**

### What data feeds the signal?
**NIFTY futures 200-level order book** → already being captured, chartified, and ready for LLM vision

### What strategy?
**Order flow reading**: NIFTY futures depth absorption → directional bias → buy ATM or 1-OTM option → exit at +45% or -35% or time-stop

### What does the agent look at?
**5 images** (bookmap heatmap, footprint, DOM ladder, 5m candles, 15m candles) **+ structured JSON** (regime, option chain, PCR, VIX, account state)

### What tools does the agent use?
Already built: `calculate_margin_requirement`, `place_intraday_equity_order`, `get_account_snapshot`, `get_super_order_list`, `get_kill_switch_status`
New needed: `get_nifty_option_chain_snapshot`, `get_nifty_atm_strike`, `calculate_option_lot_quantity`

### What is the monitor?
A new `FoTradeMonitor` that runs 9 deterministic exit rules every 30 seconds + LLM advisory every 5 minutes on active positions. Fundamentally different from equity monitor because it tracks premium%, theta acceleration, VIX changes, and enforces a hard time-stop at 3:05 PM.

### How much to start with?
**₹50,000 minimum recommended.** Trade 1 lot at a time. Risk max 8% per trade (₹4,000). Hard daily stop at 6% loss (₹3,000). Paper trade 20+ rounds before going live.

### What is the biggest risk?
Theta decay. NIFTY weekly options expire every Thursday. If you buy an option and NIFTY doesn't move enough, the premium evaporates even if you're technically "right" about direction. This is why: (a) avoid the dead zone 12–1:30 PM, (b) prefer 1–2 DTE options when near expiry (cheaper, faster to reach target), (c) set time-stops ruthlessly.

---

## APPENDIX: FILES TO CREATE OR MODIFY

### New Files

```
python-backend/pipeline/fo/
├── __init__.py
├── fo_agent.py                  # CHRONOS-FNO agent
├── fo_trade_monitor.py          # F&O specific post-entry monitor
├── fo_packet_builder.py         # Builds the complete agent input packet
├── fo_security_resolver.py      # Resolves Dhan security IDs for NIFTY options
└── fo_option_chain_charting.py  # OI distribution + IV skew chart generator

python-backend/pipeline/runtime/
├── run_fo_agent.py              # Entry point for F&O agent loop
└── run_fo_monitor.py            # Entry point for F&O trade monitor loop
```

### Files to Modify

```
python-backend/pipeline/runtime/run_session_supervisor.py
  → Add FO_MODE=1 branch (skip Stage1/2, trigger FoAgent instead)

python-backend/pipeline/services/charting_service.py
  → Add generate_nifty_futures_charts() method (same charts, different security)

docker-compose.yml
  → Add fo-monitor service
  → Modify sorting service to support FO_MODE
```

### Files Unchanged (reuse as-is)

```
pipeline/services/nifty_depth_monitor.py     ← Already perfect
pipeline/services/nifty_depth_charting.py    ← Already perfect
pipeline/services/dhan_execution_toolkit.py  ← Already has all needed tools
pipeline/services/dhan_service.py            ← Already has option chain fetch
pipeline/regime/regime_analyzer.py           ← Already has VIX, PCR, option chain
pipeline/regime/regime_analysis_agent.py     ← Already produces structured output
```
