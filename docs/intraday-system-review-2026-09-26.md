# Intraday system review, September 26, 2026

## Scope and evidence

I inspected the current Python trading pipeline, execution rules, deployment configuration, dashboard session reader, existing session reviews, native Agno sessions in Supabase, and the account's Dhan historical trade fills. The queries were read-only. The run window was August 28 through September 26, 2026, India time. The latest session returned was September 25. No order was placed, changed, or cancelled for this review.

The run store contains agent reasoning and tool results. A successful placement-tool result identifies an order accepted for submission; it does **not** prove a fill, an exit, or profit. Dhan's historical trade endpoint returned 338 intraday fills for this window, including per-fill charges. I grouped them by trading date, exchange, and security. For a group with equal buy and sell quantity, gross realized P&L is sale proceeds minus purchase cost, and net is gross less the six reported charge fields. I excluded unequal-quantity groups from realized P&L. This is a fill-based account reconciliation, not a contract-note audit; corporate actions, later adjustments, and any charge missing from the endpoint are not captured.

## What the last 30 days show

The database has 968 stock-agent sessions on 12 active dates in this window, for one user. There were 413 completed runs and 555 errors. Of the errors, 517 occurred on September 25. Every one of those runs ended with the same OpenRouter response: the request asked for up to 131,072 output tokens, exceeding the key's remaining credit allowance. None reached a trading tool. The failures continued from 09:15:39 to 15:00:22 IST, across 79 symbols and 517 distinct request IDs. Median interval between failed starts was 34 seconds. This is a full trading-day model outage with a missing stop or alert in the dispatch path, not evidence that 517 trades lost money.

| Date | Runs | Completed | Errors | Accepted order IDs |
| --- | ---: | ---: | ---: | ---: |
| Aug 28 | 53 | 39 | 14 | 5 |
| Aug 31 | 137 | 114 | 23 | 16 |
| Sep 1 | 74 | 73 | 1 | 24 |
| Sep 9 | 35 | 35 | 0 | 26 |
| Sep 10 | 2 | 2 | 0 | 0 |
| Sep 11 | 17 | 17 | 0 | 15 |
| Sep 15 | 12 | 12 | 0 | 9 |
| Sep 21 | 14 | 14 | 0 | 13 |
| Sep 22 | 59 | 59 | 0 | 36 |
| Sep 23 | 34 | 34 | 0 | 18 |
| Sep 24 | 14 | 14 | 0 | 12 |
| Sep 25 | 517 | 0 | 517 | 0 |
| **Total** | **968** | **413** | **555** | **174** |

The 174 accepted order IDs came from `place_protected_intraday_order` results. For completed runs before September 25, model duration was 64.74 seconds at the median, 93.75 seconds at the 75th percentile, and 329.13 seconds at the maximum. Among 174 accepted orders, median planned entry notional was ₹855.40, median planned stop risk ₹8, and median gross gain at the initial target ₹13. The median planned reward/risk ratio was 1.75. Fifty-one of 174 targets offered at most ₹10 gross; 153 offered at most ₹20 gross. These are planned values from tool arguments, not realized results. They explain why even a profitable strategy would produce modest rupee gains at this account allocation. They do not establish positive expectancy after costs.

## Actual broker results

Of 174 accepted parent order IDs, 169 appear in the historical fills and five do not. All 145 fully closed exchange-specific position groups contain at least one accepted agent parent. Nineteen groups contain more than one agent parent, so a group result is not always a one-order result. Other orders can also close an agent entry, as the September 9 review shows. Two September 9 groups remain unmatched: a BSE short and a separate NSE long in TCC. Their cash flows and ₹0.50 reported charges are excluded from the closed figures below. An NSE purchase did not close the BSE short.

| Date | Closed groups | Gross P&L | Reported charges | Net P&L |
| --- | ---: | ---: | ---: | ---: |
| Aug 28 | 5 | −₹43.00 | ₹15.28 | −₹58.28 |
| Aug 31 | 15 | +₹68.67 | ₹23.58 | +₹45.09 |
| Sep 1 | 20 | −₹81.99 | ₹30.07 | −₹112.06 |
| Sep 9 | 18 | −₹24.17 | ₹24.84 | −₹49.01 |
| Sep 11 | 15 | +₹25.37 | ₹13.63 | +₹11.74 |
| Sep 15 | 9 | +₹3.32 | ₹8.04 | −₹4.72 |
| Sep 21 | 11 | +₹34.67 | ₹12.16 | +₹22.51 |
| Sep 22 | 24 | +₹11.48 | ₹29.04 | −₹17.56 |
| Sep 23 | 16 | −₹105.24 | ₹12.71 | −₹117.95 |
| Sep 24 | 12 | +₹84.59 | ₹16.73 | +₹67.86 |
| **Closed total** | **145** | **−₹26.30** | **₹186.08** | **−₹212.38** |

There were 61 gross-winning and 84 gross-losing groups. After reported charges, 58 won and 87 lost. Median closed-group net result was −₹2.92. Net gains totaled ₹640.58 and net losses ₹852.96, giving a net profit factor of about 0.75. The average net winner was ₹11.04 and average net loser ₹9.80. That realized payoff needs about a 47% win rate to break even, while the observed rate was 40%. The worst closed-group net loss was ₹79.50. This is negative expectancy in the observed window, though the sample is only ten trading dates with fills and includes changing code, models, and operational conditions. The gross loss was small relative to the ₹186.08 in charges, but fees were not the sole cause: the strategy also lost ₹26.30 before them.

Across the pre-September-25 runs, placement tools reported 96 capacity blocks, 70 price-drift blocks, 16 stale quotes, 16 invalidated side setups, and three stale-candle blocks. These are tool-call counts, so retries can contribute multiple observations per run. A block is often a correct safety action; the volume of blocks is evidence that signals and chart-based decisions often arrived late relative to live prices.

The detailed September 9 audit found 660 signals, 35 agent starts, 26 submitted Super Orders, 23 filled entries, and 22 same-venue closures. Nine closed in profit and 13 in loss. Its broker-reconciled **−₹24.17 before fees**, excluding open TCC positions, agrees with the historical-fill calculation above. Twenty-two closed entries collapse to 18 date/venue/security groups because repeated entries in one security are netted together. The median signal-to-first-order attempt was 100.36 seconds and signal-to-fill 129 seconds. A Graphite short planned ₹7 of stop risk but closed through a separate market order at a ₹78.60 loss. The record cannot prove the exact cause of its failed protected exit.

## How the system trades

1. Universe Scanner prepares a broad NSE/BSE equity list and historical profiles before market open. A dated fallback universe keeps trading possible if the daily publication fails.
2. Intra-Finder consumes Dhan Full Packet data, ranks unusual activity, builds completed-minute indicator events and a deterministic readiness score, then dispatches selected candidates.
3. The account workflow checks authorization, available trade slots, broker state, and user allocation. It builds charts and a fresh decision snapshot.
4. A multimodal stock agent sees the charts and snapshot, chooses buy, sell, or no trade, calls quantity sizing, and may call the protected-order tool.
5. Execution rechecks positions, active orders, quote/candle freshness, price drift, margin, and stop/target geometry before sending a Dhan Super Order. Accepted but unfilled entries keep their trade slot until a terminal broker state.

The boundaries are sensible. The detector does not force a trade direction, and the placement tool has no unprotected fallback. The weak points are the time spent reaching a decision, incomplete lifecycle visibility after submission, fragile daily scanner publication, and missing financial attribution.

## Findings and priorities

### 1. Fix the model outage path before tuning signals

The September 25 failure rate was 517/517. The current local model wrapper sets `max_tokens=None`, while the persisted provider response says its request required a 131,072-token allowance. The precise default applied by the deployed SDK/provider needs verification; the saved run error proves the operational failure. Add a bounded, affordable output-token setting and a startup/provider preflight. On repeated billing or provider errors, stop new model dispatch for that provider, preserve signals as skipped with a reason, and alert once. Check the running deployment's model ID and token parameters before resuming live automated entry. The local model and Compose files currently have uncommitted edits, so do not assume this checkout matches production.

### 2. Build a broker-reconciled performance ledger

Persist one immutable chain from signal ID to agent run, order attempt, Dhan parent and child order IDs, fills, exchange/security key, charges, and realized exit. Reconcile it against broker order/trade/position books daily. Record gross and net P&L, risk-normalized return, fill rate, hold time, slippage, target/stop outcome, and unmatched positions. This review required joining live APIs and grouping fills outside the product. The dashboard currently presents agent sessions from Agno and hardcodes `executed_count: 0` in its summary; it is not a reliable monthly trade-performance report. The proposed ledger makes this accounting repeatable and auditable.

### 3. Monitor protection throughout the order lifecycle

September 9 confirmed that initial stop/target geometry was correct for all 26 submissions, but Graphite, TCC, and Pashupati exposed unresolved exit and venue-state cases. Add an order-update journal and watchdog that compares active child legs with same-venue open quantity. Distinguish pending entry, partial fill, armed stop, triggered but unfilled stop-limit, cancelled leg, terminal fill, and broker-state uncertainty. Alert on an open position without verified protection. Define and test an escalation policy before automatic corrective orders. Dhan's [Super Order API](https://dhanhq.co/docs/v2/super-order/) documents entry, target, stop, modification and cancellation, but initial acceptance is not proof of a completed protective exit.

### 4. Measure whether the edge survives delay and charges

The September 9 signal-to-fill median was 129 seconds, and the completed model runs in this 30-day window took about 65 seconds at the median before all other preparation and execution work. Log timestamps for signal, admission, data snapshot, chart completion, model request, each tool call, broker acknowledgement, fill, and exit. Compare opportunity remaining at each point. Backtest with time-ordered data, realistic bid/ask spread, nonfills, slippage, and Dhan fees. Dhan lists equity intraday brokerage as the lower of ₹20 or 0.03% per executed order, plus other charges; use actual contract notes for final net P&L. See [Dhan pricing](https://dhan.co/pricing/) and its [brokerage calculator](https://dhan.co/calculators/brokerage-calculator/).

Test a smaller chart/context package and bounded inference budget in shadow mode. A faster decision is useful only if execution quality and net expectancy improve. The safety preflight should stay in place.

### 5. Improve capacity use without raising risk limits blindly

The September 9 audit traced 417 blocked dispatches to full trade slots, including long-lived unfilled entries. Define a broker-confirmed expiry and cancellation policy for pending entries, including partial fills and ambiguous responses. Rank simultaneously eligible pending candidates and revalidate them before analysis. Do not release a slot until the broker confirms the entry cannot fill. Do not increase concurrent positions or leverage merely to raise rupee P&L.

### 6. Make morning data publication dependable

The September 17 read-only production check found the scanner reached its 90-minute guard after processing 1,500 of 3,520 baselines and published no new Stage 1 artifact. Trading used the September 15 fallback universe. The current checkout's configuration shows a 06:00 start and 10,800-second maximum, while that production observation reflected an earlier 07:00/5,400-second policy. Verify the deployed revision and actual daily publication before changing this again. Publish a validated base universe first, then incrementally refresh profiles with explicit coverage and staleness flags; keep the fallback age limit visible in admission metrics.

## Suggested decision sequence

1. Restore and verify model availability, then add provider-error circuit breaking and alerts. Treat September 25 as a production incident.
2. Implement the order/fill/charge ledger and protection watchdog. Reconcile the existing unmatched cases with the broker.
3. Collect several untouched live sessions with complete net P&L and timestamp traces. Establish baseline expectancy by setup, time of day, liquidity, side, and signal-to-fill delay.
4. Shadow-test changes to candidate priority, chart payload, model budget, and pending-order expiry against that baseline. Promote only changes that improve net risk-adjusted results without weakening execution safety.

The observed window lost ₹212.38 net on fully closed groups. A contract-note or account-ledger check should confirm the final charge total, and the two TCC venue positions still need explicit broker reconciliation. The next strategy decision should use this negative baseline, not the number of signals or submitted orders.
