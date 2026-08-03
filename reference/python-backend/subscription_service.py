import hashlib
import hmac
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import requests

import config
from convex_usage_service import get_convex_usage_service
from supabase_client import supabase_client

logger = logging.getLogger(__name__)

RAZORPAY_API_BASE = "https://api.razorpay.com/v1"
DEFAULT_SUBSCRIPTION_TOTAL_COUNT = 120
PAID_PLAN_TYPES = {"pro", "elite"}
ACCESS_ACTIVE_STATUSES = {"active", "authenticated", "resumed"}
ACCESS_WINDOW_STATUSES = {"cancelled", "paused"}
TERMINAL_STATUSES = {"completed", "expired", "halted"}
SUBSCRIPTION_CHANGEABLE_STATUSES = {"authenticated", "active"}
SUBSCRIPTION_BLOCKING_STATUSES = {"authenticated", "active", "pending", "paused", "resumed"}
PLAN_RANK = {"free": 0, "pro": 1, "elite": 2}


PLAN_CATALOG: dict[str, dict[str, Any]] = {
    "free": {
        "type": "free",
        "name": "Core",
        "price_inr": 0,
        "limit_tokens": 50_000,
        "interval_label": "day",
        "description": "Entry tier with a daily token budget.",
        "cta_label": "Included",
        "accent": "core",
    },
    "pro": {
        "type": "pro",
        "name": "Pro",
        "price_inr": 428,
        "limit_tokens": 5_000_000,
        "interval_label": "month",
        "description": "Monthly plan for regular heavy usage.",
        "cta_label": "Upgrade to Pro",
        "accent": "pro",
    },
    "elite": {
        "type": "elite",
        "name": "Elite",
        "price_inr": 4_428,
        "limit_tokens": 50_000_000,
        "interval_label": "month",
        "description": "Highest monthly allowance for intensive workflows.",
        "cta_label": "Upgrade to Elite",
        "accent": "elite",
    },
}

NON_ACCESS_STATUSES = {"created", "pending", "halted", "expired", "completed"}
INCOMPLETE_SUBSCRIPTION_STATUSES = {"created", "pending", "halted", "expired"}
ABANDONED_CHECKOUT_STATUSES = {"created", "expired"}


class UsageLimitExceeded(Exception):
    def __init__(self, summary: dict[str, Any]):
        self.summary = summary
        super().__init__(format_limit_message(summary))


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _to_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _subscription_total_count() -> int:
    configured = _to_int(getattr(config, "RAZORPAY_SUBSCRIPTION_TOTAL_COUNT", DEFAULT_SUBSCRIPTION_TOTAL_COUNT))
    configured_max = _to_int(getattr(config, "RAZORPAY_SUBSCRIPTION_MAX_TOTAL_COUNT", DEFAULT_SUBSCRIPTION_TOTAL_COUNT))
    if configured <= 0:
        configured = DEFAULT_SUBSCRIPTION_TOTAL_COUNT
    if configured_max <= 0:
        configured_max = DEFAULT_SUBSCRIPTION_TOTAL_COUNT
    return max(1, min(configured, configured_max, DEFAULT_SUBSCRIPTION_TOTAL_COUNT))


def _parse_dt(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _dt_to_iso(value: Optional[datetime]) -> Optional[str]:
    if not value:
        return None
    normalized = value.astimezone(timezone.utc)
    return normalized.isoformat()


def _unix_to_dt(value: Any) -> Optional[datetime]:
    try:
        if value in (None, ""):
            return None
        return datetime.fromtimestamp(int(value), tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None


def _next_utc_day_boundary(now: Optional[datetime] = None) -> datetime:
    current = now or _utc_now()
    midnight = datetime(
        year=current.year,
        month=current.month,
        day=current.day,
        tzinfo=timezone.utc,
    )
    return midnight + timedelta(days=1)


def _utc_day_start(now: Optional[datetime] = None) -> datetime:
    current = now or _utc_now()
    return datetime(
        year=current.year,
        month=current.month,
        day=current.day,
        tzinfo=timezone.utc,
    )


def _resolve_usage_window_from_profile(profile: dict[str, Any], now: Optional[datetime] = None) -> dict[str, Any]:
    current = now or _utc_now()
    plan_type = str(profile.get("plan_type") or "free").strip().lower()
    status = str(profile.get("subscription_status") or "none").strip().lower()
    current_period_end = _parse_dt(profile.get("current_period_end"))
    day_key = current.astimezone(timezone.utc).strftime("%Y-%m-%d")

    if (
        plan_type in PAID_PLAN_TYPES
        and _status_grants_paid_access(status, current_period_end)
    ):
        if current_period_end and current_period_end > current:
            window_key = f"{plan_type}:{int(current_period_end.timestamp())}"
            return {
                "plan_type": plan_type,
                "subscription_status": status,
                "limit_interval": "month",
                "day_key": day_key,
                "window_key": window_key,
                "window_start": None,
                "window_end": current_period_end,
            }

        month_start = datetime(year=current.year, month=current.month, day=1, tzinfo=timezone.utc)
        if current.month == 12:
            month_end = datetime(year=current.year + 1, month=1, day=1, tzinfo=timezone.utc)
        else:
            month_end = datetime(year=current.year, month=current.month + 1, day=1, tzinfo=timezone.utc)
        return {
            "plan_type": plan_type,
            "subscription_status": status,
            "limit_interval": "month",
            "day_key": day_key,
            "window_key": f"{plan_type}:calendar:{month_start.strftime('%Y-%m')}",
            "window_start": month_start,
            "window_end": month_end,
        }

    window_start = _utc_day_start(current)
    window_end = _next_utc_day_boundary(current)
    return {
        "plan_type": "free",
        "subscription_status": "none" if plan_type == "free" else status,
        "limit_interval": "day",
        "day_key": day_key,
        "window_key": f"free:{window_start.strftime('%Y-%m-%d')}",
        "window_start": window_start,
        "window_end": window_end,
    }


def _extract_response_data(response: Any, default: Any) -> Any:
    """
    The Supabase client can return `None` from execute() in transient edge-cases.
    Normalize that so callers don't crash on `response.data`.
    """
    if response is None:
        return default
    return getattr(response, "data", default)


def get_plan_catalog() -> list[dict[str, Any]]:
    plans: list[dict[str, Any]] = []
    for key in ("free", "pro", "elite"):
        plan = dict(PLAN_CATALOG[key])
        plan["token_limit_label"] = format_token_limit(plan["limit_tokens"], plan["interval_label"])
        plans.append(plan)
    return plans


def get_plan_config(plan_type: Optional[str]) -> dict[str, Any]:
    key = str(plan_type or "free").strip().lower()
    return PLAN_CATALOG.get(key, PLAN_CATALOG["free"])


def get_plan_id_for_type(plan_type: str) -> Optional[str]:
    normalized = str(plan_type or "").strip().lower()
    if normalized == "pro":
        return config.PRO_PLAN_ID
    if normalized == "elite":
        return config.ELITE_PLAN_ID
    return None


def resolve_plan_type_from_plan_id(plan_id: Optional[str]) -> Optional[str]:
    if not plan_id:
        return None
    if config.PRO_PLAN_ID and str(plan_id) == str(config.PRO_PLAN_ID):
        return "pro"
    if config.ELITE_PLAN_ID and str(plan_id) == str(config.ELITE_PLAN_ID):
        return "elite"
    return None


def format_token_limit(limit_tokens: int, interval_label: str) -> str:
    return f"{int(limit_tokens):,} tokens/{interval_label}"


def _extract_error_message(response: requests.Response) -> str:
    try:
        payload = response.json() or {}
    except ValueError:
        payload = {}

    error_payload = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(error_payload, dict):
        description = error_payload.get("description") or error_payload.get("reason")
        code = error_payload.get("code")
        if description and code:
            return f"{description} ({code})"
        if description:
            return str(description)
    if isinstance(payload, dict) and payload.get("description"):
        return str(payload["description"])
    body = (response.text or "").strip()
    return body or f"HTTP {response.status_code}"


def _razorpay_auth_available() -> bool:
    return bool(config.RAZORPAY_KEY_ID and config.RAZORPAY_KEY_SECRET)


def get_profile(user_id: str) -> dict[str, Any]:
    response = (
        supabase_client
        .from_("profiles")
        .select(
            "id,email,name,plan_type,subscription_status,"
            "razorpay_customer_id,razorpay_subscription_id,current_period_end"
        )
        .eq("id", str(user_id))
        .single()
        .execute()
    )
    data = _extract_response_data(response, {}) or {}
    if not data:
        raise ValueError("Profile not found.")
    return data


def update_profile(user_id: str, fields: dict[str, Any]) -> dict[str, Any]:
    payload = dict(fields or {})
    if not payload:
        return get_profile(user_id)
    response = (
        supabase_client
        .from_("profiles")
        .update(payload)
        .eq("id", str(user_id))
        .execute()
    )
    updated_rows = _extract_response_data(response, []) or []
    return updated_rows[0] if updated_rows else get_profile(user_id)


def find_user_id_by_subscription_id(subscription_id: str) -> Optional[str]:
    if not subscription_id:
        return None
    response = (
        supabase_client
        .from_("profiles")
        .select("id")
        .eq("razorpay_subscription_id", str(subscription_id))
        .maybe_single()
        .execute()
    )
    data = _extract_response_data(response, {}) or {}
    return data.get("id")


def get_usage_window_descriptor(user_id: str, refresh_window: bool = True) -> dict[str, Any]:
    profile = get_profile(user_id)
    if refresh_window:
        profile = ensure_usage_window(user_id, profile)
    window = _resolve_usage_window_from_profile(profile)
    window.update(
        {
            "user_id": str(user_id),
            "plan_type": str(window.get("plan_type") or "free").lower(),
            "subscription_status": str(profile.get("subscription_status") or "none").lower(),
            "current_period_end": _dt_to_iso(_parse_dt(profile.get("current_period_end"))),
        }
    )
    return window


def _sync_profile_snapshot_to_convex(user_id: str, profile: dict[str, Any]) -> None:
    service = get_convex_usage_service()
    if not service.is_enabled():
        return
    try:
        service.upsert_subscription_snapshot(user_id=str(user_id), profile=profile)
    except Exception as exc:
        logger.warning("[ConvexUsage] Failed to upsert subscription snapshot for user %s: %s", user_id, exc)


def _get_convex_window_usage(user_id: str, window_key: str) -> Optional[dict[str, Any]]:
    service = get_convex_usage_service()
    if not service.is_enabled():
        return None
    try:
        response = service.get_window_usage(user_id=str(user_id), window_key=str(window_key))
        return response if isinstance(response, dict) else None
    except Exception as exc:
        logger.warning("[ConvexUsage] Failed to fetch window usage for user %s key %s: %s", user_id, window_key, exc)
        return None


def _get_convex_lifetime_usage(user_id: str) -> Optional[dict[str, Any]]:
    service = get_convex_usage_service()
    if not service.is_enabled():
        return None
    try:
        response = service.get_lifetime_usage(user_id=str(user_id))
        return response if isinstance(response, dict) else None
    except Exception as exc:
        logger.warning("[ConvexUsage] Failed to fetch lifetime usage for user %s: %s", user_id, exc)
        return None


def get_daily_usage_for_user(user_id: str, day_key: Optional[str] = None, limit: int = 30) -> list[dict[str, Any]]:
    service = get_convex_usage_service()
    if not service.is_enabled():
        return []
    try:
        rows: list[dict[str, Any]] = []
        try:
            daily_response = service.get_daily_usage_for_user(user_id=str(user_id), day_key=day_key, limit=limit)
            rows = daily_response if isinstance(daily_response, list) else []
        except Exception as exc:
            logger.warning(
                "[ConvexUsage] Primary usage_daily fetch failed for user=%s day_key=%s limit=%s err=%s",
                user_id,
                day_key,
                limit,
                exc,
            )

        normalized_rows = rows if isinstance(rows, list) else []
        if normalized_rows:
            logger.info(
                "[ConvexUsage] Daily graph source=usage_daily user=%s rows=%s day_key=%s limit=%s",
                user_id,
                len(normalized_rows),
                day_key,
                limit,
            )
            return normalized_rows

        event_limit = max(500, min(int(limit or 30) * 200, 10000))
        events: list[dict[str, Any]] = []
        try:
            event_response = service.get_usage_events_for_user(user_id=str(user_id), limit=event_limit)
            events = event_response if isinstance(event_response, list) else []
        except Exception as exc:
            logger.warning(
                "[ConvexUsage] usage_events fallback fetch failed for user=%s limit=%s err=%s",
                user_id,
                event_limit,
                exc,
            )
        event_rows = events if isinstance(events, list) else []
        if not event_rows:
            logger.info(
                "[ConvexUsage] usage_events fallback has no rows user=%s day_key=%s limit=%s",
                user_id,
                day_key,
                limit,
            )

        aggregated: dict[str, dict[str, Any]] = {}
        for event in event_rows:
            raw_day_key = str(event.get("day_key") or "").strip().strip('"')
            if not raw_day_key:
                continue
            day_row = aggregated.get(raw_day_key)
            if day_row is None:
                day_row = {
                    "user_id": str(user_id),
                    "day_key": raw_day_key,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "total_tokens": 0,
                    "first_event_at_ms": None,
                    "last_event_at_ms": None,
                    "created_at_ms": None,
                    "updated_at_ms": None,
                }
                aggregated[raw_day_key] = day_row

            input_tokens = _to_int(event.get("input_tokens"))
            output_tokens = _to_int(event.get("output_tokens"))
            total_tokens = _to_int(event.get("total_tokens")) or (input_tokens + output_tokens)
            created_at_ms = _to_int(event.get("created_at_ms"))

            day_row["input_tokens"] = _to_int(day_row.get("input_tokens")) + input_tokens
            day_row["output_tokens"] = _to_int(day_row.get("output_tokens")) + output_tokens
            day_row["total_tokens"] = _to_int(day_row.get("total_tokens")) + total_tokens

            first_event = day_row.get("first_event_at_ms")
            last_event = day_row.get("last_event_at_ms")
            if created_at_ms > 0:
                day_row["first_event_at_ms"] = created_at_ms if not first_event else min(_to_int(first_event), created_at_ms)
                day_row["last_event_at_ms"] = created_at_ms if not last_event else max(_to_int(last_event), created_at_ms)
                day_row["created_at_ms"] = day_row.get("created_at_ms") or day_row["first_event_at_ms"]
                day_row["updated_at_ms"] = day_row["last_event_at_ms"]

        daily_rows = sorted(
            aggregated.values(),
            key=lambda row: str(row.get("day_key") or ""),
            reverse=True,
        )
        if day_key:
            daily_rows = [row for row in daily_rows if str(row.get("day_key")) == str(day_key)]
        else:
            daily_rows = daily_rows[: max(1, min(int(limit or 30), 365))]

        logger.warning(
            "[ConvexUsage] Daily graph source=fallback_usage_events user=%s rows=%s day_key=%s limit=%s event_rows=%s",
            user_id,
            len(daily_rows),
            day_key,
            limit,
            len(event_rows),
        )
        if daily_rows:
            return daily_rows

        # Final fallback for free-plan daily graphing:
        # derive each day from existing usage_windows keys: free:YYYY-MM-DD
        # using already-deployed getWindowUsage query.
        normalized_limit = max(1, min(int(limit or 30), 365))

        def _build_recent_day_keys(max_days: int) -> list[str]:
            today = _utc_now().astimezone(timezone.utc).date()
            keys: list[str] = []
            for offset in range(max_days):
                day = today - timedelta(days=offset)
                keys.append(day.strftime("%Y-%m-%d"))
            return keys

        if day_key:
            candidate_day_keys = [str(day_key).strip()]
        else:
            candidate_day_keys = _build_recent_day_keys(normalized_limit)

        windows_rows: list[dict[str, Any]] = []
        for dk in candidate_day_keys:
            window_key = f"free:{dk}"
            try:
                win = service.get_window_usage(user_id=str(user_id), window_key=window_key)
            except Exception as exc:
                logger.warning(
                    "[ConvexUsage] Window fallback query failed user=%s day_key=%s window_key=%s err=%s",
                    user_id,
                    dk,
                    window_key,
                    exc,
                )
                continue

            if not isinstance(win, dict):
                continue
            input_tokens = _to_int(win.get("input_tokens"))
            output_tokens = _to_int(win.get("output_tokens"))
            total_tokens = _to_int(win.get("total_tokens")) or (input_tokens + output_tokens)
            if total_tokens <= 0 and input_tokens <= 0 and output_tokens <= 0:
                continue

            updated_at_ms = _to_int(win.get("updated_at_ms"))
            windows_rows.append(
                {
                    "user_id": str(user_id),
                    "day_key": dk,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": total_tokens,
                    "first_event_at_ms": updated_at_ms or None,
                    "last_event_at_ms": updated_at_ms or None,
                    "created_at_ms": updated_at_ms or None,
                    "updated_at_ms": updated_at_ms or None,
                }
            )

        windows_rows = sorted(
            windows_rows,
            key=lambda row: str(row.get("day_key") or ""),
            reverse=True,
        )
        logger.warning(
            "[ConvexUsage] Daily graph source=fallback_usage_windows user=%s rows=%s day_key=%s limit=%s",
            user_id,
            len(windows_rows),
            day_key,
            limit,
        )
        return windows_rows
    except Exception as exc:
        logger.warning("[ConvexUsage] Failed to fetch daily usage for user %s: %s", user_id, exc)
        return []


def get_daily_usage_by_date(day_key: str, limit: int = 500) -> list[dict[str, Any]]:
    service = get_convex_usage_service()
    if not service.is_enabled():
        return []
    try:
        rows = service.get_daily_usage_by_date(day_key=day_key, limit=limit)
        return rows if isinstance(rows, list) else []
    except Exception as exc:
        logger.warning("[ConvexUsage] Failed to fetch daily usage for date %s: %s", day_key, exc)
        return []


def reset_usage_for_new_period(user_id: str) -> None:
    logger.info(
        "[Subscription] Legacy reset_usage_for_new_period called for user %s. No action taken (totals are immutable).",
        user_id,
    )


def _status_grants_paid_access(status: str, current_period_end: Optional[datetime]) -> bool:
    normalized = str(status or "none").strip().lower()
    if normalized in ACCESS_ACTIVE_STATUSES:
        return current_period_end is None or current_period_end > _utc_now()
    if normalized in ACCESS_WINDOW_STATUSES:
        return bool(current_period_end and current_period_end > _utc_now())
    return False


def _incomplete_subscription_grace_seconds() -> int:
    configured = _to_int(getattr(config, "RAZORPAY_INCOMPLETE_SUBSCRIPTION_GRACE_SECONDS", 300))
    return max(0, configured)


def _subscription_age_seconds(subscription_entity: dict[str, Any]) -> Optional[float]:
    created_at = _unix_to_dt(subscription_entity.get("created_at"))
    if not created_at:
        return None
    return max(0.0, (_utc_now() - created_at).total_seconds())


def _looks_like_unpaid_checkout_attempt(subscription_entity: dict[str, Any], status: str) -> bool:
    normalized_status = str(status or "").strip().lower()
    if normalized_status in ABANDONED_CHECKOUT_STATUSES:
        return True
    if normalized_status in {"pending", "halted"}:
        return (
            _to_int(subscription_entity.get("paid_count")) == 0
            and not subscription_entity.get("current_start")
            and not subscription_entity.get("current_end")
        )
    return False


def fetch_razorpay_subscription(subscription_id: str) -> dict[str, Any]:
    if not _razorpay_auth_available():
        raise RuntimeError("Razorpay credentials are not configured.")
    response = requests.get(
        f"{RAZORPAY_API_BASE}/subscriptions/{subscription_id}",
        auth=(config.RAZORPAY_KEY_ID, config.RAZORPAY_KEY_SECRET),
        timeout=30,
    )
    if response.status_code not in (200, 201):
        raise RuntimeError(_extract_error_message(response))
    return response.json() or {}


def cancel_razorpay_subscription(subscription_id: str, cancel_at_cycle_end: bool = False) -> dict[str, Any]:
    if not subscription_id:
        raise ValueError("subscription_id is required.")
    if not _razorpay_auth_available():
        raise RuntimeError("Razorpay credentials are not configured.")

    response = requests.post(
        f"{RAZORPAY_API_BASE}/subscriptions/{subscription_id}/cancel",
        auth=(config.RAZORPAY_KEY_ID, config.RAZORPAY_KEY_SECRET),
        json={"cancel_at_cycle_end": int(bool(cancel_at_cycle_end))},
        timeout=30,
    )
    if response.status_code not in (200, 201):
        raise RuntimeError(_extract_error_message(response))
    return response.json() or {}


def cleanup_incomplete_subscription(user_id: str, subscription_id: str) -> dict[str, Any]:
    subscription_id = str(subscription_id or "").strip()
    if not subscription_id:
        raise ValueError("subscription_id is required.")

    profile = get_profile(user_id)
    entity = fetch_razorpay_subscription(subscription_id)
    notes = entity.get("notes") if isinstance(entity.get("notes"), dict) else {}
    note_user_id = str(notes.get("user_id") or "").strip()
    linked_subscription_id = str(profile.get("razorpay_subscription_id") or "").strip()

    if note_user_id and note_user_id != str(user_id):
        raise ValueError("The Razorpay subscription does not belong to this user.")
    if linked_subscription_id and linked_subscription_id != subscription_id:
        raise ValueError("This Razorpay subscription is not linked to the active profile.")

    status = str(entity.get("status") or "created").strip().lower()
    if not _looks_like_unpaid_checkout_attempt(entity, status):
        return {"subscription": entity, "cleaned": False, "status": status}

    cancelled = entity
    if status in {"created", "pending"}:
        cancelled = cancel_razorpay_subscription(subscription_id, cancel_at_cycle_end=False)

    current_subscription_id = str(profile.get("razorpay_subscription_id") or "").strip()
    if current_subscription_id == subscription_id:
        updated_profile = update_profile(
            user_id,
            {
                "plan_type": "free",
                "subscription_status": "none",
                "razorpay_subscription_id": None,
                "current_period_end": _dt_to_iso(_next_utc_day_boundary()),
            },
        )
        _sync_profile_snapshot_to_convex(user_id, updated_profile)

    return {
        "subscription": cancelled,
        "cleaned": True,
        "status": str(cancelled.get("status") or status).lower(),
    }


def cleanup_profile_incomplete_subscription_if_due(
    user_id: str,
    profile: dict[str, Any],
    *,
    force: bool = False,
) -> dict[str, Any]:
    subscription_id = str(profile.get("razorpay_subscription_id") or "").strip()
    status = str(profile.get("subscription_status") or "none").strip().lower()
    if not subscription_id or status not in INCOMPLETE_SUBSCRIPTION_STATUSES:
        return profile
    if not _razorpay_auth_available():
        return profile

    try:
        entity = fetch_razorpay_subscription(subscription_id)
    except Exception as exc:
        logger.warning("[Subscription] Failed to inspect incomplete subscription %s: %s", subscription_id, exc)
        return profile

    entity_status = str(entity.get("status") or status).strip().lower()
    if entity_status not in INCOMPLETE_SUBSCRIPTION_STATUSES:
        return sync_subscription_state(
            user_id=user_id,
            profile=profile,
            subscription_entity=entity,
            source="incomplete_cleanup_refresh",
        )
    if not _looks_like_unpaid_checkout_attempt(entity, entity_status):
        return profile

    age_seconds = _subscription_age_seconds(entity)
    if not force and age_seconds is not None and age_seconds < _incomplete_subscription_grace_seconds():
        return profile

    try:
        cleanup_incomplete_subscription(user_id, subscription_id)
        return get_profile(user_id)
    except Exception as exc:
        logger.warning("[Subscription] Failed to clean incomplete subscription %s: %s", subscription_id, exc)
        return profile


def update_razorpay_subscription_plan(
    subscription_id: str,
    plan_type: str,
    schedule_change_at: Optional[str] = None,
) -> dict[str, Any]:
    normalized_plan = str(plan_type or "").strip().lower()
    if normalized_plan not in PAID_PLAN_TYPES:
        raise ValueError("Only paid plans can be applied to a Razorpay subscription.")
    if not subscription_id:
        raise ValueError("subscription_id is required.")
    if not _razorpay_auth_available():
        raise RuntimeError("Razorpay credentials are not configured.")

    plan_id = get_plan_id_for_type(normalized_plan)
    if not plan_id:
        raise RuntimeError(f"Missing Razorpay plan id for '{normalized_plan}'.")

    configured_mode = str(
        schedule_change_at
        or config.RAZORPAY_SUBSCRIPTION_CHANGE_MODE
        or "cycle_end"
    ).strip().lower()
    if configured_mode not in {"now", "cycle_end"}:
        configured_mode = "cycle_end"

    payload = {
        "plan_id": plan_id,
        "quantity": 1,
        "schedule_change_at": configured_mode,
        "customer_notify": True,
    }
    response = requests.patch(
        f"{RAZORPAY_API_BASE}/subscriptions/{subscription_id}",
        auth=(config.RAZORPAY_KEY_ID, config.RAZORPAY_KEY_SECRET),
        json=payload,
        timeout=30,
    )
    if response.status_code not in (200, 201):
        raise RuntimeError(_extract_error_message(response))
    return response.json() or {}


def create_razorpay_subscription(user_id: str, email: str, plan_type: str) -> dict[str, Any]:
    normalized_plan = str(plan_type or "").strip().lower()
    if normalized_plan not in PAID_PLAN_TYPES:
        raise ValueError("Only paid plans can create a Razorpay subscription.")
    if not _razorpay_auth_available():
        raise RuntimeError("Razorpay credentials are not configured.")

    plan_id = get_plan_id_for_type(normalized_plan)
    if not plan_id:
        raise RuntimeError(f"Missing Razorpay plan id for '{normalized_plan}'.")

    profile = get_profile(user_id)
    profile = cleanup_profile_incomplete_subscription_if_due(user_id, profile, force=True)
    summary = calculate_usage_summary(user_id, refresh_window=True)
    current_status = str(summary.get("subscription_status") or "none").lower()
    current_subscription_id = summary.get("razorpay_subscription_id")
    current_plan_type = str(summary.get("plan_type") or "free").strip().lower()
    if current_subscription_id and current_status in SUBSCRIPTION_BLOCKING_STATUSES:
        if current_plan_type == normalized_plan:
            raise RuntimeError("This account already has that Razorpay subscription.")
        if current_status not in SUBSCRIPTION_CHANGEABLE_STATUSES:
            raise RuntimeError(
                "This account has a pending Razorpay subscription. Complete or cancel it before changing plans."
            )
        change_type = (
            "upgrade"
            if PLAN_RANK.get(normalized_plan, 0) > PLAN_RANK.get(current_plan_type, 0)
            else "downgrade"
        )
        schedule_change_at = "now" if change_type == "upgrade" else "cycle_end"
        updated_subscription = update_razorpay_subscription_plan(
            subscription_id=str(current_subscription_id),
            plan_type=normalized_plan,
            schedule_change_at=schedule_change_at,
        )
        profile = get_profile(user_id)
        if change_type == "downgrade":
            current_period_end = _unix_to_dt(updated_subscription.get("current_end"))
            updated_profile = update_profile(
                user_id,
                {
                    "plan_type": current_plan_type,
                    "subscription_status": str(updated_subscription.get("status") or current_status),
                    "razorpay_customer_id": updated_subscription.get("customer_id") or profile.get("razorpay_customer_id"),
                    "razorpay_subscription_id": updated_subscription.get("id") or current_subscription_id,
                    "current_period_end": _dt_to_iso(current_period_end) if current_period_end else profile.get("current_period_end"),
                },
            )
            _sync_profile_snapshot_to_convex(user_id, updated_profile)
        else:
            updated_profile = sync_subscription_state(
                user_id=user_id,
                profile=profile,
                subscription_entity=updated_subscription,
                source="subscription_change",
            )
        updated_subscription["_aetheria_change_type"] = change_type
        updated_subscription["_aetheria_schedule_change_at"] = schedule_change_at
        updated_subscription["_aetheria_profile_plan_type"] = updated_profile.get("plan_type")
        return updated_subscription

    payload = {
        "plan_id": plan_id,
        "total_count": _subscription_total_count(),
        "quantity": 1,
        "customer_notify": True,
        "notes": {
            "user_id": str(user_id),
            "email": str(email or ""),
            "plan_type": normalized_plan,
            "app": "aetheria_ai",
        },
    }

    response = requests.post(
        f"{RAZORPAY_API_BASE}/subscriptions",
        auth=(config.RAZORPAY_KEY_ID, config.RAZORPAY_KEY_SECRET),
        json=payload,
        timeout=30,
    )
    if response.status_code not in (200, 201):
        raise RuntimeError(_extract_error_message(response))

    data = response.json() or {}
    if data.get("id"):
        existing_profile = get_profile(user_id)
        updated_profile = update_profile(
            user_id,
            {
                "plan_type": existing_profile.get("plan_type") or "free",
                "subscription_status": str(data.get("status") or "created").strip().lower(),
                "razorpay_customer_id": data.get("customer_id") or existing_profile.get("razorpay_customer_id"),
                "razorpay_subscription_id": data.get("id"),
                "current_period_end": existing_profile.get("current_period_end") or _dt_to_iso(_next_utc_day_boundary()),
            },
        )
        _sync_profile_snapshot_to_convex(user_id, updated_profile)
    return data


def verify_subscription_checkout_signature(
    payment_id: str,
    subscription_id: str,
    signature: str,
) -> None:
    if not config.RAZORPAY_KEY_SECRET:
        raise RuntimeError("Razorpay key secret is not configured.")

    message = f"{payment_id}|{subscription_id}".encode("utf-8")
    expected_signature = hmac.new(
        config.RAZORPAY_KEY_SECRET.encode("utf-8"),
        message,
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected_signature, str(signature or "")):
        raise ValueError("Invalid Razorpay checkout signature.")


def verify_webhook_signature(raw_body: bytes, signature: str) -> None:
    if not config.RAZORPAY_WEBHOOK_SECRET:
        raise RuntimeError("RAZORPAY_WEBHOOK_SECRET is not configured.")
    expected_signature = hmac.new(
        config.RAZORPAY_WEBHOOK_SECRET.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected_signature, str(signature or "")):
        raise ValueError("Invalid Razorpay webhook signature.")


def sync_subscription_state(
    user_id: str,
    profile: dict[str, Any],
    subscription_entity: dict[str, Any],
    source: str,
) -> dict[str, Any]:
    now = _utc_now()
    status = str(subscription_entity.get("status") or "none").strip().lower()
    plan_type = resolve_plan_type_from_plan_id(subscription_entity.get("plan_id"))
    current_period_end = _unix_to_dt(subscription_entity.get("current_end"))
    effective_plan = str(profile.get("plan_type") or "free").strip().lower()

    if plan_type and _status_grants_paid_access(status, current_period_end):
        effective_plan = plan_type
    elif plan_type and status in ACCESS_WINDOW_STATUSES and current_period_end and current_period_end > now:
        effective_plan = plan_type
    elif status in TERMINAL_STATUSES or (current_period_end and current_period_end <= now):
        effective_plan = "free"

    current_subscription_id = str(profile.get("razorpay_subscription_id") or "").strip()
    incoming_subscription_id = str(subscription_entity.get("id") or "").strip()
    if status in NON_ACCESS_STATUSES and current_subscription_id and incoming_subscription_id != current_subscription_id:
        return profile

    update_fields = {
        "plan_type": effective_plan,
        "subscription_status": status,
        "razorpay_customer_id": subscription_entity.get("customer_id"),
        "razorpay_subscription_id": subscription_entity.get("id"),
        "current_period_end": _dt_to_iso(current_period_end) if current_period_end else None,
    }
    updated_profile = update_profile(user_id, update_fields)
    _sync_profile_snapshot_to_convex(user_id, updated_profile)
    return updated_profile


def _refresh_profile_from_razorpay_if_needed(profile: dict[str, Any]) -> dict[str, Any]:
    subscription_id = profile.get("razorpay_subscription_id")
    if not subscription_id or not _razorpay_auth_available():
        return profile

    try:
        entity = fetch_razorpay_subscription(str(subscription_id))
        return sync_subscription_state(
            user_id=str(profile["id"]),
            profile=profile,
            subscription_entity=entity,
            source="razorpay_sync",
        )
    except Exception as exc:
        logger.warning("[Subscription] Failed Razorpay refresh for %s: %s", subscription_id, exc)
        return profile


def ensure_usage_window(user_id: str, profile: dict[str, Any]) -> dict[str, Any]:
    now = _utc_now()
    current_period_end = _parse_dt(profile.get("current_period_end"))
    plan_type = str(profile.get("plan_type") or "free").strip().lower()
    status = str(profile.get("subscription_status") or "none").strip().lower()

    if profile.get("razorpay_subscription_id") and status in INCOMPLETE_SUBSCRIPTION_STATUSES:
        profile = cleanup_profile_incomplete_subscription_if_due(user_id, profile, force=False)
        current_period_end = _parse_dt(profile.get("current_period_end"))
        plan_type = str(profile.get("plan_type") or "free").strip().lower()
        status = str(profile.get("subscription_status") or "none").strip().lower()

    if plan_type in PAID_PLAN_TYPES and current_period_end and current_period_end <= now:
        refreshed = _refresh_profile_from_razorpay_if_needed(profile)
        profile = refreshed or profile
        current_period_end = _parse_dt(profile.get("current_period_end"))
        plan_type = str(profile.get("plan_type") or "free").strip().lower()
        status = str(profile.get("subscription_status") or "none").strip().lower()

    if plan_type == "free":
        if status in NON_ACCESS_STATUSES and not profile.get("razorpay_subscription_id"):
            profile = update_profile(user_id, {"subscription_status": "none"})
            status = "none"
        if not current_period_end or current_period_end <= now:
            profile = update_profile(
                user_id,
                {
                    "plan_type": "free",
                    "current_period_end": _dt_to_iso(_next_utc_day_boundary(now)),
                },
            )
        _sync_profile_snapshot_to_convex(user_id, profile)
        return profile

    if plan_type in PAID_PLAN_TYPES and not _status_grants_paid_access(status, current_period_end):
        profile = update_profile(
            user_id,
            {
                "plan_type": "free",
                "subscription_status": "none" if status in NON_ACCESS_STATUSES else status,
                "razorpay_subscription_id": None if status in NON_ACCESS_STATUSES else profile.get("razorpay_subscription_id"),
                "current_period_end": _dt_to_iso(_next_utc_day_boundary(now)),
            },
        )
        _sync_profile_snapshot_to_convex(user_id, profile)
        return profile

    if plan_type in PAID_PLAN_TYPES and current_period_end and current_period_end <= now:
        profile = update_profile(
            user_id,
            {
                "plan_type": "free",
                "current_period_end": _dt_to_iso(_next_utc_day_boundary(now)),
            },
        )
        _sync_profile_snapshot_to_convex(user_id, profile)
        return profile

    _sync_profile_snapshot_to_convex(user_id, profile)
    return profile


def _build_status_label(plan_type: str, status: str) -> str:
    normalized_status = str(status or "none").strip().lower()
    if plan_type == "free" and normalized_status in {"none", "", *NON_ACCESS_STATUSES}:
        return "Free"
    return normalized_status.replace("_", " ").title()


def calculate_usage_summary(user_id: str, refresh_window: bool = True) -> dict[str, Any]:
    profile = get_profile(user_id)
    if refresh_window:
        profile = ensure_usage_window(user_id, profile)

    usage_window = _resolve_usage_window_from_profile(profile)
    convex_window_usage = _get_convex_window_usage(user_id, str(usage_window.get("window_key")))
    convex_lifetime_usage = _get_convex_lifetime_usage(user_id)

    usage_source = "convex_window" if isinstance(convex_window_usage, dict) else "convex_window_unavailable"
    input_tokens = (
        _to_int(convex_window_usage.get("input_tokens"))
        if isinstance(convex_window_usage, dict)
        else 0
    )
    output_tokens = (
        _to_int(convex_window_usage.get("output_tokens"))
        if isinstance(convex_window_usage, dict)
        else 0
    )
    total_tokens = (
        _to_int(convex_window_usage.get("total_tokens"))
        if isinstance(convex_window_usage, dict)
        else 0
    )
    if total_tokens <= 0:
        total_tokens = input_tokens + output_tokens

    lifetime_input_tokens = (
        _to_int(convex_lifetime_usage.get("input_tokens"))
        if isinstance(convex_lifetime_usage, dict)
        else input_tokens
    )
    lifetime_output_tokens = (
        _to_int(convex_lifetime_usage.get("output_tokens"))
        if isinstance(convex_lifetime_usage, dict)
        else output_tokens
    )
    lifetime_total_tokens = (
        _to_int(convex_lifetime_usage.get("total_tokens"))
        if isinstance(convex_lifetime_usage, dict)
        else total_tokens
    )
    lifetime_created_at = (
        convex_lifetime_usage.get("updated_at_ms")
        if isinstance(convex_lifetime_usage, dict)
        else None
    )

    plan_type = str(profile.get("plan_type") or "free").strip().lower()
    plan = get_plan_config(plan_type)
    limit_tokens = _to_int(plan["limit_tokens"])
    remaining_tokens = max(limit_tokens - total_tokens, 0)
    usage_percent = int(min((total_tokens / limit_tokens) * 100, 100)) if limit_tokens > 0 else 0
    period_end = _parse_dt(usage_window.get("window_end")) or _parse_dt(profile.get("current_period_end"))
    subscription_status = str(profile.get("subscription_status") or "none").strip().lower()
    is_enforceable = usage_source == "convex_window"
    # Pre-live testing bypass:
    # Keep free-plan users effectively unblocked while the app is being tested
    # heavily before launch. When going live, replace this with `limit_tokens`
    # so Core users are capped at the configured 50,000 tokens/day allowance.
    enforcement_limit_tokens = 5_000_000_000 if plan_type == "free" else limit_tokens
    access_locked = bool(is_enforceable and limit_tokens > 0 and total_tokens >= enforcement_limit_tokens)
    warning_threshold = 80
    is_near_limit = bool(is_enforceable and usage_percent >= warning_threshold and not access_locked)
    _sync_profile_snapshot_to_convex(user_id, profile)

    summary = {
        "plan_type": plan_type,
        "plan_name": plan["name"],
        "price_inr": plan["price_inr"],
        "subscription_status": subscription_status,
        "status_label": _build_status_label(plan_type, subscription_status),
        "current_period_end": _dt_to_iso(period_end),
        "period_label": "Current day" if plan_type == "free" else "Current billing cycle",
        "limit_interval": plan["interval_label"],
        "limit_tokens": limit_tokens,
        "limit_label": format_token_limit(limit_tokens, plan["interval_label"]),
        "remaining_tokens": remaining_tokens,
        "usage_percent": usage_percent,
        "is_limit_reached": access_locked,
        "is_near_limit": is_near_limit,
        "warning_threshold_percent": warning_threshold,
        "is_enforceable": is_enforceable,
        "usage_source": usage_source,
        "usage_window": {
            "day_key": usage_window.get("day_key"),
            "window_key": usage_window.get("window_key"),
            "window_start": _dt_to_iso(_parse_dt(usage_window.get("window_start"))),
            "window_end": _dt_to_iso(_parse_dt(usage_window.get("window_end"))),
        },
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
            "created_at": lifetime_created_at,
        },
        "lifetime_usage": {
            "input_tokens": lifetime_input_tokens,
            "output_tokens": lifetime_output_tokens,
            "total_tokens": lifetime_total_tokens,
            "created_at": lifetime_created_at,
        },
        "plans": get_plan_catalog(),
        "profile": {
            "email": profile.get("email"),
            "name": profile.get("name"),
        },
        "razorpay_customer_id": profile.get("razorpay_customer_id"),
        "razorpay_subscription_id": profile.get("razorpay_subscription_id"),
        "can_create_subscription": not (
            profile.get("razorpay_subscription_id")
            and subscription_status in {"authenticated", "active", "pending", "paused", "resumed"}
        ),
    }
    summary["message"] = format_limit_message(summary) if access_locked else None
    summary["warning_message"] = (
        f"{plan['name']} usage is at {usage_percent}% of your {summary['limit_label']} allowance."
        if is_near_limit
        else None
    )
    return summary


def format_limit_message(summary: dict[str, Any]) -> str:
    plan_name = summary.get("plan_name") or "Current"
    limit_label = summary.get("limit_label") or "the allowed usage limit"
    period_end = _parse_dt(summary.get("current_period_end"))
    if period_end:
        reset_text = period_end.astimezone(timezone.utc).strftime("%d %b %Y, %H:%M UTC")
        return f"{plan_name} usage limit reached. Your allowance resets at {reset_text}."
    return f"{plan_name} usage limit reached for {limit_label}."


def enforce_usage_limit(user_id: str) -> dict[str, Any]:
    summary = calculate_usage_summary(user_id, refresh_window=True)
    if summary.get("is_limit_reached"):
        raise UsageLimitExceeded(summary)
    return summary


def verify_checkout_and_activate(
    user_id: str,
    payment_id: str,
    subscription_id: str,
    signature: str,
) -> dict[str, Any]:
    verify_subscription_checkout_signature(payment_id, subscription_id, signature)
    entity = fetch_razorpay_subscription(subscription_id)

    entity_notes = entity.get("notes") or {}
    entity_user_id = str(entity_notes.get("user_id") or "").strip()
    profile = get_profile(user_id)
    linked_subscription_id = str(profile.get("razorpay_subscription_id") or "").strip()
    if entity_user_id and entity_user_id != str(user_id):
        raise ValueError("The Razorpay subscription does not belong to this user.")
    if linked_subscription_id and linked_subscription_id != str(subscription_id):
        raise ValueError("This Razorpay subscription is not linked to the active profile.")

    updated_profile = sync_subscription_state(
        user_id=user_id,
        profile=profile,
        subscription_entity=entity,
        source="checkout_verify",
    )
    summary = calculate_usage_summary(user_id, refresh_window=False)
    return {
        "profile": updated_profile,
        "subscription": entity,
        "summary": summary,
    }


def handle_webhook_event(payload: dict[str, Any]) -> dict[str, Any]:
    event_name = str(payload.get("event") or "").strip()
    subscription_entity = (
        (payload.get("payload") or {})
        .get("subscription", {})
        .get("entity", {})
    ) or {}
    if not subscription_entity:
        raise ValueError("Webhook payload does not contain a subscription entity.")

    subscription_id = str(subscription_entity.get("id") or "").strip()
    notes = subscription_entity.get("notes") or {}
    user_id = str(notes.get("user_id") or "").strip() or find_user_id_by_subscription_id(subscription_id)
    if not user_id:
        raise ValueError("Unable to resolve user for webhook event.")

    profile = get_profile(user_id)
    updated_profile = sync_subscription_state(
        user_id=user_id,
        profile=profile,
        subscription_entity=subscription_entity,
        source=f"webhook:{event_name}",
    )
    return {
        "event": event_name,
        "user_id": user_id,
        "subscription_id": subscription_id,
        "status": updated_profile.get("subscription_status"),
    }


def parse_webhook_body(raw_body: bytes) -> dict[str, Any]:
    try:
        return json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid webhook body.") from exc
