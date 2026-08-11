# Stage 2: Intra-Finder

## The simple idea

Intra-Finder watches every Stage 1 survivor and asks:

> Has a technical observation matured into a liquid, confirmed, well-located intraday opportunity that deserves an AI-agent review?

One-minute events now open a watch instead of immediately calling an agent. Intra-Finder evaluates completed five- and fifteen-minute structure, support/resistance location, target room, participation, persistent depth, spread, slippage and confirmation. Only an `ENTRY_READY` result crosses the configured readiness threshold and reaches the agent.

There is no fixed top 30. The output count is determined by independently qualified setups.

## Why completed candles are important

Events are calculated only when a one-minute candle has closed. A changing, unfinished candle can temporarily look like a doji, engulfing candle or EMA cross and then look completely different at the close. Waiting for the next minute's first tick prevents this form of look-ahead and repainting.

Each candle stores open, high, low, close, minute volume and session VWAP. The engine keeps 420 completed candles per stock, which covers one normal cash-market session and supports slower five- and fifteen-minute reasoning.

## Events detected

The first version recognizes:

- EMA 9 crossing above or below EMA 21.
- RSI 14 entering or leaving the oversold level of 30.
- RSI 14 entering or leaving the overbought level of 70.
- Doji, hammer and shooting-star candles.
- Bullish and bearish engulfing candles.
- A candle close crossing session VWAP.
- A candle close breaking the completed 09:15-09:30 opening range.
- One-minute volume at least 1.8 times the median of recent one-minute volume. A surge receives a direction only when the completed candle has a meaningful body and closes near the corresponding end of its range.

Entering RSI oversold or overbought is neutral evidence because it may represent continuing momentum. Exiting an extreme can support a reversal, but does not create a setup on its own.

## Transition-only behavior

Intra-Finder emits a cross only when the relationship changes. It does not send `price above EMA` on every packet. RSI events fire when a threshold is crossed, not for every candle that remains beyond it.

Each event type also has a default ten-minute cooldown per stock. This prevents repeated doji candles or noisy VWAP crossings from producing a new AI request every minute.

If an inactive stock receives no new tick for several minutes, its last candle closes late from the detector's point of view. The candle is retained for indicator history, but an event more than 60 seconds late is not emitted as a current opportunity.

## Event aggregation

The first new event opens a 60-second observation window. Related events are collected, then the stock enters `FORMING` while the readiness model waits for completed five-minute confirmation. A watch can be reevaluated every 60 seconds for up to ten minutes. Short-lived evidence expires sooner: volume after three minutes and VWAP/candlestick/RSI evidence after five minutes.

The combined direction is:

- `LONG` when all directional evidence is bullish.
- `SHORT` when all directional evidence is bearish.
- `MIXED` when bullish and bearish evidence conflict.
- `NEUTRAL` when the evidence has no directional claim.

Mixed and neutral observations are not dispatched. Conflicting structural transitions, conflicting recent price action and repeated signal churn are explicit rejection reasons.

## Hard gates and readiness scoring

Operational hard gates run first:

- The live packet is fresh and complete enough to trust.
- Five bid and ask levels are present.
- Spread and estimated slippage are within configured limits.
- The feed has finished warming after a reconnect.
- The stock is not unusably close to a circuit condition.
- It is before the new-entry cutoff, initially 15:00 IST.
- The same stock is not inside its default 20-minute agent cooldown.

The readiness model then scores five independent areas. Weak clues cannot compensate for a failed hard requirement.

| Component | Maximum | Meaning |
|---|---:|---|
| Five-/fifteen-minute structure | 30 | VWAP side, slower EMA alignment and directional progress |
| Location and target room | 25 | Nearby supportive level, opposing level and ATR-normalized room |
| Confirmation | 20 | Setup-family confirmation on completed five-minute candles |
| Participation | 15 | Time-of-day RVOL, volume acceleration, recent five-minute volume and trade freshness |
| Execution quality | 10 | Spread, slippage and persistent—not single-packet—depth support |

Default admission requires a score of 75, at least a ten-point advantage over the opposite direction, enough target room, adequate structure and participation, and a confirmed setup family. The score is not a win probability.

Candlestick names have deliberately small weights. A doji or volume surge alone is discarded. A hammer, shooting star or engulfing candle requires meaningful location and additional confirmation. A pattern-only reversal needs supporting RSI-exit or directional-volume evidence.

A bearish stock reaching support is not automatically shorted or bought. It remains under observation until price either confirms acceptance below support or produces a confirmed reversal. This protects the system from both shorting directly into support and guessing a reversal too early.

## Agent dispatch controls

Event IDs are deterministic from the market date, stock venue, first evidence time and event types. Repeated packets and restarts therefore cannot create the same job twice.

At most three new stock analyses run concurrently. The Intra-Finder dispatch queue is capped at 50 packets and expires queued work after 120 seconds. The AI gateway has a second bounded safety limit of 20 waiting events; it returns HTTP 429 instead of creating an unbounded backlog. Before a worker starts expensive analysis it expires an event older than 300 seconds. A stock-specific 20-minute cooldown prevents repeated agent spending on the same stock.

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
INTRA_FINDER_READINESS_SCORE_THRESHOLD=75
INTRA_FINDER_READINESS_DIRECTION_MARGIN=10
INTRA_FINDER_READINESS_MIN_COMPLETED_BARS=45
INTRA_FINDER_READINESS_MIN_ROOM_ATR=0.55
INTRA_FINDER_READINESS_MAX_LAST_TRADE_AGE_SECONDS=90
INTRA_FINDER_READINESS_OBSERVATION_SECONDS=600
INTRA_FINDER_READINESS_REEVALUATION_SECONDS=60
INTRA_FINDER_READINESS_MIN_CONFIRMATION_SECONDS=300
INTRA_FINDER_READINESS_MAX_ENTRY_DRIFT_ATR=0.80
INTRA_FINDER_AGENT_QUEUE_MAX=50
INTRA_FINDER_AGENT_QUEUE_MAX_AGE_SECONDS=120
AI_TRADING_EVENT_QUEUE_MAX=20
AI_TRADING_EVENT_MAX_AGE_SECONDS=300
```

## WebSocket and recovery behavior

One Dhan WebSocket can monitor thousands of instruments, while one subscription message contains at most 100. For 250 stocks, Intra-Finder sends batches of 100, 100 and 50 on the same connection.

The service preserves its minute bars, current candle, indicator snapshot, pending aggregate, cooldowns and idempotency state in its runtime checkpoint. After reconnection it resubscribes to the complete Stage 1 universe. After a process restart it restores the compatible checkpoint before detecting new events.

The health endpoint at `http://localhost:8040/health` reports detector mode, requested/observed coverage, packet age, reconnects, raw observations, readiness evaluations, successful readiness events, rechecks, pending watches and shadow state.

Raw packets are retained for seven days. Normalized one-second observations are retained for ninety days. Setup-event records and decisions are retained long-term.

## What this system cannot know directly

Five-level depth and indicators do not reveal the identity or true intention of a bank, operator, hedge fund or investor. They also cannot show every hidden order, another trader's exact stop-loss, or guarantee that a pattern will work. The watcher notices observable changes; the AI agent evaluates whether those changes form a sensible, executable trade.

# User affordability boundary

Intra-Finder never reads a user's trading amount when building or monitoring the global universe. Its common depth-capacity probe is one share only. Each accepted event carries the five raw depth levels needed by the downstream gateway to calculate a user's whole-share quantity and user-sized slippage.

For each configured user, downstream routing first resolves an effective amount: a fresh manual value when supplied, otherwise current available broker balance. It then requires `current price <= effective amount`, at least one whole share, sufficient five-level depth for `floor(effective amount / price)` shares, and acceptable estimated slippage. This user-specific pass can admit affordable events beyond a small fixed shortlist without altering the global Stage 1 universe. A failure suppresses only that user's agent dispatch. It does not suppress the global event or another user's route.
