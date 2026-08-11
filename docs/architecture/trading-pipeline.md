# Trading Pipeline Architecture

## What changed

The pipeline is separated by the kind of information each job uses:

1. **Universe Scanner** uses Dhan reference data and completed historical candles.
2. **Intra-Finder** watches the resulting stocks continuously with live Full Packet data.
3. **AI trading agents** start only after Intra-Finder observes and aggregates a new technical event.

The old `sorting` process mixed historical scanning, live scanning, scheduling and
agent triggering. A failure in one responsibility could therefore affect all of
them. The new services can restart and report health independently.

```mermaid
flowchart LR
    Auth["dhan-auth-manager"] --> Gateway["market-data-gateway"]
    Gateway --> Stage1["universe-scanner"]
    Stage1 --> Stage2["intra-finder"]
    Stage2 --> Agent["ai-trading-agents"]
    Regime["regime"] --> Agent
    Nifty["nifty-50-market-depth"] --> Agent
```

Regime and NIFTY information are context for the agent. They do not silently
remove a stock-specific setup.

## Container responsibilities

| Container | Owns | Does not own |
|---|---|---|
| `dhan-auth-manager` | Scanner-token validation, renewal and TOTP recovery | Website-user OAuth tokens |
| `market-data-gateway` | REST rate limits, historical data and recovery quotes | Live WebSocket sorting |
| `universe-scanner` | Master validation, ASM/GSM exclusion, historical filters and venue selection | Live prices |
| `intra-finder` | Full Packet capture, causal one-minute indicator/candle events, aggregation and event dispatch | Final trade decision or prediction of profitability |
| `nifty-50-market-depth` | NIFTY futures, options and deep-market context | Individual-stock qualification |
| `regime` | General market context | Blocking Intra-Finder events |
| `ai-trading-agents` | Final evidence/risk analysis and possible execution | Broad top-N scanning |

## Shared contracts

Every stock carries `isin`, `exchange_segment` and `security_id`. ISIN identifies
the security across exchanges. The segment and security ID identify the exact
venue used by Dhan. Downstream code must copy this identity; it must not infer
BSE or NSE from a symbol or number.

Critical snapshots are written to a temporary file and atomically renamed. A
reader therefore sees either the previous complete snapshot or the next complete
snapshot, never half-written JSON.

## Rollout safety

Intra-Finder defaults to `INTRA_FINDER_SHADOW_MODE=1`. It records indicator-event packets
without calling an agent. Replay the captured data and review events before
setting the value to `0`. Live order placement remains separately protected by
`EXECUTIONER_ALLOW_LIVE_ORDERS`.

# Per-user trading amount (dynamic Stage 2 routing)

The Universe Scanner and Intra-Finder are continuous backend services. A website user does not start a scan. Stage 1 stays global and uses only historical/reference data. Intra-Finder also remains one global live detector.

After a global indicator/candlestick event passes the common safety gates, the agent gateway evaluates it separately for every configured user. The amount field is optional. When it is blank, the gateway fetches current available broker balance and uses that as the effective amount. When a user supplies an amount, that fresh positive value becomes the effective amount. The route uses `floor(effective_amount / current_price)` whole shares; if the result is zero, that user is skipped while other users and global monitoring continue. Five-level depth and slippage are then estimated for that user's requested quantity. One user's rejection never removes the stock globally.

The effective amount is a strict cash/notional cap. Intraday margin data may be shown as evidence, but it cannot increase buying power. The mode, amount source, effective amount and requested quantity travel in the agent evidence packet. Current LTP is fetched again immediately before placement. Automatic mode also refreshes available balance; if either check no longer covers the requested notional, placement fails closed.

The current runtime represents multiple web-user configurations but uses one configured Dhan backend credential set. Per-user eligibility and evidence are isolated, but true per-user broker execution requires a credential resolver that creates a Dhan client for the routed `user_id`. Keep live orders disabled until that account isolation exists and is tested.
