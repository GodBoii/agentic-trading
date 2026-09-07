# Stage 2: Intra-Finder

## Purpose

Intra-Finder watches the complete Stage 1 equity universe and answers:

1. Which stocks have unusual participation and realized movement now?
2. Has one of those stocks formed a fresh named momentum or mean-reversion setup?

Historical data describes normal behavior. Live Full Packet data supplies the
trigger. There is no fixed bar warm-up, indicator-event aggregation, readiness
score or periodic recheck queue.

## Live state

Each instrument uses the composite `(exchange_segment, security_id)` key and a
typed, bounded state containing:

- LTP, LTT, cumulative volume and session average trade price
- day and opening-range OHLC
- five-level depth, spread and persistent imbalance
- one-second price and traded-value samples
- completed one-minute bars
- historical ADV, ATR and same-time volume/range baselines
- activity percentiles, rank and setup state

Packet updates are constant-time. Ranking runs once per second from 09:15 to
09:30 and once every five seconds afterward.

## Activity ranking

The ranker first removes stale, incomplete, circuit-bound or wide-spread states.
It then calculates real cross-sectional percentile ranks for:

- time-of-day volume pace, with ADV turnover fallback
- five-minute realized volatility
- five-minute traded value

`hotness = min(volume percentile, volatility percentile)`. Both participation
and movement are therefore required. Traded value and spread break ties.

The first 60 stocks form the hot working set. Ranks 61 to 100 provide short
hysteresis so boundary movement does not repeatedly create and destroy setup
state. Setup detection and agent admission run only for the top 10 ranks.

## Setup families

Production detectors are explicit state machines:

- `OPENING_DRIVE`
- `GAP_REJECTION`
- `OPENING_RANGE_ACCEPTANCE`
- `VOLATILITY_IGNITION`
- `VWAP_REVERSION`

Opening-drive detection can trigger after seconds of live observation without a
completed minute bar. Opening-range setups become available after 09:30. Gap
setups are disabled on deterministic corporate-action ex-dates.

Every setup follows `IDLE -> ARMED -> TRIGGERED` and resets when its qualifying
condition fails. Holding periods are 5 to 8 seconds, not five-minute waiting
windows. Triggered events expire after 30 to 45 seconds. The same setup family
on the same stock cannot re-arm for five minutes after a trigger.

## Agent contract and controls

The existing workflow remains:

```text
deterministic trigger -> stock agent -> current risk and execution checks
```

Each event carries `armed_at`, `triggered_at`, `expires_at`, trigger level,
invalidation, activity rank, percentiles, compact recent bars and five-level
depth. Intra-Finder and the AI gateway cap concurrent new agent work using their
configured limits. The gateway and stock runner reject expired events.

Account admission checks active positions, pending orders and reserved analysis
slots before building charts. The account-capital tiers allow three trades below
Rs 2,000, five from Rs 2,000 through Rs 5,000, and ten above Rs 5,000. Manual margin
allocations can reduce that count when capital cannot support the full tier.

Scanner direction, setup labels, scores and explanations stay in the event
archive. The stock agent receives observed market data and charts, chooses BUY,
SELL or no trade independently, and has no tool-call count limit. Event expiry
controls admission; it does not impose a deadline on an admitted model run.
Fresh funds, active-trade capacity, current prices and the agent's stop/target
geometry are rechecked before protected order placement. Price rejections return
the refreshed market state for reassessment. See [trading agent policy](trading-agent-policy.md).

## Recording

Full-universe one-second numeric summaries are retained for baseline research.
Raw JSON packets default to hot stocks only. This avoids multiplying the old
hundreds-of-megabytes partial-session archive by the larger universe.

Defaults:

```text
INTRA_FINDER_SHADOW_MODE=0
INTRA_FINDER_RECORD_ALL_RAW_PACKETS=0
INTRA_FINDER_RECORD_HOT_RAW_PACKETS=1
```

The shadow switch remains available for incident response and offline testing,
but Docker starts the requested small-capital live path by default.

## Recovery and health

Current-session compact state is checkpointed. A restart restores recent price,
value, depth, bars, opening range and setup state. If an after-09:30 restart has
no opening range, background recovery is rate-limited to 100 queued instruments
at a time and never blocks packet processing.

Health and status expose feed coverage, eligible rank population, hot count,
rank duration, candidate count, events, dispatch concurrency, gate failures and
raw capture scope.

The old indicator engine and trade-readiness model remain importable only for
historical replay compatibility. The live scanner does not import or execute
them.
