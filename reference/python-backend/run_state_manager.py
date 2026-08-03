# python-backend/run_state_manager.py
#
# Manages per-conversation run state in Redis.
# States: "running" | "completed" | "failed"
#
# This decouples the agent lifecycle from the WebSocket SID, so that:
#  - The frontend can poll or listen for state after a reconnect.
#  - The backend never emits to a dead SID room, always uses conv room.
#  - On reconnect, the client knows whether a run is still in-progress.

import json
import logging
import time
from typing import Optional, Dict, Any
from redis import Redis

logger = logging.getLogger(__name__)

# Redis key namespaces
RUN_STATE_PREFIX = "run_state:"        # run_state:{conversation_id}
RUN_RESULT_PREFIX = "run_result:"      # run_result:{conversation_id}

# TTL values
STATE_TTL   = 7200   # 2 hours — matches session TTL
RESULT_TTL  = 86400  # 24 hours — completed responses kept longer for catch-up


class RunStateManager:
    """
    Thin wrapper around Redis for tracking agent run state per conversation.
    All methods are synchronous (called from eventlet greenlets).
    """

    def __init__(self, redis_client: Redis):
        self.redis = redis_client

    # ------------------------------------------------------------------ #
    # STATE MANAGEMENT                                                     #
    # ------------------------------------------------------------------ #

    def start_run(self, conversation_id: str, message_id: str, user_id: str) -> None:
        """Mark a run as 'running' in Redis."""
        state = {
            "status": "running",
            "message_id": message_id,
            "user_id": user_id,
            "started_at": time.time(),
            "updated_at": time.time(),
        }
        key = f"{RUN_STATE_PREFIX}{conversation_id}"
        self.redis.set(key, json.dumps(state), ex=STATE_TTL)
        logger.info(f"[RunState] Started run for conv={conversation_id} msg={message_id}")

    def complete_run(
        self,
        conversation_id: str,
        message_id: str,
        final_content: Optional[str] = None,
        events: Optional[list] = None,
        conversation_title: Optional[str] = None,
    ) -> None:
        """Mark a run as 'completed' and persist structured catch-up payload."""
        previous_state = self.get_state(conversation_id) or {}
        state = {
            "status": "completed",
            "message_id": message_id,
            "user_id": previous_state.get("user_id"),
            "updated_at": time.time(),
        }
        key = f"{RUN_STATE_PREFIX}{conversation_id}"
        self.redis.set(key, json.dumps(state), ex=STATE_TTL)

        # Persist the final response and structured replay events for catch-up.
        if final_content or events:
            result = {
                "status": "completed",
                "message_id": message_id,
                "content": final_content,
                "events": events or [],
                "title": conversation_title,
                "completed_at": time.time(),
            }
            result_key = f"{RUN_RESULT_PREFIX}{conversation_id}"
            self.redis.set(result_key, json.dumps(result), ex=RESULT_TTL)

        logger.info(f"[RunState] Completed run for conv={conversation_id}")

    def fail_run(self, conversation_id: str, message_id: str, error: str) -> None:
        """Mark a run as 'failed' and store the error."""
        previous_state = self.get_state(conversation_id) or {}
        state = {
            "status": "failed",
            "message_id": message_id,
            "user_id": previous_state.get("user_id"),
            "error": error,
            "updated_at": time.time(),
        }
        key = f"{RUN_STATE_PREFIX}{conversation_id}"
        self.redis.set(key, json.dumps(state), ex=STATE_TTL)

        result = {
            "status": "failed",
            "message_id": message_id,
            "error": error,
            "failed_at": time.time(),
        }
        result_key = f"{RUN_RESULT_PREFIX}{conversation_id}"
        self.redis.set(result_key, json.dumps(result), ex=RESULT_TTL)

        logger.info(f"[RunState] Failed run for conv={conversation_id}: {error}")

    # ------------------------------------------------------------------ #
    # QUERIES                                                              #
    # ------------------------------------------------------------------ #

    def get_state(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        """Return current run state dict, or None if no run is tracked."""
        key = f"{RUN_STATE_PREFIX}{conversation_id}"
        raw = self.redis.get(key)
        if not raw:
            return None
        try:
            return json.loads(raw)
        except Exception:
            return None

    def get_result(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        """Return the stored run result (for catch-up on reconnect)."""
        key = f"{RUN_RESULT_PREFIX}{conversation_id}"
        raw = self.redis.get(key)
        if not raw:
            return None
        try:
            return json.loads(raw)
        except Exception:
            return None

    def is_running(self, conversation_id: str) -> bool:
        state = self.get_state(conversation_id)
        return bool(state and state.get("status") == "running")

    def clear(self, conversation_id: str) -> None:
        """Remove all run state for a conversation (e.g. on new conversation)."""
        self.redis.delete(f"{RUN_STATE_PREFIX}{conversation_id}")
        self.redis.delete(f"{RUN_RESULT_PREFIX}{conversation_id}")
