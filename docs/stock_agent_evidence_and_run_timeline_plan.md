# Stock Agent Evidence, Charts, Tools, and Run Timeline Plan

Date: 2026-07-29  
Status: Implementation design only  
Scope: The single stock agent architecture  
Explicitly out of scope: balance fixes, global portfolio selection, and Stage-1 Full-feed implementation

## 1. Decisions

The target stock-agent input is:

1. Five neutral price charts:
   - Current day 1-minute
   - Current day 5-minute
   - Current day 15-minute
   - Previous day 5-minute
   - Previous day 15-minute
2. Four dedicated evidence charts:
   - Volume and participation
   - Momentum and volatility
   - Price-structure liquidity map
   - TPO market profile
3. Compact structured tools:
   - `get_security_overview`
   - `get_technical_data`
   - One compact, fresh `get_current_stock_state` immediately before the final decision

The target is therefore **nine images per stock-agent run**, not the old seven-timeframe bundle and not the current four-image bundle.

The charts will not contain role labels such as `SETUP`, `EXECUTION`, `STRUCTURE`, or `CONTEXT`. These labels can anchor the model toward a particular interpretation. Titles will identify only the security, timeframe, date, data cutoff, and factual metrics.

The agent will not be instructed to avoid institutional or operator interpretations. It remains free to form those conclusions from the evidence. The data layer and chart labels will remain factual about what was observed or derived, so the agent can distinguish an observation from its interpretation.

No DOM, CVD, footprint, bid/ask imbalance, or five-level-depth chart is included in this change. The historical inputs available from Dhan do not support those charts accurately. A separate recording design is documented in `docs/stage1_dhan_full_feed_recording_design.md`.

## 2. Current tool duplication

### 2.1 What `get_current_stock_state` currently contains

The current implementation calls the live snapshot tool internally and then obtains recent intraday history. Its result contains:

- A nested live-market payload
  - Last traded price
  - Average traded price
  - Last trade time and age
  - Cumulative session volume
  - Total buy and sell quantities
  - Best bid and ask
  - Spread
  - Five depth levels
  - Session open, high, low, and close
  - Circuit limits
- The latest market-data timestamp
- Eight recent 1-minute candles
- Four recent 5-minute candles

This is why the result is commonly about 3,000-6,000 characters.

### 2.2 Where it duplicates other evidence

| Current-state field | Also available from | Decision |
|---|---|---|
| Recent 1-minute candles | Current-day 1-minute chart | Remove the candle list |
| Recent 5-minute candles | Current-day 5-minute chart | Remove the candle list |
| Long OHLC sequences | `get_ohlc_snapshot` and charts | Do not expose them in current state |
| Session OHLC | Live quote/OHLC and price charts | Keep compactly because it is cheap and fresh |
| Indicator history | `get_technical_data` and charts | Do not add it to current state |
| Full five-level depth | Live snapshot | Leave out of the compact contract until the depth design is decided |
| Last price and freshness | No chart can guarantee final-decision freshness | Keep |
| Current partial candle | The rendered chart can become stale while the model reasons | Keep one compact partial candle |
| Latest completed candle | Useful for verifying the partial candle and final state | Keep one per required timeframe |

The key distinction is that a chart is historical evidence created at a particular cutoff. It is not a substitute for a final fresh market-state check. The correct optimization is to remove historical arrays, not to remove all current price data.

### 2.3 Target `get_current_stock_state` contract

The tool should make one fresh state acquisition and return a compact payload similar to:

```json
{
  "status": "success",
  "source": "dhan_quote_and_intraday",
  "security_id": "12345",
  "exchange_segment": "BSE_EQ",
  "as_of": "2026-07-29T14:41:08+05:30",
  "market_data_age_seconds": 1.2,
  "chart_as_of": "2026-07-29T14:39:00+05:30",
  "chart_age_seconds": 128.0,
  "quote": {
    "ltp": 267.25,
    "average_price": 265.84,
    "cumulative_volume": 184255,
    "session_open": 261.10,
    "session_high": 270.20,
    "session_low": 260.70,
    "previous_close": 260.45,
    "upper_circuit": 286.45,
    "lower_circuit": 234.45
  },
  "one_minute": {
    "latest_completed": {
      "timestamp": "2026-07-29T14:39:00+05:30",
      "open": 267.10,
      "high": 267.40,
      "low": 267.00,
      "close": 267.25,
      "volume": 1472
    },
    "current_partial": {
      "timestamp": "2026-07-29T14:40:00+05:30",
      "open": 267.25,
      "high": 267.35,
      "low": 267.15,
      "close": 267.25,
      "volume": 418
    }
  },
  "five_minute": {
    "latest_completed": {
      "timestamp": "2026-07-29T14:35:00+05:30",
      "open": 266.90,
      "high": 267.40,
      "low": 266.75,
      "close": 267.25,
      "volume": 7204
    },
    "current_partial": {
      "timestamp": "2026-07-29T14:40:00+05:30",
      "open": 267.25,
      "high": 267.35,
      "low": 267.15,
      "close": 267.25,
      "volume": 418
    }
  },
  "partial": false,
  "missing_fields": []
}
```

This is an illustrative schema, not sample market truth.

Expected result size: approximately **1,200-2,500 characters**, depending on missing fields and diagnostics.

The tool must not silently turn an upstream exception into an apparently complete result. It should return:

- `status`: `success`, `partial`, or `error`
- `partial`: boolean
- `missing_fields`: explicit field paths
- `errors`: sanitized upstream failure descriptions
- Separate quote, last-trade, and candle timestamps
- Freshness ages calculated by the backend

### 2.4 Removing `get_ohlc_snapshot`

`get_ohlc_snapshot` should be removed from the model-visible tool list.

The reason is not simply that images exist. It is that:

- The five price charts already carry the historical OHLC shape needed for visual analysis.
- The technical tool carries exact calculated values that are awkward to read from pixels.
- The final current-state tool carries only the last completed and partial candles required to bridge chart generation to decision time.
- An arbitrary 5-60 candle JSON response encourages large, duplicative calls without adding a clearly separate evidence class.

The implementation can retain a private OHLC-fetching helper for chart generation and internal calculations. Only the agent-facing tool is removed.

`get_live_market_snapshot` should also stop being model-visible. Its internal data-fetching function can be used by `get_current_stock_state`, but exposing both tools invites the agent to request substantially the same live data twice.

## 3. Nine-chart contract

The exact chart order should be stable:

1. `current_1m_price`
2. `current_5m_price`
3. `current_15m_price`
4. `previous_5m_price`
5. `previous_15m_price`
6. `current_volume_participation`
7. `current_momentum_volatility`
8. `current_price_structure_liquidity`
9. `current_and_previous_tpo_profile`

A stable order makes the prompt easier to understand and makes regression tests deterministic.

### 3.1 Five price charts

Price-chart titles should use a neutral format:

```text
Swiggy | 5m | 2026-07-29 | DATA THROUGH 14:40 IST
LAST ₹267.25 | VWAP ₹265.84 | ATR(14) ₹0.66
```

Allowed content:

- Candlesticks
- EMA 9
- EMA 21
- Session VWAP
- ATR(14) in the title
- A visible `PARTIAL` marker on an unfinished final candle
- A small number of factual, nearest relevant reference levels
- Confirmed patterns or zones when their derivation is deterministic and does not use future data

Remove from headings and prompt descriptions:

- `SETUP`
- `EXECUTION`
- `STRUCTURE`
- `CONTEXT`
- Directional words such as “bullish chart” or “bearish chart”

The previous-day 5-minute chart must be added alongside the existing previous-day 15-minute chart. No previous-day 1-minute or 1-hour chart is added.

#### Price-scale rules

Each timeframe should scale its visible y-axis from the candle range and only the nearby levels displayed on that chart. Distant PDL/PDH or zones must not flatten the candles.

Recommended deterministic rule:

1. Calculate visible candle low/high.
2. Add nearby plotted overlays that are within a configurable ATR distance.
3. Add 8-12% vertical padding.
4. Put distant levels in a small factual side list or omit them from that timeframe.
5. Never extend the price axis solely to include a distant reference line.

This preserves the improved candle readability already observed in the current charts.

### 3.2 Volume and participation chart

This chart uses only Dhan historical OHLCV and known session timing.

Recommended panels:

1. Current-session 5-minute volume bars
2. Same-time relative volume line
3. Cumulative session volume versus the prior-session same-time median
4. A compact volume-acceleration statistic

Definitions:

- **Time-of-day RVOL** at minute `t`:

  ```text
  current cumulative volume through t
  ------------------------------------
  median cumulative volume through t across completed prior sessions
  ```

- **Volume acceleration**:

  ```text
  volume in the most recent completed 5-minute window
  ----------------------------------------------------
  volume in the preceding completed 5-minute window
  ```

  Apply a median-volume denominator floor to avoid a meaningless ratio when the previous window is almost empty.

Correctness requirements:

- Fetch or reuse enough history for a meaningful baseline, initially 15 completed trading sessions.
- Exclude the current day from its own baseline.
- Compare matching market minutes, not simply the same row number.
- Exclude incomplete sessions from the baseline unless their coverage is explicitly adequate for the compared time.
- Mark the partial current bar.
- Share the same calculation function with Stage 2 so the chart and tool cannot disagree.
- Do not call green-candle volume “buy volume” or red-candle volume “sell volume”.
- Do not infer aggressor side from candle color.
- If an outlier scale transform is used, label it visibly.

### 3.3 Momentum and volatility chart

This chart contains calculated price momentum, not order flow.

Recommended panels:

- RSI(14) for 1-minute, 5-minute, and 15-minute timeframes
- ATR(14) and ATR as a percentage of close for the same timeframes
- Optional factual rate of change for completed bars

Correctness requirements:

- Calculate indicators with warm-up data from prior sessions.
- Do not reset the RSI/ATR calculation at market open and then display an invented neutral value while fewer than 14 bars exist.
- VWAP remains session-reset; RSI and ATR use adequate preceding candles.
- Show gaps for unavailable values rather than substituting `50` for RSI.
- Clearly mark partial timeframe values.
- Use the same resampling boundaries as the price charts.
- Do not add “buy”, “sell”, or setup labels.

### 3.4 Price-structure liquidity map

This is deliberately named a **price-structure liquidity map**, not DOM liquidity.

It uses Dhan OHLCV to show where price is likely to encounter or seek visible liquidity based on repeated highs/lows and known references. It does not claim to see queued orders.

Allowed evidence:

- Previous-day high, low, and close
- Current session high and low
- Opening-range high and low
- Confirmed swing highs and lows
- Equal-high and equal-low clusters within a deterministic tolerance
- Confirmed gaps
- Deterministically formed supply/demand candidate zones
- Completed-candle sweep/reclaim events

Example sweep rule:

1. A known reference level exists before the tested candle.
2. Price breaches the level by at least one tick or a small ATR-based buffer.
3. The completed candle closes back inside the prior range.
4. The event is timestamped at confirmation.
5. The implementation does not inspect future candles.

The chart title must say:

```text
PRICE-STRUCTURE LIQUIDITY MAP — OHLCV DERIVED
```

This protects factual correctness while leaving the agent free to reason about operator, institutional, or crowd behavior.

Not included:

- Order-book quantities
- Five-level imbalance
- Cancellations
- Replenishment
- Spoofing claims
- Aggressor-side volume

### 3.5 TPO market profile

The first implementation should be a **TPO/time-at-price profile**, not a falsely precise historical volume-at-price profile.

Dhan historical candles provide volume for the whole candle, not the exact volume executed at each price. Distributing candle volume across its price range would only be an estimate. Therefore, version one should show:

- Current-session TPO profile through the data cutoff
- Previous-session completed TPO profile
- TPO point of control
- 70% TPO value area high and low
- Initial-balance high and low from the first 60 minutes
- Profile range and single-print areas when deterministically available

Recommended construction:

- Use one-minute historical bars.
- Use 30-minute TPO letters/brackets.
- Use a tick-aware price-row size, with a documented cap so very volatile securities remain readable.
- Count each bracket once for each traversed price row.
- Choose POC by maximum TPO count, with a deterministic tie-break.
- Expand outward from POC until at least 70% of TPOs are covered to determine value area.
- Mark the current profile as incomplete.

A historical **volume profile** must be labeled `OHLCV BAR-RANGE ESTIMATE` if it is later introduced from candles. An exact volume-at-price profile should wait for recorded trade-level data.

## 4. What is not in the four new charts

Until live Full-feed recording is approved and validated, do not add:

- CVD
- Footprint
- DOM heatmap
- Bid/ask imbalance
- Order-book replenishment
- Trade-side volume
- Exact historical volume profile

The system cannot reconstruct these accurately from historical OHLCV. Displaying approximations without an explicit quality label would make the model more confident in data the system does not actually possess.

## 5. Agent-facing evidence contract

The stock-agent prompt should identify images only by neutral contents:

```text
Images 1-5: price charts in the declared timeframe order.
Image 6: current-session volume and participation.
Image 7: multi-timeframe momentum and volatility.
Image 8: OHLCV-derived price-structure liquidity map.
Image 9: current and previous TPO market profiles.
```

The prompt should explain:

- The time cutoff and whether the final bar is partial.
- TPO is time-at-price, not trade-side flow.
- Price-structure liquidity is OHLCV-derived, not a live order book.
- The agent may make its own market-participant interpretation, but it should state which observed facts support it.

Recommended tool sequence:

1. Read all nine images.
2. Call `get_security_overview`.
3. Call `get_technical_data` if exact metrics are needed.
4. Form a provisional conclusion.
5. Call `get_current_stock_state` exactly once immediately before the final decision.
6. Revise or confirm the decision using the fresh state.

The system should not force a tool call if its dependency failed. A tool result marked `partial` must be shown to the model as partial.

## 6. Chronological agent-run experience

### 6.1 Current gap

The current stock-agent execution calls Agno in non-streaming mode. The frontend receives project-level lifecycle events such as:

- Agent started
- Charts ready
- Agent completed or failed

The completed metadata can contain a reasoning trace and tool-call JSON, but those are rendered after the run and are not presented in their true chronological position. The visible experience therefore looks like:

```text
User input → native thinking → final response
```

even when the agent actually made several tool calls between reasoning steps.

### 6.2 Target timeline

The target frontend should show:

```text
Input
  ↓
Thinking block
  ↓
Tool call started
  ↓
Tool result or error
  ↓
Thinking block
  ↓
Additional tool call/result pairs
  ↓
Final response
```

For parallel stock agents, every event needs both:

- A per-agent monotonically increasing `sequence`
- The agent rank/security identity

Chronology must be ordered within each agent. The global display may interleave agents by timestamp.

### 6.3 Normalized event schema

Backend events:

| Event | Required fields |
|---|---|
| `stock_agent_input` | run ID, rank, security, input summary, timestamp, sequence |
| `stock_agent_thinking` | text block or delta, timestamp, sequence |
| `stock_agent_tool_call_started` | tool call ID, tool name, sanitized arguments, timestamp, sequence |
| `stock_agent_tool_call_completed` | tool call ID, duration, result length, preview, result reference, timestamp, sequence |
| `stock_agent_tool_call_error` | tool call ID, error class/message, duration, timestamp, sequence |
| `stock_agent_response_delta` | content delta, timestamp, sequence |
| `stock_agent_final` | final content, decision metadata, timestamp, sequence |

Agno already exposes the relevant streaming events, including reasoning, content, tool started, tool completed, tool error, and run completed. The stock-agent wrapper should normalize these rather than making the frontend understand Agno-specific objects.

### 6.4 Backend changes

1. Add an optional progress callback to the stock agent.
2. Run Agno with event streaming enabled.
3. Iterate over events and normalize them to the schema above.
4. Accumulate response content so the existing decision parser still receives a complete final response.
5. Preserve final run metrics and tool-call metadata.
6. Coalesce tiny reasoning/content deltas at a sentence boundary or every 100-250 ms.
7. Assign the sequence number on the backend.
8. Persist the complete normalized timeline in the session archive.
9. Publish live events through the existing pipeline event callback/WebSocket.

Do not fabricate reasoning text. If the provider does not emit reasoning for a run, show an `Analyzing…` status until a real event arrives.

### 6.5 Tool-result handling

The UI needs useful results without flooding the WebSocket:

- Always send exact character/byte length.
- Send a compact live preview, initially capped around 2,000 characters.
- Persist the full sanitized result and expose it by a `result_ref`.
- Allow the frontend to expand/fetch the full result on demand.
- Show result status, duration, freshness, and whether it was partial.
- Redact access tokens, credentials, request headers, and environment values.
- Keep security IDs and market values because they are required evidence.

The frontend card should show:

```text
get_current_stock_state
Succeeded in 1.24s · 1,842 characters · data age 1.2s
[arguments] [result preview] [open full result]
```

For an error:

```text
get_technical_data
Failed in 10.01s · Dhan historical request timed out
```

### 6.6 Frontend changes

1. Replace the post-run raw tool JSON as the primary presentation with a chronological timeline.
2. Keep the raw metadata panel as an advanced diagnostic view.
3. Render thinking blocks, tool calls, tool results, and final response as distinct cards.
4. Group streamed deltas into readable blocks.
5. Deduplicate by `(run_id, rank, sequence)` after reconnect.
6. Restore the same timeline from persisted session data for historical runs.
7. Auto-scroll only while the user is already near the bottom.
8. Make long tool results expandable.
9. Show failures inline where they happened, not only in a final error banner.

### 6.7 Run-level tool statistics

Every completed agent run should also expose a compact audited summary:

- Total tool calls
- Successful calls
- Partial results
- Failed calls
- Success rate, with partial kept separate from success
- Total and average tool latency
- Total result characters/bytes
- Average and largest result size
- Per-tool call count, success count, latency, and result-size distribution
- The largest individual tool results and their content category

Example:

```json
{
  "tool_calls": 3,
  "succeeded": 2,
  "partial": 1,
  "failed": 0,
  "success_rate": 0.6667,
  "total_result_characters": 9214,
  "largest_result": {
    "tool": "get_technical_data",
    "characters": 5271,
    "content_category": "multi_timeframe_indicators_and_levels"
  }
}
```

The backend should calculate this from actual normalized tool-completion/error events, not by parsing the model's final prose. This makes future run audits reliable and lets the UI show both chronology and aggregate health.

## 7. Order-state truth

### 7.1 What “stop calling TRANSIT executed” means

In simple words:

> `TRANSIT` means Dhan has received or is processing the order. It does not prove that shares were bought or sold.

Only a confirmed traded quantity proves execution.

Target internal states:

| Dhan/order observation | System meaning |
|---|---|
| Request accepted / `TRANSIT` | `SUBMITTED` or `PENDING` |
| `PENDING` | Waiting at broker/exchange |
| `PART_TRADED` | Partially filled; record actual filled quantity |
| `TRADED` | Filled; terminal success |
| `REJECTED` | Terminal failure; retain rejection reason |
| `CANCELLED` | Terminal cancellation |
| No terminal response by monitoring deadline | `UNKNOWN`, not executed |

Implementation approach:

1. Save the broker order ID after submission.
2. Listen for Dhan order-update/postback events.
3. Poll `get_order_by_id` as a recovery path if no update arrives.
4. Reconcile updates idempotently by broker order ID.
5. Count a trade as executed only when filled quantity is greater than zero.
6. Do not treat transport success, HTTP success, or `TRANSIT` as a fill.
7. Surface `UNKNOWN` for unresolved states and reconcile later.

This is an accounting/truth correction. It is separate from the balance issue and does not change balance handling.

### 7.2 Pending-order TTL and setup revalidation

In simple words:

> A limit order can remain waiting after the market situation that justified it has disappeared. TTL gives that waiting order an expiry time. Revalidation cancels it sooner if its original conditions become false.

The more accurate name is:

- **Pending-order revalidation before fill**
- **Post-fill verification after a fill**

It is impossible to guarantee a final check at the exact exchange matching instant. A cancellation and a fill can race. The design therefore reduces stale fills but cannot mathematically eliminate them.

Proposed design:

1. At decision time, store an immutable setup snapshot:
   - Decision timestamp
   - Chart/data cutoff
   - Intended entry, stop, and target
   - Reference level/VWAP relationship
   - Maximum acceptable spread and adverse movement
   - Invalidation rules
2. Assign `valid_until`, expressed as time and optionally a completed-candle limit.
3. While the order is pending, consume fresh quotes/candles.
4. Cancel if:
   - TTL expires
   - Price crosses the stored invalidation level
   - The required breakout/reclaim fails on a completed candle
   - Spread or data staleness exceeds the stored limit
   - The potential stop distance/risk changes beyond tolerance
5. If a fill notification wins the race, record the fill first and then run post-fill verification.
6. Do not automatically exit an invalid post-fill position until an explicit position-management policy is approved.

The safer alternative for setups that require confirmation is not to place a resting order early. The system can watch for the confirmation condition and submit only after it occurs. This reduces stale pending orders but may increase missed entries and slippage.

This plan should be implemented only after the TTL values and invalidation policy are approved.

## 8. Global candidate ranking and simultaneous limits

In simple words:

> Today, several stock agents can independently say “take my trade.” Global ranking means the system first compares all proposed trades and permits only the strongest one or few. A simultaneous limit is a final account-wide rule such as “never have more than two open trades” or “never risk more than ₹X across all open stops.”

Example:

- Four agents propose A, B, C, and D.
- The system normalizes confidence, evidence quality, freshness, reward/risk, liquidity, and correlation.
- It ranks them A, C, B, D.
- If the configured maximum is one new trade, only A proceeds.
- If A and C are highly correlated, the account-wide layer may still allow only one.

This is not a balance correction. It is a portfolio-level selection and risk feature.

Per the current instruction, this is **explanation only and deferred**. It is not part of the present implementation plan.

## 9. Implementation sequence

### Phase 0 — Lock fixtures and contracts

- Save representative closed-market Dhan OHLCV fixtures.
- Save a complete and a partial live-state fixture.
- Define the nine-image names and order.
- Define the compact current-state JSON schema.
- Define the normalized agent-event schema.

### Phase 1 — Consolidate agent tools

- Convert the live snapshot implementation to a private helper.
- Remove `get_live_market_snapshot` from the agent toolkit.
- Remove `get_ohlc_snapshot` from the agent toolkit.
- Rewrite `get_current_stock_state` to the compact schema.
- Add explicit partial/error/freshness metadata.
- Update the stock-agent tool instructions.

### Phase 2 — Produce the five price charts

- Set current timeframes to 1, 5, and 15 minutes.
- Set previous timeframes to 5 and 15 minutes.
- Remove role labels from chart titles and prompt descriptions.
- Add ATR(14) to every price-chart title.
- Preserve local y-axis scaling and partial-candle markers.
- Add golden-image tests.

### Phase 3 — Produce four dedicated charts

- Build one shared indicator/resampling data layer.
- Implement volume/participation with a 15-session baseline.
- Implement multi-timeframe momentum/volatility with warm-up data.
- Implement OHLCV-derived price-structure liquidity.
- Implement current/previous TPO profile.
- Attach data-cutoff and quality metadata to each image.

### Phase 4 — Update the agent evidence contract

- Supply the nine images in the exact stable order.
- Use neutral descriptions.
- Explain data limitations.
- Keep institutional/operator interpretation available to the agent.
- Require the final compact current-state check.

### Phase 5 — Stream and persist the real run timeline

- Enable Agno event streaming in the stock-agent wrapper.
- Normalize and sequence events.
- Publish through the existing WebSocket path.
- Persist full sanitized tool results and the timeline.
- Render chronological events in the frontend.
- Verify reconnect/deduplication behavior.

### Phase 6 — Correct terminal order truth

- Introduce explicit submitted/pending/partial/traded/rejected/cancelled/unknown states.
- Reconcile by broker order ID.
- Count only filled quantity as execution.
- Preserve existing balance behavior.

### Phase 7 — Evaluate before live rollout

- Replay historical stock-agent inputs with the old and new chart bundles.
- Compare tool count, tool-result size, latency, missing fields, and decisions.
- Run paper/shadow mode for multiple sessions.
- Check that extra evidence improves calibration rather than merely increasing confidence.
- Roll out only after chart and event-stream invariants pass.

Pending-order TTL/revalidation and global candidate ranking remain separate approval items.

## 10. Verification checklist

### Tools

- Agent cannot call `get_live_market_snapshot`.
- Agent cannot call `get_ohlc_snapshot`.
- `get_current_stock_state` contains no candle arrays.
- Current state reports freshness and partial/missing fields.
- Chart and current-state timestamps are distinguishable.

### Price charts

- Exactly five price charts.
- Previous-day 5-minute and 15-minute charts exist.
- No role words in headings.
- ATR(14) is present.
- Distant levels do not compress candles.
- Partial candles are visibly marked.

### Dedicated charts

- Exactly four dedicated charts.
- No depth/CVD/footprint fields are present.
- RVOL baseline excludes current session.
- RSI/ATR have sufficient warm-up.
- Liquidity map uses no lookahead.
- TPO POC and value area are deterministic.
- Estimated historical volume-at-price is not presented as exact.

### Agent timeline

- Every tool call appears where it occurred.
- Successful and failed tool calls are distinguishable.
- Tool duration and result length are visible.
- Full sanitized results are available on demand.
- Historical runs reproduce the same chronology.
- Reconnect does not duplicate events.

### Order truth

- `TRANSIT` never increments executed trade count.
- Partial fills record actual filled quantity.
- Unknown outcomes remain unknown until reconciled.
- No balance behavior is changed.
