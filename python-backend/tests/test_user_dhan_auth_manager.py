from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import os
import unittest

from pipeline.services.user_dhan_auth_manager import UserDhanAuthManager
from pipeline.services.user_dhan_credentials import UserDhanCredentials, require_static_ip_response
from pipeline.services.dhan_credentials import DhanCredentials
from pipeline.services.dhan_service import DhanService
from pipeline.config import PipelineConfig


class UserAuthLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = patch.dict(os.environ, {"DHAN_USER_CREDENTIALS_ENCRYPTION_SECRET": "unit-test-only"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.now = datetime.now(timezone.utc)
        self.manager = UserDhanAuthManager(SimpleNamespace(backend_dir=Path(self.tmp.name)))
        self.row = {
            "supabaseUserId": "test-user", "dhanClientId": "123456",
            "encryptedAccessToken": self.encrypt("old", "access-token"),
            "updatedAt": self.now.isoformat(), "tokenIssuedAt": self.now.isoformat(),
            "tokenSource": "web", "autoRenew": True,
        }
        self.service = MagicMock()
        self.service.fetch_user_profile.return_value = self.profile()
        self.service.fetch_static_ips.return_value = {"status": "success", "data": {
            "detectedIP": "1.2.3.4", "primaryIP": "1.2.3.4", "ordersAllowed": True}}
        self.factory = patch("pipeline.services.user_dhan_auth_manager.DhanService", return_value=self.service)
        self.factory.start()
        self.addCleanup(self.factory.stop)
        self.store = patch("pipeline.services.user_dhan_auth_manager.DhanCredentialStore")
        self.store_mock = self.store.start()
        self.store_mock.return_value.load.return_value = None
        self.addCleanup(self.store.stop)

    def encrypt(self, value, kind):
        return UserDhanCredentials.encrypt(value, "test-user", kind)

    def profile(self):
        return {"status": "success", "data": {"dhanClientId": "123456", "tokenValidity": (self.now + timedelta(hours=23)).isoformat()}}

    def due(self):
        self.row["tokenIssuedAt"] = (self.now - timedelta(hours=13)).isoformat()

    def recovery(self):
        self.row.update(encryptedPin=self.encrypt("123456", "pin"),
                        encryptedTotpSecret=self.encrypt("JBSWY3DPEHPK3PXP", "totp-secret"))

    def test_valid_token_does_not_rotate(self):
        result = self.manager.check(self.row)
        self.assertEqual(result["authStatus"], "ready")
        self.service.renew_access_token.assert_not_called()
        self.service.generate_access_token.assert_not_called()

    def test_web_token_rotates_after_twelve_hours(self):
        self.due()
        self.service.renew_access_token.return_value = {"status": "success", "data": {"accessToken": "replacement"}}
        result = self.manager.check(self.row)
        self.assertEqual(UserDhanCredentials._decrypt(result["encryptedAccessToken"], "test-user", "access-token"), "replacement")
        self.assertTrue(self.manager._pending_path("test-user").exists())

    def test_consent_token_uses_totp_not_unsupported_renewal(self):
        self.due()
        self.recovery()
        self.row["tokenSource"] = "consent"
        self.service.generate_access_token.return_value = {"status": "success", "data": {"accessToken": "replacement"}}
        result = self.manager.check(self.row)
        self.assertEqual(result["tokenSource"], "totp")
        self.service.renew_access_token.assert_not_called()
        self.service.generate_access_token.assert_called_once()

    def test_network_failure_does_not_rotate_tokens(self):
        self.due()
        self.service.fetch_user_profile.return_value = {"status": "failure", "remarks": "timeout", "data": None}
        self.assertEqual(self.manager.check(self.row)["authStatus"], "unavailable")
        self.service.renew_access_token.assert_not_called()
        self.service.generate_access_token.assert_not_called()

    def test_invalid_token_recovers_without_browser(self):
        self.recovery()
        self.service.fetch_user_profile.side_effect = [
            {"status": "failure", "data": {"errorCode": "DH-906"}}, self.profile()]
        self.service.generate_access_token.return_value = {"status": "success", "data": {"accessToken": "recovered"}}
        self.assertEqual(self.manager.check(self.row)["authStatus"], "ready")

    def test_disabled_renewal_does_not_generate(self):
        self.due()
        self.recovery()
        self.row["autoRenew"] = False
        self.manager.check(self.row)
        self.service.renew_access_token.assert_not_called()
        self.service.generate_access_token.assert_not_called()

    def test_shared_account_uses_scanner_rotation_owner(self):
        self.due()
        self.row["accountVerifiedAt"] = self.now.isoformat()
        self.store_mock.return_value.load.return_value = DhanCredentials(
            "123456", "scanner-current", 2, (self.now + timedelta(hours=20)).isoformat(), self.now.isoformat())
        result = self.manager.check(self.row)
        self.assertEqual(result["tokenSource"], "scanner")
        self.assertEqual(UserDhanCredentials._decrypt(result["encryptedAccessToken"], "test-user", "access-token"), "scanner-current")
        self.service.renew_access_token.assert_not_called()
        self.service.generate_access_token.assert_not_called()

    def test_matching_client_id_without_ownership_cannot_obtain_scanner_token(self):
        self.store_mock.return_value.load.return_value = DhanCredentials("123456", "scanner", 2)
        self.service.fetch_user_profile.return_value = {"status": "failure", "data": {"errorCode": "DH-906"}}
        result = self.manager.check(self.row)
        self.assertEqual(result["authError"], "verify_account_once")
        self.assertNotIn("encryptedAccessToken", result)

    def test_replacement_survives_failed_validation(self):
        self.due()
        self.service.renew_access_token.return_value = {"status": "success", "data": {"accessToken": "replacement"}}
        self.service.fetch_user_profile.side_effect = [self.profile(), {"status": "failure"}]
        result = self.manager.check(self.row)
        self.assertEqual(result["authStatus"], "unavailable")
        self.assertIn("encryptedAccessToken", result)

    def test_journal_replays_without_another_broker_rotation(self):
        result = {"authStatus": "pending", "encryptedAccessToken": self.encrypt("replacement", "access-token")}
        self.manager._journal(self.row, result)
        client = MagicMock()
        client.query.return_value = [self.row]
        client.mutation.return_value = True
        with patch("pipeline.services.user_dhan_auth_manager.ConvexService.client", return_value=client):
            self.manager.run_once()
        self.service.renew_access_token.assert_not_called()
        self.assertFalse(self.manager._pending_path("test-user").exists())
        self.assertEqual(client.mutation.call_args.args[1]["encryptedAccessToken"], result["encryptedAccessToken"])

    def test_lease_denial_skips_broker_calls(self):
        client = MagicMock()
        client.query.return_value = [self.row]
        client.mutation.return_value = False
        with patch("pipeline.services.user_dhan_auth_manager.ConvexService.client", return_value=client):
            self.manager.run_once()
        self.service.fetch_user_profile.assert_not_called()

    def test_invalid_token_is_not_labelled_ip_failure(self):
        with self.assertRaisesRegex(RuntimeError, "user_dhan_invalid_token"):
            require_static_ip_response({"status": "failure", "data": {"errorCode": "DH-906", "errorMessage": "Invalid Token"}})

    def test_cached_service_still_rejects_expiry(self):
        row = {**self.row, "tokenExpiresAt": (self.now - timedelta(seconds=1)).isoformat()}
        credentials = UserDhanCredentials()
        credentials._services["test-user"] = (row["updatedAt"], object())
        with patch("pipeline.services.user_dhan_credentials.ConvexService.get_dhan_credentials", return_value=row):
            with self.assertRaisesRegex(RuntimeError, "authorization_expired"):
                credentials.service("test-user")

    def test_explicit_user_credentials_never_use_environment_account(self):
        creds = DhanCredentials("user-account", "user-token", 1)
        with patch.object(DhanService, "_rebuild_clients"), patch.object(DhanService, "_select_credentials", side_effect=AssertionError("must not select globals")):
            service = DhanService(PipelineConfig(), prefer_gateway=False, credentials=creds)
        self.assertEqual(service.client_id, "user-account")
        self.assertEqual(service.access_token, "user-token")


if __name__ == "__main__":
    unittest.main()
