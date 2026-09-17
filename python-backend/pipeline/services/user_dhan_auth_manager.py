"""Maintain user trading tokens independently of browser sessions."""
from __future__ import annotations

import logging
import hashlib
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from pathlib import Path
from zoneinfo import ZoneInfo

from pipeline.config import PipelineConfig
from pipeline.services.convex_service import ConvexService
from pipeline.services.dhan_credentials import DhanCredentials, DhanCredentialStore, generate_totp
from pipeline.services.dhan_service import DhanService
from pipeline.services.user_dhan_credentials import UserDhanCredentials, require_static_ip_response
from pipeline.services.storage_service import StorageService

logger = logging.getLogger(__name__)


def parse_expiry(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.strptime(value, "%d/%m/%Y %H:%M") if "/" in value else datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=ZoneInfo("Asia/Kolkata")) if parsed.tzinfo is None else parsed
    except ValueError:
        return None


def response_data(response: Any) -> dict[str, Any]:
    if not isinstance(response, dict) or response.get("status") != "success":
        return {}
    data = response.get("data")
    if isinstance(data, dict) and isinstance(data.get("data"), dict):
        data = data["data"]
    return data if isinstance(data, dict) else {}


class UserDhanAuthManager:
    def __init__(self, config: PipelineConfig) -> None:
        self.config = config
        self.owner = str(uuid.uuid4())
        self.failures: dict[str, int] = {}
        self.next_checks: dict[str, float] = {}

    def _pending_path(self, uid: str) -> Path:
        return self.config.backend_dir / "runtime-data" / "secrets" / "user-auth-pending" / f"{hashlib.sha256(uid.encode()).hexdigest()}.json"

    def _journal(self, row: dict[str, Any], result: dict[str, Any]) -> None:
        StorageService.save_snapshot(self._pending_path(row["supabaseUserId"]), {"expectedUpdatedAt": row["updatedAt"], "result": result})

    def check(self, row: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        uid = row["supabaseUserId"]
        client_id = row["dhanClientId"]
        source = row.get("tokenSource", "consent")
        token = UserDhanCredentials._decrypt(row["encryptedAccessToken"], uid, "access-token") if row.get("encryptedAccessToken") else ""
        issued = parse_expiry(row.get("tokenIssuedAt") or row.get("updatedAt")) or now - timedelta(days=1)
        scanner = DhanCredentialStore(self.config).load(required=False)
        shared = scanner is not None and scanner.client_id == client_id
        # A client ID alone is not proof that this website user owns the account.
        if shared and row.get("accountVerifiedAt"):
            token, issued, source = scanner.access_token, parse_expiry(scanner.issued_at) or now, "scanner"
        if not token and not (row.get("autoRenew") and row.get("encryptedPin") and row.get("encryptedTotpSecret")):
            return {"authStatus": "action_required", "authError": "authorization_required"}
        service = DhanService(self.config, prefer_gateway=False, credentials=DhanCredentials(client_id, token or "pending", 0))
        profile_response = service.fetch_user_profile() if token else {}
        profile = response_data(profile_response)
        if token and not profile:
            failure = profile_response.get("data") if isinstance(profile_response, dict) else None
            code = str(failure.get("errorCode") or failure.get("error_code") or "") if isinstance(failure, dict) else ""
            if code not in {"DH-901", "DH-906", "901", "906"}:
                return {"authStatus": "unavailable", "authError": "profile_check_unavailable"}
        if profile and str(profile.get("dhanClientId")) != client_id:
            return {"authStatus": "action_required", "authError": "account_mismatch"}
        expiry = parse_expiry(profile.get("tokenValidity"))
        verified = row.get("accountVerifiedAt") or (now.isoformat() if profile else None)
        if shared:
            if not verified:
                return {"authStatus": "action_required", "authError": "verify_account_once"}
            if source != "scanner":
                result = self.check({**row, "accountVerifiedAt": verified, "tokenSource": "scanner"})
                result["tokenSource"] = "scanner"
                return result
            # The scanner owns this account's renewal and PIN/TOTP recovery.
            if not profile or not expiry:
                return {"authStatus": "unavailable", "authError": "scanner_auth_unavailable"}
        else:
            due = not profile or not expiry or issued + timedelta(hours=12) <= now or expiry <= now + timedelta(hours=4)
            if due and row.get("autoRenew"):
                replacement = response_data(service.renew_access_token()) if profile and source == "web" else {}
                if not replacement and row.get("encryptedPin") and row.get("encryptedTotpSecret"):
                    pin = UserDhanCredentials._decrypt(row["encryptedPin"], uid, "pin")
                    seed = UserDhanCredentials._decrypt(row["encryptedTotpSecret"], uid, "totp-secret")
                    replacement = response_data(service.generate_access_token(pin=pin, totp=generate_totp(seed)))
                    source = "totp"
                new_token = replacement.get("accessToken")
                if not isinstance(new_token, str) or not new_token:
                    return {"authStatus": "action_required", "authError": "renewal_failed_or_recovery_missing"}
                # Broker rotation has already happened. Persist the replacement even if the validation read fails.
                token, issued = new_token, now
                expiry = parse_expiry(replacement.get("expiryTime")) or now + timedelta(hours=24)
                self._journal(row, {
                    "authStatus": "pending", "encryptedAccessToken": UserDhanCredentials.encrypt(token, uid, "access-token"),
                    "tokenIssuedAt": issued.isoformat(), "tokenExpiresAt": expiry.isoformat(), "tokenSource": source,
                })
                service = DhanService(self.config, prefer_gateway=False, credentials=DhanCredentials(client_id, token, 0))
                profile = response_data(service.fetch_user_profile())
                if profile and str(profile.get("dhanClientId")) != client_id:
                    return {"authStatus": "action_required", "authError": "account_mismatch"}
                expiry = parse_expiry(profile.get("tokenValidity")) or expiry
                verified = now.isoformat() if profile else verified
        if not expiry or expiry <= now:
            return {"authStatus": "action_required", "authError": "invalid_or_expired_token"}
        result: dict[str, Any] = {"authStatus": "ready" if profile else "unavailable", "tokenExpiresAt": expiry.isoformat()}
        if verified:
            result["accountVerifiedAt"] = verified
        if row.get("autoRenew") or shared:
            result["nextRenewalAt"] = min(issued + timedelta(hours=12), expiry - timedelta(hours=4)).isoformat()
        old_token = UserDhanCredentials._decrypt(row["encryptedAccessToken"], uid, "access-token") if row.get("encryptedAccessToken") else ""
        if token != old_token or source != row.get("tokenSource"):
            result.update(encryptedAccessToken=UserDhanCredentials.encrypt(token, uid, "access-token"), tokenIssuedAt=issued.isoformat(), tokenSource=source)
        if not profile:
            result["authError"] = "profile_check_unavailable"
            return result
        try:
            require_static_ip_response(service.fetch_static_ips())
        except RuntimeError as exc:
            result.update(authStatus="blocked", authError=str(exc))
        return result

    def run_once(self) -> None:
        client = ConvexService.client()
        for row in client.query("dhanCredentials:listAll", {}) or []:
            uid = row["supabaseUserId"]
            key = f"{uid}:{row['updatedAt']}"
            if time.monotonic() < self.next_checks.get(key, 0):
                continue
            args = {"supabaseUserId": uid, "expectedUpdatedAt": row["updatedAt"], "owner": self.owner}
            if not client.mutation("dhanCredentials:acquireLease", args):
                continue
            pending_path = self._pending_path(uid)
            try:
                pending = StorageService.load_snapshot(pending_path) if pending_path.exists() else None
                if pending and pending.get("expectedUpdatedAt") == row["updatedAt"]:
                    result = {**pending["result"], "authStatus": "pending"}
                else:
                    result = self.check(dict(row))
            except Exception as exc:
                # Never log broker bodies or exception text that could contain a credential-bearing URL.
                logger.warning("User Dhan check failed: %s", type(exc).__name__)
                pending = StorageService.load_snapshot(pending_path) if pending_path.exists() else None
                result = pending["result"] if pending and pending.get("expectedUpdatedAt") == row["updatedAt"] else {
                    "authStatus": "unavailable", "authError": "authentication_check_failed",
                }
            if result.get("encryptedAccessToken"):
                self._journal(row, result)
            published = False
            try:
                published = client.mutation("dhanCredentials:finishCheck", {**args, **result})
                if published:
                    pending_path.unlink(missing_ok=True)
            except Exception as exc:
                logger.warning("User Dhan publication pending: %s", type(exc).__name__)
            failed = result["authStatus"] != "ready"
            self.failures[uid] = min(4, self.failures.get(uid, 0) + 1) if failed else 0
            self.next_checks = {k: v for k, v in self.next_checks.items() if not k.startswith(f"{uid}:")}
            self.next_checks[key] = time.monotonic() + (min(900, 60 * 2 ** self.failures[uid]) if failed else 300)
            if not published:
                self.next_checks[key] = time.monotonic() + 60

    def run_forever(self) -> None:
        while True:
            try:
                self.run_once()
            except Exception as exc:
                logger.warning("User Dhan scheduler unavailable: %s", type(exc).__name__)
            time.sleep(60)
