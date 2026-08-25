# Dhan Backend Authentication

## Separate credential domains

The backend scanner account and website-user trading accounts are different
credential domains. `dhan-auth-manager` manages only the scanner account used by
the backend containers. Existing website-user tokens remain in Supabase.

## Runtime credential file

The active scanner token is stored in:

```text
python-backend/runtime-data/secrets/dhan-scanner-credentials.json
```

The file contains metadata and AES-GCM ciphertext. It does not contain a
readable token. Every update increments `version` and uses atomic replacement.

Consumers compare the file modification/version values. REST clients rebuild
before their next request. WebSocket services reconnect and resubscribe.

## Renewal sequence

1. Validate the current token with Dhan profile.
2. Keep the token only while it is younger than 12 hours and more than four
   hours remain before expiry.
3. If the token is 12 hours old or renewal is otherwise due, call RenewToken.
4. If renewal is impossible, generate a TOTP and use PIN/TOTP recovery.
5. Publish the new encrypted token.
6. If both methods fail, expose `auth_unavailable` and stop invalid retries.

The manager also wakes at 08:30 Asia/Kolkata every day, independent of its
normal polling cadence, and validates the token with Dhan's profile endpoint.
The sanitized health output records the latest live check and the date/status
of the latest 08:30 check.

The AI trading service independently calls Dhan's static-IP endpoint at startup,
every configured interval, and at 08:30 Asia/Kolkata. Order placement remains
blocked unless Dhan's detected IP matches the primary or secondary registered IP
and `ordersAllowed` is true.

RenewToken can invalidate the old token immediately, so publication and consumer
reload are designed to happen promptly.

## Secret configuration

Prefer `*_FILE` variables pointing to protected files:

- `DHAN_DATA_CLIENT_ID_FILE`
- `DHAN_DATA_ACCESS_TOKEN_FILE`
- `DHAN_CREDENTIAL_ENCRYPTION_SECRET_FILE`
- `DHAN_SCANNER_PIN_FILE`
- `DHAN_SCANNER_TOTP_SECRET_FILE`

For this local Docker deployment, place those files under the ignored host
directory `python-backend/runtime-data/bootstrap/` and use container paths such
as `/app/python-backend/runtime-data/bootstrap/dhan_credential_key`. This path is
already available through the backend bind mount.

Direct environment values are supported for local migration but are less
desirable. Never commit real values. The TOTP seed and PIN can generate a fresh
session and must be protected like a password.

Health output contains only expiry, version, method, timestamps and sanitized
failure names. Tokens, PINs and TOTP values are never logged.
