# Custom Domain, Cloudflare Tunnel, and Trading Backend — Progress and Handoff

Last updated: 15 August 2026

## Current status

The custom frontend domain, Cloudflare-managed DNS, public backend hostname, and Cloudflare Tunnel are configured and operational.

The current production topology is:

```text
Browser
  ├─ HTTPS → www.polycognition.online → Vercel frontend
  └─ WSS   → api.polycognition.online → Cloudflare Tunnel → Docker AI backend

Vercel server routes
  └─ HTTPS → api.polycognition.online → Cloudflare Tunnel → Docker AI backend
```

Verified infrastructure state:

- `www.polycognition.online` serves the Vercel frontend.
- `polycognition.online` redirects to the canonical `www` hostname.
- Cloudflare is the authoritative DNS provider for `polycognition.online`.
- The Vercel-facing frontend records use Cloudflare **DNS only**, avoiding the unsupported double-proxy configuration reported by Vercel.
- Cloudflare Tunnel `polycognition-backend` is healthy.
- The tunnel has one active replica with four registered QUIC connections to Cloudflare edge locations.
- `api.polycognition.online` is published through the tunnel.
- `https://api.polycognition.online/health` returns HTTP `200` with `{"status":"ok"}`.
- A request to a protected endpoint without credentials returns HTTP `401`, confirming that publishing the tunnel did not make trading controls anonymously accessible.

The implementation changes are currently local and have not yet been committed or pushed to `origin/master`.

## Domain and DNS work completed

The domain was purchased through GoDaddy and added to Cloudflare. The GoDaddy nameservers were replaced with the two Cloudflare-assigned nameservers, making Cloudflare authoritative for the zone.

Cloudflare imported the pre-existing DNS records. The obsolete imported website records were reviewed and replaced with the DNS targets required by Vercel. The apex and `www` frontend records were switched to **DNS only** so requests reach Vercel directly instead of passing through a second reverse proxy.

The frontend domain was added to the Vercel `agentic-trading` project:

- `polycognition.online`
- `www.polycognition.online`

Vercel owns the apex-to-`www` production redirect. The canonical application URL is therefore:

```text
https://www.polycognition.online
```

## Cloudflare Tunnel work completed

A remotely managed Cloudflare Tunnel was created with the following non-secret identifiers:

```text
Tunnel name: polycognition-backend
Tunnel ID: d59fa9dc-0648-43aa-9b72-0a6bdddf56f8
```

The connector runs as the `cloudflared` service in the repository's Docker Compose project. Its token is stored only in ignored local environment files and is not committed.

The published application route is:

```text
Public hostname: api.polycognition.online
Origin service:  http://ai-trading-agents:8020
Path restriction: none
```

Cloudflare automatically created the corresponding proxied CNAME pointing the `api` hostname to the tunnel target.

The `cloudflared` logs confirmed:

- DNS resolution checks passed.
- UDP/QUIC connectivity passed.
- TCP/HTTP2 fallback connectivity passed.
- The Cloudflare API was reachable.
- Four tunnel connections registered successfully.
- The published hostname configuration was received by the connector.

## Docker deployment changes

`docker-compose.yml` now includes a `cloudflared` service under the `ai` profile.

Important behavior:

- The tunnel connector reads `CLOUDFLARE_TUNNEL_TOKEN` from the ignored root `.env`.
- It waits for the AI trading backend health check before starting.
- It connects to the backend over the Docker network using `ai-trading-agents:8020`.
- The backend's host-published port is restricted to `127.0.0.1:8020`, so it is not directly exposed on every host interface.
- The backend also uses Docker `expose: 8020` for container-to-container traffic.
- The backend health check calls the intentionally public `/health` endpoint.
- Containers use `restart: unless-stopped` where applicable.

The active relevant containers are:

- `trader-dhan-auth-manager-1`
- `trader-market-data-gateway-1`
- `trader-ai-trading-agents`
- `trader-cloudflared`

All were healthy or running at the latest verification.

## Authentication and authorization design

Supabase remains the only user-facing authentication system. Users sign up and log in through Supabase; no second login or user password system was added.

The backend credential serves a different purpose: it authenticates trusted server-to-server and internal Docker requests after Vercel has authenticated the user. This prevents a visitor from bypassing the Vercel/Supabase layer and directly invoking trading controls through the public tunnel hostname.

Only one application secret is required:

```text
AI_TRADING_BACKEND_TOKEN
```

The previously considered separate `AI_TRADING_WS_SIGNING_SECRET` is optional. When it is absent, the backend credential also signs short-lived WebSocket tickets, keeping the minimum configuration to one application secret.

The Cloudflare tunnel token is separate infrastructure authentication. It authorizes the local `cloudflared` connector to attach to the managed tunnel; it is not a user credential and is not placed in Vercel.

### REST request flow

```text
Authenticated browser
  → Vercel Next.js API route
  → Supabase session verification
  → Vercel adds the private backend bearer credential
  → Python trading gateway
  → user-scoped operation
```

### WebSocket request flow

```text
Authenticated browser
  → POST /api/ai-trading/ws-ticket on Vercel
  → Supabase session verification
  → short-lived, one-time WebSocket ticket
  → wss://api.polycognition.online/ai-trading/stream?ticket=...
  → Python gateway validates origin, signature, expiry, audience, issuer, user, and replay state
  → user-scoped live events
```

Tickets default to a 45-second lifetime and cannot be reused after a successful connection.

## Python gateway security changes

`python-backend/pipeline/runtime/run_ai_trading_orchestrator.py` was hardened for public tunnel exposure.

Implemented protections:

- The gateway fails closed when the backend credential is absent, a placeholder, or too weak.
- Protected REST endpoints require a valid bearer credential.
- `/health` remains public and returns only a minimal health response.
- WebSocket upgrades require an allowed browser `Origin`.
- WebSocket upgrades require a valid short-lived ticket.
- Ticket signatures use HS256.
- Ticket issuer and audience are validated.
- Ticket issued-at and expiry bounds are validated.
- Ticket IDs are recorded and rejected on replay.
- WebSocket clients are registered against a specific Supabase user ID.
- Live events are broadcast only to sockets belonging to the matching user.
- Status responses are sanitized and scoped to the requested authenticated user.
- Event and decision propagation retains the owning user ID.
- Responses use `Cache-Control: no-store` and `X-Content-Type-Options: nosniff` where appropriate.

## Next.js and frontend changes

### New WebSocket ticket route

Created:

```text
app/api/ai-trading/ws-ticket/route.ts
```

This server-only route:

- Verifies the current Supabase user.
- Refuses unauthenticated requests.
- Issues a short-lived, user-scoped, one-time WebSocket JWT.
- Never exposes the permanent backend credential to browser JavaScript.
- Uses private, no-store response caching.

### Live agent connection

Updated:

```text
components/agent/use-agent-run.ts
```

The live-agent hook now:

- Requests a fresh WebSocket ticket before every connection attempt.
- Adds the ticket to the WebSocket URL.
- Obtains a new ticket during reconnection instead of reusing an expired ticket.
- Preserves existing status polling, visibility awareness, event de-duplication, and reconnect behavior.

### Public WebSocket configuration

Updated:

```text
components/ai-trading/utils.ts
```

The permanent public token mechanism was removed. Production requires an explicit browser-safe URL through `NEXT_PUBLIC_AI_TRADING_WS_URL`. Only the WebSocket address is public; no long-lived credential is stored in a `NEXT_PUBLIC_*` variable.

### Trading API proxy routes

Updated:

```text
app/api/ai-trading/toggle/route.ts
app/api/ai-trading/config/route.ts
```

These routes now:

- Verify the Supabase user before backend interaction.
- Attach the server-only backend bearer credential.
- Use a bounded backend timeout.
- Request user-scoped status/configuration.
- Return an upstream error when the configured production backend is unavailable instead of pretending Vercel's local filesystem is the active backend.
- Keep the existing local file fallback only for development when no remote backend URL is configured.

## Environment configuration

Live credential values are intentionally omitted from this document.

### Local Docker/root environment

The ignored local `.env` contains:

```env
AI_TRADING_BACKEND_TOKEN=<private server credential>
AI_TRADING_BACKEND_URL=http://127.0.0.1:8020
AI_TRADING_ALLOWED_ORIGINS=http://localhost:3000,https://www.polycognition.online
NEXT_PUBLIC_AI_TRADING_WS_URL=ws://localhost:8020/ai-trading/stream
CLOUDFLARE_TUNNEL_TOKEN=<private connector token>
```

### Vercel production environment

The following production configuration was added or updated by the user:

```env
NEXT_PUBLIC_APP_URL=https://www.polycognition.online
AI_TRADING_BACKEND_URL=https://api.polycognition.online
AI_TRADING_BACKEND_TOKEN=<same private server credential as the Python gateway>
NEXT_PUBLIC_AI_TRADING_WS_URL=wss://api.polycognition.online/ai-trading/stream
AI_TRADING_BACKEND_TIMEOUT_MS=10000
SUPABASE_SERVICE_ROLE_KEY=<existing private Supabase service key>
```

Existing Supabase and Dhan variables remain configured in Vercel:

```text
NEXT_PUBLIC_SUPABASE_URL
NEXT_PUBLIC_SUPABASE_ANON_KEY
SUPABASE_URL
SUPABASE_DB_URL
DHAN_APP_ID
DHAN_APP_SECRET
```

The following must not be added to Vercel:

```text
CLOUDFLARE_TUNNEL_TOKEN
AI_TRADING_ALLOWED_ORIGINS
```

`AI_TRADING_WS_SIGNING_SECRET` may remain unset because the implementation falls back to the backend credential for ticket signing.

## Dhan application migration

A new Dhan API application named `polycognition` was created for the production custom domain.

Configured URLs:

```text
Redirect URL: https://www.polycognition.online/api/dhan/callback
Postback URL: https://www.polycognition.online/api/dhan/postback
```

These map to the implemented routes:

```text
GET  /api/dhan/callback
POST /api/dhan/postback
```

The Dhan API Key maps to `DHAN_APP_ID`, and the Dhan API Secret maps to `DHAN_APP_SECRET`.

The new Dhan credentials were updated consistently in the ignored local files:

- `.env`
- `.env.local`
- `python-backend/.env`

The Dhan authentication container was recreated after the change and returned to a healthy state. The old Dhan application should remain active until the new production consent and callback flow has been tested successfully; it can then be revoked.

## Files changed

Tracked implementation files:

- `.env.example`
- `app/api/ai-trading/config/route.ts`
- `app/api/ai-trading/toggle/route.ts`
- `app/api/ai-trading/ws-ticket/route.ts`
- `components/agent/use-agent-run.ts`
- `components/ai-trading/utils.ts`
- `docker-compose.yml`
- `python-backend/pipeline/runtime/run_ai_trading_orchestrator.py`
- `python-backend/tests/test_ai_gateway_security.py`

Ignored local configuration files were also updated but must not be committed:

- `.env`
- `.env.local`
- `python-backend/.env`

## Validation completed

Completed checks:

- `npm run build` — passed.
- Focused gateway security tests — passed.
- Node-issued ticket to Python-validator compatibility check — passed.
- `docker compose --profile ai config --quiet` — passed.
- `git diff --check` — passed, apart from informational Windows LF-to-CRLF notices.
- Local backend `/health` — HTTP `200`.
- Public tunneled backend `/health` — HTTP `200`.
- Public protected endpoint without authorization — HTTP `401` as expected.
- Cloudflare connectivity prechecks — passed.
- Tunnel route configuration — received by the connector.
- Dhan authentication service after credential update — healthy.
- Vercel custom-domain frontend — HTTP `200`.

The focused test file currently contains four passing tests covering:

- Valid user-scoped, one-time WebSocket tickets.
- Rejection of tampered tickets.
- Isolation of broadcasts between users.
- Refusal to start the public gateway without its server credential.

The broader Python suite previously produced 108 passing tests and one unrelated pre-existing UI-contract failure concerning the trading-amount accessibility label. That unrelated UI assertion was not changed as part of the tunnel work.

The Next.js build reports only non-blocking maintenance notices for outdated Browserslist/baseline metadata.

## Operational commands

Start or rebuild the AI backend and tunnel:

```powershell
docker compose --profile ai up -d --build cloudflared
```

Inspect container status:

```powershell
docker compose --profile ai ps
```

Inspect tunnel logs:

```powershell
docker compose logs --tail 100 cloudflared
```

Test the local gateway:

```powershell
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8020/health
```

Test the public gateway:

```powershell
Invoke-WebRequest -UseBasicParsing https://api.polycognition.online/health
```

Recreate the connector after changing its token:

```powershell
docker compose --profile ai up -d --force-recreate cloudflared
```

## Remaining work

1. Review the local diff one final time.
2. Commit the tracked implementation files and this progress document.
3. Push the commit to `origin/master` so Vercel can deploy the new application code.
4. Confirm the Vercel production deployment uses the newly configured environment variables.
5. Update Supabase Authentication URL Configuration:
   - Site URL: `https://www.polycognition.online`
   - Redirect URL: `https://www.polycognition.online/auth/callback`
   - Keep `http://localhost:3000/auth/callback` for development.
6. Complete the production smoke test below.
7. Revoke the old Dhan API application only after the new consent flow succeeds.
8. Rotate the Cloudflare connector token because its original value was shown during interactive setup, update the ignored local `.env`, and recreate `cloudflared`.
9. Plan an always-on hosting destination if uninterrupted availability is required.

## Recommended production smoke test

After the code is pushed and Vercel finishes deploying:

1. Open `https://www.polycognition.online` in a private browser window.
2. Sign up or log in through Supabase.
3. Confirm the authentication callback returns to the custom domain.
4. Open the dashboard and connect the Dhan account.
5. Confirm Dhan redirects to `/api/dhan/callback` on the custom domain.
6. Confirm the dashboard reports the Dhan connection as successful.
7. Load funds, holdings, positions, and orders.
8. Open the AI Trading page.
9. Save automatic sizing and confirm the backend configuration request succeeds.
10. Save a valid manual amount and confirm it persists.
11. Start or enable AI trading.
12. Confirm the Vercel route reaches `api.polycognition.online` without a `401`, `502`, or timeout.
13. Confirm the live stream becomes connected through `wss://api.polycognition.online/ai-trading/stream`.
14. Confirm status and live events belong only to the signed-in user.
15. Open the protected API hostname directly without credentials and confirm it remains unauthorized.
16. Place or simulate an eligible Dhan order only under the project's established safety controls, then confirm the postback route receives the status update.
17. Review Vercel, Cloudflare Tunnel, and Docker logs for unexpected `401`, `403`, `502`, WebSocket handshake, origin, or timeout errors.

## Availability limitation

The backend currently runs on the local Windows computer. Production backend availability therefore depends on:

- The computer remaining powered on.
- Windows not entering sleep or hibernation.
- Docker Desktop running.
- The Docker containers remaining healthy.
- The local internet connection remaining available.

For reliable 24/7 operation, the same Docker services and tunnel connector should eventually move to an always-on VPS or server. The current local deployment is functional but inherits the availability of the host computer.

