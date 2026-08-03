"""Pure helpers for truthful system-assistant stream finalization."""

from typing import Any, Dict, Iterable


_READ_ONLY_TOOLS = {
    "get_device_state",
    "get_active_app_context",
    "get_visible_ui_text",
    "list_apps",
    "search_notes",
    "get_note",
    "get_travel_estimate",
}

_FAILURE_STATUSES = {
    "error",
    "failed",
    "rejected",
    "unavailable",
    "privacy_blocked",
    "not_completed",
}


def _tool_output(entry: Dict[str, Any]) -> Dict[str, Any]:
    payload = entry.get("payload")
    if not isinstance(payload, dict):
        return {}
    output = payload.get("tool_output")
    return output if isinstance(output, dict) else {}


def build_system_assistant_terminal_message(
    tool_history: Iterable[Dict[str, Any]],
) -> str:
    """
    Build a conservative terminal message only when a tool run produced no
    post-tool model answer. It reports observed tool state and never guesses
    that a message was sent or that an unverified action succeeded.
    """
    history = list(tool_history)
    for entry in reversed(history):
        name = str(entry.get("name") or "").strip()
        if not name or name in _READ_ONLY_TOOLS:
            continue

        output = _tool_output(entry)
        status = str(output.get("status") or "").strip().lower()
        if status in _FAILURE_STATUSES:
            return "I couldn't complete the last device step. Please review the current screen."

        if name == "send_message":
            return "I opened the message composer with your message ready for review."
        if name == "input_text":
            return "I entered the requested text. Please review it before sending."
        if name == "open_app":
            return "I opened the requested app."
        if name in {"set_alarm", "set_timer"}:
            return "I prepared the requested time action. Please review it on screen."
        if name in {"prepare_navigation", "open_navigation"}:
            return "I prepared the requested navigation. Please review it on screen."
        return "I finished the available device steps. Please review the current screen."

    if history:
        return "I finished checking the device."
    return ""
