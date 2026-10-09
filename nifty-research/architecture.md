# Architecture and research decisions

Started 30 September 2026, IST.

## Current flow

```mermaid
flowchart LR
    A[Original local archives] --> B[Read-only validation and hashes]
    B --> C[Continuous session segments]
    C --> D[Causal minute features]
    D --> E[Training on earlier dates]
    E --> F[Held-out forecasts and ablations]
    F --> G[Conditional quote replay]
    G --> H[Evidence report and unresolved risks]
```

Collection and production trading remain outside this workspace. The Ubuntu collector stays parked. Raw archives are not copied or rewritten.

## Data contracts

Every feature has a decision timestamp. Its market source timestamp precedes that timestamp. Depth is joined backward with a two-second maximum age; its two sides must be from the same security and no more than one second old. Prices must be positive, book sides ordered, and best bid below best ask. Invalid records are counted, not silently converted into usable evidence.

Market state resets on a gap over ten seconds, a contract change, a cumulative-volume decrease or a local event-sequence restart. Estimated signed volume begins at zero for every segment. The collector's stored CVD is audited but never used as a model feature. A first packet's latest-trade quantity is not counted as a known volume increment.

A minute is complete only when its first and last packets reach within two seconds of the minute boundaries. A prediction needs six complete historical minutes. Scoring also needs a complete future horizon in the same segment. Test predictions do not depend on whether a future label exists. Partial final periods can therefore produce forecasts and unresolved option exits instead of disappearing from replay.

The forecast target is sampled futures quote midpoint return. It is not spot return, option return or a volatility forecast. Futures contract rollover never becomes a return across two security IDs.

## Experimental controls

All models use a common set of decision-time rows so data coverage cannot explain an ablation advantage. Ridge alpha, features, threshold and holding time are fixed before examining the first results. Model scaling and fitting use earlier dates only. A model may use prior test dates for later expanding-window training, as would be possible over time.

Overlapping five-minute labels are dependent. Paired error differences are aggregated by date before a descriptive bootstrap. The small number of dates and multiple model comparisons prevent a significance or production claim. A later fresh dataset must test the chosen hypothesis without further tuning.

## Strategy and execution contracts

The payoff library uses explicit long/short legs, real strikes and one common expiry. Payoff extrema use the piecewise-linear structure rather than an arbitrary plotted spot range. Unlimited upper-tail loss is represented explicitly. Maximum loss assumes all intended legs are filled and does not substitute for margin or intratrade stress testing.

Conditional replay chooses contract identities at decision time and never switches them to the new ATM strike while holding. It uses bid/ask sides, one-second latency and a fixed horizon. The futures price is an explicitly labelled ATM proxy. Missing quote sizes and exchange timestamps remain unresolved. An unpriced exit creates unresolved exposure and blocks further trades that date.

Replay policies are separate experiments, not positions in one combined portfolio. Results report rupees per assumed one-lot trade, not capital returns. No hypothetical broker fill, margin response, account balance or news score is manufactured.

## Agent architecture to build after numerical validation

The decision agent receives a timestamped evidence bundle containing coverage, horizon, forecast uncertainty, model version, event evidence and evaluated candidates. Candidate tools return contract IDs, quote times, executable prices, Greeks, costs, expiry risk, margin requirements and adverse scenarios. Missing fields produce an unavailable candidate.

The agent selects a candidate ID and an allowed exit policy. It cannot invent security IDs, quantities, margin numbers, Greeks or expected profits. No trade is a candidate. Exits and execution belong to deterministic controllers; an agent cannot disable loss, freshness, exposure or reconciliation limits.

Broker adapters must be isolated from research imports. Before integration they need paper fills, idempotent order reconciliation, partial-fill handling, cash/margin checks, static-IP configuration and recovery tests. Account-wide P&L exits must not unexpectedly close the separate stock strategy. Dhan's kill switch blocks trading after positions and pending orders are cleared; it is not a flatten instruction.

## Next data additions

1. Synchronized Nifty spot and point-in-time constituent weights and quotes.
2. Option bid/ask sizes, original timestamps and fixed contract identities.
3. Full option-chain snapshots with IV and Greeks across relevant expiries.
4. Event calendar and news with both publication and receipt timestamps.
5. Collector restart IDs, session IDs and reconnection diagnostics.
6. Actual paper-execution logs, rejection/latency distributions and legging exposure.

## Acceptance requirements

An additional feature must improve held-out forecasts or net decisions across dates, survive cost stress and retain its benefit on fresh untouched sessions. A strategy needs complete valuation, adverse-path testing, margin modelling and paper execution. The agent needs comparison with the same numerical candidate selector without an agent. Trading remains unavailable until those requirements have evidence.
