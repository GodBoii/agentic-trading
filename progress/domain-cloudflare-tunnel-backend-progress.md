# Custom Domain, Cloudflare Tunnel, and Trading Backend — Progress and Handoff

Last updated: 17 August 2026

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

## 17 August live-production verification

The complete backend was restored and verified during the live market session:

- Dhan auth manager, market-data gateway, Universe Scanner, Intra-Finder and AI
  trading gateway were healthy.
- The NIFTY depth worker and Cloudflare connector were running and receiving
  current data.
- `https://api.polycognition.online/health` and the local gateway health route
  returned HTTP `200`.
- Protected public gateway routes rejected unauthenticated requests with HTTP
  `401`; unauthenticated Vercel dashboard/API requests redirected to `/login`.
- The full Python backend suite passed: 116 tests.
- Read-only Dhan reconciliation reported zero positions, orders and trades
  before agent processing.
- Intra-Finder subscribed to all 792 universe instruments and reached 792/792
  Full Packet coverage with no reconnect or dispatch failures.

No agent event or order was created during this verification. The service was
restarted late in the session and correctly held every candidate behind
`INSUFFICIENT_COMPLETED_BARS` (45 completed one-minute bars). Opening-range
recovery restores the 09:15-09:30 range, but does not currently backfill the
full intraday indicator-bar history. This is safe fail-closed behavior, not an
AI gateway failure; a normal pre-market start avoids it.

Compose was hardened so `ai-trading-agents` is now part of the default service
set and Intra-Finder explicitly waits for its health check. The Cloudflare
connector is part of the default stack, so the production startup command is:

```powershell
docker compose up -d --build
```

A market-calendar-aware NIFTY depth health check was also added. These Compose
source changes take effect when their containers are next recreated; the live
NIFTY worker was deliberately not restarted during the market session.

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

`docker-compose.yml` includes `cloudflared` in the default backend stack.

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

The browser's Supabase access token is now the end-to-end user credential. Vercel verifies the session and forwards that short-lived token to the Python gateway. The Python gateway independently verifies it with Supabase and derives the user ID itself before processing any user-scoped request. This prevents callers from impersonating another user by supplying a `user_id` in a query string or JSON body.

The backend credential is retained only for trusted internal Docker service-to-service requests, such as pipeline events. It is no longer used by the Vercel user-facing routes.

One internal application secret is required on the Python/Docker host:

```text
AI_TRADING_BACKEND_TOKEN
```

The separate `AI_TRADING_WS_SIGNING_SECRET` remains optional. When absent, the internal backend credential also signs short-lived WebSocket tickets. Neither value is exposed to browser JavaScript or required in Vercel.

The Cloudflare tunnel token is separate infrastructure authentication. It authorizes the local `cloudflared` connector to attach to the managed tunnel; it is not a user credential and is not placed in Vercel.

### REST request flow

```text
Authenticated browser
  → Vercel Next.js API route
  → Supabase session verification
  → Vercel forwards the Supabase access token
  → Python gateway verifies the token with Supabase `/auth/v1/user`
  → Python gateway derives the authenticated user ID
  → user-scoped operation
```

### WebSocket request flow

```text
Authenticated browser
  → POST /api/ai-trading/ws-ticket on Vercel
  → Supabase session verification
  → Supabase access token forwarded to Python
  → Python verifies the user and issues a short-lived, one-time WebSocket ticket
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
- User-facing REST endpoints validate the bearer token with Supabase and derive the user identity server-side.
- Internal pipeline endpoints accept only the separate internal service credential.
- User-provided `user_id` and email values are ignored and replaced with the verified Supabase identity.
- Enable and disable requests are applied by the Python gateway through `/ai-trading/toggle`; Vercel no longer maintains a separate production toggle state that can drift from the running engine.
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
- Structured audit logs record request receipt, authentication success or rejection, ticket issuance, request completion, and WebSocket client connection/disconnection without logging access tokens or email addresses.

## Next.js and frontend changes

### New WebSocket ticket route

Created:

```text
app/api/ai-trading/ws-ticket/route.ts
```

This server-only route:

- Verifies the current Supabase user.
- Refuses unauthenticated requests.
- Forwards the current Supabase access token to the Python gateway.
- Returns the short-lived, user-scoped, one-time WebSocket JWT issued by Python after independent verification.
- Never exposes the internal backend credential to browser JavaScript.
- Uses private, no-store response caching.

### Live agent connection

Updated:

```text
components/agent/use-agent-run.ts
```

The live-agent hook and dashboard-level provider now:

- Requests a fresh WebSocket ticket before every connection attempt.
- Adds the ticket to the WebSocket URL.
- Obtains a new ticket during reconnection instead of reusing an expired ticket.
- Preserves existing status polling, visibility awareness, event de-duplication, and reconnect behavior.
- Maintain one authenticated live connection across all `/dashboard/*` pages, so opening the authenticated dashboard produces a backend `client_connected` event without creating duplicate sockets on the AI Trading page.

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
- Forward the current Supabase access token to the Python gateway.
- Allow the Python gateway to independently verify and derive the user identity.
- Use a bounded backend timeout.
- Request user-scoped status/configuration.
- Return an upstream error when the configured production backend is unavailable instead of pretending Vercel's local filesystem is the active backend.
- Keep the existing local file fallback only for development when no remote backend URL is configured.
- Send both enable and disable operations to the Python gateway, with a best-effort backend rollback if the subsequent Supabase state update fails.

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
SUPABASE_URL=<Supabase project URL>
NEXT_PUBLIC_SUPABASE_ANON_KEY=<Supabase anonymous key used for token verification>
SUPABASE_AUTH_TIMEOUT_SECONDS=5
SUPABASE_AUTH_CACHE_SECONDS=30
```

### Vercel production environment

The following production configuration was added or updated by the user:

```env
NEXT_PUBLIC_APP_URL=https://www.polycognition.online
AI_TRADING_BACKEND_URL=https://api.polycognition.online
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

The following are not used by the Vercel frontend and should remain only on the Docker host:

```text
CLOUDFLARE_TUNNEL_TOKEN
AI_TRADING_ALLOWED_ORIGINS
AI_TRADING_BACKEND_TOKEN
AI_TRADING_WS_SIGNING_SECRET
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
- `app/api/ai-trading/assets/route.ts`
- `app/api/ai-trading/config/route.ts`
- `app/api/ai-trading/toggle/route.ts`
- `app/api/ai-trading/ws-ticket/route.ts`
- `app/dashboard/ai-trading/page.tsx`
- `app/dashboard/layout.tsx`
- `components/agent/agent-run-provider.tsx`
- `components/agent/use-agent-run.ts`
- `components/ai-trading/utils.ts`
- `components/trading-status.tsx`
- `docker-compose.yml`
- `python-backend/pipeline/runtime/run_ai_trading_orchestrator.py`
- `python-backend/pipeline/stages/intra_finder.py`
- `python-backend/tests/test_ai_gateway_security.py`

Ignored local configuration files were also updated but must not be committed:

- `.env`
- `.env.local`
- `python-backend/.env`

## Validation completed

Completed checks:

- `npm run build` — passed.
- Complete Python test suite — `115 passed`.
- Backend-issued ticket and Python-validator compatibility checks — passed.
- Supabase verifier cache, invalid-token rejection, ticket scope, tamper rejection, replay prevention, and user-isolated broadcast tests — passed.
- `docker compose --profile ai config --quiet` — passed.
- `git diff --check` — passed, apart from informational Windows LF-to-CRLF notices.
- Local backend `/health` — HTTP `200`.
- Public tunneled backend `/health` — HTTP `200`.
- Public protected endpoint without authorization — HTTP `401` as expected.
- Cloudflare connectivity prechecks — passed.
- Tunnel route configuration — received by the connector.
- Dhan authentication service after credential update — healthy.
- Vercel custom-domain frontend — HTTP `200`.
- Real tunneled WebSocket handshake — connected and received `status_snapshot`.
- Backend audit logs — verified `request_received`, `auth_success`, `auth_denied`, `request_completed`, `client_connected`, and `client_disconnected` events.
- Scheduled weekend idle is treated as healthy by Universe Scanner and Intra-Finder.

The earlier trading-amount accessibility/copy contract failure was corrected. The complete suite now passes.

The Next.js build reports only non-blocking maintenance notices for outdated Browserslist/baseline metadata.

## Operational commands

Start or rebuild the AI backend and tunnel:

```powershell
docker compose up -d --build cloudflared
```

Inspect container status:

```powershell
docker compose ps
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
docker compose up -d --force-recreate cloudflared
```

## Remaining work

1. Review the local diff one final time.
2. Commit the tracked implementation files and this progress document.
3. Push the commit to `origin/master` so Vercel can deploy the new application code.
4. Confirm the Vercel production deployment uses the listed environment variables. `AI_TRADING_BACKEND_TOKEN` may be removed from Vercel because user requests now use Supabase tokens end to end.
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
14. In Docker logs, confirm the signed-in dashboard produces `auth_success`, `websocket_ticket_issued`, and `client_connected` for the verified user ID.
15. Confirm status and live events belong only to the signed-in user.
16. Open the protected API hostname directly without credentials and confirm it remains unauthorized.
17. Place or simulate an eligible Dhan order only under the project's established safety controls, then confirm the postback route receives the status update.
18. Review Vercel, Cloudflare Tunnel, and Docker logs for unexpected `401`, `403`, `502`, WebSocket handshake, origin, or timeout errors.

## Availability limitation

The backend currently runs on the local Windows computer. Production backend availability therefore depends on:

- The computer remaining powered on.
- Windows not entering sleep or hibernation.
- Docker Desktop running.
- The Docker containers remaining healthy.
- The local internet connection remaining available.

For reliable 24/7 operation, the same Docker services and tunnel connector should eventually move to an always-on VPS or server. The current local deployment is functional but inherits the availability of the host computer.
