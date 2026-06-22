# Development Note

We are currently in development mode for this trading backend.

Because of that, market-hours gating is intentionally **not enforced right now**. This lets us run and test Stage 1 and Stage 2 at any time using:

```powershell
docker compose up --build
```

## What is intentionally relaxed right now

- Stage 2 is allowed to start even when the market is closed.
- The tick collector is allowed to start even when the market is closed.
- The backend orchestrator focuses on:
  - running Stage 1 once per market date
  - skipping Stage 1 if today's snapshot already exists
  - moving directly into Stage 2 loop for development testing

## Before production, add market-hours gates back

Production should enforce market-time checks before any live-market workflow starts.

The main place to add that gate back is:

- [python-backend/pipeline/runtime/run_backend.py](c:/Users/prajw/Downloads/Trader/python-backend/pipeline/runtime/run_backend.py)

That is the current single-entry orchestration flow used by Docker.

Supporting file for market-time logic:

- [python-backend/pipeline/services/market_time_service.py](c:/Users/prajw/Downloads/Trader/python-backend/pipeline/services/market_time_service.py)

## Recommended production behavior later

1. Stage 1:
   - run once daily before market open
   - skip if already completed for the current market date

2. Stage 2:
   - only run during market hours
   - wait or sleep outside the allowed market window

3. Tick collector:
   - only connect during market hours
   - stop or idle outside market hours

4. Optional hardening:
   - add weekday checks
   - add holiday calendar checks
   - add pre-market and post-market behavior explicitly

## Why this note exists

This is here so we do not forget that the current runtime behavior is optimized for development convenience, not production safety.
