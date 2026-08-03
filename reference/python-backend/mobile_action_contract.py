"""Versioned contract for Aetheria's Android-only assistant actions.

This module deliberately has no dependency on Flask or Agno so the socket layer,
toolkit, and tests can share the same policy without importing the full backend.
The Android implementation mirrors ``CONTRACT_VERSION`` and rejects commands
from an incompatible contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, FrozenSet


CONTRACT_VERSION = 2
COMMAND_TTL_SECONDS = 60
REQUEST_BINDING_TTL_SECONDS = 90
BRIDGE_REGISTRATION_TTL_SECONDS = 60 * 60 * 6


@dataclass(frozen=True)
class MobileActionSpec:
    risk: str
    mutates_device: bool
    confirmation: str
    description: str


ACTION_SPECS: Dict[str, MobileActionSpec] = {
    "get_device_state": MobileActionSpec("read", False, "none", "Read device status"),
    "get_active_app_context": MobileActionSpec("sensitive_read", False, "none", "Read the foreground app context"),
    "get_visible_ui_text": MobileActionSpec("sensitive_read", False, "none", "Read redacted visible interface text"),
    "list_apps": MobileActionSpec("read", False, "none", "List launchable apps"),
    "open_app": MobileActionSpec("low", True, "none", "Open an installed app"),
    "open_settings": MobileActionSpec("low", True, "none", "Open an Android settings screen"),
    "act_settings": MobileActionSpec("medium", True, "native", "Change a device setting"),
    "modify_settings": MobileActionSpec("medium", True, "native", "Change a numeric device setting"),
    "open_notifications": MobileActionSpec("low", True, "none", "Open notifications"),
    "open_quick_settings": MobileActionSpec("low", True, "none", "Open quick settings"),
    "open_recents": MobileActionSpec("low", True, "none", "Open recent apps"),
    "ensure_location_enabled": MobileActionSpec("low", True, "none", "Check location and open settings when needed"),
    "get_travel_estimate": MobileActionSpec("read", False, "none", "Estimate travel time"),
    "prepare_navigation": MobileActionSpec("low", True, "none", "Prepare a navigation route"),
    "open_navigation": MobileActionSpec("medium", True, "native", "Open turn-by-turn navigation"),
    "set_alarm": MobileActionSpec("medium", True, "native", "Create an alarm"),
    "set_timer": MobileActionSpec("medium", True, "native", "Create a timer"),
    "create_note": MobileActionSpec("low", True, "none", "Create an assistant note"),
    "append_note": MobileActionSpec("low", True, "none", "Append to an assistant note"),
    "search_notes": MobileActionSpec("sensitive_read", False, "none", "Search assistant notes"),
    "get_note": MobileActionSpec("sensitive_read", False, "none", "Read an assistant note"),
    "send_message": MobileActionSpec("high", True, "native", "Open a message composer with a prepared message"),
    "tap_text": MobileActionSpec("medium", True, "conditional", "Activate a visible interface control"),
    "input_text": MobileActionSpec("medium", True, "conditional", "Enter text into the focused field"),
    "tap": MobileActionSpec("medium", True, "conditional", "Tap screen coordinates"),
    "swipe": MobileActionSpec("low", True, "none", "Swipe on screen"),
    "press_back": MobileActionSpec("low", True, "none", "Navigate back one screen"),
}

EXPOSED_ACTIONS: FrozenSet[str] = frozenset(ACTION_SPECS)


def get_action_spec(action: str) -> MobileActionSpec | None:
    return ACTION_SPECS.get(str(action or "").strip())
