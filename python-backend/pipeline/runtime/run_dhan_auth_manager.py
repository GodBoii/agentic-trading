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
from typing import Any, Dict, Optional
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
            return datetime.strptime(text, fmt).replace(tzinfo=ZoneInfo("Asia/Kolkata"))
        except ValueError:
            continue
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=ZoneInfo("Asia/Kolkata"))
    except ValueError:
        return None


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
    def __init__(self, config: Optional[PipelineConfig] = None) -> None:
        self.config = config or PipelineConfig()
        self.store = DhanCredentialStore(self.config)
        self.health: Dict[str, Any] = {
            "status": "starting",
            "credential_version": 0,
            "expires_at": None,
            "last_successful_refresh": None,
            "last_refresh_method": None,
            "consecutive_failures": 0,
            "error": None,
        }

    def _save_health(self) -> None:
        payload = {
            **self.health,
            "checked_at_utc": datetime.now(timezone.utc).isoformat(),
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
        expiry = fallback_expiry or datetime.now(ZoneInfo("Asia/Kolkata")) + timedelta(hours=24)
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
                "last_successful_refresh": datetime.now(timezone.utc).isoformat(),
                "last_refresh_method": method,
                "consecutive_failures": 0,
                "error": None,
            }
        )
        self._save_health()
        print(f"Dhan credentials refreshed using {method}; version={credentials.version}.")
        return True

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

    def run_once(self) -> bool:
        try:
            self.store.bootstrap()
            service = DhanService(self.config, prefer_gateway=False)
        except Exception as exc:
            self._failure(f"credential_bootstrap_failed:{type(exc).__name__}")
            return False

        profile = service.fetch_user_profile()
        expiry = _parse_expiry(_profile_data(profile).get("tokenValidity")) if _success(profile) else None
        now = datetime.now(ZoneInfo("Asia/Kolkata"))
        renew_before = timedelta(minutes=int(os.getenv("DHAN_AUTO_RENEW_BEFORE_MINUTES", "240")))

        if _success(profile) and expiry and expiry - now > renew_before:
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

        if _success(profile):
            renewed = service.renew_access_token()
            if _success(renewed) and self._publish(service, renewed, method="renew_token"):
                return True

        secrets = scanner_recovery_secrets(self.config)
        if secrets.get("pin") and secrets.get("totp_secret"):
            try:
                totp = generate_totp(str(secrets["totp_secret"]))
                generated = service.generate_access_token(pin=str(secrets["pin"]), totp=totp)
                if _success(generated) and self._publish(service, generated, method="totp_recovery"):
                    return True
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
            ok = self.run_once()
            delay = interval if ok else min(interval, 60 * (2 ** min(4, int(self.health["consecutive_failures"]))))
            time.sleep(delay + random.uniform(0, min(10, delay * 0.05)))


def main() -> None:
    DhanAuthManager().run_forever()


if __name__ == "__main__":
    main()
