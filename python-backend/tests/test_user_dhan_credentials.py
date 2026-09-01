from __future__ import annotations

import base64
import hashlib
import os
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from pipeline.services.user_dhan_credentials import UserDhanCredentials


def encrypted(value: str, user_id: str, kind: str, secret: str) -> str:
    key = hashlib.sha256(secret.encode("utf-8")).digest()
    nonce = b"0123456789ab"
    ciphertext = AESGCM(key).encrypt(
        nonce,
        value.encode("utf-8"),
        f"dhan:{user_id}:{kind}".encode("utf-8"),
    )
    body, tag = ciphertext[:-16], ciphertext[-16:]
    encode = lambda item: base64.urlsafe_b64encode(item).decode("ascii").rstrip("=")
    return f"enc:v2:{encode(nonce)}.{encode(tag)}.{encode(body)}"


class UserDhanCredentialsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.user_id = "user-123"
        self.secret = "test-secret"

    def record(self, expires_at: datetime) -> dict[str, str]:
        return {
            "dhanClientId": "1100000001",
            "encryptedAccessToken": encrypted(
                "customer-access-token",
                self.user_id,
                "access-token",
                self.secret,
            ),
            "tokenExpiresAt": expires_at.isoformat(),
            "updatedAt": "2026-09-01T00:00:00+00:00",
        }

    def test_loads_customer_token_from_convex_record(self) -> None:
        expires_at = datetime.now(timezone.utc) + timedelta(hours=12)
        with patch.dict(os.environ, {"DHAN_USER_CREDENTIALS_ENCRYPTION_SECRET": self.secret}), patch(
            "pipeline.services.user_dhan_credentials.ConvexService.get_dhan_credentials",
            return_value=self.record(expires_at),
        ):
            credentials = UserDhanCredentials().load(self.user_id)

        self.assertEqual(credentials.client_id, "1100000001")
        self.assertEqual(credentials.access_token, "customer-access-token")
        self.assertEqual(credentials.source, "convex-user")

    def test_rejects_expired_customer_token(self) -> None:
        expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        with patch.dict(os.environ, {"DHAN_USER_CREDENTIALS_ENCRYPTION_SECRET": self.secret}), patch(
            "pipeline.services.user_dhan_credentials.ConvexService.get_dhan_credentials",
            return_value=self.record(expires_at),
        ):
            with self.assertRaisesRegex(RuntimeError, "user_dhan_authorization_expired"):
                UserDhanCredentials().load(self.user_id)

    def test_ciphertext_is_bound_to_user(self) -> None:
        value = encrypted("token", self.user_id, "access-token", self.secret)
        with patch.dict(os.environ, {"DHAN_USER_CREDENTIALS_ENCRYPTION_SECRET": self.secret}):
            with self.assertRaises(Exception):
                UserDhanCredentials._decrypt(value, "different-user", "access-token")

    def test_requires_matching_static_ip_for_customer_orders(self) -> None:
        service = SimpleNamespace(
            fetch_static_ips=lambda: {
                "status": "success",
                "data": {
                    "detectedIP": "1.2.3.4",
                    "primaryIP": "1.2.3.4",
                    "secondaryIP": "",
                    "ordersAllowed": True,
                },
            }
        )
        credentials = UserDhanCredentials()
        with patch.object(credentials, "service", return_value=service):
            self.assertIs(credentials.require_order_access(self.user_id), service)

    def test_rejects_customer_order_access_from_wrong_ip(self) -> None:
        service = SimpleNamespace(
            fetch_static_ips=lambda: {
                "status": "success",
                "data": {
                    "detectedIP": "9.9.9.9",
                    "primaryIP": "1.2.3.4",
                    "ordersAllowed": True,
                },
            }
        )
        credentials = UserDhanCredentials()
        with patch.object(credentials, "service", return_value=service):
            with self.assertRaisesRegex(RuntimeError, "user_dhan_static_ip_not_allowed"):
                credentials.require_order_access(self.user_id)


if __name__ == "__main__":
    unittest.main()
