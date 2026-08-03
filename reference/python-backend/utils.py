# python-backend/utils.py
#
# JWT validation with Redis-backed caching (5-minute TTL).
#
# Why cache JWT validation?
# ─────────────────────────
# Every authenticated endpoint calls supabase_client.auth.get_user(jwt=...) which
# makes an outbound HTTPS request to your Supabase project URL. That round-trip
# typically adds 50-200 ms to every single request. By caching the validated user
# object in Redis for 5 minutes we avoid that external HTTP call on repeated
# requests within an active session, cutting Supabase auth API traffic by ~90%.
#
# Security design decisions:
# - The JWT itself is NEVER stored in Redis. We hash it with SHA-256 (a
#   one-way function) and use the hash as the cache key. Even if Redis is
#   compromised, the attacker cannot recover any JWT from the keys.
# - Invalid / expired tokens are never written to the cache. Only successful
#   Supabase validations produce a cache entry.
# - TTL is 5 minutes. Supabase JWTs expire in ~1 hour by default, but we use
#   a much shorter cache TTL so that a revoked or logged-out token stops working
#   within 5 minutes — an acceptable window for most applications.
# - The cached value is the JSON-serialised user payload (id, email, role, etc.)
#   reconstructed into a types.SimpleNamespace on retrieval, which quacks like
#   the real Supabase User object for all downstream code (user.id, user.email).

import hashlib
import httpx
import json
import logging
import time
import types
import redis

from gotrue.errors import AuthApiError

from supabase_client import supabase_client
import config

logger = logging.getLogger(__name__)

# Dedicated Redis client for JWT caching.
# We lazily initialise this so that import-time failures (e.g. Redis not yet up)
# don't crash the whole application — a failed cache lookup falls through to
# Supabase exactly as before.
_jwt_cache_redis: redis.Redis | None = None

# Cache TTL: 5 minutes. Short enough that logout/revocation takes effect quickly;
# long enough to capture repeated requests within a normal user session.
_JWT_CACHE_TTL_SECONDS = 300

# Redis key prefix — makes it easy to spot JWT cache entries in redis-cli
# and to flush them selectively without touching other cache namespaces.
_JWT_CACHE_PREFIX = "jwt_cache:"

_AUTH_NETWORK_ATTEMPTS = 2
_AUTH_NETWORK_RETRY_DELAY_SECONDS = 0.2


def _get_jwt_redis() -> redis.Redis | None:
    """
    Return (and lazily initialise) the Redis client used for JWT caching.
    Returns None if Redis is not configured or cannot connect, so callers
    can treat a None return as a cache miss and fall through to Supabase.
    """
    global _jwt_cache_redis
    if _jwt_cache_redis is not None:
        return _jwt_cache_redis
    if not config.REDIS_URL:
        return None
    try:
        # decode_responses=True so we work with str, not bytes
        _jwt_cache_redis = redis.from_url(config.REDIS_URL, decode_responses=True)
        return _jwt_cache_redis
    except Exception as exc:
        logger.warning("[JWT Cache] Failed to initialise Redis client: %s", exc)
        return None


def _jwt_cache_key(jwt: str) -> str:
    """
    Derive a safe, compact Redis key from the raw JWT.

    We SHA-256 hash the token so:
      1. The key is always exactly 64 hex characters regardless of JWT length.
      2. The raw token cannot be recovered from the key (one-way function).
      3. Two identical JWTs always produce the same cache key (deterministic).
    """
    digest = hashlib.sha256(jwt.encode("utf-8")).hexdigest()
    return f"{_JWT_CACHE_PREFIX}{digest}"


def _user_from_cache(jwt: str):
    """
    Attempt to load a previously cached user object from Redis.

    Returns a types.SimpleNamespace with the same attributes as a Supabase
    User object (id, email, role, etc.) so all downstream code works without
    changes, or None on cache miss / Redis error.
    """
    r = _get_jwt_redis()
    if r is None:
        return None
    try:
        raw = r.get(_jwt_cache_key(jwt))
        if not raw:
            return None
        data = json.loads(raw)
        # Reconstruct a lightweight object that behaves like the Supabase User.
        # SimpleNamespace supports attribute access (user.id, user.email, etc.)
        # which is all downstream code ever does.
        user_ns = types.SimpleNamespace(**data)
        logger.info("[JWT Cache] HIT for user=%s", data.get("id", "unknown"))
        return user_ns
    except Exception as exc:
        # Cache errors must never break authentication — just miss and continue.
        logger.warning("[JWT Cache] Read error (treating as miss): %s", exc)
        return None


def _user_to_cache(jwt: str, user) -> None:
    """
    Persist the validated Supabase user object in Redis for 5 minutes.

    We serialise only the fields downstream code actually uses (plus a safe
    superset). If a field is missing on the user object we skip it gracefully.
    """
    r = _get_jwt_redis()
    if r is None:
        return
    try:
        # Build a plain dict from the Supabase User object.  We extract
        # attributes explicitly rather than using __dict__ / vars() because
        # the Supabase client returns a pydantic/dataclass model whose
        # internal representation may differ from what callers expect.
        payload: dict = {}
        for field in ("id", "email", "phone", "role", "aud",
                      "email_confirmed_at", "created_at", "updated_at",
                      "user_metadata", "app_metadata"):
            val = getattr(user, field, None)
            if val is not None:
                # Ensure all values are JSON-serialisable primitives.
                # user_metadata / app_metadata are dicts; timestamps are strings.
                payload[field] = val if isinstance(val, (str, int, float, bool, dict, list)) else str(val)

        if not payload.get("id"):
            # Safety check: don't cache if we couldn't extract a user ID.
            logger.warning("[JWT Cache] Skipping cache write — could not extract user id.")
            return

        r.set(_jwt_cache_key(jwt), json.dumps(payload), ex=_JWT_CACHE_TTL_SECONDS)
        logger.info("[JWT Cache] WRITE user=%s TTL=%ds", payload["id"], _JWT_CACHE_TTL_SECONDS)
    except Exception as exc:
        # Cache write failures are non-fatal — the user object was already
        # returned to the caller successfully.
        logger.warning("[JWT Cache] Write error (non-fatal): %s", exc)


def _validate_user_with_supabase(jwt: str):
    """Validate a JWT and distinguish auth failures from transport outages."""
    for attempt in range(1, _AUTH_NETWORK_ATTEMPTS + 1):
        try:
            user_response = supabase_client.auth.get_user(jwt=jwt)
        except AuthApiError as exc:
            logger.warning("API authentication rejected: %s", exc.message)
            return None, ("Invalid or expired token", 401)
        except httpx.TransportError as exc:
            if attempt < _AUTH_NETWORK_ATTEMPTS:
                logger.warning(
                    "Authentication service connection failed; retrying "
                    "attempt=%s/%s error=%s",
                    attempt,
                    _AUTH_NETWORK_ATTEMPTS,
                    type(exc).__name__,
                )
                time.sleep(_AUTH_NETWORK_RETRY_DELAY_SECONDS)
                continue

            logger.error(
                "Authentication service unavailable after %s attempts: %s",
                _AUTH_NETWORK_ATTEMPTS,
                type(exc).__name__,
            )
            return None, ("Authentication service temporarily unavailable", 503)

        if not user_response.user:
            logger.warning("API authentication rejected: user missing from response")
            return None, ("Invalid or expired token", 401)

        return user_response.user, None

    return None, ("Authentication service temporarily unavailable", 503)


def get_user_from_token(request_object):
    """
    Validates a JWT from an Authorization header and returns the authenticated user.

    Flow:
      1. Extract the Bearer token from the Authorization header.
      2. Check Redis cache (key = SHA-256 hash of JWT, TTL 5 min).
         - HIT  → return cached user object immediately (no Supabase call).
         - MISS → call Supabase auth.get_user(), cache the result, return user.
      3. On AuthApiError (bad/expired token) return a 401 error tuple.

    Args:
        request_object: The Flask request object.

    Returns:
        (user, None) on success  — user has .id, .email, etc.
        (None, (message, status_code)) on failure.
    """
    auth_header = request_object.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return None, ("Authorization header is missing or invalid", 401)

    jwt = auth_header.split(" ", 1)[1]

    # ── Step 1: Try cache first ──────────────────────────────────────────────
    cached_user = _user_from_cache(jwt)
    if cached_user is not None:
        return cached_user, None

    # ── Step 2: Cache miss — validate against Supabase ──────────────────────
    logger.info("[JWT Cache] MISS — calling Supabase auth.get_user()")
    user, error = _validate_user_with_supabase(jwt)
    if error:
        return None, error

    # Only successful validations are cached.
    _user_to_cache(jwt, user)
    return user, None


def get_user_from_jwt(jwt: str):
    """
    Validates a raw JWT and returns the authenticated user.

    Socket.IO messages carry the token in the event payload instead of an HTTP
    Authorization header, so they cannot call get_user_from_token(request)
    directly. Keep the same Redis-backed cache behavior as REST endpoints.
    """
    if not jwt:
        return None, ("Authentication token is missing", 401)

    cached_user = _user_from_cache(jwt)
    if cached_user is not None:
        return cached_user, None

    logger.info("[JWT Cache] MISS — calling Supabase auth.get_user()")
    user, error = _validate_user_with_supabase(jwt)
    if error:
        return None, error

    _user_to_cache(jwt, user)
    return user, None
