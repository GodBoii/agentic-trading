# Per-user Dhan authentication

Implemented in the local checkout. No production tokens, orders or settings were changed.

## Behavior

- Profile is now a floating settings window with Account, Authentication and Appearance sections.
- Dhan controls moved out of the portfolio header. Portfolio errors link to Authentication.
- Authentication accepts API key, API secret, Dhan Web access token, and optional PIN/TOTP recovery setup.
- New tokens are checked against the claimed client ID and broker-reported expiry before saving.
- Encryption remains AES-GCM with user ID and field name as authenticated data. Secrets are never read back into forms.
- The existing auth-manager process runs the user scheduler independently of the scanner loop.
- A verified user sharing the scanner client ID follows the scanner's token. There is no second rotation loop for that account.
- Other accounts rotate every 12 hours, or earlier near expiry, with PIN/TOTP recovery when enabled.
- Credential leases, revision checks and an encrypted publication journal protect concurrent renewal and database recovery.
- Invalid tokens no longer masquerade as IP rejection. Explicit user credentials cannot fall back to the environment account.
- Cached trading clients still check expiry before reuse. Existing broker/order safety checks remain.

## Rollout

1. Keep the same `DHAN_USER_CREDENTIALS_ENCRYPTION_SECRET` on Next.js and the backend. Back it up separately from Convex. Do not rotate it as part of this release.
2. Deploy the additive Convex schema and credential functions, then the frontend and backend together during a maintenance window. The callback now requires a revision-bound lease, so old callbacks should be completed or restarted after deployment.
3. Restart `dhan-auth-manager` and the trading service to load the new scheduler and credential handling. Preserve the existing runtime-data volume. Services using the changed shared Dhan client should reload the code as well.
4. Existing records remain readable. An existing valid token can establish account ownership during the next check. If the token is already invalid and ownership has never been recorded, the user must verify it once with a current token or consent login.
5. For a separate trading account, enable automatic renewal and save PIN plus the TOTP setup secret in Profile → Authentication. A six-digit current TOTP is not a setup secret. For the scanner account, its existing backend recovery configuration remains authoritative.
6. Verify a read-only profile and per-user IP check after the first scheduler cycle. Verify portfolio reads, token expiry and next-renewal display. Do not infer live order readiness from container health alone.
7. Observe the first real 12-hour rotation before considering unattended operation proven. Do not place a test trade merely to validate authentication.

## Verification and limits

The backend suite passed with 301 tests, six skips and 25 subtests. Focused tests cover browser-independent renewal, TOTP recovery, scanner ownership, wrong-account rejection, cached expiry, publication replay and lease denial. Node tests exercise credential mutations and the settings endpoint, including concurrent publication, disconnect, ownership and secret handling. TypeScript checking passes.

Browser checks use the real Profile components with synthetic API responses, not a live Dhan account. Desktop and mobile, light and dark, empty/error states, form saving, focus trapping, Escape dismissal, focus return and reduced motion were checked. Screenshots are under the ignored `tmp/profile-auth-verification` directory.

Production deployment, actual per-user TOTP credentials and a live 12-hour renewal were not exercised. Broker requests are bounded, but this initial scheduler checks accounts serially; a larger public launch needs measured capacity and bounded parallelism. The backend still requires valid Dhan authorization and IP permission. It cannot continue submitting orders with a broker-rejected token.
