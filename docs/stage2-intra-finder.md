# Stage 2: Intra-Finder

## The simple idea

Intra-Finder watches every Stage 1 survivor and asks:

> Did a new technical or candlestick event just appear on a completed one-minute candle?

If the answer is yes, it groups nearby events for that stock and sends one compact evidence packet to the stock AI agent. The event is an **attention flag**, not a claim that the stock will rise or fall. The AI agent reads the charts, structure, volume, liquidity, risk and broader context before choosing `TRADE` or `SKIP`.

There is no fixed top 30, and the old 75-point predictive ORB/VWAP gate is no longer the active detection path.

## Why completed candles are important

Events are calculated only when a one-minute candle has closed. A changing, unfinished candle can temporarily look like a doji, engulfing candle or EMA cross and then look completely different at the close. Waiting for the next minute's first tick prevents this form of look-ahead and repainting.

Each candle stores open, high, low, close, minute volume and session VWAP. The engine keeps the most recent 120 completed candles per stock.

## Events detected

The first version recognizes:

- EMA 9 crossing above or below EMA 21.
- RSI 14 entering or leaving the oversold level of 30.
- RSI 14 entering or leaving the overbought level of 70.
- Doji, hammer and shooting-star candles.
- Bullish and bearish engulfing candles.
- A candle close crossing session VWAP.
- A candle close breaking the completed 09:15-09:30 opening range.
- One-minute volume at least 1.8 times the median of recent one-minute volume.

RSI oversold is not automatically bullish, and overbought is not automatically bearish. These directions are hints for agent investigation. A trend can remain overbought or oversold for a long time.

## Transition-only behavior

Intra-Finder emits a cross only when the relationship changes. It does not send `price above EMA` on every packet. RSI events fire when a threshold is crossed, not for every candle that remains beyond it.

Each event type also has a default ten-minute cooldown per stock. This prevents repeated doji candles or noisy VWAP crossings from producing a new AI request every minute.

If an inactive stock receives no new tick for several minutes, its last candle closes late from the detector's point of view. The candle is retained for indicator history, but an event more than 60 seconds late is not emitted as a current opportunity.

## Event aggregation

The first new event opens a 60-second aggregation window. Other events for the same stock during that window are added to the same evidence packet. For example, a bullish engulfing candle, VWAP cross and volume surge can become one request rather than three agent runs.

The combined direction is:

- `LONG` when all directional evidence is bullish.
- `SHORT` when all directional evidence is bearish.
- `MIXED` when bullish and bearish evidence conflict.
- `NEUTRAL` when the evidence has no directional claim.

Mixed and neutral packets are still valid attention flags. The AI agent is explicitly told to reject weak, noisy or contradictory evidence.

## Basic safety gates

The watcher deliberately does not demand predictive RVOL, depth imbalance or a high setup score. Before requesting an expensive agent run, it only checks operational safety:

- The live packet is fresh and complete enough to trust.
- Five bid and ask levels are present.
- Spread and estimated slippage are within configured limits.
- The feed has finished warming after a reconnect.
- The stock is not unusably close to a circuit condition.
- It is before the new-entry cutoff, initially 15:00 IST.
- The same stock is not inside its default 20-minute agent cooldown.

The displayed 0-100 value is an **attention priority** used to order simultaneous requests. It is not trade confidence, predicted win probability or a required threshold. Any detected event may form a packet if the basic safety gates pass.

## Agent dispatch controls

Event IDs are deterministic from the market date, stock venue, first evidence time and event types. Repeated packets and restarts therefore cannot create the same job twice.

At most three new stock analyses run concurrently. Additional valid packets wait in attention-priority order, but the queue is capped at 50 packets and a queued event expires after 120 seconds. This prevents the agent from analyzing a once-interesting move after the market has already changed. Queue expiry is capacity control, not a statement that the event was technically wrong. A stock-specific 20-minute cooldown prevents the system from repeatedly spending an agent on the same stock, while the event-type cooldown reduces repeated indicator noise.

## Shadow mode

Shadow mode records exactly what would have been sent but does not call an agent:

```text
INTRA_FINDER_SHADOW_MODE=1
```

This remains the default in Docker Compose. Changing it to `0` enables agent requests; it does not by itself enable live orders. Live execution has a separate safety switch.

Useful configuration values are:

```text
INTRA_FINDER_INDICATOR_AGGREGATION_SECONDS=60
INTRA_FINDER_INDICATOR_EVENT_COOLDOWN_SECONDS=600
INTRA_FINDER_STOCK_AGENT_COOLDOWN_SECONDS=1200
INTRA_FINDER_INDICATOR_VOLUME_SURGE_RATIO=1.8
INTRA_FINDER_INDICATOR_MAX_EVENT_LAG_SECONDS=60
INTRA_FINDER_AGENT_QUEUE_MAX=50
INTRA_FINDER_AGENT_QUEUE_MAX_AGE_SECONDS=120
```

## WebSocket and recovery behavior

One Dhan WebSocket can monitor thousands of instruments, while one subscription message contains at most 100. For 250 stocks, Intra-Finder sends batches of 100, 100 and 50 on the same connection.

The service preserves its minute bars, current candle, indicator snapshot, pending aggregate, cooldowns and idempotency state in its runtime checkpoint. After reconnection it resubscribes to the complete Stage 1 universe. After a process restart it restores the compatible checkpoint before detecting new events.

The health endpoint at `http://localhost:8040/health` reports detector mode, requested/observed coverage, packet age, reconnects, events detected, aggregates formed, pending aggregates and shadow state.

Raw packets are retained for seven days. Normalized one-second observations are retained for ninety days. Setup-event records and decisions are retained long-term.

## What this system cannot know directly

Five-level depth and indicators do not reveal the identity or true intention of a bank, operator, hedge fund or investor. They also cannot show every hidden order, another trader's exact stop-loss, or guarantee that a pattern will work. The watcher notices observable changes; the AI agent evaluates whether those changes form a sensible, executable trade.
