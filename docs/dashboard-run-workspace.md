# Dashboard and concurrent agent runs

The dashboard uses open sections and dividers instead of repeated framed panels. Portfolio records keep their existing broker queries and table controls. Trade history adds stock/request search and fixes the shared CSS rule that broke row alignment.

Below 640px, portfolio tables become labelled records that expose every column, including fields previously hidden on phones. The phone header gives navigation its own row so Portfolio, Agent and Trades remain visible at 320px. Desktop tables and navigation retain their existing structure.

## Live runs

`lib/live-agent-runs.ts` groups events by backend `request_id`, then agent rank. Rank alone is insufficient because concurrent Intra-Finder requests all begin at rank 1. Selections, failures and no-trade outcomes affect only their own request. Replayed sequence/type pairs are deduplicated within the request and rank.

The live board offers active, failed and finished filters, stock/request search, and one selected agent workspace. New events do not change the selection. Desktop shows the run list alongside details; phones use a back action that returns keyboard focus to the selected row. Activity can be filtered to tool calls or analysis/outcome. Capital sizing and broker execution rules are unchanged.

The dashboard provider retains one authenticated connection across route changes. Saved status results remain available when the WebSocket is unavailable. A disconnected stream explicitly marks displayed activity as potentially stale.

The backend replays recent events after an authenticated connection opens. This buffer is in memory, scoped to each user, and limited to six hours, 3,000 events and 16 MiB of serialized JSON per user. It is not a durable archive and resets when the backend restarts. The browser retains active requests and up to 60 finished requests. Older results remain in Trades. The UI describes this as observed activity rather than claiming to contain every historical run.

Deploy the backend change along with the frontend to enable reconnect replay. The frontend can still receive live events from the existing backend because request identifiers are already present in its current event protocol.

## PWA

The manifest starts the installed app at `/dashboard`. It provides 192px and 512px icons, a maskable icon and an Apple touch icon. The header offers installation when supported and browser instructions otherwise.

The service worker registers only in production. It caches only `/offline.html`. Dashboard HTML always comes from the network; failed navigations show the public offline screen. API/auth requests, mutations and third-party URLs bypass the worker. No financial data, credentials or trade requests are stored in its cache or queued for later execution. Updates wait for the user's reload action.

The manifest, service worker and offline page are public so installation can load them without an authenticated session. Dashboard and API authentication remain unchanged. See [MDN's installation guide](https://developer.mozilla.org/en-US/docs/Web/Progressive_web_apps/Guides/Making_PWAs_installable) and [service worker guidance](https://developer.mozilla.org/en-US/docs/Web/API/Service_Worker_API/Using_Service_Workers).

## Verification

Run `node --test tests/live-agent-runs.test.cjs tests/pwa.test.cjs`, `npx tsc --noEmit`, and `npm run build`. From `python-backend`, run `python -m unittest tests.test_ai_gateway_security tests.test_ai_orchestrator_admission`.

For populated visual checks, start `npm run dev` and visit `/auth/design-preview`. This fixture uses synthetic data and supports adding a concurrent run, disconnecting the displayed stream, and viewing portfolio/history components. It returns 404 in production and does not connect to a broker or start agents.

Actual OS installation and a market-hours session should be checked after deployment. Local synthetic checks do not place orders or prove real broker execution.

Browser checks covered 320px and 390px phones, a 768px tablet, and desktop widths up to 1440px, including both themes, run selection, concurrent arrivals, search, activity filters, reconnect messaging, mobile back/focus restoration and installation help. The synthetic preview produced no browser errors during these checks.
