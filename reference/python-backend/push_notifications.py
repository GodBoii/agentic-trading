import json
import logging
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List

import config
from supabase_client import supabase_client

try:
    import firebase_admin
    from firebase_admin import credentials, messaging
except Exception:  # pragma: no cover - handled at runtime if dependency is missing
    firebase_admin = None
    credentials = None
    messaging = None

logger = logging.getLogger(__name__)

PUSH_TOKEN_TABLE = "user_push_tokens"


def _utc_iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class PushNotificationService:
    def __init__(self) -> None:
        self._app = None
        self._init_attempted = False
        self._lock = threading.Lock()

    def enabled(self) -> bool:
        return bool(config.FCM_ENABLED)

    def _get_or_init_app(self):
        if not self.enabled():
            return None
        if firebase_admin is None or credentials is None or messaging is None:
            logger.warning("FCM is enabled but firebase-admin is not installed.")
            return None

        if self._app is not None:
            return self._app

        with self._lock:
            if self._app is not None:
                return self._app
            if self._init_attempted:
                return None
            self._init_attempted = True

            try:
                cred_obj = None
                if config.FIREBASE_SERVICE_ACCOUNT_JSON:
                    cred_dict = json.loads(config.FIREBASE_SERVICE_ACCOUNT_JSON)
                    cred_obj = credentials.Certificate(cred_dict)
                elif config.FIREBASE_SERVICE_ACCOUNT_PATH:
                    cred_obj = credentials.Certificate(config.FIREBASE_SERVICE_ACCOUNT_PATH)
                else:
                    logger.warning(
                        "FCM disabled at runtime: set FIREBASE_SERVICE_ACCOUNT_PATH or FIREBASE_SERVICE_ACCOUNT_JSON."
                    )
                    return None

                try:
                    self._app = firebase_admin.get_app()
                except ValueError:
                    self._app = firebase_admin.initialize_app(cred_obj)

                logger.info("Firebase app initialized for FCM push delivery.")
                return self._app
            except Exception as e:
                logger.error("Failed to initialize Firebase app: %s", e, exc_info=True)
                return None

    def upsert_device_token(
        self,
        *,
        user_id: str,
        device_id: str,
        fcm_token: str,
        platform: str = "android",
        app_version: str | None = None,
    ) -> bool:
        token = (fcm_token or "").strip()
        if not user_id or not device_id or not token:
            return False

        payload = {
            "user_id": str(user_id),
            "device_id": str(device_id),
            "platform": str(platform or "android"),
            "fcm_token": token,
            "is_active": True,
            "app_version": app_version,
            "last_seen_at": _utc_iso_now(),
            "updated_at": _utc_iso_now(),
        }

        try:
            supabase_client.table(PUSH_TOKEN_TABLE).upsert(
                payload,
                on_conflict="user_id,device_id,platform",
            ).execute()
            return True
        except Exception as e:
            logger.error("Failed to upsert FCM token for user=%s: %s", user_id, e, exc_info=True)
            return False

    def deactivate_device_token(self, *, fcm_token: str, platform: str = "android") -> None:
        token = (fcm_token or "").strip()
        if not token:
            return
        try:
            supabase_client.table(PUSH_TOKEN_TABLE).update(
                {
                    "is_active": False,
                    "updated_at": _utc_iso_now(),
                }
            ).eq("fcm_token", token).eq("platform", platform).execute()
        except Exception as e:
            logger.warning("Failed to deactivate stale FCM token: %s", e)

    def _list_active_tokens(self, *, user_id: str, platform: str = "android") -> List[str]:
        try:
            response = (
                supabase_client
                .table(PUSH_TOKEN_TABLE)
                .select("fcm_token")
                .eq("user_id", str(user_id))
                .eq("platform", platform)
                .eq("is_active", True)
                .execute()
            )
        except Exception as e:
            logger.error("Failed to fetch push tokens for user=%s: %s", user_id, e, exc_info=True)
            return []

        rows = response.data or []
        unique_tokens = []
        seen = set()
        for row in rows:
            token = str((row or {}).get("fcm_token") or "").strip()
            if token and token not in seen:
                seen.add(token)
                unique_tokens.append(token)
        return unique_tokens

    def send_to_user(
        self,
        *,
        user_id: str,
        title: str,
        body: str,
        data: Dict[str, Any] | None = None,
        platform: str = "android",
    ) -> bool:
        app = self._get_or_init_app()
        if app is None:
            return False

        tokens = self._list_active_tokens(user_id=user_id, platform=platform)
        if not tokens:
            return True

        payload_data = {k: str(v) for k, v in (data or {}).items() if v is not None}
        try:
            message = messaging.MulticastMessage(
                tokens=tokens,
                notification=messaging.Notification(title=title, body=body),
                data=payload_data,
                android=messaging.AndroidConfig(
                    priority="high",
                    notification=messaging.AndroidNotification(
                        channel_id=config.FCM_ANDROID_CHANNEL_ID,
                        click_action="FCM_PLUGIN_ACTIVITY",
                        sound="default",
                    ),
                ),
            )
            response = messaging.send_each_for_multicast(message, app=app)
        except Exception as e:
            logger.error("FCM send failed for user=%s: %s", user_id, e, exc_info=True)
            return False

        stale_tokens: List[str] = []
        for idx, result in enumerate(response.responses):
            if result.success:
                continue
            token = tokens[idx]
            exc = result.exception
            code = str(getattr(exc, "code", "") or "").lower()
            msg = str(exc or "").lower()
            name = exc.__class__.__name__.lower() if exc else ""
            if (
                "unregistered" in code
                or "registration-token-not-registered" in code
                or "invalid-argument" in code
                or "unregistered" in name
                or "invalid" in name
                or "registration-token-not-registered" in msg
            ):
                stale_tokens.append(token)

        for stale_token in set(stale_tokens):
            self.deactivate_device_token(fcm_token=stale_token, platform=platform)

        logger.info(
            "FCM send summary user=%s sent=%s success=%s failed=%s",
            user_id,
            len(tokens),
            response.success_count,
            response.failure_count,
        )
        return response.success_count > 0

    @staticmethod
    def _normalize_title(title_hint: str | None) -> str:
        normalized = (title_hint or "").strip()
        if not normalized:
            return "AI task"
        return normalized[:64]

    def notify_run_started(self, *, user_id: str, conversation_id: str, title_hint: str | None = None) -> bool:
        task_title = self._normalize_title(title_hint)
        return self.send_to_user(
            user_id=user_id,
            title="Aetheria AI",
            body=f'Your "{task_title}" task is running in background',
            data={
                "type": "run_started",
                "conversationId": conversation_id,
                "title": task_title,
            },
            platform="android",
        )

    def notify_run_completed(self, *, user_id: str, conversation_id: str, title_hint: str | None = None) -> bool:
        task_title = self._normalize_title(title_hint)
        return self.send_to_user(
            user_id=user_id,
            title="Aetheria AI",
            body=f'Your "{task_title}" task is completed',
            data={
                "type": "run_completed",
                "conversationId": conversation_id,
                "title": task_title,
            },
            platform="android",
        )


push_notification_service = PushNotificationService()

