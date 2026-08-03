import sys
import types
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
from gotrue.errors import AuthApiError

# The production image installs redis from requirements.txt. Keep this focused
# unit test runnable in lightweight developer environments that omit it.
try:
    import redis  # noqa: F401
except ModuleNotFoundError:
    redis_stub = types.ModuleType("redis")
    redis_stub.Redis = object
    redis_stub.from_url = Mock()
    sys.modules["redis"] = redis_stub

import utils


def test_auth_transport_failure_retries_then_returns_503(monkeypatch):
    get_user = Mock(side_effect=httpx.ConnectError("resolver unavailable"))
    monkeypatch.setattr(utils.supabase_client.auth, "get_user", get_user)
    monkeypatch.setattr(utils.time, "sleep", lambda _seconds: None)

    user, error = utils._validate_user_with_supabase("test-jwt")

    assert user is None
    assert error == ("Authentication service temporarily unavailable", 503)
    assert get_user.call_count == 2


def test_auth_transport_retry_can_recover(monkeypatch):
    expected_user = SimpleNamespace(id="user-123")
    get_user = Mock(
        side_effect=[
            httpx.ConnectError("temporary resolver failure"),
            SimpleNamespace(user=expected_user),
        ]
    )
    monkeypatch.setattr(utils.supabase_client.auth, "get_user", get_user)
    monkeypatch.setattr(utils.time, "sleep", lambda _seconds: None)

    user, error = utils._validate_user_with_supabase("test-jwt")

    assert error is None
    assert user is expected_user
    assert get_user.call_count == 2


def test_auth_api_error_returns_401_without_retry(monkeypatch):
    get_user = Mock(
        side_effect=AuthApiError("invalid token", 401, "bad_jwt")
    )
    monkeypatch.setattr(utils.supabase_client.auth, "get_user", get_user)
    monkeypatch.setattr(utils.time, "sleep", lambda _seconds: None)

    user, error = utils._validate_user_with_supabase("test-jwt")

    assert user is None
    assert error == ("Invalid or expired token", 401)
    assert get_user.call_count == 1


def test_missing_user_returns_401_without_retry(monkeypatch):
    get_user = Mock(return_value=SimpleNamespace(user=None))
    monkeypatch.setattr(utils.supabase_client.auth, "get_user", get_user)
    monkeypatch.setattr(utils.time, "sleep", lambda _seconds: None)

    user, error = utils._validate_user_with_supabase("test-jwt")

    assert user is None
    assert error == ("Invalid or expired token", 401)
    assert get_user.call_count == 1


def test_unexpected_programming_error_is_not_hidden(monkeypatch):
    get_user = Mock(side_effect=ValueError("unexpected response shape"))
    monkeypatch.setattr(utils.supabase_client.auth, "get_user", get_user)

    with pytest.raises(ValueError, match="unexpected response shape"):
        utils._validate_user_with_supabase("test-jwt")

    assert get_user.call_count == 1


def test_rest_auth_propagates_transport_outage_as_503(monkeypatch):
    request = SimpleNamespace(
        headers={"Authorization": "Bearer test-jwt"}
    )
    monkeypatch.setattr(utils, "_user_from_cache", lambda _jwt: None)
    monkeypatch.setattr(utils.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        utils.supabase_client.auth,
        "get_user",
        Mock(side_effect=httpx.ConnectError("resolver unavailable")),
    )

    user, error = utils.get_user_from_token(request)

    assert user is None
    assert error == ("Authentication service temporarily unavailable", 503)


def test_socket_auth_success_still_writes_through_to_cache(monkeypatch):
    expected_user = SimpleNamespace(id="user-123")
    cache_write = Mock()
    monkeypatch.setattr(utils, "_user_from_cache", lambda _jwt: None)
    monkeypatch.setattr(utils, "_user_to_cache", cache_write)
    monkeypatch.setattr(
        utils.supabase_client.auth,
        "get_user",
        Mock(return_value=SimpleNamespace(user=expected_user)),
    )

    user, error = utils.get_user_from_jwt("test-jwt")

    assert error is None
    assert user is expected_user
    cache_write.assert_called_once_with("test-jwt", expected_user)
