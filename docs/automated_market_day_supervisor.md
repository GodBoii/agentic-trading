# Automated Market Day Supervisor

> Retired: this legacy batch supervisor is disabled by default. The dedicated
> Universe Scanner and continuous Intra-Finder now own scheduling and event
> routing. `SESSION_SUPERVISOR_LEGACY_ENABLED=1` exists only for isolated
> migration tests and must not be enabled beside the production services.

## Purpose

This document explains the backend automation layer for the trading system. The goal is simple: the Python backend should keep working even when the frontend is closed or offline. The frontend remains a viewer and control surface for live agent status and past trade sessions, but market-day execution must not depend on a browser tab being open.

The automation is implemented through the `sorting` Docker service, which now runs `python -m pipeline.runtime.run_session_supervisor`. The service name remains familiar, but the runtime is now a market-day supervisor that owns Stage 1 timing, Stage 2 timing, and AI agent trigger decisions.

## Why This Exists

Previously the AI trading run depended on a frontend action. The dashboard toggle wrote `ai_trading_request.json` or called the AI trading backend, and the `ai-trading-agents` container waited for that request. If the operator forgot to press Start, the backend could have market data and Stage 2 results available, but no agents would run.

The new design removes that dependency. The backend now has a deterministic supervisor that checks the market session, runs prerequisites, waits for the right Stage 2 time, and triggers the existing AI trading backend automatically.

The frontend still works the same way for observation. It can show running agents through the AI trading backend WebSocket and show past sessions from saved artifacts. If the site is offline, the backend still runs.

## Main Runtime Components

`market-data-gateway` is the shared Dhan data gateway. It runs continuously and exposes local HTTP endpoints for historical candles, quote batches, OHLC batches, option chain data, and profile checks. Other services use it through `MARKET_DATA_GATEWAY_URL=http://market-data-gateway:8010`.

`sorting` now runs the session supervisor. It owns the daily schedule for Stage 1 and Stage 2. It also decides when a new Stage 2 result is meaningful enough to trigger AI agents. It calls the `ai-trading-agents` backend over HTTP. It does not need the frontend.

`monitor` records NIFTY market structure. By default it records the front-month NIFTY future, because NIFTY 50 itself is an index and does not have a tradeable order book. It records `MarketFeed.Full`, dedicated 200-level depth, normalized trade ticks, latest snapshots, and chart artifacts.

`regime` runs independently on its own schedule. It should be treated as broad market context and a risk filter. It is not a decisive trade source. A strong stock-level setup can still be valid in a weak market, but the regime can reduce size, require cleaner confirmation, or block specific setup types.

`ai-trading-agents` remains the agent runtime and status gateway. It receives start requests, waits for Stage 2 if needed, runs the stock agent, saves status snapshots, saves trade session artifacts, and broadcasts events to the frontend when the frontend is connected.

## Market Calendar And Session Verification

The backend now has `MarketCalendarService` in `python-backend/pipeline/services/market_calendar_service.py`.

It combines three layers:

1. Local session times from `PipelineConfig`: open `09:15`, close `15:30`, new-entry cutoff `15:00`, protect-position time `15:20`.
2. Manual overrides through `MARKET_HOLIDAY_DATES`, `MARKET_FORCE_OPEN`, `MARKET_FORCE_CLOSED`, and optional `python-backend/market_holidays.json`.
3. Best-effort NSE holiday sync from the NSE holiday master endpoint into `python-backend/market_calendar_cache.json`.

If NSE sync fails, the system does not crash. It falls back to weekday logic plus manual holiday overrides. This is deliberate because the backend should degrade safely rather than stop completely because a calendar HTTP request failed.

The session status is saved in `python-backend/session_supervisor_status.json`, along with the current supervisor state and reason for idling or acting.

## Stage 1 Behavior

Stage 1 is the daily universe sanitation stage.

It is scheduled for `08:45 IST`. If the backend was down at `08:45` and starts later in the day, the supervisor checks whether `stage1-YYYY-MM-DD.json` exists. If it is missing and today is a trading day, Stage 1 runs immediately.

This gives the desired behavior:

`08:45` normal case: Stage 1 runs before market open.

Late startup case: Stage 1 runs as soon as the backend comes alive.

Already completed case: Stage 1 is skipped for the rest of the market date.

Stage 1 uses static BSE universe data, ASM/GSM surveillance data, Dhan OHLC snapshots, and daily historical candles. It does not need live depth. It produces `stage1_universe_latest.json` and `stage1-YYYY-MM-DD.json`.

## Stage 2 Behavior

Stage 2 starts at `09:32 IST`. The delay is intentional. The market opens at `09:15`, and Stage 2 uses a 15-minute opening range. Running at `09:32` gives the opening range a small buffer to complete and reduces early incomplete-data behavior.

After the first run, Stage 2 runs every `1800` seconds, which is 30 minutes. This is controlled by `stage2_loop_interval_seconds` in `PipelineConfig`.

Stage 2 requires today’s Stage 1 snapshot. If Stage 1 is missing, Stage 2 does not run until Stage 1 is produced.

Stage 2 produces `stage2_momentum_latest.json` and `stage2-YYYY-MM-DD.json`. The supervisor records the latest Stage 2 signature in `session_supervisor_state.json`.

## AI Agent Trigger Logic

The supervisor does not run AI agents on every loop. It evaluates Stage 2 output and triggers agents only when there is a reason.

The first Stage 2 result of the day always triggers AI agents if candidates or near misses exist, AI trading is enabled, the backend is not already running, and the market is still inside the new-entry window.

After the first run, the supervisor triggers again only when Stage 2 changes meaningfully. A meaningful change is one of these conditions:

1. The top candidate changed.
2. A new candidate entered the Stage 2 candidate pool.
3. A candidate’s Stage 2 score improved materially.
4. Enough time passed to justify a periodic refresh.

The supervisor also enforces cooldowns:

`agent_min_run_interval_seconds` prevents agents from being restarted too frequently across the whole system.

`agent_security_cooldown_seconds` prevents the same security from repeatedly waking agents unless the setup materially improves.

`agent_periodic_refresh_seconds` allows a slower re-check if the same opportunity remains relevant for a long time.

This separation is important. Stage 2 is a signal generator. The supervisor is the deterministic scheduler. The AI agents are analysts and execution decision makers. The execution toolkit is the final safety gate.

## How The Agent Request Works

The supervisor calls:

`POST /ai-trading/start`

on the `ai-trading-agents` backend. In Docker this is:

`http://ai-trading-agents:8020/ai-trading/start`

This preserves the existing frontend experience. The AI trading backend still writes run status, saves sessions, and streams events. If the frontend is online, it can display the live agent run. If the frontend is offline, the backend still runs and saves the session for later.

The supervisor uses the first enabled user from `ai_trading_state.json`. Trade config comes from environment variables first, then falls back to the last `ai_trading_request.json`:

`SUPERVISOR_TRADE_MODE`

`SUPERVISOR_TRADE_AMOUNT`

`SUPERVISOR_REGIME_ANALYSIS_ENABLED`

If no amount is set and trade mode is `auto`, the existing stock-agent flow can derive effective capital from account funds.

## Regime Role

Regime is market context. It should be treated as a bird’s-eye view of market conditions, not as the final trade authority.

The stock agent may receive regime context, but it should judge each stock from stock-level evidence first: Stage 2 signal quality, charts, technical metadata, current quote snapshot, account state, existing orders, margin feasibility, and execution safety.

Regime can still matter. It can reduce position size, make long breakouts require stronger confirmation, make short/reversal setups more acceptable, or block new trades near extreme risk conditions. But it should not blindly override clean stock-level evidence.

## NIFTY Monitor And Tick Data

The monitor records NIFTY market structure using the front-month NIFTY future.

It now saves these files under `python-backend/nifty_market_depth/<market-date>/`:

`latest.json`

`full_market.ndjson`

`depth_200.ndjson`

`trade_ticks.ndjson`

`errors.ndjson`

`depth_200.ndjson` contains the 200-level bid and ask updates from the dedicated full-depth feed.

`full_market.ndjson` contains raw full-market packets from `MarketFeed.Full`.

`trade_ticks.ndjson` is a normalized tick stream built from full-market packets. It stores latest price, last traded quantity, last trade time, volume, volume delta, open interest, best bid, best ask, and inferred aggressor side.

By default, the monitor now uses:

`NIFTY_DEPTH_PERSIST_EVERY_PACKET=1`

`NIFTY_DEPTH_RAW_WRITE_SECONDS=0`

That means the recorder persists every packet rather than sampling once per second. This is important for real order-flow analysis.

## What Tick-By-Tick Adds

Without tick-by-tick persistence, the system can still see broad market structure, but it may miss events between saved samples.

With tick-by-tick data, the system can reconstruct sequence. Sequence is what allows better detection of aggressive buying, aggressive selling, sweep behavior, absorption, rapid liquidity pulls, liquidity stacking, real cumulative delta, burst volume, and whether price moved because trades lifted offers or because liquidity disappeared.

The chart generator now prefers `trade_ticks.ndjson` for footprint-style charts. If that file is missing, it falls back to reconstructing from `full_market.ndjson`.

## Files Added Or Changed

`python-backend/pipeline/services/market_calendar_service.py` adds market-day and session-window checks.

`python-backend/pipeline/runtime/run_session_supervisor.py` adds autonomous Stage 1, Stage 2, and agent triggering.

`python-backend/pipeline/config.py` adds supervisor schedule, agent trigger thresholds, and calendar paths.

`python-backend/pipeline/services/nifty_depth_monitor.py` now persists every packet by default and writes normalized trade ticks.

`python-backend/pipeline/services/nifty_depth_charting.py` now uses `trade_ticks.ndjson` when available.

`docker-compose.yml` makes the `sorting` service run the session supervisor.

`.env.example` documents the new supervisor and monitor settings.

## Operational Flow

The normal trading day is:

`08:45`: Stage 1 runs if missing.

`09:15`: Monitor is expected to be recording NIFTY full-market and 200-depth streams.

`09:32`: First Stage 2 run starts.

After first Stage 2 completes: AI agents trigger immediately if there are candidates or near misses.

Every 30 minutes after that: Stage 2 runs again.

After each Stage 2 run: the supervisor decides whether the change is meaningful enough to trigger agents.

`15:00`: New entries close.

`15:20`: Position protection and exit logic should become the focus.

`15:30`: Market session closes. No new agent entry triggers should occur.

## Dependency Chain

Stage 1 depends on Dhan credentials, BSE universe data, security master data, ASM/GSM inputs, OHLC snapshots, and daily historical data.

Stage 2 depends on today’s Stage 1 snapshot and intraday minute history.

The stock agent depends on today’s Stage 2 snapshot, enabled AI trading state, trade config, account context, Dhan order/margin tools, chart generation, and optional regime context.

The execution tools depend on `EXECUTIONER_ALLOW_LIVE_ORDERS=1` for real order placement. If it is `0`, the agent can analyze but live orders are blocked.

The monitor depends on Dhan WebSocket credentials and the security master’s front-month NIFTY future resolution.

Regime depends on market data, option chain data, index/future sources, news/context sources, and LLM availability when enabled.

The frontend depends on saved status and session files plus the AI trading WebSocket. The backend does not depend on the frontend.

## Safety Notes

Live orders are still gated by `EXECUTIONER_ALLOW_LIVE_ORDERS`. This should remain `0` during testing.

Manual holiday overrides should be maintained. Use `MARKET_HOLIDAY_DATES=YYYY-MM-DD,YYYY-MM-DD` or `python-backend/market_holidays.json`.

If NSE holiday sync fails, check `market_calendar_cache.json` and `session_supervisor_status.json`.

If agents are not triggering, check `session_supervisor_status.json`, `session_supervisor_state.json`, `ai_trading_state.json`, and `ai_trading_run_status.json`.

If NIFTY tick data is missing, check `nifty_market_depth_latest.json`, `stream_states`, and `errors.ndjson`.

If the frontend was offline, open the AI trading page later and inspect past sessions. The backend should have saved the run independently.
# Archived Architecture

This document describes the retired `sorting`/Session Supervisor design. The
active architecture is documented in
[`architecture/trading-pipeline.md`](architecture/trading-pipeline.md). Stage 1
is now `universe-scanner`, Stage 2 is `intra-finder`, and agent runs are
event-driven.
