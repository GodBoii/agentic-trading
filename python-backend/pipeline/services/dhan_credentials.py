"""Versioned, encrypted credentials for the backend Dhan scanner account."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import struct
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from dotenv import dotenv_values

from pipeline.config import PipelineConfig
from pipeline.services.storage_service import StorageService


class CredentialUnavailable(RuntimeError):
    pass


def _secret_value(name: str, config: PipelineConfig) -> Optional[str]:
    file_name = os.getenv(f"{name}_FILE")
    if file_name:
        try:
            return Path(file_name).read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise CredentialUnavailable(f"Cannot read secret file for {name}: {exc}") from exc
    value = os.getenv(name)
    if value:
        return value.strip()
    for path in (config.backend_dir / ".env", config.root_dir / ".env"):
        candidate = dotenv_values(path).get(name)
        if candidate:
            return str(candidate).strip()
    return None


def _key(config: PipelineConfig) -> bytes:
    secret = _secret_value("DHAN_CREDENTIAL_ENCRYPTION_SECRET", config)
    if not secret:
        raise CredentialUnavailable(
            "DHAN_CREDENTIAL_ENCRYPTION_SECRET or DHAN_CREDENTIAL_ENCRYPTION_SECRET_FILE is required."
        )
    return hashlib.sha256(secret.encode("utf-8")).digest()


@dataclass(frozen=True)
class DhanCredentials:
    client_id: str
    access_token: str
    version: int
    expires_at: Optional[str] = None
    issued_at: Optional[str] = None
    source: str = "runtime"


class DhanCredentialStore:
    def __init__(self, config: Optional[PipelineConfig] = None) -> None:
        self.config = config or PipelineConfig()
        self.path = self.config.dhan_credentials_path

    def bootstrap(self) -> DhanCredentials:
        existing = self.load(required=False)
        if existing:
            return existing
        client_id = _secret_value("DHAN_DATA_CLIENT_ID", self.config) or _secret_value(
            "DHAN_CLIENT_ID", self.config
        )
        token = _secret_value("DHAN_DATA_ACCESS_TOKEN", self.config) or _secret_value(
            "DHAN_ACCESS_TOKEN", self.config
        )
        if not client_id or not token:
            raise CredentialUnavailable(
                "Missing Dhan scanner credentials. Configure client ID and access token secret files."
            )
        return self.publish(
            client_id=client_id,
            access_token=token,
            expires_at=None,
            source="bootstrap",
        )

    def load(self, *, required: bool = True) -> Optional[DhanCredentials]:
        if not self.path.exists():
            if required:
                raise CredentialUnavailable(f"Credential file does not exist: {self.path}")
            return None
        try:
            envelope = json.loads(self.path.read_text(encoding="utf-8"))
            nonce = base64.b64decode(envelope["nonce"])
            ciphertext = base64.b64decode(envelope["ciphertext"])
            aad = str(envelope["version"]).encode("ascii")
            plaintext = AESGCM(_key(self.config)).decrypt(nonce, ciphertext, aad)
            content = json.loads(plaintext.decode("utf-8"))
            return DhanCredentials(
                client_id=str(content["client_id"]),
                access_token=str(content["access_token"]),
                version=int(envelope["version"]),
                expires_at=envelope.get("expires_at"),
                issued_at=envelope.get("issued_at"),
                source=str(envelope.get("source") or "runtime"),
            )
        except CredentialUnavailable:
            raise
        except Exception as exc:
            raise CredentialUnavailable("Dhan runtime credential file is unreadable.") from exc

    def publish(
        self,
        *,
        client_id: str,
        access_token: str,
        expires_at: Optional[str],
        source: str,
    ) -> DhanCredentials:
        current = self.load(required=False)
        version = (current.version if current else 0) + 1
        issued_at = datetime.now(timezone.utc).isoformat()
        plaintext = json.dumps(
            {"client_id": str(client_id), "access_token": str(access_token)},
            separators=(",", ":"),
        ).encode("utf-8")
        nonce = os.urandom(12)
        ciphertext = AESGCM(_key(self.config)).encrypt(
            nonce,
            plaintext,
            str(version).encode("ascii"),
        )
        envelope = {
            "schema_version": 1,
            "version": version,
            "issued_at": issued_at,
            "expires_at": expires_at,
            "source": source,
            "nonce": base64.b64encode(nonce).decode("ascii"),
            "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
        }
        StorageService.save_snapshot(self.path, envelope)
        return DhanCredentials(
            client_id=str(client_id),
            access_token=str(access_token),
            version=version,
            expires_at=expires_at,
            issued_at=issued_at,
            source=source,
        )

    def mtime_ns(self) -> int:
        try:
            return self.path.stat().st_mtime_ns
        except OSError:
            return 0


def generate_totp(secret: str, *, at_time: Optional[int] = None, digits: int = 6) -> str:
    normalized = "".join(str(secret).strip().split()).upper()
    padding = "=" * ((8 - len(normalized) % 8) % 8)
    key = base64.b32decode(normalized + padding, casefold=True)
    counter = int((at_time if at_time is not None else time.time()) // 30)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(value % (10**digits)).zfill(digits)


def scanner_recovery_secrets(config: PipelineConfig) -> Dict[str, Optional[str]]:
    return {
        "pin": _secret_value("DHAN_SCANNER_PIN", config),
        "totp_secret": _secret_value("DHAN_SCANNER_TOTP_SECRET", config),
    }
