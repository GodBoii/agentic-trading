# Trading Pipeline Operations Runbook

## First-time configuration

1. Configure the five scanner secret values described in
   `docs/dhan-authentication.md`.
2. Confirm the intended small-capital mode. Compose currently defaults to
   `INTRA_FINDER_SHADOW_MODE=0`; set it to `1` for a non-dispatching session.
3. Validate Compose:

   ```powershell
   docker compose config --quiet
   ```

4. Build and start the complete production stack, including the Cloudflare
   connector, in detached mode:

   ```powershell
   npm run backend:start
   ```

   This runs `docker compose up --build -d`. The `cloudflared` connector is
   part of the default stack and publishes the gateway at
   `api.polycognition.online`.

5. Check:

   ```powershell
   docker compose ps
   docker compose logs dhan-auth-manager
   docker compose logs ai-trading-agents
   docker compose logs universe-scanner
   docker compose logs intra-finder
   ```

## Expected daily order

- Auth manager becomes healthy.
- Gateway becomes healthy.
- AI trading gateway becomes healthy before Intra-Finder is allowed to start.
- Universe Scanner runs at or after 07:00 IST and refreshes the broad tradable
  universe and cached profiles.
- Intra-Finder accepts a completed last-known-good universe up to four calendar
  days old, so market-open monitoring does not wait for profile refresh.
- Opening activity ranks begin after live trades arrive. Opening-drive setups
  can arm after fifteen seconds and do not require a completed candle.
- Named setup events appear in `results/stage2/YYYY-MM-DD/setup-events.jsonl`.

## Calendar and scheduling

- Every backend service uses `Asia/Calcutta`, with `Asia/Kolkata` as the timezone alias.
- Universe Scanner runs once on an NSE cash-market trading day at or after 07:00 IST.
- A missing build may start only before the 07:30 premarket cutoff or after
  market close. A restart during the live session uses the last-known-good
  universe instead of competing with agents for Dhan historical capacity.
- A heavy scan is terminated after 90 minutes and retried safely; publication
  happens only after a complete atomic build.
- A completed schema-3 artifact prevents a second heavy run that day.
- A failed build retries after the configured degraded interval.
- Intra-Finder connects five minutes before the calendar's market open and
  releases session memory after the calendar's market close.
- Saturdays and Sundays stop before any calendar API, history scan or live feed.
- Only the NSE `CM` cash-market holiday list is used. Commodity, currency and
  clearing holidays cannot close the equity system by mistake.
- If NSE sync fails, a cached calendar for the current year remains usable. If
  the current year is not covered, `MARKET_CALENDAR_FAIL_CLOSED=1` keeps every
  trading process closed.
- `MARKET_FORCE_OPEN` and `MARKET_FORCE_CLOSED` are emergency operator overrides.
  Do not use `MARKET_FORCE_OPEN` for an untested special-session timetable.

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

`AGENT_DISPATCH_CAPACITY` or `AGENT_CAPACITY` means the configured new-entry
analysis slots are occupied. The event is not queued because its market evidence
is short-lived.

`CORPORATE_ACTION_GAP_UNTRUSTED` means an ex-date action made the previous-close
gap unsafe. Live-only volatility setups remain available.

`global_packet_idle` means no instrument produced a packet within the aggregate
idle deadline. This causes a controlled reconnect and resubscription.

## Detector-to-live checklist

Before changing shadow mode to `0`:

- Replay several complete sessions.
- Review activity ranks and named setups against the recorded price path.
- Confirm opening events use seconds of current data rather than old evidence.
- Confirm repeated qualifying states do not create repeated setup instances.
- Confirm expired events and a fourth concurrent agent are rejected.
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

Saving with `POST /api/ai-trading/config` persists either automatic mode (blank field) or a manual amount and arms continuous event routing for that user; it does not launch a batch. Intra-Finder currently defaults to live event dispatch (`INTRA_FINDER_SHADOW_MODE=0`). Order permission remains separately controlled by `EXECUTIONER_ALLOW_LIVE_ORDERS`, the shared placement gate and `stock_agent_max_concurrent_trades`.
