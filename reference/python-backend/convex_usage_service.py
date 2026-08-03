import logging
from datetime import datetime, timezone
from typing import Any, Optional

import config

try:
    from convex import ConvexClient
except Exception:  # pragma: no cover - runtime dependency guard
    try:
        # Some convex package versions expose the client under convex.client
        from convex.client import ConvexClient  # type: ignore
    except Exception:
        ConvexClient = None


logger = logging.getLogger(__name__)


def _to_int(value: Any) -> int:
    try:
        return max(int(value or 0), 0)
    except (TypeError, ValueError):
        return 0


def _to_unix_ms(value: Any) -> Optional[int]:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, datetime):
        normalized = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return int(normalized.timestamp() * 1000)
    try:
        text = str(value).strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
        if not parsed.tzinfo:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return int(parsed.timestamp() * 1000)
    except Exception:
        return None


class ConvexUsageService:
    def __init__(self) -> None:
        self._client = None
        self._warned_disabled = False
        self._warned_no_admin_key = False

    def is_enabled(self) -> bool:
        return bool(config.CONVEX_USAGE_ENABLED and config.CONVEX_URL and ConvexClient)

    def _get_client(self):
        if not self.is_enabled():
            if not self._warned_disabled:
                self._warned_disabled = True
                logger.warning(
                    "[ConvexUsage] Disabled. CONVEX_USAGE_ENABLED=%s CONVEX_URL_set=%s convex_sdk=%s",
                    bool(config.CONVEX_USAGE_ENABLED),
                    bool(config.CONVEX_URL),
                    bool(ConvexClient),
                )
            return None

        if self._client is not None:
            return self._client

        try:
            self._client = ConvexClient(config.CONVEX_URL)
            if config.CONVEX_ADMIN_KEY:
                self._client.set_admin_auth(config.CONVEX_ADMIN_KEY)
            elif not self._warned_no_admin_key:
                self._warned_no_admin_key = True
                logger.warning(
                    "[ConvexUsage] CONVEX_ADMIN_KEY not set. Using unauthenticated Convex calls."
                )
            return self._client
        except Exception as exc:
            logger.error("[ConvexUsage] Failed to initialize ConvexClient: %s", exc, exc_info=True)
            return None

    def record_token_usage(
        self,
        *,
        user_id: str,
        conversation_id: str,
        message_id: Optional[str],
        metrics: dict[str, Any],
        usage_window: dict[str, Any],
        source: str = "agent_runner",
    ) -> Optional[dict[str, Any]]:
        client = self._get_client()
        if client is None:
            return None

        event_key = f"{conversation_id}:{message_id or 'unknown'}"
        day_key = str(usage_window.get("day_key") or datetime.now(timezone.utc).strftime("%Y-%m-%d"))
        payload = {
            "user_id": str(user_id),
            "event_key": event_key,
            "conversation_id": str(conversation_id or ""),
            "message_id": str(message_id or ""),
            "day_key": day_key,
            "window_key": str(usage_window.get("window_key") or f"fallback:{day_key}"),
            "plan_type": str(usage_window.get("plan_type") or "free"),
            "limit_interval": str(usage_window.get("limit_interval") or "day"),
            "input_tokens": _to_int(metrics.get("input_tokens")),
            "output_tokens": _to_int(metrics.get("output_tokens")),
            "total_tokens": _to_int(metrics.get("total_tokens")),
            "window_start_ms": _to_unix_ms(usage_window.get("window_start")),
            "window_end_ms": _to_unix_ms(usage_window.get("window_end")),
            "source": str(source or "agent_runner"),
        }
        if payload["total_tokens"] <= 0:
            payload["total_tokens"] = payload["input_tokens"] + payload["output_tokens"]

        return client.mutation("usage:recordTokenUsage", payload)

    def get_window_usage(self, *, user_id: str, window_key: str) -> Optional[dict[str, Any]]:
        client = self._get_client()
        if client is None:
            return None
        return client.query(
            "usage:getWindowUsage",
            {
                "user_id": str(user_id),
                "window_key": str(window_key),
            },
        )

    def get_daily_usage_for_user(
        self,
        *,
        user_id: str,
        day_key: Optional[str] = None,
        limit: int = 30,
    ) -> Optional[list[dict[str, Any]]]:
        client = self._get_client()
        if client is None:
            return None
        args: dict[str, Any] = {
            "user_id": str(user_id),
            "limit": max(min(int(limit or 30), 365), 1),
        }
        if day_key:
            args["day_key"] = str(day_key)
        return client.query(
            "usage:getDailyUsageForUser",
            args,
        )

    def get_usage_events_for_user(
        self,
        *,
        user_id: str,
        limit: int = 2000,
    ) -> Optional[list[dict[str, Any]]]:
        client = self._get_client()
        if client is None:
            return None
        return client.query(
            "usage:getUsageEventsForUser",
            {
                "user_id": str(user_id),
                "limit": max(min(int(limit or 2000), 10000), 1),
            },
        )

    def get_daily_usage_by_date(self, *, day_key: str, limit: int = 500) -> Optional[list[dict[str, Any]]]:
        client = self._get_client()
        if client is None:
            return None
        return client.query(
            "usage:getDailyUsageByDate",
            {
                "day_key": str(day_key),
                "limit": max(min(int(limit or 500), 5000), 1),
            },
        )

    def get_lifetime_usage(self, *, user_id: str) -> Optional[dict[str, Any]]:
        client = self._get_client()
        if client is None:
            return None
        return client.query(
            "usage:getLifetimeUsage",
            {
                "user_id": str(user_id),
            },
        )

    def upsert_subscription_snapshot(self, *, user_id: str, profile: dict[str, Any]) -> Optional[dict[str, Any]]:
        client = self._get_client()
        if client is None:
            return None

        payload = {
            "user_id": str(user_id),
            "plan_type": str(profile.get("plan_type") or "free"),
            "subscription_status": str(profile.get("subscription_status") or "none"),
            "current_period_end_iso": str(profile.get("current_period_end"))
            if profile.get("current_period_end")
            else None,
            "current_period_end_ms": _to_unix_ms(profile.get("current_period_end")),
            # Convex validators in this project expect strings, not null.
            "razorpay_customer_id": str(profile.get("razorpay_customer_id") or ""),
            "razorpay_subscription_id": str(profile.get("razorpay_subscription_id") or ""),
        }
        return client.mutation("usage:upsertSubscriptionSnapshot", payload)


_usage_service_singleton: Optional[ConvexUsageService] = None


def get_convex_usage_service() -> ConvexUsageService:
    global _usage_service_singleton
    if _usage_service_singleton is None:
        _usage_service_singleton = ConvexUsageService()
    return _usage_service_singleton
