# Trading Pipeline Operations Runbook

## First-time configuration

1. Configure the five scanner secret values described in
   `docs/dhan-authentication.md`.
2. Keep `INTRA_FINDER_SHADOW_MODE=1`.
3. Validate Compose:

   ```powershell
   docker compose config --quiet
   ```

4. Build and start:

   ```powershell
   docker compose up --build -d
   ```

5. Check:

   ```powershell
   docker compose ps
   docker compose logs dhan-auth-manager
   docker compose logs universe-scanner
   docker compose logs intra-finder
   ```

## Expected daily order

- Auth manager becomes healthy.
- Gateway becomes healthy.
- Universe Scanner runs at or after 08:40 IST.
- Intra-Finder starts after today's successful universe exists.
- One-minute indicator calculations begin after the first completed candle.
- EMA and RSI need enough completed candles before their first event can appear.
- Aggregated indicator events appear in `results/stage2/YYYY-MM-DD/setup-events.jsonl`.

Check the Stage 2 readiness endpoint:

```powershell
docker exec trader-intra-finder-1 python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8040/health').read().decode())"
```

## Common states

`auth_unavailable` means renewal and recovery cannot currently establish a valid
scanner session. Inspect the sanitized auth health file and protected secret
configuration. Do not paste tokens into logs.

`degraded` Stage 1 means its diagnostics were saved but `latest.json` was not
replaced. Check master age/schema and historical failure counts.

`DATA_STALE` means Intra-Finder has not received a trustworthy recent packet for
that stock. It cannot trigger until live data recovers.

`quiet_instruments` does not automatically mean the WebSocket is broken. Dhan
is event-driven, so an inactive stock may legitimately have no recent packet.
Use `global_packet_age_seconds` and `connection_state` to diagnose the whole
feed.

`CONNECTION_WARMING_UP` protects the first thirty seconds after a real
reconnection.

`global_packet_idle` means no instrument produced a packet within the aggregate
idle deadline. This causes a controlled reconnect and resubscription.

## Shadow-to-live checklist

Before changing shadow mode to `0`:

- Replay several complete sessions.
- Review indicator and candlestick events against their completed one-minute candles.
- Confirm repeated states do not create repeated events.
- Confirm multiple events within sixty seconds become one agent request.
- Confirm queue-expired and overflow-dropped counters are visible and bounded; a stale event must never wait for hours.
- Confirm NSE and BSE venue propagation in every event.
- Confirm duplicate events remain suppressed after restart.
- Check observed disk growth.
- Keep `EXECUTIONER_ALLOW_LIVE_ORDERS=0` for the first event-dispatch test.

Only after agent-event behavior is satisfactory should live order permission be
considered separately.

## Safe cleanup

Intra-Finder automatically removes raw-depth directories older than seven days
and one-second directories older than ninety days. Setup events and Stage 1
results are retained. Cleanup validates that the target is specifically the
Stage 2 results directory before deleting anything.

# Trading-amount diagnostics

Market monitoring must remain healthy even when a user cannot be routed. Check `python-backend/ai_trading_state.json` under `user_states.<user_id>` for `trade_mode`, `trade_amount` and `amount_updated_at_utc`. `trade_mode=auto` intentionally stores no amount and resolves current available balance for every event. `trade_mode=manual` requires a positive finite amount; its default freshness window is 30 days (`TRADING_AMOUNT_MAX_AGE_SECONDS=2592000`). Invalid or stale manual values, or unavailable/zero automatic balance, pause only that user's agent/execution path.

The browser endpoint `GET /api/ai-trading/config` returns a plain status such as `automatic_balance`, `manual_amount`, `amount_missing_or_invalid`, `amount_timestamp_unavailable`, or `amount_stale`. Event dispatch diagnostics additionally use `available_balance_unavailable`, `price_above_trading_amount`, `price_unavailable`, `user_depth_unavailable`, and `user_slippage_too_high`.

Saving with `POST /api/ai-trading/config` persists either automatic mode (blank field) or a manual amount and arms continuous event routing for that user; it does not launch a batch. Intra-Finder shadow mode remains the Compose default (`INTRA_FINDER_SHADOW_MODE=1`), and `EXECUTIONER_ALLOW_LIVE_ORDERS=0` must remain unchanged during validation.
