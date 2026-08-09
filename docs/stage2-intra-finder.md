# Stage 2: Intra-Finder

## The simple idea

Intra-Finder watches every Stage 1 survivor and asks:

> Is this stock forming a confirmed ORB or VWAP setup now, with enough volume,
> depth and execution capacity to justify an AI-agent run?

It does not choose a fixed top 30. Every stock must independently pass the live
evidence threshold.

## Current validation status

Keep Intra-Finder in shadow mode. The available July 31, August 3, and August 4
recordings do not support automatic scalp or agent triggering yet. A leakage-safe
indicator/order-flow research layer and its failed holdout result are documented
in [Stage 2 setup-quality research](stage2-quality-research.md). The production
score below describes the existing event collector; it is not a proven trading
edge.

## WebSocket limits

One WebSocket connection can hold thousands of instruments. Dhan limits a
single subscription message to 100 instruments. These are different limits.

For 250 stocks, the logical subscription batches are 100, 100 and 50. They are
sent over one Full Packet connection. Full Packet supplies price, volume, day
OHLC and five bid/ask levels.

## Features

Intra-Finder derives:

- Session VWAP from Dhan's average traded price.
- The 09:15–09:30 opening range.
- Relative volume compared with the same time on previous days.
- Short-term volume acceleration.
- Best bid/ask spread.
- Top-five quantity and order-count imbalance.
- Estimated slippage for the configured trade amount.
- Feed freshness and depth completeness.

Raw packets are retained for seven days. Flat one-second observations are
retained for ninety days. Both are compressed Parquet partitions by date/hour.

## Setup states

- `WARMING_UP`: opening data is still forming.
- `WATCHING`: sufficient data exists but no setup is forming.
- `FORMING`: early setup evidence exists.
- `ARMED`: confirmation is present.
- `TRIGGERED`: the event was recorded/dispatched.
- `COOLDOWN`: an equivalent event was recently sent.
- `DATA_STALE`: the feed is not trustworthy.

## ORB

An Opening Range Breakout needs the completed first 15-minute range. A bullish
event confirms above its high; bearish confirms below its low. A temporary touch
does not qualify. Volume, spread, five-level capacity and directional depth must
also be acceptable.

## VWAP reclaim/pullback

For a bullish setup, price must first trade below VWAP, reclaim it, return close
to VWAP without failing, and show upward support. The bearish rule is mirrored.
This is intentionally stricter than merely checking whether price is above or
below VWAP.

## Score and dispatch

The score is 0–100:

- Structure: 35
- Volume: 20
- Depth: 20
- Spread/capacity: 15
- Data quality: 10

The initial threshold is 75. Hard gates can still block a high numerical score.
Every event ID is deterministic for its market date, stock, venue, setup,
direction and cooldown window. Restarts or repeated packets therefore cannot
create the same agent job twice.

Shadow mode records events only. Production event dispatch is enabled with:

```text
INTRA_FINDER_SHADOW_MODE=0
```

An event is permission to analyze, not a promise to trade. The agent retains its
final veto.

## Reliability and fail-closed behavior

Historical minute-of-day baselines are explicitly converted to
`Asia/Kolkata` before Stage 1 publishes them. A missing, old, or wrongly
time-zoned baseline makes the stock fail closed; volume acceleration cannot
silently replace unavailable RVOL.

If the process reconnects, the opening range, volume history, VWAP sequence and
confirmation state are preserved. A process restart restores a compact runtime
checkpoint. When the service genuinely starts after 09:30 and no checkpoint
contains the range, it recovers completed 09:15–09:30 one-minute candles
through the shared, rate-limited market-data gateway.

Confirmation is time based. Evidence must remain valid in separate five-second
buckets and persist for at least eight seconds. A burst of several packets in
the same millisecond can never arm a setup.

## Connection and health behavior

Dhan drives the protocol keepalive by sending server pings. Intra-Finder
disables the Python WebSocket library's separate client-initiated ping timeout,
which can otherwise close a healthy Dhan feed. It independently detects a
genuinely idle aggregate feed using a packet-idle deadline.

The health endpoint is available inside the container at:

```text
http://localhost:8040/health
```

It reports the requested universe, instruments actually observed, instruments
with Full Packets, aggregate packet age, real reconnects, opening-range
recovery and shadow-mode state. Quiet individual stocks are reported
separately from a globally disconnected feed.

If an instrument produces no WebSocket event after the verification grace
period, Intra-Finder checks its selected venue once through the shared quote
gateway. `observed_instruments` remains honest WebSocket coverage, while
`quote_verified_instruments` and `covered_instruments` explain quiet but valid
securities without pretending that a packet arrived.

Large Parquet and status writes are serialized on a background I/O worker, so
disk activity does not block the hot packet receive loop. Setup events contain
compact references and summaries for regime and NIFTY context instead of
embedding their complete result files in every JSONL line.
