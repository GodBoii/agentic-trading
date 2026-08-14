# Trade History Redesign — Progress and Handoff

Last updated: 14 August 2026

## Current status

The requested Trade History redesign is implemented locally and passes the production build and TypeScript checks.

The interaction now follows the intended three-level hierarchy:

1. The archive initially displays one compact card for each trading date.
2. Clicking a date card expands that card and reveals all agent-run/session cards for the selected date.
3. Clicking an individual run card opens the complete archived agent run, including its agents, charts, artifacts, metadata, and responses.

Only one date is expanded at a time. Clicking the open date again collapses it.

## Implemented user experience

- Sessions are grouped using their local calendar date.
- Date cards are collapsed by default.
- Each date card displays the weekday, full date, and number of runs.
- The complete date-card header is a keyboard-accessible disclosure button.
- A plus control rotates into a close state when the date is expanded.
- Expanded content uses a smooth height-and-opacity transition.
- Hidden run controls are removed from keyboard interaction through CSS visibility handling.
- Run cards display time, agent count, status, archive source, title, and a clear `View run` action.
- Run loading has an immediate `Opening` state and spinner.
- Pointer-down and keyboard-focus prefetching reuse the same deduplicated request.
- Reduced-motion preferences disable nonessential animation.
- Responsive layouts use one, two, or three run columns inside the expanded date card.

## Navigation and refresh behavior

- Opening an archived run writes its session ID into the URL as `session=...`.
- Refreshing an opened run restores that same run instead of losing the selected state.
- Closing a run removes the session parameter and returns to the date archive.
- Switching between Amount, Live Run, and Trades updates URL state consistently.
- Archive navigation does not require a full page reload.

## Performance and reliability improvements

The previous frontend could issue the same sessions request several times during initial loading and again from the frequent status poll. That request fan-out was removed.

Current behavior:

- Trade sessions load only when the Trades view is active.
- Identical in-flight list requests are deduplicated.
- List results receive a 30-second client freshness window.
- Server-side session summaries receive a short, per-user 15-second cache.
- Individual session requests are cached and deduplicated in the client.
- Status polling is paused while viewing the archive.
- Status polling runs every eight seconds only while the page is visible.
- The live WebSocket is paused outside the Live Run view.
- Supabase service requests use the existing five-second abort timeout so an upstream issue does not consume the entire platform request window.
- Loading, retry, and non-destructive error states keep the rest of the interface usable.

## Modular architecture

The page component now owns data fetching, selected-run state, navigation, and the full run-detail view. The archive interface is separated into focused modules:

- `components/trade-history/archive.tsx`
  - Archive-level state and orchestration
  - Date disclosure selection
  - Hero, metrics, loading, error, and empty states
  - GSAP entrance and text-reveal orchestration

- `components/trade-history/trade-date-card.tsx`
  - One card per date
  - Disclosure accessibility state
  - Expand/collapse behavior
  - Responsive collection of run cards

- `components/trade-history/trade-run-card.tsx`
  - Individual session summary
  - Prefetch, opening, disabled, and status states

- `components/trade-history/utils.ts`
  - Date grouping
  - Localized date and time formatting
  - Status-color and pluralization helpers

- `components/trade-history/types.ts`
  - Shared session-summary and date-group types

- `components/trade-history-archive.tsx`
  - Stable public re-export used by the AI Trading page

## Files changed

- `app/dashboard/ai-trading/page.tsx`
- `app/globals.css`
- `lib/ai-trading-sessions.ts`
- `components/trade-history-archive.tsx`
- `components/trade-history/archive.tsx`
- `components/trade-history/trade-date-card.tsx`
- `components/trade-history/trade-run-card.tsx`
- `components/trade-history/utils.ts`
- `components/trade-history/types.ts`
- `package.json`
- `package-lock.json`

`tsconfig.tsbuildinfo` was updated automatically by TypeScript/build validation and is not a product-source change.

## Validation completed

- `npx tsc --noEmit` — passed after the final modular split.
- `npm run build` — passed after the final modular split.
- `git diff --check` — passed.
- Next.js generated all application routes successfully.

The build continues to report non-blocking maintenance warnings for outdated Browserslist/baseline metadata. Earlier builds also reported existing Supabase Edge Runtime compatibility warnings. These did not fail compilation.

## Deployment and domain context

The supplied Cloudflare screenshot shows:

- `polycognition.online` is active and protected by Cloudflare.
- DNS setup is `Full`.
- Cloudflare proxying, caching, security, and SSL/TLS are active.
- No Cloudflare Worker is connected to the domain.

The supplied Vercel screenshot shows:

- `agentic-trading-six.vercel.app` has a valid production configuration.
- `www.polycognition.online` points to Production but Vercel detects a proxy.
- `polycognition.online` is proxied and returns a `308` redirect to `www.polycognition.online`.
- Vercel warns that a proxy in front of Vercel can interfere with its DDoS/bot protection and may degrade performance.

This Cloudflare/Vercel proxy configuration is separate from the frontend code. It is the main remaining infrastructure item relevant to the reported intermittent reload quality. If Vercel remains the origin and reliability is the priority, review whether the Vercel-facing DNS records should be changed from Cloudflare `Proxied` to `DNS only`. Do not change this blindly: first record the current DNS targets, confirm the intended apex-to-www redirect owner, and confirm which platform should terminate TLS, caching, security, and redirects.

## Remaining work

The requested frontend behavior is complete. The following items remain outside the completed implementation:

1. Commit and deploy the current working-tree changes.
2. Verify the deployed archive while authenticated on desktop and mobile.
3. Test a direct refresh of a URL containing `?view=trades&session=<session-id>` in production.
4. Decide whether Cloudflare or Vercel should own proxying, caching, redirects, and edge protection; then remove the current double-proxy warning if appropriate.
5. Review the dependency audit separately. The install command reported seven high-severity advisories in the existing dependency tree; no automated breaking upgrade was applied.
6. Optionally refresh Browserslist and baseline-browser metadata in a dedicated maintenance change.

## Recommended production smoke test

After deployment:

1. Open `/dashboard/ai-trading?view=trades` while authenticated.
2. Confirm only date cards are visible initially.
3. Expand one date and confirm only that date reveals run cards.
4. Expand another date and confirm the previous date collapses.
5. Open a run and confirm its complete archived output loads.
6. Refresh the run URL and confirm the same run is restored.
7. Return to Trade History and confirm the archive responds immediately.
8. Repeat at mobile width and with reduced motion enabled.
9. Repeat several hard refreshes against the production custom domain while monitoring Vercel and Cloudflare logs for 404, 502, 503, or timeout responses.
