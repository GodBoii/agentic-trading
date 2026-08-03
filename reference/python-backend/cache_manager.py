# python-backend/cache_manager.py
#
# Redis-backed cache with JSON serialisation, TTL support, and non-blocking
# bulk key invalidation via SCAN (never uses the blocking KEYS command).
import json
import logging
import redis
from datetime import datetime, date
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID
import config


class _SupabaseEncoder(json.JSONEncoder):
    """
    JSON encoder that handles all types Supabase/PostgREST returns that the
    standard library cannot serialise out of the box.

    Without this encoder, CacheManager.set() silently fails for any payload
    containing these types, turning every request into a perpetual cache miss.

    Conversion rules:
      - datetime  → ISO-8601 string   e.g. "2026-04-30T04:23:30"
      - date      → ISO-8601 string   e.g. "2026-04-30"
      - UUID      → string            e.g. "c069d103-4568-4479-ab87-a3e264c0ebe9"
      - Decimal   → float             e.g. 3.14
      - set       → list              e.g. [1, 2, 3]
      - All other types fall back to the default encoder (raises TypeError
        for truly un-serialisable objects, preserving correct error behaviour).
    """
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, date):
            return obj.isoformat()
        if isinstance(obj, UUID):
            return str(obj)
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, set):
            return list(obj)
        return super().default(obj)

logger = logging.getLogger(__name__)

# Initialize a dedicated Redis connection for caching using the global config
# Decode responses ensures we get strings back instead of bytes, making JSON parsing easier
cache_redis = redis.from_url(config.REDIS_URL, decode_responses=True)

class CacheManager:
    @staticmethod
    def get(key: str) -> Optional[Any]:
        """
        Attempt to retrieve and deserialize JSON data from Redis.
        Returns None if cache miss or error.
        """
        try:
            data = cache_redis.get(key)
            if data:
                logger.info(f"[CACHE HIT] {key}")
                return json.loads(data)
            logger.info(f"[CACHE MISS] {key}")
            return None
        except Exception as e:
            logger.error(f"Cache get error for key {key}: {e}")
            return None

    @staticmethod
    def set(key: str, data: Any, ttl_seconds: int = 3600) -> bool:
        """
        Serialize and store data in Redis with a TTL (default 1 hour = 3600 seconds).

        Uses _SupabaseEncoder so that non-standard types returned by Supabase
        (datetime, date, UUID, Decimal, set) are automatically converted to
        JSON-safe primitives instead of raising TypeError.
        """
        try:
            # Use _SupabaseEncoder so that datetime, UUID, Decimal, etc.
            # objects returned by Supabase are serialised correctly.
            serialized = json.dumps(data, cls=_SupabaseEncoder)
            # ex=ttl_seconds sets the expiration time automatically in Redis
            return cache_redis.set(key, serialized, ex=ttl_seconds)
        except Exception as e:
            logger.error(f"Cache set error for key {key}: {e}")
            return False

    @staticmethod
    def delete(key: str) -> bool:
        """
        Delete a key from Redis (used for active cache invalidation).
        """
        try:
            cache_redis.delete(key)
            logger.info(f"[CACHE INVALIDATED] {key}")
            return True
        except Exception as e:
            logger.error(f"Cache delete error for key {key}: {e}")
            return False

    @staticmethod
    def invalidate_pattern(pattern: str) -> None:
        """
        Invalidate all Redis keys matching a glob pattern (e.g. 'cache:memories:user123:*').

        Why SCAN instead of KEYS:
        - KEYS is O(N) and holds Redis's single-threaded command lock for the
          entire scan. Every other client — Flask-Limiter, SocketIO pub/sub,
          session reads — stalls until it completes. On large keyspaces this can
          mean tens of milliseconds of full Redis unavailability.
        - SCAN iterates in small cursor-based batches (count=100 per call).
          Redis can serve other commands between batches, so latency stays low
          even on keyspaces with millions of keys.

        Keys matched across all cursor pages are deleted in one single DEL call
        (one round-trip regardless of how many keys were found).
        """
        try:
            matched: list[str] = []
            cursor = 0
            while True:
                # count=100 is a hint to Redis about batch size per iteration.
                # It does NOT guarantee exactly 100 results per call — Redis may
                # return more or fewer depending on its internal data structures.
                # 100 strikes a balance between round-trip count and per-call work.
                cursor, batch = cache_redis.scan(cursor=cursor, match=pattern, count=100)
                if batch:
                    matched.extend(batch)
                # cursor returns to 0 when the full keyspace has been visited.
                if cursor == 0:
                    break

            if matched:
                # Single DEL with all keys — one network round-trip.
                cache_redis.delete(*matched)
                logger.info(
                    "[CACHE PATTERN INVALIDATED] %s (%d keys deleted)",
                    pattern,
                    len(matched),
                )
        except Exception as e:
            logger.error(f"Cache invalidate pattern error for {pattern}: {e}")
