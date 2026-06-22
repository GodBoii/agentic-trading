# Trade Monitor System Design

This document describes how the post-entry trade monitor should work. It is a design specification only; the trade monitor is not implemented yet.

## Purpose

The trade monitor is the post-execution safety and supervision layer. It is different from the existing Stage 2 liquidity monitor, which filters pre-trade candidates.

The trade monitor activates only when there is at least one live intraday order or position. It monitors all live trades together in one system context. If one trade is live, the monitor receives one trade. If three trades are live, the same monitor receives all three trades. The system should not create a separate LLM monitor agent per trade.

## Inputs

The monitor should receive:

- Executioner output for each placed or attempted trade.
- Dhan order book, order-by-id, trade book, positions, holdings, and funds.
- Live quote or LTP for each active security.
- Bid, ask, spread, latest OHLC/candle, latest market timestamp, and staleness.
- Entry price, side, quantity, product type, exchange segment, order ID, and correlation ID.
- Stop loss, target, intended hold time, and expected trade thesis from executioner.
- Unrealized P&L, realized P&L, time since entry, and time to market close.
- Broker/API status and any rejected, partial, pending, or modified order state.

Every input should include Indian market time. Keep `fetched_at_utc` for audit compatibility, but always provide `fetched_at_ist`, `market_timezone`, source name, fetch status, and staleness where possible. The monitor should reason in IST because the system trades Indian equities.

## Core Behavior

The first version should be deterministic-first. Hard risk rules should decide urgent actions. The LLM should not be the kill switch.

Deterministic rules should handle:

- Stop-loss breach.
- Target hit.
- Max loss breach.
- End-of-day square-off window.
- Rejected order or failed protected order.
- Partial fill that changes risk.
- Missing stop or target on a live position.
- Quote/feed staleness beyond threshold.
- Abnormally wide spread or collapsed liquidity.
- Position/order mismatch.
- Broker/API failure during a live trade.

The monitor should persist every decision with the exact rule that triggered it. If a rule exits or modifies a trade, the snapshot should show why, when, and which data was used.

## LLM Role

The optional LLM monitor agent should use `mimo-v2.5-pro`, but it should be advisory in v1.

The LLM should receive all live trades in one compact payload and return:

- Summary of live trade health.
- Which trades are stable, deteriorating, or in danger.
- Whether the original executioner thesis still appears valid.
- Whether data quality is good enough to trust.
- Advisory recommendation such as `hold`, `tighten_review`, `exit_review`, or `no_advice_due_to_stale_data`.

The LLM should not directly call broker tools in v1. Any live broker action should come from deterministic rules only.

## Lifecycle

States:

- `idle`: no live intraday trade exists.
- `observing`: live trade exists and no hard rule is active.
- `warning`: data, spread, P&L, or structure is deteriorating.
- `action_required`: deterministic rule wants an order action.
- `action_sent`: monitor sent exit/modify/cancel action.
- `resolved`: trade closed or no longer needs monitoring.
- `failed_safe`: monitoring data is too broken to make discretionary decisions.

The monitor loop should run frequently enough for intraday risk, but the LLM should run less often or only on material state change. Deterministic checks should be faster and more frequent than LLM checks.

## Snapshot Shape

Suggested latest snapshot:

```json
{
  "stage": "trade_monitor",
  "generated_at_utc": "2026-06-03T09:50:00+00:00",
  "generated_at_ist": "2026-06-03T15:20:00+05:30",
  "summary": {
    "market_timezone": "Asia/Calcutta",
    "status": "observing",
    "live_trade_count": 2,
    "deterministic_action_count": 0,
    "llm_advisory_status": "completed"
  },
  "live_trades": [],
  "deterministic_actions": [],
  "llm_advisory": {
    "model_id": "mimo-v2.5-pro",
    "advice": "hold",
    "report_text": ""
  },
  "data_quality": {
    "quote_staleness_seconds_max": 8,
    "broker_fetch_status": "success"
  }
}
```

Persist:

- `trade_monitor_latest.json`
- `trade-monitor-{market_date}.json`

## Failure Rules

If the LLM fails, deterministic monitoring continues.

If quote data is stale, the monitor should avoid discretionary decisions and rely only on hard broker/order/position safety rules.

If broker position/order data fails, the system should enter protective mode and avoid assuming a trade is safe.

If a position exists without a protected stop/target, deterministic rules should flag the trade as high priority.

## Dashboard Expectations

The dashboard can later show a separate post-entry monitor section with:

- Live trade count.
- Current monitor state.
- Per-trade P&L and status.
- Latest deterministic rule result.
- Latest LLM advisory.
- Data staleness.

This dashboard work is not part of the current implementation.
