# Convex persistence

Supabase remains responsible for user authentication and broker-connection
metadata. Convex is the canonical store for trading configuration such as the
enabled flag, sizing mode, trading amount, and its freshness timestamp.

Agno 2.6.12 does not provide a native Convex database provider. The trading
agents therefore keep Agno's supported `PostgresDb` provider (Supabase Postgres)
and use a small adapter that mirrors each complete Agno session and run into
Convex. Payloads are JSON-encoded and chunked so deeply nested Agno output does
not run into Convex document nesting or single-document size constraints.

## Required server configuration

Create a development deployment key for the `qualified-wren-407` deployment in
the Convex dashboard. A concrete deployment key can be used by both the CLI and
the trusted server clients:

```dotenv
CONVEX_URL=https://qualified-wren-407.convex.cloud
CONVEX_DEPLOY_KEY=dev:qualified-wren-407|...
CONVEX_ADMIN_KEY=dev:qualified-wren-407|...
CONVEX_REQUIRED=1
```

`CONVEX_ADMIN_KEY` must only be configured in Next.js/Vercel and the Python
containers. Never prefix it with `NEXT_PUBLIC_` or expose it to a browser.

## Deploy and migrate

```powershell
npm run convex:deploy
python scripts/migrate_trading_state_to_convex.py
```

The migration is idempotent. Once deployed, the local
`python-backend/ai_trading_state.json` file is only a disposable operational
cache; all reads refresh it from Convex.

## Stored Convex tables

- `tradingConfigurations`: one record per Supabase user ID.
- `agentSessions`: indexed Agno session headers.
- `agentRuns`: indexed run headers and readable output previews.
- `agentPayloadChunks`: lossless JSON payload chunks for sessions and runs.

Chart images remain in the existing Supabase Storage bucket. Convex stores the
Agno payload containing their cloud URLs; broker access tokens are never copied
to Convex.
