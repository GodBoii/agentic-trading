"""Keep the backend scanner account authenticated without exposing secrets."""

from __future__ import annotations

import json
import os
import random
import time
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import Any, Callable, Dict, Optional
from zoneinfo import ZoneInfo

from pipeline.config import PipelineConfig
from pipeline.services.dhan_credentials import (
    CredentialUnavailable,
    DhanCredentialStore,
    generate_totp,
    scanner_recovery_secrets,
)
from pipeline.services.dhan_service import DhanService
from pipeline.services.storage_service import StorageService


MARKET_TIMEZONE = ZoneInfo("Asia/Kolkata")
DEFAULT_MAX_TOKEN_AGE_HOURS = 12
DEFAULT_DAILY_VERIFICATION_TIME = "08:30"


def _success(response: Any) -> bool:
    return isinstance(response, dict) and str(response.get("status") or "").lower() == "success"


def _profile_data(response: Dict[str, Any]) -> Dict[str, Any]:
    data = response.get("data")
    return data if isinstance(data, dict) else {}


def _parse_expiry(raw: Any) -> Optional[datetime]:
    if not raw:
        return None
    text = str(raw).strip()
    for fmt in ("%d/%m/%Y %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=MARKET_TIMEZONE)
        except ValueError:
            continue
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=MARKET_TIMEZONE)
    except ValueError:
        return None


def _parse_timestamp(raw: Any) -> Optional[datetime]:
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(str(raw).strip().replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _daily_verification_parts(raw: str) -> tuple[int, int]:
    try:
        parsed = datetime.strptime(raw.strip(), "%H:%M")
    except ValueError as exc:
        raise ValueError("DHAN_DAILY_VERIFICATION_TIME_IST must use HH:MM format.") from exc
    return parsed.hour, parsed.minute


def _walk_dicts(value: Any):
    if isinstance(value, dict):
        yield value
        for nested in value.values():
            yield from _walk_dicts(nested)


def _extract_token(response: Dict[str, Any]) -> Optional[str]:
    for item in _walk_dicts(response):
        for key in ("accessToken", "access_token", "token"):
            value = item.get(key)
            if value:
                return str(value)
    return None


class DhanAuthManager:
    def __init__(
        self,
        config: Optional[PipelineConfig] = None,
        *,
        now: Optional[Callable[[], datetime]] = None,
    ) -> None:
        self.config = config or PipelineConfig()
        self.store = DhanCredentialStore(self.config)
        self._now = now or (lambda: datetime.now(timezone.utc))
        self.health: Dict[str, Any] = {
            "status": "starting",
            "credential_version": 0,
            "expires_at": None,
            "last_successful_refresh": None,
            "last_refresh_method": None,
            "last_live_token_check": None,
            "last_0830_token_check_date": None,
            "last_0830_token_check_status": None,
            "consecutive_failures": 0,
            "error": None,
        }

    def _now_utc(self) -> datetime:
        current = self._now()
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        return current.astimezone(timezone.utc)

    def _now_ist(self) -> datetime:
        return self._now_utc().astimezone(MARKET_TIMEZONE)

    def _save_health(self) -> None:
        payload = {
            **self.health,
            "checked_at_utc": self._now_utc().isoformat(),
        }
        StorageService.save_snapshot(self.config.dhan_auth_health_path, payload)

    def _publish(
        self,
        service: DhanService,
        response: Dict[str, Any],
        *,
        method: str,
        fallback_expiry: Optional[datetime] = None,
    ) -> bool:
        token = _extract_token(response)
        if not token:
            self._failure(f"{method}_response_missing_access_token")
            return False
        expiry = fallback_expiry or self._now_ist() + timedelta(hours=24)
        credentials = self.store.publish(
            client_id=str(service.client_id),
            access_token=token,
            expires_at=expiry.isoformat(),
            source=method,
        )
        self.health.update(
            {
                "status": "healthy",
                "credential_version": credentials.version,
                "expires_at": expiry.isoformat(),
                "last_successful_refresh": self._now_utc().isoformat(),
                "last_refresh_method": method,
                "consecutive_failures": 0,
                "error": None,
            }
        )
        self._save_health()
        print(f"Dhan credentials refreshed using {method}; version={credentials.version}.")
        return True

    def _record_live_check(self, *, scheduled_0830: bool) -> None:
        self.health["last_live_token_check"] = self._now_utc().isoformat()
        if scheduled_0830:
            self.health["last_0830_token_check_date"] = self._now_ist().date().isoformat()
            self.health["last_0830_token_check_status"] = "healthy"

    def _confirm_published_token(self, *, scheduled_0830: bool) -> bool:
        try:
            refreshed_service = DhanService(self.config, prefer_gateway=False)
            profile = refreshed_service.fetch_user_profile()
        except Exception as exc:
            self._failure(f"published_token_validation_failed:{type(exc).__name__}")
            return False
        if not _success(profile):
            self._failure("published_token_validation_failed:dhan_profile_rejected")
            return False
        expiry = _parse_expiry(_profile_data(profile).get("tokenValidity"))
        self._record_live_check(scheduled_0830=scheduled_0830)
        if expiry is not None:
            self.health["expires_at"] = expiry.isoformat()
        self.health.update(
            {
                "status": "healthy",
                "consecutive_failures": 0,
                "error": None,
            }
        )
        self._save_health()
        return True

    def _rotation_due(self, issued_at: Any) -> bool:
        issued = _parse_timestamp(issued_at)
        if issued is None:
            return True
        max_age = self._max_token_age()
        return self._now_utc() - issued.astimezone(timezone.utc) >= max_age

    @staticmethod
    def _max_token_age() -> timedelta:
        return timedelta(
            hours=max(
                1,
                int(
                    os.getenv(
                        "DHAN_AUTO_RENEW_MAX_AGE_HOURS",
                        str(DEFAULT_MAX_TOKEN_AGE_HOURS),
                    )
                ),
            )
        )

    def _seconds_until_rotation(self) -> float:
        try:
            credentials = self.store.load(required=False)
        except CredentialUnavailable:
            return 0.0
        issued = _parse_timestamp(credentials.issued_at if credentials else None)
        if issued is None:
            return 0.0
        due_at = issued.astimezone(timezone.utc) + self._max_token_age()
        return max(0.0, (due_at - self._now_utc()).total_seconds())

    def _seconds_until_daily_verification(self) -> float:
        hour, minute = _daily_verification_parts(
            os.getenv("DHAN_DAILY_VERIFICATION_TIME_IST", DEFAULT_DAILY_VERIFICATION_TIME)
        )
        now = self._now_ist()
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        return max(0.0, (target - now).total_seconds())

    def _daily_verification_due(self) -> bool:
        hour, minute = _daily_verification_parts(
            os.getenv("DHAN_DAILY_VERIFICATION_TIME_IST", DEFAULT_DAILY_VERIFICATION_TIME)
        )
        now = self._now_ist()
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        return (
            now >= target
            and self.health.get("last_0830_token_check_date") != now.date().isoformat()
        )

    def _failure(self, reason: str) -> None:
        failures = int(self.health.get("consecutive_failures") or 0) + 1
        self.health.update(
            {
                "status": "auth_unavailable",
                "consecutive_failures": failures,
                "error": reason[:300],
            }
        )
        self._save_health()
        print(f"Dhan authentication unavailable: {reason}")

    def run_once(self, *, scheduled_0830: bool = False) -> bool:
        try:
            credentials = self.store.bootstrap()
            service = DhanService(self.config, prefer_gateway=False)
        except Exception as exc:
            self._failure(f"credential_bootstrap_failed:{type(exc).__name__}")
            return False

        profile = service.fetch_user_profile()
        expiry = _parse_expiry(_profile_data(profile).get("tokenValidity")) if _success(profile) else None
        now = self._now_ist()
        renew_before = timedelta(minutes=int(os.getenv("DHAN_AUTO_RENEW_BEFORE_MINUTES", "240")))
        profile_ok = _success(profile)
        if profile_ok:
            self._record_live_check(scheduled_0830=scheduled_0830)

        if profile_ok and not self._rotation_due(credentials.issued_at) and expiry and expiry - now > renew_before:
            self.health.update(
                {
                    "status": "healthy",
                    "credential_version": service.credential_version,
                    "expires_at": expiry.isoformat(),
                    "consecutive_failures": 0,
                    "error": None,
                }
            )
            self._save_health()
            return True

        if profile_ok:
            renewed = service.renew_access_token()
            if _success(renewed):
                published = self._publish(
                    service,
                    renewed,
                    method=(
                        "scheduled_12h_renewal"
                        if self._rotation_due(credentials.issued_at)
                        else "renew_token"
                    ),
                )
                if published:
                    return self._confirm_published_token(scheduled_0830=scheduled_0830)

        secrets = scanner_recovery_secrets(self.config)
        if secrets.get("pin") and secrets.get("totp_secret"):
            try:
                totp = generate_totp(str(secrets["totp_secret"]))
                generated = service.generate_access_token(pin=str(secrets["pin"]), totp=totp)
                if _success(generated):
                    published = self._publish(service, generated, method="totp_recovery")
                    if published:
                        return self._confirm_published_token(scheduled_0830=scheduled_0830)
            except Exception as exc:
                self._failure(f"totp_recovery_failed:{type(exc).__name__}")
                return False

        self._failure("renewal_failed_and_totp_recovery_unavailable")
        return False

    def serve_health(self) -> None:
        manager = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                if self.path.rstrip("/") not in {"", "/health", "/ready"}:
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
                status = HTTPStatus.OK if manager.health.get("status") == "healthy" else HTTPStatus.SERVICE_UNAVAILABLE
                body = json.dumps(manager.health).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_: Any) -> None:
                return

        port = int(os.getenv("DHAN_AUTH_HEALTH_PORT", "8030"))
        ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()

    def run_forever(self) -> None:
        Thread(target=self.serve_health, daemon=True).start()
        interval = max(60, int(os.getenv("DHAN_AUTO_RENEW_CHECK_SECONDS", "900")))
        while True:
            scheduled_0830 = self._daily_verification_due()
            ok = self.run_once(scheduled_0830=scheduled_0830)
            retry_delay = interval if ok else min(
                interval,
                60 * (2 ** min(4, int(self.health["consecutive_failures"]))),
            )
            interval_delay = retry_delay + random.uniform(0, min(10, retry_delay * 0.05))
            deadlines = [interval_delay, self._seconds_until_daily_verification()]
            if ok:
                deadlines.append(self._seconds_until_rotation())
            time.sleep(max(1.0, min(deadlines)))


def main() -> None:
    DhanAuthManager().run_forever()


if __name__ == "__main__":
    main()
