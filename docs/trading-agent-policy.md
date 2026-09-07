# Trading agent policy

Updated September 7, 2026.

## Account capacity

The live Python runner and frontend preview use these account-capital tiers:

| Account capital | Maximum active trades |
| --- | ---: |
| Positive balance below Rs 2,000 | 3 |
| Rs 2,000 through Rs 5,000 inclusive | 5 |
| Above Rs 5,000 | 10 |

Capital uses the existing account-margin calculation, the larger of available
balance plus utilized margin and the broker's start-of-day limit. This preserves
the tier when margin is allocated to an open trade. Available cash is still
checked separately before placing an order. Missing or non-finite funds do not
establish capacity.

Automatic mode allocates capital divided by the tier count, floored to paise.
Manual mode retains the saved per-trade margin amount. Its effective concurrent
limit is the smaller of the tier and the number of those allocations the account
can fund. The Python rule is in `pipeline/services/trade_capacity.py`; the display
mirror is `lib/trade-sizing.ts`.

Active capacity counts distinct instruments with an open intraday position or
active order, including active protected-order legs. It also includes recently
accepted orders that have not yet appeared in the broker book. Position and order
rows for the same instrument consume one slot.

Before history, charts, image uploads or model work, the stock runner checks the
user's broker account and reserves an analysis slot. Reservations are shared by
that user's concurrent event runs and released in `finally`, including failures.
Placement checks the broker state and balance again. An external trade or a
balance change during analysis can still cause a valid final rejection.

The model snapshot includes active trade count, effective maximum and admission
counts. Scanner dispatch worker limits are separate from account trade limits
and from tool calls. `stock_agent_max_concurrent_events` defaults to ten gateway
event workers. The old `stock_agent_max_concurrent_trades` field is retained for
compatibility but does not set the live balance-based account policy.

Reservations live in the existing gateway process. This protects concurrent
events in the current single-gateway deployment. Multiple gateway replicas would
require shared transactional reservations before they could enforce one account
limit across processes.

## Scanner, Intra-Finder and agent responsibilities

Stage 1 Universe Scanner builds the broad broker-tradable NSE/BSE equity universe,
selects venues and attaches historical profiles and baselines. It does not choose
an intraday trade direction.

Intra-Finder watches that universe during the session, ranks unusual activity and
movement, and emits candidate events from its setup detectors. Those detectors
still record their own direction and setup metadata for observation and research.

The stock agent independently analyzes each assigned stock using the charts,
observed quote/candle/depth data, technical readings and account state. Its model
input excludes scanner setup names, direction, scores and explanations, including
the legacy scanner indicator snapshot. Execution no longer checks the proposed
side against detector direction. User-specific affordability admission checks
both sides and admits a stock when either side is executable; that check does not
instruct the model which side to trade.

## Tool calls and price rejections

Agno receives `tool_call_limit=None`. The protected-order attempt counter has
also been removed. The model can resize and retry without a numeric call budget.
Confirmed rejected broker orders can be retried. An accepted order cannot be
duplicated, and a submission whose broker acknowledgement is unknown requires
reconciliation before another submission. Broker permission, funds, margin and
protected-order validation still apply.

Previously, a price drift rejection returned only `status: failure` and
`remarks: final_price_drift_exceeds_limit`. The updated response includes:

- `order_submitted: false`.
- The reason for rejection.
- `current_market_state`, containing LTP, quote time and age, session OHLC,
  volume, recent completed/developing one-minute and five-minute candles,
  candle timestamp and age, and any unavailable-data details.
- The proposed entry, target, stop and allowed entry drift.
- An instruction to reassess the new evidence and resize before retrying.

These are newly fetched market observations, not regenerated chart images. The
agent can change its plan or decline the trade. A rejection does not communicate
a scanner opinion.

## Latency and persistence

The model has no application-imposed analysis deadline. Event expiry remains an
admission freshness rule. Final placement fetches current market observations.

Full accounts skip chart and model work. The initial state reuses intraday
history when that history was just fetched for the charts, avoiding a duplicate
history request. A cached chart seed still triggers a current-state refresh.
Existing parallel context fetching and image uploads remain in place.

Supabase remains the Agno session and image store. Convex remains the trading
configuration, credential and live-session projection store. No database schema
or migration is required. Deploy the Python backend and frontend together to
keep execution and the sizing preview aligned.

Validation covers tier boundaries, manual allocation, account isolation,
concurrent admission, reservation release, final balance changes, repeated price
and broker rejections, duplicate protection, scanner-input exclusion and the
unlimited Agno setting. No live orders were submitted for verification.
