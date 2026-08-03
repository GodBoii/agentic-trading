# python-backend/sockets.py
#
# Manages all Socket.IO event handlers.
#
# KEY ARCHITECTURE CHANGE (Queued-Run System):
#   - Every send_message NOW joins the socket into a conversation room
#     named "conv:{conversation_id}".
#   - agent_runner emits to that room (not the ephemeral SID).
#   - On reconnect, the client sends "join_conversation" to rejoin the room
#     and receive the current run state / catch-up result.
#   - RunStateManager tracks: running | completed | failed in Redis.

import logging
import json
import uuid
import traceback
from typing import Dict, Any
from redis import Redis

import eventlet
from flask import request
from flask_socketio import join_room
from gotrue.errors import AuthApiError

import config
from extensions import socketio
from supabase_client import supabase_client
from session_service import ConnectionManager
from agent_runner import run_agent_and_stream
from plan_agent import stream_plan
from title_generator import generate_and_save_title
from run_state_manager import RunStateManager
from subscription_service import UsageLimitExceeded, enforce_usage_limit
from cache_manager import CacheManager
from socket_security import can_access_conversation, safe_socket_message_metadata
from utils import get_user_from_jwt

logger = logging.getLogger(__name__)

# --- Dependency Injection Placeholders ---
connection_manager_service: ConnectionManager = None
redis_client_instance: Redis = None
run_state_manager_instance: RunStateManager = None

# SID × conversation dedup — prevents sending run_catchup twice to the same
# socket if the client calls join_conversation more than once per session.
# Key: (sid, conversation_id)   Value: True
_catchup_sent: dict = {}
_socket_auth_tokens: dict = {}


def _normalize_agent_mode(raw_value: Any) -> str:
    value = str(raw_value or "").strip().lower()
    if value == "coder":
        return "coder"
    if value == "computer":
        return "computer"
    if value == "system-assistant":
        return "system-assistant"
    return "default"


def _normalize_coder_execution_target(raw_value: Any) -> str:
    value = str(raw_value or "").strip().lower()
    if value == "local":
        return "local"
    return "cloud"


def _sanitize_tool_config_for_user(config_data: Dict[str, Any], user_id: str) -> Dict[str, Any]:
    """
    Keep frontend tool toggles aligned with the user's actual connected services.

    The desktop client may optimistically send enabled integration flags before
    its async connection-status refresh completes. The backend is the source of
    truth, so enabled third-party tools must be gated by stored integrations.
    """
    sanitized = dict(config_data or {})

    try:
        response = (
            supabase_client.from_("user_integrations")
            .select("service")
            .eq("user_id", str(user_id))
            .execute()
        )
        connected_services = {
            str(item.get("service", "")).strip().lower()
            for item in (response.data or [])
            if item.get("service")
        }
    except Exception as exc:
        logger.warning("Failed to fetch connected integrations for user %s: %s", user_id, exc)
        connected_services = set()

    service_gates = {
        "enable_github": "github",
        "enable_vercel": "vercel",
        "enable_supabase": "supabase",
        "enable_google_email": "google",
        "enable_google_drive": "google",
        "enable_google_sheets": "google",
    }
    for flag, service in service_gates.items():
        if flag in sanitized:
            sanitized[flag] = bool(sanitized.get(flag)) and service in connected_services

    if "enable_composio_whatsapp" in sanitized and sanitized.get("enable_composio_whatsapp"):
        try:
            from composio_tools import has_active_whatsapp_connection

            sanitized["enable_composio_whatsapp"] = has_active_whatsapp_connection(str(user_id))
        except Exception as exc:
            logger.warning("Failed to verify WhatsApp integration for user %s: %s", user_id, exc)
            sanitized["enable_composio_whatsapp"] = False

    return sanitized


def _sanitize_plan_config(config_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Plan Mode is read-only and must not touch integration/database state.

    Keep only client-provided boolean capability hints so the plan agent can
    reason about likely routing without querying user_integrations or loading
    any database-backed toolkits.
    """
    allowed_flags = {
        "internet_search",
        "coding_assistant",
        "enable_github",
        "enable_vercel",
        "enable_supabase",
        "enable_google_email",
        "enable_google_drive",
        "enable_google_sheets",
        "enable_composio_whatsapp",
        "enable_computer_control",
    }
    return {
        key: bool(value)
        for key, value in (config_data or {}).items()
        if key in allowed_flags and isinstance(value, bool)
    }


# FUNCTION DESCRIPTION:
# Injects core database, session state, and execution state services from the Flask application factory.
# UPSTREAM CALLER:
# - Called by `create_app()` in `python-backend/factory.py` during startup initialization.
# DOWNSTREAM IMPACT:
# - Binds global instances used across all event handlers in this module (`connection_manager_service`, `redis_client_instance`, `run_state_manager_instance`).
# - Launches the asynchronous screenshot listener thread `listen_for_browser_screenshots`.
def set_dependencies(manager: ConnectionManager, redis_client: Redis, run_state_mgr: RunStateManager):
    """A setter function to inject dependencies from the factory."""
    global connection_manager_service, redis_client_instance, run_state_manager_instance
    connection_manager_service = manager
    redis_client_instance = redis_client
    run_state_manager_instance = run_state_mgr
    logger.info("Dependencies (ConnectionManager, RedisClient, RunStateManager) injected into sockets module.")

    # Start browser screenshot listener
    if redis_client_instance:
        eventlet.spawn(listen_for_browser_screenshots)


def listen_for_browser_screenshots():
    """Listen for browser screenshot events from Redis and forward to frontend."""
    if not redis_client_instance:
        logger.error("[Browser Screenshot] Redis client not available")
        return

    try:
        pubsub = redis_client_instance.pubsub()
        pubsub.psubscribe('browser-screenshot:*')
        logger.info("[Browser Screenshot] Listener started, subscribed to browser-screenshot:*")

        while True:
            try:
                message = pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if message and message.get('type') == 'pmessage':
                    try:
                        data = json.loads(message['data'])
                        channel = message['channel']
                        if isinstance(channel, bytes):
                            channel = channel.decode('utf-8')
                        session_id = channel.split(':')[1]
                        logger.info(f"[Browser Screenshot] Received event for session {session_id}: {data.get('action')}")
                        socketio.emit('browser_screenshot', data, room=f"conv:{session_id}")
                    except Exception as e:
                        logger.error(f"[Browser Screenshot] Error processing message payload: {e}")
            except Exception as loop_e:
                if "Timeout" not in str(type(loop_e)) and "Timeout" not in str(loop_e):
                    logger.error(f"[Browser Screenshot] Error in listener loop: {loop_e}")

            eventlet.sleep(0.01)

    except Exception as e:
        logger.error(f"[Browser Screenshot] Listener fatal error: {e}\n{traceback.format_exc()}")


# ==============================================================================
# SOCKET.IO EVENT HANDLERS
# ==============================================================================

@socketio.on("connect")
def on_connect(auth=None):
    sid = request.sid
    token = None
    if isinstance(auth, dict):
        token = auth.get("token")
    if token:
        _socket_auth_tokens[sid] = token
    logger.info(f"Client connected: {sid}")
    socketio.emit("status", {"message": "Connected to server"}, room=request.sid)


@socketio.on("disconnect")
def on_disconnect():
    sid = request.sid
    logger.info(f"Client disconnected: {sid}")
    # Clear all dedup entries for this SID so next reconnect works cleanly
    to_remove = [k for k in _catchup_sent if k[0] == sid]
    for k in to_remove:
        del _catchup_sent[k]
    _socket_auth_tokens.pop(sid, None)


@socketio.on("join_conversation")
def on_join_conversation(data: Dict[str, Any]):
    """
    Called by the client on connect/reconnect to re-subscribe to a conversation room.
    If a run was completed while the client was away, the catch-up result is sent
    directly to this SID so the client can render the finished response.
    """
    sid = request.sid
    conversation_id = data.get("conversationId") if isinstance(data, dict) else None
    if not conversation_id:
        return

    access_token = data.get("accessToken") or _socket_auth_tokens.get(sid)
    if not access_token:
        logger.warning("[Join] Rejected unauthenticated room join for SID %s", sid)
        return socketio.emit(
            "error",
            {"message": "Authentication is required to join a conversation."},
            room=sid,
        )

    user, auth_error = get_user_from_jwt(access_token)
    if auth_error:
        logger.warning("[Join] Rejected invalid authentication for SID %s", sid)
        return socketio.emit(
            "error",
            {"message": auth_error[0]},
            room=sid,
        )

    if not can_access_conversation(
        str(user.id),
        conversation_id,
        connection_manager_service,
        run_state_manager_instance,
    ):
        logger.warning(
            "[Join] Rejected unauthorized or unknown conversation for SID %s",
            sid,
        )
        return

    room_name = f"conv:{conversation_id}"
    join_room(room_name)
    logger.info(f"[Join] SID {sid} joined room {room_name}")

    if not run_state_manager_instance:
        return

    # Check current run state and send catch-up data to this specific socket
    state = run_state_manager_instance.get_state(conversation_id)
    if not state:
        # No active or recent run — just confirm join
        socketio.emit("run_status", {"status": "idle", "conversationId": conversation_id}, room=sid)
        return

    status = state.get("status")
    message_id = state.get("message_id")

    if status == "running":
        # Agent is still working — tell the client it's in-progress
        socketio.emit("run_status", {
            "status": "running",
            "conversationId": conversation_id,
            "messageId": message_id,
        }, room=sid)
        logger.info(f"[Join] Conv {conversation_id} is still running, told client to wait")

    elif status == "completed":
        # Guard: never send run_catchup twice to the same SID for the same conversation
        dedup_key = (sid, conversation_id)
        if dedup_key in _catchup_sent:
            logger.info(f"[Join] Catchup already sent for conv {conversation_id} to SID {sid}, skipping")
            return
        _catchup_sent[dedup_key] = True

        # Agent finished while client was away — send the stored result for catch-up
        result = run_state_manager_instance.get_result(conversation_id)
        if result:
            socketio.emit("run_catchup", {
                "conversationId": conversation_id,
                "messageId": message_id,
                "content": result.get("content", ""),
                "events": result.get("events", []),
                "title": result.get("title"),
                "status": "completed",
            }, room=sid)
            logger.info(f"[Join] Sent catchup result for conv {conversation_id} to SID {sid}")
        else:
            socketio.emit("run_status", {"status": "completed", "conversationId": conversation_id, "messageId": message_id}, room=sid)

    elif status == "failed":
        result = run_state_manager_instance.get_result(conversation_id)
        socketio.emit("run_status", {
            "status": "failed",
            "conversationId": conversation_id,
            "messageId": message_id,
            "error": (result or {}).get("error", "An error occurred."),
        }, room=sid)
        logger.info(f"[Join] Conv {conversation_id} had failed run, notified SID {sid}")


@socketio.on('save-user-context')
def handle_save_user_context(data: Dict[str, Any]):
    """Saves user context to agno_memories table via UserContextTools"""
    sid = request.sid
    try:
        logger.info(f"Received save-user-context request: {data.keys()}")

        access_token = data.get("accessToken") or _socket_auth_tokens.get(sid)
        if not access_token:
            logger.error("Authentication token missing")
            return socketio.emit("user-context-saved", {"success": False, "error": "Authentication token missing"}, room=sid)

        user, auth_error = get_user_from_jwt(access_token)
        if auth_error:
            logger.error("User not authenticated: %s", auth_error[0])
            return socketio.emit("user-context-saved", {"success": False, "error": auth_error[0]}, room=sid)

        context_data = data.get('context')
        if not context_data:
            logger.error("Context data missing")
            return socketio.emit("user-context-saved", {"success": False, "error": "Context data missing"}, room=sid)

        logger.info(
            "Saving user context for user %s with keys=%s",
            user.id,
            sorted(context_data.keys()) if isinstance(context_data, dict) else [],
        )

        from user_context_tools import UserContextTools
        context_tools = UserContextTools(user_id=str(user.id))
        result = context_tools.save_user_context(context_data)

        logger.info("User context save completed for user %s", user.id)
        socketio.emit("user-context-saved", {"success": True, "result": result}, room=sid)
        logger.info(f"User context saved successfully for user {user.id}")

    except Exception as e:
        logger.error(f"Error saving user context: {e}\n{traceback.format_exc()}")
        socketio.emit("user-context-saved", {"success": False, "error": str(e)}, room=sid)


@socketio.on('get-user-context')
def handle_get_user_context(data: Dict[str, Any]):
    """Retrieves user context from agno_memories table via UserContextTools"""
    sid = request.sid
    try:
        access_token = data.get("accessToken") or _socket_auth_tokens.get(sid)
        if not access_token:
            return socketio.emit("user-context-retrieved", {"success": False, "error": "Authentication token missing"}, room=sid)

        user, auth_error = get_user_from_jwt(access_token)
        if auth_error:
            return socketio.emit("user-context-retrieved", {"success": False, "error": auth_error[0]}, room=sid)

        from user_context_tools import UserContextTools
        context_tools = UserContextTools(user_id=str(user.id))
        context = context_tools.get_user_context()

        socketio.emit("user-context-retrieved", {"success": True, "context": context}, room=sid)
        logger.info(f"User context retrieved for user {user.id}")

    except Exception as e:
        logger.error(f"Error retrieving user context: {e}\n{traceback.format_exc()}")
        socketio.emit("user-context-retrieved", {"success": False, "error": str(e)}, room=sid)


@socketio.on('browser-command-result')
def handle_browser_command_result(data: Dict[str, Any]):
    """
    Receives a result from the client and PUBLISHES it to the corresponding
    Redis channel, waking up the waiting agent tool.
    """
    if not redis_client_instance:
        logger.error("Redis client not initialized. Cannot handle browser command result.")
        return

    request_id = data.get('request_id')
    result_payload = data.get('result', {})

    if request_id:
        response_channel = f"browser-response:{request_id}"
        try:
            redis_client_instance.publish(response_channel, json.dumps(result_payload))
            logger.info(f"Published result for request_id {request_id} to Redis channel {response_channel}")
        except Exception as e:
            logger.error(f"Failed to publish browser result to Redis for {request_id}: {e}")
    else:
        logger.warning("Received browser command result with no request_id.")


@socketio.on('computer-command-result')
def handle_computer_command_result(data: Dict[str, Any]):
    """
    Receives a computer control result from the client and PUBLISHES it to the
    corresponding Redis channel, waking up the waiting agent tool.
    """
    if not redis_client_instance:
        logger.error("Redis client not initialized. Cannot handle computer command result.")
        return

    request_id = data.get('request_id')
    result_payload = data.get('result', {})

    if request_id:
        response_channel = f"computer-response:{request_id}"
        try:
            redis_client_instance.publish(response_channel, json.dumps(result_payload))
            logger.info(f"Published computer result for request_id {request_id} to Redis channel {response_channel}")
        except Exception as e:
            logger.error(f"Failed to publish computer result to Redis for {request_id}: {e}")
    else:
        logger.warning("Received computer command result with no request_id.")


@socketio.on('local-coder-command-result')
def handle_local_coder_command_result(data: Dict[str, Any]):
    """
    Receives local coder bridge command result from desktop client and publishes
    it back to Redis for waiting toolkit consumers.
    """
    if not redis_client_instance:
        logger.error("Redis client not initialized. Cannot handle local coder command result.")
        return

    request_id = data.get('request_id')
    result_payload = data.get('result', {})

    if request_id:
        response_channel = f"local-coder-response:{request_id}"
        try:
            redis_client_instance.publish(response_channel, json.dumps(result_payload))
            logger.info(
                "Published local coder result for request_id %s to Redis channel %s",
                request_id,
                response_channel,
            )
        except Exception as e:
            logger.error(f"Failed to publish local coder result to Redis for {request_id}: {e}")
    else:
        logger.warning("Received local coder command result with no request_id.")


@socketio.on('mobile-command-result')
def handle_mobile_command_result(data: Dict[str, Any]):
    """
    Receives mobile command result from native assistant bridge and publishes
    it to Redis for waiting MobileTools toolkit calls.
    """
    if not redis_client_instance:
        logger.error("Redis client not initialized. Cannot handle mobile command result.")
        return

    request_id = data.get('request_id')
    result_payload = data.get('result')
    if result_payload is None:
        result_payload = data

    if request_id:
        response_channel = f"mobile-response:{request_id}"
        try:
            redis_client_instance.publish(response_channel, json.dumps(result_payload))
            logger.info(
                "Published mobile result for request_id %s to Redis channel %s",
                request_id,
                response_channel,
            )
        except Exception as e:
            logger.error(f"Failed to publish mobile result to Redis for {request_id}: {e}")
    else:
        logger.warning("Received mobile command result with no request_id.")


@socketio.on("plan_request")
def on_plan_request(data: str):
    """Generate an editable plan-mode prompt without starting the main llm_os run."""
    sid = request.sid
    request_id = None
    try:
        if isinstance(data, str):
            data = json.loads(data)
        if not isinstance(data, dict):
            data = {}

        access_token = data.get("accessToken") or _socket_auth_tokens.get(sid)
        request_id = data.get("requestId") or str(uuid.uuid4())
        message_id = data.get("messageId")
        conversation_id = data.get("conversationId")
        raw_message = str(data.get("message") or "").strip()

        if not access_token:
            return socketio.emit(
                "plan_response",
                {"success": False, "requestId": request_id, "messageId": message_id, "error": "Authentication token is missing."},
                room=sid,
            )
        if not raw_message and not data.get("files") and not data.get("selected_sessions"):
            return socketio.emit(
                "plan_response",
                {"success": False, "requestId": request_id, "messageId": message_id, "error": "Plan mode needs a request, file, or selected context."},
                room=sid,
            )

        user, auth_error = get_user_from_jwt(access_token)
        if auth_error:
            return socketio.emit(
                "plan_response",
                {"success": False, "requestId": request_id, "messageId": message_id, "error": auth_error[0]},
                room=sid,
            )

        incoming_config = _sanitize_plan_config(dict(data.get("config", {}) or {}))

        common_payload = {
            "success": True,
            "requestId": request_id,
            "messageId": message_id,
            "conversationId": conversation_id,
            "model": "mimo-v2.5-pro",
        }
        for event in stream_plan(
            message=raw_message,
            config=incoming_config,
            files=data.get("files", []),
            selected_sessions=data.get("selected_sessions", []),
            workspace_context=data.get("workspace_context", {}),
            debug_mode=config.AGNO_DEBUG_MODE,
        ):
            event_type = event.get("type")
            if event_type == "content":
                socketio.emit(
                    "plan_response",
                    {
                        **common_payload,
                        "streaming": True,
                        "content": event.get("content", ""),
                        "agent_name": event.get("agent_name", "plan_agent"),
                    },
                    room=sid,
                )
            elif event_type == "reasoning":
                socketio.emit(
                    "plan_response",
                    {
                        **common_payload,
                        "streaming": True,
                        "reasoning_content": event.get("content", ""),
                        "agent_name": event.get("agent_name", "plan_agent"),
                    },
                    room=sid,
                )
            elif event_type in ("tool_start", "tool_end"):
                socketio.emit(
                    "plan_response",
                    {
                        **common_payload,
                        "streaming": True,
                        "step_type": event_type,
                        "name": event.get("name"),
                        "agent_name": event.get("agent_name", "plan_agent"),
                        "tool": event.get("tool"),
                    },
                    room=sid,
                )
            elif event_type == "done":
                socketio.emit(
                    "plan_response",
                    {
                        **common_payload,
                        "done": True,
                        "plan": event.get("plan", ""),
                    },
                    room=sid,
                )
    except AuthApiError as e:
        logger.error("Invalid token for plan request SID %s: %s", sid, e.message)
        socketio.emit("plan_response", {"success": False, "requestId": request_id, "messageId": locals().get("message_id"), "error": "Your session has expired. Please log in again."}, room=sid)
    except Exception as e:
        logger.error("Error generating plan: %s\n%s", e, traceback.format_exc())
        socketio.emit("plan_response", {"success": False, "requestId": request_id, "messageId": locals().get("message_id"), "error": "Plan generation failed. Please try again."}, room=sid)


# FUNCTION DESCRIPTION:
# Primary Socket.IO entry point for client messages. It verifies user auth tokens using Supabase Auth,
# subscribes the connection socket to a conversation-specific WebSocket room `conv:{conversation_id}`,
# synchronizes incoming settings (modes, cloud/local targets) with Redis session keys,
# verifies pricing/usage limits, logs uploaded files in Supabase 'session_content', and
# spawns the background execution thread `run_agent_and_stream`.
#
# UPSTREAM CALLER:
# - Invoked by client socket emissions of `send_message` from `js/chat.js` (specifically `on_send_message()` handlers).
#
# DOWNSTREAM IMPACT:
# - Spawns background Eventlet thread running `run_agent_and_stream()`.
# - Modifies Redis database keys under namespace `session:{conversationId}`.
# - Spawns background title generation via `generate_and_save_title`.
# - Emits back socket messages on validation failures (e.g. `error`, `status`).
@socketio.on("send_message")
def on_send_message(data: str):
    """The main message handler for incoming chat messages."""
    sid = request.sid
    if not connection_manager_service or not redis_client_instance:
        logger.error("Services not initialized. Cannot handle message.")
        return

    try:
        data = json.loads(data)
        access_token = data.get("accessToken") or _socket_auth_tokens.get(sid)
        conversation_id = data.get("conversationId")

        if not conversation_id:
            return socketio.emit("error", {"message": "Critical error: conversationId is missing."}, room=sid)
        if not access_token:
            return socketio.emit("error", {"message": "Authentication token is missing.", "reset": True}, room=sid)

        user, auth_error = get_user_from_jwt(access_token)
        if auth_error:
            return socketio.emit("error", {"message": auth_error[0], "reset": True}, room=sid)

        if not can_access_conversation(
            str(user.id),
            conversation_id,
            connection_manager_service,
            run_state_manager_instance,
            allow_unowned=True,
        ):
            logger.warning(
                "[send_message] Rejected conversation ownership mismatch for SID %s",
                sid,
            )
            return socketio.emit(
                "error",
                {"message": "Conversation not found.", "reset": True},
                room=sid,
            )

        # Subscribe only after authentication and ownership checks.
        room_name = f"conv:{conversation_id}"
        join_room(room_name)
        logger.info(f"[send_message] SID {sid} joined room {room_name}")

        if data.get("type") == "terminate_session":
            connection_manager_service.terminate_session(conversation_id)
            if run_state_manager_instance:
                run_state_manager_instance.clear(conversation_id)
            return socketio.emit("status", {"message": f"Session {conversation_id} terminated"}, room=sid)

        requested_agent_mode = _normalize_agent_mode(
            data.get("agent_mode") or (data.get("config", {}) or {}).get("agent_mode")
        )
        requested_coder_target = _normalize_coder_execution_target(
            data.get("coder_execution_target") or (data.get("config", {}) or {}).get("coder_execution_target")
        )
        workspace_context = data.get("workspace_context")
        if not isinstance(workspace_context, dict):
            workspace_context = {}

        incoming_config = _sanitize_tool_config_for_user(
            dict(data.get("config", {}) or {}),
            str(user.id),
        )

        if not connection_manager_service.get_session(conversation_id):
            device_type = data.get("deviceType", "web")
            session_config = dict(incoming_config)
            session_config["agent_mode"] = requested_agent_mode
            session_config["coder_execution_target"] = requested_coder_target
            session_config["workspace_context"] = workspace_context
            connection_manager_service.create_session(
                conversation_id,
                str(user.id),
                session_config,
                device_type=device_type
            )

            # --- Title Generation for New Sessions ---
            user_msg_content = data.get("message", "")
            if user_msg_content:
                import time
                current_ts = int(time.time())
                eventlet.spawn(generate_and_save_title, conversation_id, str(user.id), user_msg_content, current_ts)
        else:
            # Keep routing and workspace state fresh for existing sessions.
            session_data = connection_manager_service.get_session(conversation_id) or {}
            session_config = dict(session_data.get("config", {}))
            session_config.update(incoming_config)
            session_config = _sanitize_tool_config_for_user(session_config, str(user.id))
            session_config["agent_mode"] = requested_agent_mode
            session_config["coder_execution_target"] = requested_coder_target
            session_config["workspace_context"] = workspace_context
            session_data["config"] = session_config
            connection_manager_service.redis_client.set(
                f"session:{conversation_id}",
                json.dumps(session_data),
                ex=connection_manager_service.SESSION_TTL,
            )

        try:
            enforce_usage_limit(str(user.id))
        except UsageLimitExceeded as exc:
            socketio.emit("error", {
                "message": str(exc),
                "code": "subscription_limit_exceeded",
                "limit_info": exc.summary,
            }, room=sid)
            return
        except Exception as exc:
            # Usage checks should not bring down the message pipeline.
            logger.error(
                "Usage limit check failed for user %s conversation %s: %s",
                str(user.id),
                conversation_id,
                exc,
                exc_info=True,
            )

        turn_data = {
            "user_message": data.get("message", ""),
            "files": data.get("files", []),
            "coder_execution_target": requested_coder_target,
        }
        context_session_ids = data.get("context_session_ids", [])
        message_id = data.get("id") or str(uuid.uuid4())

        # --- Register user-uploaded files in session_content for persistence ---
        files = data.get("files", [])
        if files:
            try:
                from sandbox_persistence import get_persistence_service
                persistence_service = get_persistence_service()

                for file_data in files:
                    if file_data.get('path') or file_data.get('relativePath'):
                        persistence_service.register_content(
                            session_id=conversation_id,
                            user_id=str(user.id),
                            content_type='upload',
                            reference_id=str(uuid.uuid4()),
                            message_id=message_id,
                            metadata={
                                'filename': file_data.get('name', 'unknown'),
                                'mime_type': file_data.get('type', 'application/octet-stream'),
                                'type': file_data.get('type', 'application/octet-stream'),
                                'size': file_data.get('size', 0),
                                'path': file_data.get('path'),
                                'relativePath': file_data.get('relativePath'),
                                'file_id': file_data.get('file_id'),
                                'is_text': file_data.get('isText', False),
                                'isMedia': file_data.get('isMedia', False)
                            }
                        )
                logger.info(f"Registered {len(files)} user uploads for session {conversation_id}")

                # Session content cache removed - frontend handles caching
            except Exception as e:
                logger.warning(f"Failed to register user uploads: {e}")

        browser_tools_config = {'sid': sid, 'socketio': socketio, 'redis_client': redis_client_instance}

        eventlet.spawn(
            run_agent_and_stream,
            sid,
            conversation_id,
            message_id,
            turn_data,
            browser_tools_config,
            context_session_ids,
            requested_agent_mode,
            connection_manager_service,
            redis_client_instance,
            run_state_manager_instance,  # NEW: pass run state manager
        )
        logger.info(f"Spawned agent run for conversation: {conversation_id}")

    except AuthApiError as e:
        logger.error(f"Invalid token for SID {sid}: {e.message}")
        socketio.emit("error", {"message": "Your session has expired. Please log in again."}, room=sid)
    except Exception as e:
        import sys
        print(f"DEBUG: Error in message handler: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        logger.error(f"Error in message handler: {e}\n{traceback.format_exc()}")
        socketio.emit("error", {"message": "An error occurred. Your conversation is preserved. Please try again."}, room=sid)


@socketio.on("assistant_message")
def on_assistant_message(data: str):
    """
    Dedicated message handler for Android Assistant clients.
    Requires access_token so native assistant usage is tied to real users.
    """
    sid = request.sid
    if not connection_manager_service or not redis_client_instance:
        logger.error("Services not initialized. Cannot handle assistant message.")
        return

    try:
        if isinstance(data, str):
            data = json.loads(data)

        logger.info(
            "[Assistant Socket] Received message metadata: %s",
            safe_socket_message_metadata(data),
        )

        access_token = data.get("accessToken") or _socket_auth_tokens.get(sid)
        if not access_token:
            return socketio.emit("assistant_error", {"message": "Authentication token is missing."}, room=sid)

        user, auth_error = get_user_from_jwt(access_token)
        if auth_error:
            return socketio.emit("assistant_error", {"message": auth_error[0]}, room=sid)

        user_message = data.get("message", "")
        conversation_id = data.get("conversationId")
        assistant_target = str(
            data.get("assistant_target")
            or data.get("assistantTarget")
            or ""
        ).strip().lower()

        if not conversation_id and data.get("session_id"):
            conversation_id = data.get("session_id")

        if not conversation_id:
            conversation_id = str(uuid.uuid4())
            logger.info(f"[Assistant Socket] Generated new conversation ID: {conversation_id}")

        if not user_message:
            return socketio.emit("assistant_error", {"message": "Message is required"}, room=sid)

        if not can_access_conversation(
            str(user.id),
            conversation_id,
            connection_manager_service,
            run_state_manager_instance,
            allow_unowned=True,
        ):
            logger.warning(
                "[Assistant Socket] Rejected conversation ownership mismatch for SID %s",
                sid,
            )
            return socketio.emit(
                "assistant_error",
                {"message": "Conversation not found."},
                room=sid,
            )

        # Join only after authentication and ownership checks.
        room_name = f"conv:{conversation_id}"
        join_room(room_name)

        try:
            enforce_usage_limit(str(user.id))
        except UsageLimitExceeded as exc:
            return socketio.emit("assistant_error", {
                "message": str(exc),
                "code": "subscription_limit_exceeded",
                "limit_info": exc.summary,
            }, room=sid)
        except Exception as exc:
            logger.error(
                "Usage limit check failed for assistant_message user %s: %s",
                str(user.id),
                exc,
                exc_info=True,
            )

        user_id = str(user.id)
        requested_agent_mode = "system-assistant" if assistant_target == "system-assistant" else "default"

        if not connection_manager_service.get_session(conversation_id):
            session_config = _sanitize_tool_config_for_user(
                dict(data.get("config", {
                    "internet_search": True,
                    "coding_assistant": True,
                })),
                user_id,
            )
            session_config["agent_mode"] = requested_agent_mode
            session_config["assistant_target"] = assistant_target or "system-assistant"
            connection_manager_service.create_session(
                conversation_id,
                user_id,
                session_config,
                device_type='mobile'
            )
        else:
            session_data = connection_manager_service.get_session(conversation_id) or {}
            session_config = dict(session_data.get("config", {}))
            session_config.update(
                _sanitize_tool_config_for_user(dict(data.get("config", {}) or {}), user_id)
            )
            session_config = _sanitize_tool_config_for_user(session_config, user_id)
            session_config["agent_mode"] = requested_agent_mode
            session_config["assistant_target"] = assistant_target or "system-assistant"
            session_data["config"] = session_config
            connection_manager_service.redis_client.set(
                f"session:{conversation_id}",
                json.dumps(session_data),
                ex=connection_manager_service.SESSION_TTL,
            )

        turn_data = {"user_message": user_message, "files": []}
        message_id = data.get("id") or str(uuid.uuid4())

        browser_tools_config = {'sid': sid, 'socketio': socketio, 'redis_client': redis_client_instance}

        eventlet.spawn(
            run_agent_and_stream,
            sid,
            conversation_id,
            message_id,
            turn_data,
            browser_tools_config,
            [],
            requested_agent_mode,
            connection_manager_service,
            redis_client_instance,
            run_state_manager_instance,  # NEW: pass run state manager
        )
        logger.info(f"[Assistant Socket] Spawned agent for {conversation_id}")

    except Exception as e:
        logger.error(f"[Assistant Socket] Error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        socketio.emit("assistant_error", {"message": "I encountered an error processing your request."}, room=sid)
