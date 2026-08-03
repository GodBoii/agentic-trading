# python-backend/mobile_tools.py
#
# Mobile command toolkit for native Android assistant integration.
# Uses Socket.IO + Redis Pub/Sub request/response bridging.

import json
import logging
import time
import uuid
from typing import Any, Dict

from redis import Redis

from agno.tools import Toolkit
from agno.tools.function import ToolResult

logger = logging.getLogger(__name__)

MOBILE_COMMAND_TIMEOUT_SECONDS = 35


class MobileTools(Toolkit):
    """
    Toolkit that sends mobile commands to a connected native assistant client.
    """

    def __init__(
        self,
        sid: str,
        socketio,
        redis_client: Redis,
        conversation_id: str | None = None,
        message_id: str | None = None,
        **kwargs,
    ):
        self.sid = sid
        self.socketio = socketio
        self.redis_client = redis_client
        self.conversation_id = conversation_id
        self.message_id = message_id

        super().__init__(
            name="mobile_tools",
            tools=[
                self.get_device_state,
                self.get_active_app_context,
                self.list_apps,
                self.open_app,
                self.act_settings,
                self.modify_settings,
                self.ensure_location_enabled,
                self.set_alarm,
                self.set_timer,
                self.create_note,
                self.append_note,
                self.search_notes,
                self.get_note,
                self.send_message,
                self.open_settings,
                self.open_notifications,
                self.open_quick_settings,
                self.open_recents,
                self.tap_text,
                self.input_text,
                self.tap,
                self.swipe,
                self.press_back,
            ],
            **kwargs,
        )

    def _send_command_and_wait(self, command_payload: Dict[str, Any]) -> ToolResult:
        request_id = str(uuid.uuid4())
        command_payload["request_id"] = request_id
        if self.conversation_id:
            command_payload["conversation_id"] = self.conversation_id
        if self.message_id:
            command_payload["message_id"] = self.message_id

        response_channel = f"mobile-response:{request_id}"
        pubsub = self.redis_client.pubsub()

        try:
            pubsub.subscribe(response_channel)
            self.socketio.emit("mobile-command", command_payload, room=self.sid)
            logger.info(
                "MobileTools emitted action=%s request_id=%s sid=%s",
                command_payload.get("action"),
                request_id,
                self.sid,
            )

            started = time.time()
            while time.time() - started < MOBILE_COMMAND_TIMEOUT_SECONDS:
                message = pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if not message:
                    continue

                raw_data = message.get("data")
                if raw_data is None:
                    continue

                if isinstance(raw_data, bytes):
                    raw_data = raw_data.decode("utf-8", errors="replace")

                try:
                    result = json.loads(raw_data)
                except Exception:
                    result = {
                        "status": "error",
                        "error": "Invalid mobile command response payload",
                        "raw": str(raw_data),
                    }

                return ToolResult(content=json.dumps(result))

            timeout_result = {
                "status": "error",
                "error": "Mobile command timed out waiting for native assistant bridge.",
            }
            return ToolResult(content=json.dumps(timeout_result))
        except Exception as e:
            logger.error("MobileTools command bridge error: %s", e)
            return ToolResult(content=json.dumps({"status": "error", "error": str(e)}))
        finally:
            try:
                pubsub.unsubscribe(response_channel)
            except Exception:
                pass
            try:
                pubsub.close()
            except Exception:
                pass

    def get_device_state(self) -> ToolResult:
        """
        Returns practical device state including foreground app context.
        """
        return self._send_command_and_wait({"action": "get_device_state"})

    def get_active_app_context(self) -> ToolResult:
        """
        Returns best-effort active app/window context and visible text.
        """
        return self._send_command_and_wait({"action": "get_active_app_context"})

    def get_visible_ui_text(self, limit: int = 16) -> ToolResult:
        """
        Returns visible UI text from the current foreground app.
        """
        return self._send_command_and_wait(
            {"action": "get_visible_ui_text", "limit": max(4, min(limit, 40))}
        )

    def list_apps(self, query: str = "", limit: int = 12) -> ToolResult:
        """
        Lists launchable installed apps, optionally filtered by query.
        """
        return self._send_command_and_wait(
            {
                "action": "list_apps",
                "query": query,
                "limit": max(1, min(limit, 40)),
            }
        )

    def open_app(self, app_name_or_package: str) -> ToolResult:
        """
        Opens an app by natural name or package name.
        Example: "YouTube", "WhatsApp", "com.whatsapp".
        """
        return self._send_command_and_wait(
            {"action": "open_app", "query": app_name_or_package}
        )

    def ensure_location_enabled(self) -> ToolResult:
        """
        Checks location status and opens location settings if disabled.
        """
        return self._send_command_and_wait({"action": "ensure_location_enabled"})

    def set_alarm(
        self,
        hour: int,
        minute: int,
        label: str = "",
        skip_ui: bool = False,
    ) -> ToolResult:
        """
        Sets an alarm in device clock app.
        """
        return self._send_command_and_wait(
            {
                "action": "set_alarm",
                "hour": hour,
                "minute": minute,
                "label": label,
                "skip_ui": bool(skip_ui),
            }
        )

    def set_timer(
        self,
        duration_seconds: int,
        label: str = "",
        skip_ui: bool = False,
    ) -> ToolResult:
        """
        Sets a countdown timer in device clock app.
        """
        return self._send_command_and_wait(
            {
                "action": "set_timer",
                "duration_seconds": duration_seconds,
                "label": label,
                "skip_ui": bool(skip_ui),
            }
        )

    def create_note(self, content: str, title: str = "") -> ToolResult:
        """
        Creates a local assistant note.
        """
        return self._send_command_and_wait(
            {
                "action": "create_note",
                "title": title,
                "content": content,
            }
        )

    def append_note(self, note_id: str, content: str) -> ToolResult:
        """
        Appends text to an existing note by note_id.
        """
        return self._send_command_and_wait(
            {
                "action": "append_note",
                "note_id": note_id,
                "content": content,
            }
        )

    def search_notes(self, query: str, limit: int = 8) -> ToolResult:
        """
        Searches local assistant notes.
        """
        return self._send_command_and_wait(
            {
                "action": "search_notes",
                "query": query,
                "limit": max(1, min(limit, 30)),
            }
        )

    def get_note(self, note_id: str = "", title: str = "") -> ToolResult:
        """
        Returns a full note by id or title.
        """
        return self._send_command_and_wait(
            {
                "action": "get_note",
                "note_id": note_id,
                "title": title,
            }
        )

    def send_message(
        self,
        channel: str,
        recipient: str,
        message: str,
        subject: str = "",
    ) -> ToolResult:
        """
        Opens compose/send flow for sms, whatsapp, email, telegram, instagram.
        """
        return self._send_command_and_wait(
            {
                "action": "send_message",
                "channel": channel,
                "recipient": recipient,
                "message": message,
                "subject": subject,
            }
        )

    def open_settings(self, setting: str = "general") -> ToolResult:
        """
        Opens a settings screen. Supported values:
        general, wifi, bluetooth, accessibility, apps, sound, display, location.
        """
        return self._send_command_and_wait(
            {"action": "open_settings", "setting": setting}
        )

    def act_settings(self, setting: str, enabled: bool) -> ToolResult:
        """
        Toggles a setting with on/off state (best effort on Android 15/16 policies).
        Example settings: wifi, bluetooth, location, mobile_data, hotspot, auto_rotate, dnd.
        """
        return self._send_command_and_wait(
            {
                "action": "act_settings",
                "setting": (setting or "").strip().lower(),
                "enabled": bool(enabled),
            }
        )

    def modify_settings(self, setting: str, value: int) -> ToolResult:
        """
        Modifies settings that require numeric value.
        Example settings: media_volume, ring_volume, alarm_volume, brightness, dnd_filter.
        """
        return self._send_command_and_wait(
            {
                "action": "modify_settings",
                "setting": (setting or "").strip().lower(),
                "value": int(value),
            }
        )

    def open_notifications(self) -> ToolResult:
        """
        Opens the notifications shade.
        """
        return self._send_command_and_wait({"action": "open_notifications"})

    def open_quick_settings(self) -> ToolResult:
        """
        Opens quick settings panel.
        """
        return self._send_command_and_wait({"action": "open_quick_settings"})

    def open_recents(self) -> ToolResult:
        """
        Opens Android recent apps view.
        """
        return self._send_command_and_wait({"action": "open_recents"})

    def tap_text(self, text: str, partial_match: bool = True) -> ToolResult:
        """
        Clicks a visible UI element by text/content description.
        """
        return self._send_command_and_wait(
            {
                "action": "tap_text",
                "text": text,
                "partial_match": bool(partial_match),
            }
        )

    def input_text(self, text: str) -> ToolResult:
        """
        Types text into currently focused input field.
        """
        return self._send_command_and_wait({"action": "input_text", "text": text})

    def tap(self, x: int, y: int, duration_ms: int = 80) -> ToolResult:
        """
        Performs a tap gesture at absolute screen coordinates.
        """
        return self._send_command_and_wait(
            {"action": "tap", "x": x, "y": y, "duration_ms": duration_ms}
        )

    def swipe(
        self,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        duration_ms: int = 280,
    ) -> ToolResult:
        """
        Performs a swipe gesture using absolute screen coordinates.
        """
        return self._send_command_and_wait(
            {
                "action": "swipe",
                "start_x": start_x,
                "start_y": start_y,
                "end_x": end_x,
                "end_y": end_y,
                "duration_ms": duration_ms,
            }
        )

    def press_back(self) -> ToolResult:
        """
        Performs Android global BACK action.
        """
        return self._send_command_and_wait({"action": "press_back"})
