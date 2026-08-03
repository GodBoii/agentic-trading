import hmac
import re
from typing import Any, Dict, Optional


def _safe_log_identifier(value: Any) -> Optional[str]:
    if value is None:
        return None
    cleaned = re.sub(r"[^A-Za-z0-9._:-]", "_", str(value).strip())
    return cleaned[:128] or None


def safe_socket_message_metadata(data: Any) -> Dict[str, Any]:
    payload = data if isinstance(data, dict) else {}
    message = payload.get("message")
    message_length = len(message) if isinstance(message, str) else 0
    return {
        "conversation_id": _safe_log_identifier(
            payload.get("conversationId") or payload.get("session_id")
        ),
        "message_id": _safe_log_identifier(payload.get("id")),
        "message_length": message_length,
        "has_access_token": bool(payload.get("accessToken")),
    }


def get_conversation_owner(
    conversation_id: str,
    connection_manager: Any,
    run_state_manager: Any,
) -> Optional[str]:
    if connection_manager is not None:
        session = connection_manager.get_session(conversation_id)
        if isinstance(session, dict) and session.get("user_id"):
            return str(session["user_id"])

    if run_state_manager is not None:
        state = run_state_manager.get_state(conversation_id)
        if isinstance(state, dict) and state.get("user_id"):
            return str(state["user_id"])

    return None


def can_access_conversation(
    user_id: str,
    conversation_id: str,
    connection_manager: Any,
    run_state_manager: Any,
    *,
    allow_unowned: bool = False,
) -> bool:
    owner = get_conversation_owner(
        conversation_id,
        connection_manager,
        run_state_manager,
    )
    if owner is None:
        return allow_unowned
    return hmac.compare_digest(owner, str(user_id))
