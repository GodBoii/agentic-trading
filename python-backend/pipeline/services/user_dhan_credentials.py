from __future__ import annotations

import base64
import hashlib
import os
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from pipeline.config import PipelineConfig
from pipeline.services.convex_service import ConvexService
from pipeline.services.dhan_credentials import DhanCredentials


class UserDhanCredentials:
    """Loads encrypted per-user trading credentials from Convex."""

    def __init__(self, config: Optional[PipelineConfig] = None) -> None:
        self.config = config or PipelineConfig()
        self._services: dict[str, tuple[str, Any]] = {}
        self._lock = Lock()

    @staticmethod
    def _decrypt(value: str, user_id: str, kind: str) -> str:
        if not value.startswith("enc:v2:"):
            raise RuntimeError("user_dhan_credential_not_encrypted")
        secret = os.getenv("DHAN_USER_CREDENTIALS_ENCRYPTION_SECRET", "").strip()
        if not secret:
            raise RuntimeError("DHAN_USER_CREDENTIALS_ENCRYPTION_SECRET is not configured")
        parts = value.removeprefix("enc:v2:").split(".")
        if len(parts) != 3:
            raise RuntimeError("user_dhan_credential_ciphertext_invalid")

        def decode(part: str) -> bytes:
            return base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))

        key = hashlib.sha256(secret.encode("utf-8")).digest()
        plaintext = AESGCM(key).decrypt(
            decode(parts[0]),
            decode(parts[2]) + decode(parts[1]),
            f"dhan:{user_id}:{kind}".encode("utf-8"),
        )
        return plaintext.decode("utf-8")

    def _from_record(self, normalized: str, record: Optional[dict[str, Any]]) -> DhanCredentials:
        if not record:
            raise RuntimeError("user_dhan_credentials_missing")
        token = record.get("encryptedAccessToken")
        expires_at = str(record.get("tokenExpiresAt") or "").strip()
        if not token or not expires_at:
            raise RuntimeError("user_dhan_authorization_required")
        try:
            expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)
        except ValueError as exc:
            raise RuntimeError("user_dhan_expiry_invalid") from exc
        if expiry.astimezone(timezone.utc) <= datetime.now(timezone.utc):
            raise RuntimeError("user_dhan_authorization_expired")
        return DhanCredentials(
            client_id=str(record["dhanClientId"]),
            access_token=self._decrypt(str(token), normalized, "access-token"),
            version=0,
            expires_at=expires_at,
            source="convex-user",
        )

    def load(self, user_id: str) -> DhanCredentials:
        normalized = str(user_id or "").strip()
        if not normalized:
            raise RuntimeError("user_id_required_for_dhan_credentials")
        return self._from_record(normalized, ConvexService.get_dhan_credentials(normalized))

    def service(self, user_id: str) -> Any:
        from pipeline.services.dhan_service import DhanService

        normalized = str(user_id or "").strip()
        record = ConvexService.get_dhan_credentials(normalized)
        version = str((record or {}).get("updatedAt") or "")
        with self._lock:
            cached = self._services.get(normalized)
            if cached and cached[0] == version:
                return cached[1]
            credentials = self._from_record(normalized, record)
            service = DhanService(
                self.config,
                prefer_gateway=False,
                credentials=credentials,
            )
            self._services[normalized] = (version, service)
            return service

    def require_order_access(self, user_id: str) -> Any:
        service = self.service(user_id)
        response = service.fetch_static_ips()
        data = response.get("data") if isinstance(response, dict) else None
        if isinstance(data, dict) and isinstance(data.get("data"), dict):
            data = data["data"]
        if not isinstance(data, dict):
            raise RuntimeError("user_dhan_order_access_unavailable")
        detected = str(data.get("detectedIP") or data.get("detectedIp") or "").strip()
        allowed_ips = {
            str(data.get("primaryIP") or "").strip(),
            str(data.get("secondaryIP") or "").strip(),
        }
        if data.get("ordersAllowed") is not True or not detected or detected not in allowed_ips:
            raise RuntimeError("user_dhan_static_ip_not_allowed")
        return service
