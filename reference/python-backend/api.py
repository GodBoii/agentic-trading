# python-backend/api.py

import logging
import uuid
import json
import time
import requests
import redis
import base64
import hashlib
import mimetypes
from typing import Any, Optional
from urllib.parse import urlparse, unquote
from flask import Blueprint, request, jsonify

# Import the utility function from the factory (or a future utils module)
from utils import get_user_from_token
from supabase_client import supabase_client
from extensions import socketio, limiter
from cache_manager import CacheManager
import config
from composio_client import ComposioApiError, ComposioClient
from deploy_platform import (
    activate_deployment,
    assign_subdomain,
    create_or_get_site,
    ensure_deploy_tables,
    get_deployment_summary,
    get_site_runtime_db_credentials,
    get_site_db_credentials,
    get_deployment_file_bytes,
    list_deployed_projects,
    list_deployment_files,
    list_user_databases,
    preflight_check,
    provision_turso_database,
    resolve_public_site_hostname,
    resolve_site_ref,
    upload_site_files,
    upsert_site_manifest,
)
from user_file_vault import (
    create_user_file_upload_link,
    delete_user_file,
    get_user_file_bytes,
    get_user_file,
    list_user_files,
    read_user_file_text,
    register_user_file,
    upload_user_file_from_base64,
)
from subscription_service import (
    UsageLimitExceeded,
    calculate_usage_summary,
    cleanup_incomplete_subscription,
    create_razorpay_subscription,
    enforce_usage_limit,
    get_daily_usage_by_date,
    get_daily_usage_for_user,
    get_usage_window_descriptor,
    get_plan_config,
    handle_webhook_event,
    parse_webhook_body,
    verify_checkout_and_activate,
    verify_webhook_signature,
)
from convex_usage_service import get_convex_usage_service

logger = logging.getLogger(__name__)

# Create a Blueprint for API routes, with a URL prefix of /api
api_bp = Blueprint('api_bp', __name__, url_prefix='/api')

# RunStateManager is a module-level singleton injected from the factory via
# set_run_state_manager() below.
_run_state_manager = None
_PROJECT_WORKSPACE_ROOT = "/home/sandboxuser/workspace"


def set_run_state_manager(manager):
    """Called by the factory to inject the shared RunStateManager instance."""
    global _run_state_manager
    _run_state_manager = manager


def _load_project_workspace_session(conversation_id: str, user_id: str) -> dict[str, Any]:
    redis_client = redis.from_url(config.REDIS_URL, decode_responses=True)
    session_json = redis_client.get(f"session:{conversation_id}")
    if not session_json:
        raise LookupError("session not found")

    session_data = json.loads(session_json) if isinstance(session_json, str) else (session_json or {})
    if str(session_data.get("user_id")) != str(user_id):
        raise PermissionError("Unauthorized session access")
    return session_data


def _resolve_project_workspace_sandbox_id(session_data: dict[str, Any]) -> Optional[str]:
    sandbox_id = session_data.get("active_sandbox_id")
    if sandbox_id:
        return str(sandbox_id)
    sandbox_ids = session_data.get("sandbox_ids", []) or []
    return str(sandbox_ids[-1]) if sandbox_ids else None


def _list_sandbox_workspace_rows(sandbox_id: str, path: str = _PROJECT_WORKSPACE_ROOT) -> list[dict[str, Any]]:
    resp = requests.get(
        f"{config.SANDBOX_API_URL}/sessions/{sandbox_id}/files",
        params={"path": path},
        timeout=30,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"failed to list sandbox files (HTTP {resp.status_code})")
    return (resp.json() or {}).get("files", []) or []


def _read_sandbox_workspace_bytes(sandbox_id: str, abs_path: str) -> bytes:
    resp = requests.get(
        f"{config.SANDBOX_API_URL}/sessions/{sandbox_id}/files/content",
        params={"filepath": abs_path},
        timeout=30,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"failed to load sandbox file (HTTP {resp.status_code})")
    payload = resp.json() or {}
    encoded = payload.get("content", "") or ""
    return base64.b64decode(encoded) if encoded else b""


def _collect_workspace_upload_files(sandbox_id: str, project_directory: str = _PROJECT_WORKSPACE_ROOT) -> list[dict[str, Any]]:
    rows = _list_sandbox_workspace_rows(sandbox_id=sandbox_id, path=project_directory)
    upload_files: list[dict[str, Any]] = []

    for item in rows:
        abs_path = str(item.get("path", ""))
        if not abs_path.startswith(project_directory.rstrip("/") + "/"):
            continue
        rel_path = abs_path[len(project_directory.rstrip("/")) + 1:].replace("\\", "/")
        if not rel_path or ".." in rel_path.split("/"):
            continue
        content_bytes = _read_sandbox_workspace_bytes(sandbox_id=sandbox_id, abs_path=abs_path)
        upload_files.append(
            {
                "path": rel_path,
                "content_base64": base64.b64encode(content_bytes).decode("utf-8"),
                "content_type": mimetypes.guess_type(rel_path)[0] or "application/octet-stream",
            }
        )

    return upload_files


# --- Run Status Endpoints (used for reconnect / catch-up) ---

@api_bp.route('/conversations/<conversation_id>/status', methods=['GET'])
@limiter.limit('120 per minute')
def conversation_run_status(conversation_id):
    """
    Returns the current run state for a conversation.
    The client calls this after reconnecting to learn whether a run is still
    in-progress, completed (with catch-up), or failed.
    """
    user, error = get_user_from_token(request)
    if error:
        return jsonify({"error": error[0]}), error[1]

    if not _run_state_manager:
        return jsonify({"status": "idle"}), 200

    state = _run_state_manager.get_state(conversation_id)
    if not state:
        return jsonify({"status": "idle", "conversationId": conversation_id}), 200

    return jsonify({
        "conversationId": conversation_id,
        "status": state.get("status"),
        "messageId": state.get("message_id"),
        "error": state.get("error"),
        "updatedAt": state.get("updated_at"),
    }), 200


@api_bp.route('/conversations/<conversation_id>/result', methods=['GET'])
@limiter.limit('120 per minute')
def conversation_run_result(conversation_id):
    """
    Returns the stored result (completed/failed) for a conversation run.
    Used for catch-up rendering when the client was not connected during streaming.
    """
    user, error = get_user_from_token(request)
    if error:
        return jsonify({"error": error[0]}), error[1]

    if not _run_state_manager:
        return jsonify({"status": "none"}), 200

    result = _run_state_manager.get_result(conversation_id)
    if not result:
        return jsonify({"status": "none", "conversationId": conversation_id}), 200

    return jsonify({
        "conversationId": conversation_id,
        "status": result.get("status"),
        "messageId": result.get("message_id"),
        "content": result.get("content"),
        "events": result.get("events", []),
        "title": result.get("title"),
        "error": result.get("error"),
    }), 200




def _resolve_auth_config_id(toolkit_slug: str, request_auth_config_id: str | None) -> str | None:
    if request_auth_config_id:
        return request_auth_config_id

    normalized = (toolkit_slug or "").upper()
    if normalized == "GOOGLESHEETS":
        return config.COMPOSIO_GOOGLESHEETS_AUTH_CONFIG_ID
    if normalized == "WHATSAPP":
        return config.COMPOSIO_WHATSAPP_AUTH_CONFIG_ID
    return None


def _extract_host_from_header(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    try:
        parsed = urlparse(value)
    except Exception:
        return None
    host = (parsed.netloc or "").strip().lower()
    if not host:
        return None
    if ":" in host:
        host = host.split(":", 1)[0]
    return host or None


def _to_hrana_value(value: Any) -> dict[str, Any]:
    if value is None:
        return {"type": "null"}
    if isinstance(value, bool):
        return {"type": "integer", "value": "1" if value else "0"}
    if isinstance(value, int):
        return {"type": "integer", "value": str(value)}
    if isinstance(value, float):
        return {"type": "float", "value": value}
    if isinstance(value, (dict, list)):
        import json
        return {"type": "text", "value": json.dumps(value, ensure_ascii=True)}
    return {"type": "text", "value": str(value)}


def _execute_hrana_query(hostname: str, token: str, sql: str, params: Optional[list[Any]] = None) -> dict[str, Any]:
    args = [_to_hrana_value(v) for v in (params or [])]
    payload = {
        "requests": [
            {
                "type": "execute",
                "stmt": {
                    "sql": sql,
                    "args": args,
                    "want_rows": True,
                },
            }
        ]
    }
    response = requests.post(
        f"https://{hostname}/v2/pipeline",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=30,
    )
    if response.status_code not in (200, 201):
        raise RuntimeError(f"Query failed: HTTP {response.status_code} {response.text}")

    data = response.json() or {}
    results = data.get("results") or []
    if not results:
        return {"raw": data}
    result = results[0] or {}
    if "error" in result:
        raise RuntimeError(f"Query failed: {result['error']}")
    return result.get("response", result)


def _normalize_single_statement(sql: str) -> str:
    cleaned = (sql or "").strip()
    if not cleaned:
        raise ValueError("sql is required")
    cleaned = cleaned.rstrip(";").strip()
    if ";" in cleaned:
        raise ValueError("Only a single SQL statement is allowed per request")
    return cleaned


@api_bp.route('/subscription/status', methods=['GET'])
@limiter.limit('100 per minute')
def subscription_status():
    user, error = get_user_from_token(request)
    if error:
        return jsonify({"error": error[0]}), error[1]

    cache_key = f"cache:subscription_status:{user.id}"
    cached_data = CacheManager.get(cache_key)
    if cached_data:
        return jsonify(cached_data), 200

    try:
        summary = calculate_usage_summary(str(user.id), refresh_window=True)
        response_data = {"ok": True, "summary": summary}
        CacheManager.set(cache_key, response_data, ttl_seconds=3600)
        return jsonify(response_data), 200
    except Exception as exc:
        logger.error("subscription/status failed: %s", exc, exc_info=True)
        return jsonify({"ok": False, "error": "failed to load subscription status"}), 500


@api_bp.route('/usage/daily', methods=['GET'])
@limiter.limit('60 per minute')
def usage_daily_for_user():
    user, error = get_user_from_token(request)
    if error:
        return jsonify({"error": error[0]}), error[1]

    day_key = (request.args.get("day") or "").strip() or None
    limit = request.args.get("limit", default=30, type=int) or 30
    limit = max(1, min(limit, 365))

    try:
        rows = get_daily_usage_for_user(str(user.id), day_key=day_key, limit=limit)
        logger.info(
            "usage/daily user=%s day_key=%s limit=%s rows=%s",
            str(user.id),
            day_key,
            limit,
            len(rows),
        )
        return jsonify({"ok": True, "rows": rows, "count": len(rows)}), 200
    except Exception as exc:
        logger.error("usage/daily failed for user %s: %s", str(user.id), exc, exc_info=True)
        return jsonify({"ok": False, "error": "failed to load daily usage"}), 500


@api_bp.route('/admin/usage/daily', methods=['GET'])
@limiter.limit('60 per minute')
def usage_daily_admin():
    expected_key = str(config.USAGE_ADMIN_API_KEY or "").strip()
    provided_key = str(request.headers.get("x-usage-admin-key") or "").strip()
    if not expected_key:
        return jsonify({"ok": False, "error": "USAGE_ADMIN_API_KEY is not configured"}), 503
    if provided_key != expected_key:
        return jsonify({"ok": False, "error": "unauthorized"}), 401

    day_key = (request.args.get("day") or "").strip()
    if not day_key:
        return jsonify({"ok": False, "error": "day query param is required (YYYY-MM-DD)"}), 400
    limit = request.args.get("limit", default=1000, type=int) or 1000
    limit = max(1, min(limit, 5000))

    try:
        rows = get_daily_usage_by_date(day_key=day_key, limit=limit)
        return jsonify({"ok": True, "day": day_key, "rows": rows, "count": len(rows)}), 200
    except Exception as exc:
        logger.error("admin/usage/daily failed for day %s: %s", day_key, exc, exc_info=True)
        return jsonify({"ok": False, "error": "failed to load admin daily usage"}), 500


@api_bp.route('/subscription/create', methods=['POST'])
@limiter.limit('10 per minute')
def subscription_create():
    user, error = get_user_from_token(request)
    if error:
        return jsonify({"error": error[0]}), error[1]

    body = request.json or {}
    plan_type = str(body.get("plan_type") or body.get("plan") or "").strip().lower()
    if plan_type not in {"pro", "elite"}:
        return jsonify({"ok": False, "error": "plan_type must be 'pro' or 'elite'"}), 400

    try:
        subscription = create_razorpay_subscription(
            user_id=str(user.id),
            email=str(getattr(user, "email", "") or ""),
            plan_type=plan_type,
        )
        CacheManager.delete(f"cache:subscription_status:{user.id}")
        plan = get_plan_config(plan_type)
        summary = calculate_usage_summary(str(user.id), refresh_window=False)
        checkout_required = str(subscription.get("_aetheria_change_type") or "").strip() == ""
        return jsonify({
            "ok": True,
            "key_id": config.RAZORPAY_KEY_ID,
            "plan_type": plan_type,
            "plan_name": plan["name"],
            "subscription_id": subscription.get("id"),
            "status": subscription.get("status"),
            "checkout_required": checkout_required,
            "change_type": subscription.get("_aetheria_change_type"),
            "has_scheduled_changes": subscription.get("has_scheduled_changes"),
            "change_scheduled_at": subscription.get("change_scheduled_at"),
            "subscription": subscription,
            "summary": summary,
        }), 200
    except RuntimeError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 409
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        logger.error("subscription/create failed: %s", exc, exc_info=True)
        return jsonify({"ok": False, "error": "failed to create subscription"}), 500


@api_bp.route('/subscription/verify', methods=['POST'])
@limiter.limit('10 per minute')
def subscription_verify():
    user, error = get_user_from_token(request)
    if error:
        return jsonify({"error": error[0]}), error[1]

    body = request.json or {}
    payment_id = str(body.get("razorpay_payment_id") or "").strip()
    subscription_id = str(body.get("razorpay_subscription_id") or "").strip()
    signature = str(body.get("razorpay_signature") or "").strip()
    if not payment_id or not subscription_id or not signature:
        return jsonify({
            "ok": False,
            "error": "razorpay_payment_id, razorpay_subscription_id, and razorpay_signature are required",
        }), 400

    try:
        result = verify_checkout_and_activate(
            user_id=str(user.id),
            payment_id=payment_id,
            subscription_id=subscription_id,
            signature=signature,
        )
        CacheManager.delete(f"cache:subscription_status:{user.id}")
        return jsonify({"ok": True, **result}), 200
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        logger.error("subscription/verify failed: %s", exc, exc_info=True)
        return jsonify({"ok": False, "error": "failed to verify subscription payment"}), 500


@api_bp.route('/subscription/cleanup', methods=['POST'])
@limiter.limit('20 per minute')
def subscription_cleanup():
    user, error = get_user_from_token(request)
    if error:
        return jsonify({"error": error[0]}), error[1]

    body = request.json or {}
    subscription_id = str(body.get("razorpay_subscription_id") or body.get("subscription_id") or "").strip()
    if not subscription_id:
        return jsonify({"ok": False, "error": "subscription_id is required"}), 400

    try:
        result = cleanup_incomplete_subscription(str(user.id), subscription_id)
        CacheManager.delete(f"cache:subscription_status:{user.id}")
        return jsonify({"ok": True, **result}), 200
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except RuntimeError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 409
    except Exception as exc:
        logger.error("subscription/cleanup failed: %s", exc, exc_info=True)
        return jsonify({"ok": False, "error": "failed to clean up subscription"}), 500


@api_bp.route('/webhooks/razorpay', methods=['POST'])
@limiter.limit('100 per minute')
def razorpay_webhook():
    raw_body = request.get_data(cache=False, as_text=False)
    signature = request.headers.get("X-Razorpay-Signature", "")
    if not signature:
        return jsonify({"ok": False, "error": "missing X-Razorpay-Signature header"}), 400

    try:
        verify_webhook_signature(raw_body, signature)
        payload = parse_webhook_body(raw_body)
        result = handle_webhook_event(payload)
        return jsonify({"ok": True, **result}), 200
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except RuntimeError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 503
    except Exception as exc:
        logger.error("webhooks/razorpay failed: %s", exc, exc_info=True)
        return jsonify({"ok": False, "error": "failed to process Razorpay webhook"}), 500


@api_bp.route('/integrations', methods=['GET'])
@limiter.limit('60 per minute')
def get_integrations_status():
    """
    Fetches the list of connected third-party services for the authenticated user.
    """
    user, error = get_user_from_token(request)
    if error:
        return jsonify({"error": error[0]}), error[1]
    
    cache_key = f"cache:integrations:{user.id}"
    cached_data = CacheManager.get(cache_key)
    if cached_data:
        return jsonify(cached_data), 200

    response = supabase_client.from_('user_integrations').select('service').eq('user_id', str(user.id)).execute()
    
    response_data = {"integrations": [item['service'] for item in response.data]}
    CacheManager.set(cache_key, response_data, ttl_seconds=3600)
    return jsonify(response_data), 200


@api_bp.route('/integrations/disconnect', methods=['POST'])
@limiter.limit('20 per minute')
def disconnect_integration():
    """
    Removes an integration record for the authenticated user and a given service.
    """
    user, error = get_user_from_token(request)
    if error:
        return jsonify({"error": error[0]}), error[1]
    
    service = request.json.get('service')
    if not service:
        return jsonify({"error": "Service not provided"}), 400
        
    supabase_client.from_('user_integrations').delete().match({'user_id': str(user.id), 'service': service}).execute()
    
    CacheManager.delete(f"cache:integrations:{user.id}")
    return jsonify({"message": "Disconnected"}), 200


@api_bp.route('/memories', methods=['GET'])
@limiter.limit('100 per minute')
def list_memories():
    """
    List authenticated user's memories from agno_memories table.
    Query params: limit (optional, default 100)
    """
    user, error = get_user_from_token(request)
    if error:
        return jsonify({"error": error[0]}), error[1]

    try:
        limit = request.args.get("limit", default=100, type=int) or 100
        limit = max(1, min(limit, 500))
        cache_key = f"cache:memories:{user.id}:{limit}"
        cached_data = CacheManager.get(cache_key)
        if cached_data:
            return jsonify(cached_data), 200

        response = (
            supabase_client
            .table("agno_memories")
            .select("*")
            .eq("user_id", str(user.id))
            .order("updated_at", desc=True)
            .limit(limit)
            .execute()
        )
        response_data = {"ok": True, "memories": response.data or []}
        CacheManager.set(cache_key, response_data, ttl_seconds=3600)
        return jsonify(response_data), 200
    except Exception as e:
        logger.error(f"list memories failed: {e}", exc_info=True)
        return jsonify({"ok": False, "error": "failed to load memories"}), 500


@api_bp.route('/memories', methods=['POST'])
@limiter.limit('100 per minute')
def create_memory():
    """
    Create a new user memory in agno_memories.
    body: { memory, input?, agent_id?, team_id?, topics?, memory_id? }
    """
    user, error = get_user_from_token(request)
    if error:
        return jsonify({"error": error[0]}), error[1]

    body = request.json or {}
    memory = body.get("memory")
    if memory is None:
        return jsonify({"ok": False, "error": "memory is required"}), 400

    memory_id = body.get("memory_id") or str(uuid.uuid4())
    input_text = body.get("input")
    agent_id = body.get("agent_id")
    team_id = body.get("team_id")
    topics = body.get("topics")

    if topics is not None and not isinstance(topics, (list, dict, str)):
        return jsonify({"ok": False, "error": "topics must be a JSON value"}), 400

    row = {
        "memory_id": str(memory_id),
        "memory": memory,
        "input": input_text,
        "agent_id": agent_id,
        "team_id": team_id,
        "user_id": str(user.id),
        "topics": topics,
        "updated_at": int(time.time()),
    }

    try:
        response = (
            supabase_client
            .table("agno_memories")
            .insert(row)
            .execute()
        )
        inserted = (response.data or [None])[0]
        CacheManager.invalidate_pattern(f"cache:memories:{user.id}:*")
        return jsonify({"ok": True, "memory": inserted, "memory_id": memory_id}), 201
    except Exception as e:
        logger.error(f"create memory failed: {e}", exc_info=True)
        return jsonify({"ok": False, "error": "failed to create memory"}), 500


@api_bp.route('/memories/<memory_id>', methods=['PUT', 'PATCH', 'DELETE'])
@limiter.limit('100 per minute')
def memory_by_id(memory_id):
    """
    Update or delete a memory by memory_id for authenticated user.
    """
    user, error = get_user_from_token(request)
    if error:
        return jsonify({"error": error[0]}), error[1]

    try:
        existing_resp = (
            supabase_client
            .table("agno_memories")
            .select("*")
            .eq("memory_id", str(memory_id))
            .eq("user_id", str(user.id))
            .limit(1)
            .execute()
        )
        existing = (existing_resp.data or [None])[0]
        if not existing:
            return jsonify({"ok": False, "error": "memory not found"}), 404

        if request.method == 'DELETE':
            (
                supabase_client
                .table("agno_memories")
                .delete()
                .eq("memory_id", str(memory_id))
                .eq("user_id", str(user.id))
                .execute()
            )
            CacheManager.invalidate_pattern(f"cache:memories:{user.id}:*")
            return jsonify({"ok": True, "deleted": True, "memory_id": memory_id}), 200

        body = request.json or {}
        update_data = {"updated_at": int(time.time())}

        if "memory" in body:
            if body.get("memory") is None:
                return jsonify({"ok": False, "error": "memory cannot be null"}), 400
            update_data["memory"] = body.get("memory")
        if "input" in body:
            update_data["input"] = body.get("input")
        if "agent_id" in body:
            update_data["agent_id"] = body.get("agent_id")
        if "team_id" in body:
            update_data["team_id"] = body.get("team_id")
        if "topics" in body:
            topics = body.get("topics")
            if topics is not None and not isinstance(topics, (list, dict, str)):
                return jsonify({"ok": False, "error": "topics must be a JSON value"}), 400
            update_data["topics"] = topics

        if len(update_data.keys()) == 1:
            return jsonify({"ok": False, "error": "no fields provided to update"}), 400

        updated_resp = (
            supabase_client
            .table("agno_memories")
            .update(update_data)
            .eq("memory_id", str(memory_id))
            .eq("user_id", str(user.id))
            .execute()
        )
        updated = (updated_resp.data or [None])[0]
        CacheManager.invalidate_pattern(f"cache:memories:{user.id}:*")
        return jsonify({"ok": True, "memory": updated, "memory_id": memory_id}), 200
    except Exception as e:
        logger.error(f"memory by id failed: {e}", exc_info=True)
        return jsonify({"ok": False, "error": "failed to process memory request"}), 500


@api_bp.route('/composio/status', methods=['GET'])
@limiter.limit('30 per minute')
def composio_status():
    """
    Returns Composio connection status for the authenticated user and toolkit.
    """
    user, error = get_user_from_token(request)
    if error:
        return jsonify({"error": error[0]}), error[1]

    toolkit = request.args.get('toolkit', 'GOOGLESHEETS').upper()
    
    cache_key = f"cache:composio_status:{user.id}:{toolkit}"
    cached_data = CacheManager.get(cache_key)
    if cached_data:
        return jsonify(cached_data), 200

    try:
        client = ComposioClient()
        accounts = client.list_connected_accounts(user_id=str(user.id), toolkit_slug=toolkit)
        connected = any(str(a.get("status", "")).upper() == "ACTIVE" for a in accounts)
        active_account = next((a for a in accounts if str(a.get("status", "")).upper() == "ACTIVE"), None)
        response_data = {
            "toolkit": toolkit,
            "connected": connected,
            "active_connected_account_id": active_account.get("id") if active_account else None,
            "accounts": [
                {
                    "id": a.get("id"),
                    "status": a.get("status"),
                    "toolkit_slug": ((a.get("toolkit") or {}).get("slug") if isinstance(a.get("toolkit"), dict) else None),
                }
                for a in accounts
            ],
        }
        CacheManager.set(cache_key, response_data, ttl_seconds=3600)
        return jsonify(response_data), 200
    except ComposioApiError as exc:
        return jsonify({"error": str(exc)}), 502
    except Exception as exc:
        logger.error("Unexpected Composio status error: %s", exc, exc_info=True)
        return jsonify({"error": "Failed to get Composio status"}), 500


@api_bp.route('/composio/disconnect', methods=['POST'])
@limiter.limit('10 per minute')
def composio_disconnect():
    """
    Disconnects Composio connected account(s) for a toolkit.
    If connected_account_id is provided, disconnects only that account.
    """
    user, error = get_user_from_token(request)
    if error:
        return jsonify({"error": error[0]}), error[1]

    body = request.json or {}
    toolkit = (body.get('toolkit') or 'GOOGLESHEETS').upper()
    connected_account_id = body.get('connected_account_id')

    try:
        client = ComposioClient()
        deleted_ids = []

        if connected_account_id:
            client.delete_connected_account(connected_account_id)
            deleted_ids.append(connected_account_id)
        else:
            accounts = client.list_connected_accounts(user_id=str(user.id), toolkit_slug=toolkit)
            for account in accounts:
                account_id = account.get("id")
                if account_id:
                    client.delete_connected_account(account_id)
                    deleted_ids.append(account_id)

        CacheManager.delete(f"cache:composio_status:{user.id}:{toolkit}")
        CacheManager.delete(f"cache:composio_status:{user.id}:{toolkit}")
        return jsonify({
            "toolkit": toolkit,
            "disconnected_count": len(deleted_ids),
            "disconnected_connected_account_ids": deleted_ids,
        }), 200
    except ComposioApiError as exc:
        return jsonify({"error": str(exc)}), 502
    except Exception as exc:
        logger.error("Unexpected Composio disconnect error: %s", exc, exc_info=True)
        return jsonify({"error": "Failed to disconnect Composio account"}), 500


@api_bp.route('/composio/connect-url', methods=['GET', 'POST'])
@limiter.limit('10 per minute')
def composio_connect_url():
    """
    Generates a Composio connected-account link for the authenticated user.
    """
    user, error = get_user_from_token(request)
    if error:
        return jsonify({"error": error[0]}), error[1]

    body = request.json if request.method == 'POST' and request.is_json else {}
    toolkit = (request.args.get('toolkit') or (body or {}).get('toolkit') or 'GOOGLESHEETS').upper()
    callback_url = request.args.get('callback_url') or (body or {}).get('callback_url') or config.FRONTEND_URL
    request_auth_config_id = request.args.get('auth_config_id') or (body or {}).get('auth_config_id')
    auth_config_id = _resolve_auth_config_id(toolkit, request_auth_config_id)
    if not auth_config_id:
        return jsonify({
            "error": (
                f"Auth config id is required for toolkit '{toolkit}'. "
                f"Set COMPOSIO_{toolkit}_AUTH_CONFIG_ID in backend env or provide auth_config_id."
            )
        }), 400

    try:
        client = ComposioClient()
        result = client.create_connected_account_link(
            user_id=str(user.id),
            auth_config_id=auth_config_id,
            callback_url=callback_url,
        )
        redirect_url = (
            result.get("redirect_url")
            or result.get("redirectUrl")
            or result.get("url")
            or result.get("link")
        )
        return jsonify({
            "toolkit": toolkit,
            "auth_config_id": auth_config_id,
            "callback_url": callback_url,
            "redirect_url": redirect_url,
            "raw": result,
        }), 200
    except ComposioApiError as exc:
        return jsonify({"error": str(exc)}), 502
    except Exception as exc:
        logger.error("Unexpected Composio connect-url error: %s", exc, exc_info=True)
        return jsonify({"error": "Failed to generate Composio connect url"}), 500


@api_bp.route('/composio/tools', methods=['GET'])
@limiter.limit('30 per minute')
def composio_tools():
    """
    Lists available Composio tools for a toolkit.
    """
    user, error = get_user_from_token(request)
    if error:
        return jsonify({"error": error[0]}), error[1]

    _ = user  # authenticated endpoint; user is currently not needed for listing
    toolkit = request.args.get('toolkit', 'GOOGLESHEETS').upper()
    important_only = request.args.get('important', 'true').lower() == 'true'

    try:
        client = ComposioClient()
        tools = client.list_tools(toolkit_slug=toolkit, important_only=important_only)
        return jsonify({"toolkit": toolkit, "count": len(tools), "tools": tools}), 200
    except ComposioApiError as exc:
        return jsonify({"error": str(exc)}), 502
    except Exception as exc:
        logger.error("Unexpected Composio tools error: %s", exc, exc_info=True)
        return jsonify({"error": "Failed to list Composio tools"}), 500


@api_bp.route('/generate-upload-url', methods=['POST'])
@limiter.limit('20 per minute')
def generate_upload_url():
    """
    Generates a pre-signed URL for securely uploading a file to Supabase storage.
    The file is placed in a user-specific folder.
    """
    user, error = get_user_from_token(request)
    if error:
        return jsonify({"error": error[0]}), error[1]
        
    file_name = request.json.get('fileName')
    if not file_name:
        return jsonify({"error": "fileName is required"}), 400
        
    # Create a unique path for the file to prevent collisions
    file_path = f"{user.id}/{uuid.uuid4()}/{file_name}"
    
    upload_details = supabase_client.storage.from_('media-uploads').create_signed_upload_url(file_path)

    return jsonify({"signedURL": upload_details['signed_url'], "path": upload_details['path']}), 200


@api_bp.route('/user-files/upload-link', methods=['POST'])
def user_files_upload_link():
    """
    Generate a signed upload URL for persistent user file vault uploads.
    body: { fileName, mimeType?, sizeBytes? }
    """
    user, error = get_user_from_token(request)
    if error:
        return jsonify({"error": error[0]}), error[1]

    body = request.json or {}
    file_name = body.get("fileName")
    mime_type = body.get("mimeType")
    size_bytes = body.get("sizeBytes")
    if not file_name:
        return jsonify({"error": "fileName is required"}), 400

    try:
        result = create_user_file_upload_link(
            user_id=str(user.id),
            file_name=str(file_name),
            mime_type=str(mime_type or "application/octet-stream"),
            size_bytes=int(size_bytes or 0),
        )
        return jsonify(
            {
                "ok": True,
                "uploadUrl": result["upload_url"],
                "path": result["path"],
                "bucket": result["bucket"],
                "fileName": result["file_name"],
                "mimeType": result["mime_type"],
                "sizeBytes": result["size_bytes"],
            }
        ), 200
    except PermissionError as e:
        return jsonify({"ok": False, "error": str(e)}), 403
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except Exception as e:
        logger.error("user-files/upload-link failed: %s", e, exc_info=True)
        return jsonify({"ok": False, "error": "failed to generate upload link"}), 500


@api_bp.route('/user-files/register', methods=['POST'])
def user_files_register():
    """
    Register a successfully uploaded file into user vault metadata.
    body: { path, fileName?, mimeType?, sizeBytes?, tags? }
    """
    user, error = get_user_from_token(request)
    if error:
        return jsonify({"error": error[0]}), error[1]

    body = request.json or {}
    path = body.get("path")
    if not path:
        return jsonify({"error": "path is required"}), 400

    try:
        tags = body.get("tags")
        if tags is None:
            tags = []
        if not isinstance(tags, list):
            return jsonify({"ok": False, "error": "tags must be an array"}), 400

        content_base64 = body.get("contentBase64")
        if content_base64:
            row = upload_user_file_from_base64(
                user_id=str(user.id),
                file_name=body.get("fileName") or body.get("name") or "file.bin",
                mime_type=body.get("mimeType"),
                content_base64=str(content_base64),
                size_bytes=body.get("sizeBytes"),
                tags=tags,
            )
        else:
            row = register_user_file(
                user_id=str(user.id),
                path=str(path),
                file_name=body.get("fileName"),
                mime_type=body.get("mimeType"),
                size_bytes=body.get("sizeBytes"),
                tags=tags,
            )
        CacheManager.invalidate_pattern(f"cache:user_files:{user.id}:*")
        return jsonify({"ok": True, "file": row}), 200
    except PermissionError as e:
        return jsonify({"ok": False, "error": str(e)}), 403
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except Exception as e:
        logger.error("user-files/register failed: %s", e, exc_info=True)
        return jsonify({"ok": False, "error": "failed to register uploaded file"}), 500


@api_bp.route('/user-files/upload', methods=['POST'])
def user_files_upload():
    """
    Upload a file directly into Turso-backed file vault.
    body: { fileName, mimeType?, contentBase64, sizeBytes?, tags? }
    """
    user, error = get_user_from_token(request)
    if error:
        return jsonify({"error": error[0]}), error[1]

    body = request.json or {}
    file_name = body.get("fileName")
    content_base64 = body.get("contentBase64")
    if not file_name:
        return jsonify({"ok": False, "error": "fileName is required"}), 400
    if not content_base64:
        return jsonify({"ok": False, "error": "contentBase64 is required"}), 400

    tags = body.get("tags")
    if tags is None:
        tags = []
    if not isinstance(tags, list):
        return jsonify({"ok": False, "error": "tags must be an array"}), 400

    try:
        row = upload_user_file_from_base64(
            user_id=str(user.id),
            file_name=str(file_name),
            mime_type=body.get("mimeType"),
            content_base64=str(content_base64),
            size_bytes=body.get("sizeBytes"),
            tags=tags,
        )
        CacheManager.invalidate_pattern(f"cache:user_files:{user.id}:*")
        return jsonify({"ok": True, "file": row}), 200
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except Exception as e:
        logger.error("user-files upload failed: %s", e, exc_info=True)
        return jsonify({"ok": False, "error": "failed to upload file"}), 500


@api_bp.route('/user-files', methods=['GET'])
def user_files_list():
    """
    List persistent user vault files.
    Query params: limit, search, file_type
    """
    user, error = get_user_from_token(request)
    if error:
        return jsonify({"error": error[0]}), error[1]

    try:
        limit = request.args.get("limit", default=100, type=int) or 100
        search = (request.args.get("search") or "").strip()
        file_type = (request.args.get("file_type") or "all").strip().lower()
        
        cache_key = f"cache:user_files:{user.id}:{limit}:{search}:{file_type}"
        cached_data = CacheManager.get(cache_key)
        if cached_data:
            return jsonify(cached_data), 200
            
        rows = list_user_files(
            user_id=str(user.id),
            limit=limit,
            search=search,
            file_type=file_type,
            signed_url_expiry=3600,
        )
        response_data = {"ok": True, "files": rows, "count": len(rows)}
        CacheManager.set(cache_key, response_data, ttl_seconds=3600)
        return jsonify(response_data), 200
    except Exception as e:
        logger.error("user-files list failed: %s", e, exc_info=True)
        return jsonify({"ok": False, "error": "failed to list user files"}), 500


@api_bp.route('/user-files/<file_id>/content', methods=['GET'])
def user_files_content(file_id):
    """
    Read text content preview for a user vault file.
    """
    user, error = get_user_from_token(request)
    if error:
        return jsonify({"error": error[0]}), error[1]

    try:
        max_chars = request.args.get("max_chars", default=40000, type=int) or 40000
        row = read_user_file_text(user_id=str(user.id), file_id=str(file_id), max_chars=max_chars)
        CacheManager.invalidate_pattern(f"cache:user_files:{user.id}:*")
        return jsonify({"ok": True, "file": row}), 200
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 404
    except Exception as e:
        logger.error("user-files content failed: %s", e, exc_info=True)
        return jsonify({"ok": False, "error": "failed to read file content"}), 500


@api_bp.route('/user-files/<file_id>/download', methods=['GET'])
def user_files_download(file_id):
    """
    Download raw bytes for one vault file.
    """
    user, error = get_user_from_token(request)
    if error:
        return jsonify({"error": error[0]}), error[1]

    try:
        meta, data = get_user_file_bytes(user_id=str(user.id), file_id=str(file_id))
        from flask import Response

        response = Response(data, mimetype=meta.get("mime_type") or "application/octet-stream")
        response.headers["Content-Disposition"] = f"inline; filename=\"{meta.get('file_name') or 'file.bin'}\""
        response.headers["Content-Length"] = str(len(data))
        return response
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 404
    except Exception as e:
        logger.error("user-files download failed: %s", e, exc_info=True)
        return jsonify({"ok": False, "error": "failed to download file"}), 500


@api_bp.route('/user-files/<file_id>', methods=['GET'])
def user_files_get(file_id):
    """
    Get metadata for one user vault file.
    """
    user, error = get_user_from_token(request)
    if error:
        return jsonify({"error": error[0]}), error[1]

    try:
        row = get_user_file(user_id=str(user.id), file_id=str(file_id), include_signed_url=True)
        CacheManager.invalidate_pattern(f"cache:user_files:{user.id}:*")
        return jsonify({"ok": True, "file": row}), 200
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 404
    except Exception as e:
        logger.error("user-files get failed: %s", e, exc_info=True)
        return jsonify({"ok": False, "error": "failed to load file details"}), 500


@api_bp.route('/user-files/<file_id>', methods=['DELETE'])
def user_files_delete(file_id):
    """
    Delete a user vault file and metadata.
    """
    user, error = get_user_from_token(request)
    if error:
        return jsonify({"error": error[0]}), error[1]

    try:
        result = delete_user_file(user_id=str(user.id), file_id=str(file_id))
        CacheManager.invalidate_pattern(f"cache:user_files:{user.id}:*")
        return jsonify({"ok": True, **result}), 200
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 404
    except Exception as e:
        logger.error("user-files delete failed: %s", e, exc_info=True)
        return jsonify({"ok": False, "error": "failed to delete file"}), 500


def _to_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _read_metric_value(container: Any, *keys: str) -> int:
    if not container:
        return 0

    if isinstance(container, dict):
        for key in keys:
            if key in container:
                return _to_int(container.get(key))
        return 0

    for key in keys:
        if hasattr(container, key):
            return _to_int(getattr(container, key))

    return 0


def _extract_assistant_metrics(run_output: Any) -> dict[str, int]:
    metrics = getattr(run_output, "metrics", None)
    if not metrics:
        return {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

    input_tokens = _read_metric_value(
        metrics,
        "input_tokens",
        "prompt_tokens",
        "prompt_token_count",
        "input_token_count",
    )
    output_tokens = _read_metric_value(
        metrics,
        "output_tokens",
        "completion_tokens",
        "candidate_tokens",
        "candidates_token_count",
        "output_token_count",
    )
    total_tokens = _read_metric_value(
        metrics,
        "total_tokens",
        "total_token_count",
    )

    # Some providers keep token data in nested provider/additional metrics fields.
    if input_tokens <= 0 and output_tokens <= 0:
        if isinstance(metrics, dict):
            metric_sources = [metrics.get("provider_metrics"), metrics.get("additional_metrics")]
        else:
            metric_sources = [getattr(metrics, "provider_metrics", None), getattr(metrics, "additional_metrics", None)]

        for source in metric_sources:
            input_tokens = max(
                input_tokens,
                _read_metric_value(source, "input_tokens", "prompt_tokens", "prompt_token_count", "input_token_count"),
            )
            output_tokens = max(
                output_tokens,
                _read_metric_value(
                    source,
                    "output_tokens",
                    "completion_tokens",
                    "candidate_tokens",
                    "candidates_token_count",
                    "output_token_count",
                ),
            )
            total_tokens = max(total_tokens, _read_metric_value(source, "total_tokens", "total_token_count"))

    # Last fallback: usage/token_usage payloads occasionally appear in run metadata.
    if input_tokens <= 0 and output_tokens <= 0:
        metadata = getattr(run_output, "metadata", None)
        usage_blob = None
        if isinstance(metadata, dict):
            usage_blob = metadata.get("usage") or metadata.get("token_usage")

        input_tokens = max(
            input_tokens,
            _read_metric_value(usage_blob, "input_tokens", "prompt_tokens", "prompt_token_count", "input_token_count"),
        )
        output_tokens = max(
            output_tokens,
            _read_metric_value(
                usage_blob,
                "output_tokens",
                "completion_tokens",
                "candidate_tokens",
                "candidates_token_count",
                "output_token_count",
            ),
        )
        total_tokens = max(total_tokens, _read_metric_value(usage_blob, "total_tokens", "total_token_count"))

    if total_tokens <= 0:
        total_tokens = input_tokens + output_tokens

    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
    }


def _log_assistant_token_usage(
    *,
    user_id: str,
    conversation_id: str,
    message_id: str,
    metrics: dict[str, int],
    source: str = "assistant_http",
) -> None:
    if (metrics.get("input_tokens", 0) <= 0) and (metrics.get("output_tokens", 0) <= 0):
        logger.warning(
            "Skipping assistant token usage log due to empty metrics: user=%s conversation=%s message=%s source=%s metrics=%s",
            user_id,
            conversation_id,
            message_id,
            source,
            metrics,
        )
        return

    try:
        convex_service = get_convex_usage_service()
        usage_window = get_usage_window_descriptor(user_id=str(user_id), refresh_window=False)
        result = convex_service.record_token_usage(
            user_id=str(user_id),
            conversation_id=str(conversation_id),
            message_id=str(message_id),
            metrics=metrics,
            usage_window=usage_window,
            source=source,
        )
        if result is None:
            logger.warning(
                "Assistant token usage was not recorded (Convex unavailable): user=%s conversation=%s message=%s source=%s metrics=%s",
                user_id,
                conversation_id,
                message_id,
                source,
                metrics,
            )
            return

        logger.info(
            "Assistant token usage recorded: user=%s conversation=%s message=%s source=%s input=%s output=%s total=%s",
            user_id,
            conversation_id,
            message_id,
            source,
            metrics.get("input_tokens", 0),
            metrics.get("output_tokens", 0),
            metrics.get("total_tokens", 0),
        )
    except Exception as exc:
        logger.warning(
            "Failed to log assistant token usage for user=%s conversation=%s message=%s: %s",
            user_id,
            conversation_id,
            message_id,
            exc,
        )


def _extract_media_upload_path(url: str) -> Optional[str]:
    if not url:
        return None
    marker = "media-uploads/"
    if marker not in url:
        return None
    relative_path = url.split(marker, 1)[1]
    relative_path = relative_path.split("?", 1)[0].strip("/")
    if not relative_path:
        return None
    return unquote(relative_path)


def _decode_data_url_image(data_url: str) -> bytes | None:
    if not data_url or not isinstance(data_url, str):
        return None
    if not data_url.startswith("data:image/") or ";base64," not in data_url:
        return None
    try:
        encoded = data_url.split(";base64,", 1)[1]
        return base64.b64decode(encoded, validate=True)
    except Exception:
        return None


def _extract_run_response_text(run_response: Any) -> str:
    if hasattr(run_response, 'content') and run_response.content:
        return str(run_response.content)
    if hasattr(run_response, 'messages') and run_response.messages:
        for msg in reversed(run_response.messages):
            if hasattr(msg, 'role') and msg.role == 'assistant' and hasattr(msg, 'content') and msg.content:
                return str(msg.content)
    return ""


@api_bp.route('/assistant/upload-link', methods=['POST'])
def assistant_upload_link():
    """
    Generate a signed upload URL for assistant image analysis.
    Requires a valid user auth token.
    """
    user, error = get_user_from_token(request)
    if error:
        return jsonify({"error": error[0]}), error[1]

    try:
        data = request.json or {}
        file_extension = str(data.get('extension', 'jpg')).strip().lower().lstrip(".")
        if not file_extension.isalnum():
            file_extension = "jpg"

        file_name = f"{uuid.uuid4()}.{file_extension}"
        file_path = f"{user.id}/assistant-temp/{file_name}"

        logger.info("Generating assistant upload link for user %s path=%s", user.id, file_path)

        upload_details = supabase_client.storage.from_('media-uploads').create_signed_upload_url(file_path)
        public_url = supabase_client.storage.from_('media-uploads').get_public_url(file_path)

        return jsonify({
            "uploadUrl": upload_details['signed_url'],
            "publicUrl": public_url,
            "path": file_path
        }), 200
    except Exception as e:
        logger.error("Error generating assistant upload link: %s", e, exc_info=True)
        return jsonify({"error": "Failed to generate upload link"}), 500


@api_bp.route('/mindspace/ask', methods=['POST'])
@limiter.limit('30 per minute')
def mindspace_ask():
    """
    Ask a follow-up question about a saved Mindspace analysis.
    Runs Aetheria in a constrained mode: internet search only, no third-party
    platform, browser, Google, Supabase, Vercel, GitHub, media, mobile, or file tools.
    """
    import traceback
    from agno.media import Image
    from assistant import get_llm_os

    user, error = get_user_from_token(request)
    if error:
        return jsonify({"error": error[0], "response": "Please sign in to continue."}), error[1]

    try:
        enforce_usage_limit(str(user.id))
    except UsageLimitExceeded as exc:
        return jsonify({
            "error": str(exc),
            "code": "subscription_limit_exceeded",
            "limit_info": exc.summary,
            "response": str(exc),
        }), 429
    except Exception as exc:
        logger.error("Usage limit check failed for mindspace_ask user=%s: %s", user.id, exc, exc_info=True)

    try:
        data = request.json or {}
        question = str(data.get("question") or "").strip()
        analysis_text = str(data.get("analysisText") or "").strip()
        analysis_title = str(data.get("title") or "Mindspace Analysis").strip()[:160]
        analysis_id = str(data.get("analysisId") or "").strip() or str(uuid.uuid4())
        image_data = str(data.get("imageData") or "")
        previous_questions = data.get("previousQuestions") or []

        if not question:
            return jsonify({"error": "Question is required", "response": "Ask a question first."}), 400
        if not analysis_text and not image_data:
            return jsonify({"error": "Mindspace context is required", "response": "This Mindspace run has no saved context."}), 400

        history_lines = []
        if isinstance(previous_questions, list):
            for entry in previous_questions[-6:]:
                if not isinstance(entry, dict):
                    continue
                prev_q = str(entry.get("question") or "").strip()
                prev_a = str(entry.get("answer") or "").strip()
                if prev_q and prev_a:
                    history_lines.append(f"Q: {prev_q}\nA: {prev_a}")

        prompt = "\n".join([
            "You are Aetheria AI answering a follow-up question about one saved Mindspace screen analysis.",
            "Use only the saved analysis, the attached screenshot if present, and internet search when current facts are needed.",
            "Do not attempt to use or reference browser, GitHub, Vercel, Supabase, Google, mobile, file, deployment, email, drive, sheet, or media-generation tools.",
            "Answer directly and concisely. If the question cannot be answered from the saved context, say what is missing.",
            "",
            f"Mindspace title: {analysis_title}",
            f"Mindspace analysis id: {analysis_id}",
            "",
            "Saved analysis:",
            analysis_text or "(No text analysis was saved.)",
            "",
            "Previous follow-up Q&A:",
            "\n\n".join(history_lines) if history_lines else "(None)",
            "",
            "User question:",
            question,
        ])

        images = []
        image_bytes = _decode_data_url_image(image_data)
        if image_bytes:
            images.append(Image(content=image_bytes))

        message_id = str(uuid.uuid4())
        team = get_llm_os(
            user_id=str(user.id),
            session_info={"device_type": "mobile", "source": "mindspace"},
            internet_search=True,
            coding_assistant=False,
            Planner_Agent=False,
            enable_supabase=False,
            use_memory=False,
            use_session_summaries=False,
            debug_mode=False,
            enable_github=False,
            enable_vercel=False,
            enable_google_email=False,
            enable_google_drive=False,
            enable_google_sheets=False,
            enable_composio_whatsapp=False,
            enable_browser=False,
            enable_computer_control=False,
            browser_tools_config=None,
            computer_tools_config=None,
            custom_tool_config=None,
            session_id=f"mindspace-{analysis_id}",
            message_id=message_id,
            enable_user_file_vault=False,
        )

        result = team.run(
            input=prompt,
            images=images or None,
            session_id=f"mindspace-{analysis_id}",
            stream=False,
            stream_intermediate_steps=False,
            add_history_to_context=False,
        )

        response_text = _extract_run_response_text(result)
        if not response_text:
            response_text = "I couldn't generate a response for this Mindspace question. Please try again."

        metrics = _extract_assistant_metrics(result)
        _log_assistant_token_usage(
            user_id=str(user.id),
            conversation_id=f"mindspace-{analysis_id}",
            message_id=message_id,
            metrics=metrics,
            source="mindspace_ask",
        )

        return jsonify({"response": response_text}), 200
    except Exception as e:
        logger.error("Critical mindspace_ask error for user=%s: %s", user.id, e, exc_info=True)
        traceback.print_exc()
        return jsonify({
            "error": str(e),
            "response": "I'm having trouble answering that Mindspace question. Please try again in a moment."
        }), 500


@api_bp.route('/assistant/chat', methods=['POST'])
def assistant_chat():
    """
    Authenticated voice assistant endpoint for Android native features.
    Supports text and multimodal (image) inputs with usage enforcement.
    """
    import traceback
    from system_assistant import get_system_assistant
    from agno.media import Image

    user, error = get_user_from_token(request)
    if error:
        return jsonify({
            "error": error[0],
            "response": "Please sign in to continue."
        }), error[1]

    try:
        enforce_usage_limit(str(user.id))
    except UsageLimitExceeded as exc:
        return jsonify({
            "error": str(exc),
            "code": "subscription_limit_exceeded",
            "limit_info": exc.summary,
            "response": str(exc),
        }), 429
    except Exception as exc:
        logger.error("Usage limit check failed for assistant_chat user=%s: %s", user.id, exc, exc_info=True)

    try:
        data = request.json or {}
        user_message = data.get('message', '')
        image_urls = data.get('images', []) or []
        conversation_id = str(data.get("session_id") or data.get("conversationId") or uuid.uuid4())
        message_id = str(data.get("id") or uuid.uuid4())
        assistant_target = str(
            data.get("assistant_target")
            or data.get("assistantTarget")
            or ""
        ).strip().lower()
        assistant_sid = str(
            data.get("assistant_sid")
            or data.get("assistantSocketSid")
            or data.get("socketSid")
            or ""
        ).strip()

        if not user_message:
            return jsonify({"error": "Message is required", "response": "I didn't catch that. Please try again."}), 400

        msg_preview = (user_message[:75] + '...') if len(user_message) > 75 else user_message
        logger.info(
            "Assistant query user=%s conversation=%s target=%s images=%s preview=%s",
            user.id,
            conversation_id,
            assistant_target or "system-assistant",
            len(image_urls),
            msg_preview,
        )

        mobile_tools_config = None
        if assistant_sid:
            if config.REDIS_URL:
                try:
                    mobile_redis_client = redis.from_url(config.REDIS_URL, decode_responses=True)
                    mobile_tools_config = {
                        "sid": assistant_sid,
                        "socketio": socketio,
                        "redis_client": mobile_redis_client,
                        "conversation_id": conversation_id,
                        "message_id": message_id,
                    }
                    logger.info(
                        "Assistant chat enabling mobile tools user=%s conversation=%s sid=%s",
                        user.id,
                        conversation_id,
                        assistant_sid,
                    )
                except Exception as redis_err:
                    logger.warning(
                        "Assistant chat mobile tools unavailable (redis init failed) user=%s sid=%s err=%s",
                        user.id,
                        assistant_sid,
                        redis_err,
                    )
            else:
                logger.warning(
                    "Assistant chat received assistant_sid but REDIS_URL is not configured. user=%s sid=%s",
                    user.id,
                    assistant_sid,
                )
        else:
            logger.info(
                "Assistant chat request without assistant_sid user=%s conversation=%s",
                user.id,
                conversation_id,
            )

        if assistant_target and assistant_target != "system-assistant":
            logger.warning(
                "assistant_chat received unsupported assistant_target=%s for user=%s conversation=%s; defaulting to system assistant",
                assistant_target,
                user.id,
                conversation_id,
            )

        agent = get_system_assistant(mobile_tools_config=mobile_tools_config)

        try:
            images = []
            if image_urls:
                expected_prefix = f"{user.id}/assistant-temp/"
                for url in image_urls:
                    try:
                        relative_path = _extract_media_upload_path(url)
                        if relative_path and relative_path.startswith(expected_prefix):
                            logger.info("Downloading assistant image from storage path: %s", relative_path)
                            image_bytes = supabase_client.storage.from_('media-uploads').download(relative_path)
                            images.append(Image(content=image_bytes))
                            continue

                        logger.info("Downloading assistant image via URL: %s", url)
                        resp = requests.get(url, timeout=10)
                        if resp.status_code == 200:
                            images.append(Image(content=resp.content))
                        else:
                            logger.error("Failed to fetch image URL %s status=%s", url, resp.status_code)
                    except Exception as img_err:
                        logger.error("Error processing image %s: %s", url, img_err)

            result = agent.run(input=user_message, images=images, stream=False)

            response_text = ""
            if hasattr(result, 'content') and result.content:
                response_text = result.content
            elif hasattr(result, 'messages') and result.messages:
                for msg in reversed(result.messages):
                    if hasattr(msg, 'role') and msg.role == 'assistant' and hasattr(msg, 'content'):
                        response_text = msg.content
                        break

            if not response_text:
                response_text = "I processed your request but couldn't generate a response. Please try again."

            metrics = _extract_assistant_metrics(result)
            _log_assistant_token_usage(
                user_id=str(user.id),
                conversation_id=conversation_id,
                message_id=message_id,
                metrics=metrics,
                source="assistant_http_vision" if image_urls else "assistant_http_text",
            )

            return jsonify({"response": response_text}), 200
        except Exception as agent_error:
            logger.error("Assistant agent error for user=%s: %s", user.id, agent_error)
            traceback.print_exc()
            return jsonify({"response": generate_fallback_response(user_message)}), 200
    except Exception as e:
        logger.error("Critical assistant_chat error for user=%s: %s", user.id, e)
        traceback.print_exc()
        return jsonify({
            "error": str(e),
            "response": "I'm having trouble connecting. Please try again in a moment."
        }), 500


@api_bp.route('/mic/transcribe', methods=['POST'])
@limiter.limit('30 per minute')
def mic_transcribe():
    """
    Authenticated cloud-only mic transcription endpoint.
    Converts a short mic recording into text using the configured OpenRouter
    multimodal mic model.
    """
    from mic_agent import MicAgentError, mic_agent

    user, error = get_user_from_token(request)
    if error:
        return jsonify({"ok": False, "error": error[0]}), error[1]

    try:
        enforce_usage_limit(str(user.id))
    except UsageLimitExceeded as exc:
        return jsonify({
            "ok": False,
            "error": str(exc),
            "code": "subscription_limit_exceeded",
            "limit_info": exc.summary,
        }), 429
    except Exception as exc:
        logger.error("Usage limit check failed for mic_transcribe user=%s: %s", user.id, exc, exc_info=True)

    data = request.json or {}
    audio_base64 = data.get("audio") or data.get("audio_base64") or ""
    audio_format = data.get("format") or "wav"
    language = data.get("language") or "en"

    try:
        result = mic_agent.transcribe(
            audio_base64=audio_base64,
            audio_format=audio_format,
            language=language,
        )
        logger.info(
            "Mic transcription complete user=%s model=%s text_len=%s",
            user.id,
            result.model,
            len(result.text),
        )
        return jsonify({
            "ok": True,
            "text": result.text,
            "raw_text": result.raw_text,
            "backend": "openrouter_mic_agent",
            "model": result.model,
            "usage": result.usage,
        }), 200
    except MicAgentError as exc:
        logger.warning("Mic transcription rejected user=%s: %s", user.id, exc)
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        logger.error("Mic transcription failed user=%s: %s", user.id, exc, exc_info=True)
        return jsonify({"ok": False, "error": "mic transcription failed"}), 502


def generate_fallback_response(query: str) -> str:
    """Generate smart fallback responses when AI is unavailable."""
    return "This is taking longer than expected. I'm still working on your request, so please wait a moment and try again if the answer doesn't appear."


@api_bp.route('/healthz')
@limiter.limit('30 per minute')
def health_check():
    """A simple health check endpoint for monitoring."""
    return "OK", 200


@api_bp.route('/health')
@limiter.limit('10 per minute')
def health():
    """Detailed health check endpoint with memory stats."""
    try:
        import psutil
        import os
        
        process = psutil.Process(os.getpid())
        memory_info = process.memory_info()
        
        return jsonify({
            "status": "ok",
            "message": "Backend is running",
            "service": "aios-web",
            "memory": {
                "rss_mb": round(memory_info.rss / 1024 / 1024, 2),
                "vms_mb": round(memory_info.vms / 1024 / 1024, 2),
                "percent": round(process.memory_percent(), 2)
            },
            "cpu_percent": round(process.cpu_percent(interval=0.1), 2)
        }), 200
    except ImportError:
        # psutil not available, return basic health
        return jsonify({
            "status": "ok",
            "message": "Backend is running",
            "service": "aios-web"
        }), 200


@api_bp.route('/deploy/preflight', methods=['GET'])
def deploy_preflight():
    """
    Validate deploy platform prerequisites and initialize deploy tables.
    """
    user, error = get_user_from_token(request)
    if error:
        return jsonify({"error": error[0]}), error[1]
    _ = user

    try:
        ensure_deploy_tables()
        result = preflight_check()
        return jsonify(result), 200 if result.get("ok") else 503
    except Exception as e:
        logger.error(f"Deploy preflight error: {e}", exc_info=True)
        return jsonify({"ok": False, "error": str(e)}), 500


@api_bp.route('/deploy/projects', methods=['GET'])
def deploy_projects():
    """
    List deployed projects for authenticated user.
    Query params: limit (optional, default 20)
    """
    user, error = get_user_from_token(request)
    if error:
        return jsonify({"error": error[0]}), error[1]

    try:
        ensure_deploy_tables()
        limit = request.args.get("limit", default=20, type=int)
        
        cache_key = f"cache:deploy_projects:{user.id}:{limit}"
        cached_data = CacheManager.get(cache_key)
        if cached_data:
            return jsonify(cached_data), 200
            
        projects = list_deployed_projects(user_id=str(user.id), limit=limit or 20)
        response_data = {"ok": True, "projects": projects}
        CacheManager.set(cache_key, response_data, ttl_seconds=3600)
        return jsonify(response_data), 200
    except Exception as e:
        logger.error(f"deploy/projects failed: {e}", exc_info=True)
        return jsonify({"error": "failed to load deployed projects"}), 500


@api_bp.route('/deploy/files', methods=['GET'])
def deploy_files():
    """
    List files for a site's deployment from R2.
    Query params: site_id|site_ref, deployment_id (optional)
    """
    user, error = get_user_from_token(request)
    if error:
        return jsonify({"error": error[0]}), error[1]

    site_ref = request.args.get("site_id") or request.args.get("site_ref") or "default"
    deployment_id = request.args.get("deployment_id")

    try:
        ensure_deploy_tables()
        site = resolve_site_ref(user_id=str(user.id), site_ref=str(site_ref))
        files = list_deployment_files(
            site_id=str(site["id"]),
            user_id=str(user.id),
            deployment_id=str(deployment_id) if deployment_id else None,
        )
        return jsonify({
            "ok": True,
            "site_id": str(site["id"]),
            "deployment_id": deployment_id,
            "file_count": len(files),
            "files": files,
        }), 200
    except PermissionError as e:
        return jsonify({"error": str(e)}), 403
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error(f"deploy/files failed: {e}", exc_info=True)
        return jsonify({"error": "failed to load deployment files"}), 500


@api_bp.route('/deploy/file-content', methods=['GET'])
def deploy_file_content():
    """
    Get one deployed file's content.
    Query params: site_id|site_ref, path, deployment_id (optional), include_base64(optional bool)
    """
    user, error = get_user_from_token(request)
    if error:
        return jsonify({"error": error[0]}), error[1]

    site_ref = request.args.get("site_id") or request.args.get("site_ref") or "default"
    rel_path = (request.args.get("path") or "").strip()
    deployment_id = request.args.get("deployment_id")
    include_base64 = str(request.args.get("include_base64") or "").strip().lower() in {"1", "true", "yes"}
    if not rel_path:
        return jsonify({"error": "path is required"}), 400

    try:
        ensure_deploy_tables()
        site = resolve_site_ref(user_id=str(user.id), site_ref=str(site_ref))
        data = get_deployment_file_bytes(
            site_id=str(site["id"]),
            user_id=str(user.id),
            path=rel_path,
            deployment_id=str(deployment_id) if deployment_id else None,
        )

        is_binary = b"\x00" in (data or b"")
        if is_binary:
            encoded = base64.b64encode(data or b"").decode("utf-8") if include_base64 else None
            return jsonify({
                "ok": True,
                "path": rel_path,
                "is_binary": True,
                "size_bytes": len(data or b""),
                "content": None,
                "content_base64": encoded,
            }), 200

        text_content = (data or b"").decode("utf-8", errors="replace")
        lim = 300_000
        truncated = text_content[:lim]
        encoded = base64.b64encode(data or b"").decode("utf-8") if include_base64 else None
        return jsonify({
            "ok": True,
            "path": rel_path,
            "is_binary": False,
            "size_bytes": len(data or b""),
            "truncated": len(text_content) > len(truncated),
            "content": truncated,
            "content_base64": encoded,
        }), 200
    except PermissionError as e:
        return jsonify({"error": str(e)}), 403
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error(f"deploy/file-content failed: {e}", exc_info=True)
        return jsonify({"error": "failed to load deployment file content"}), 500


@api_bp.route('/deploy/databases', methods=['GET'])
def deploy_databases():
    """
    List provisioned site databases for authenticated user.
    Query params: limit (optional, default 50)
    """
    user, error = get_user_from_token(request)
    if error:
        return jsonify({"error": error[0]}), error[1]

    try:
        ensure_deploy_tables()
        limit = request.args.get("limit", default=50, type=int)
        databases = list_user_databases(user_id=str(user.id), limit=limit or 50)
        return jsonify({"ok": True, "databases": databases}), 200
    except Exception as e:
        logger.error(f"deploy/databases failed: {e}", exc_info=True)
        return jsonify({"error": "failed to load database list"}), 500


@api_bp.route('/deploy/site/init', methods=['POST'])
def deploy_site_init():
    """
    Create (or return existing) site metadata record.
    body: { site_id, project_name, slug }
    """
    user, error = get_user_from_token(request)
    if error:
        return jsonify({"error": error[0]}), error[1]

    body = request.json or {}
    site_id = body.get("site_id")
    project_name = body.get("project_name", "Untitled")
    slug = body.get("slug")
    if not site_id or not slug:
        return jsonify({"error": "site_id and slug are required"}), 400

    try:
        ensure_deploy_tables()
        site = create_or_get_site(
            site_id=str(site_id),
            user_id=str(user.id),
            project_name=str(project_name),
            slug=str(slug),
        )
        return jsonify({"ok": True, "site": site}), 200
    except PermissionError as e:
        return jsonify({"error": str(e)}), 403
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error(f"deploy/site/init failed: {e}", exc_info=True)
        return jsonify({"error": "failed to init site"}), 500


@api_bp.route('/deploy/assign-subdomain', methods=['POST'])
def deploy_assign_subdomain():
    """
    Assign and persist canonical hostname for a site.
    body: { site_id }
    """
    user, error = get_user_from_token(request)
    if error:
        return jsonify({"error": error[0]}), error[1]

    body = request.json or {}
    site_id = body.get("site_id")
    if not site_id:
        return jsonify({"error": "site_id is required"}), 400

    try:
        ensure_deploy_tables()
        result = assign_subdomain(site_id=str(site_id), user_id=str(user.id))
        return jsonify({"ok": True, **result}), 200
    except PermissionError as e:
        return jsonify({"error": str(e)}), 403
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error(f"deploy/assign-subdomain failed: {e}", exc_info=True)
        return jsonify({"error": "failed to assign subdomain"}), 500


@api_bp.route('/deploy/upload-site', methods=['POST'])
def deploy_upload_site():
    """
    Upload built site files to R2.
    body: { site_id, files: [{path, content_base64?, content?, content_type?}] }
    """
    user, error = get_user_from_token(request)
    if error:
        return jsonify({"error": error[0]}), error[1]

    body = request.json or {}
    site_id = body.get("site_id")
    files = body.get("files", [])
    if not site_id:
        return jsonify({"error": "site_id is required"}), 400
    if not isinstance(files, list) or not files:
        return jsonify({"error": "files must be a non-empty array"}), 400

    try:
        ensure_deploy_tables()
        result = upload_site_files(site_id=str(site_id), user_id=str(user.id), files=files)
        return jsonify({
            "ok": True,
            "deployment_id": result.deployment_id,
            "version": result.version,
            "r2_prefix": result.r2_prefix,
            "files_uploaded": result.files_uploaded,
        }), 200
    except PermissionError as e:
        return jsonify({"error": str(e)}), 403
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error(f"deploy/upload-site failed: {e}", exc_info=True)
        return jsonify({"error": f"failed to upload site files: {e}"}), 500


@api_bp.route('/deploy/provision-database', methods=['POST'])
def deploy_provision_database():
    """
    Create one Turso database per site and store encrypted credentials.
    body: { site_id }
    """
    user, error = get_user_from_token(request)
    if error:
        return jsonify({"error": error[0]}), error[1]

    body = request.json or {}
    site_id = body.get("site_id")
    if not site_id:
        return jsonify({"error": "site_id is required"}), 400

    try:
        ensure_deploy_tables()
        result = provision_turso_database(site_id=str(site_id), user_id=str(user.id))
        return jsonify({"ok": True, **result}), 200
    except PermissionError as e:
        return jsonify({"error": str(e)}), 403
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error(f"deploy/provision-database failed: {e}", exc_info=True)
        return jsonify({"error": "failed to provision database"}), 500


@api_bp.route('/deploy/get-db-credentials', methods=['POST'])
def deploy_get_db_credentials():
    """
    Retrieve per-site credentials for internal deploy inject flow.
    body: { site_id, include_admin?: bool }
    """
    user, error = get_user_from_token(request)
    if error:
        return jsonify({"error": error[0]}), error[1]

    body = request.json or {}
    site_id = body.get("site_id")
    include_admin = bool(body.get("include_admin", False))
    if not site_id:
        return jsonify({"error": "site_id is required"}), 400

    try:
        ensure_deploy_tables()
        creds = get_site_db_credentials(site_id=str(site_id), user_id=str(user.id), include_admin=include_admin)
        return jsonify({"ok": True, "credentials": creds}), 200
    except PermissionError as e:
        return jsonify({"error": str(e)}), 403
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error(f"deploy/get-db-credentials failed: {e}", exc_info=True)
        return jsonify({"error": "failed to get credentials"}), 500


@api_bp.route('/deploy/runtime/query', methods=['POST'])
def deploy_runtime_query():
    """
    Runtime database query endpoint for deployed websites.

    Modes:
    - Authenticated (Authorization bearer token): resolves site_id/site_ref under user ownership.
    - Anonymous (no auth): resolves site strictly from Origin/Referer hostname.

    body: { sql, params?: [], site_id?: str, site_ref?: str }
    """
    body = request.json or {}
    sql = body.get("sql")
    params = body.get("params", [])
    if not isinstance(params, list):
        return jsonify({"ok": False, "error": "params must be an array"}), 400

    try:
        cleaned_sql = _normalize_single_statement(str(sql or ""))
        ensure_deploy_tables()

        auth_header = (request.headers.get("Authorization") or "").strip()
        site_id = None
        site_hostname = None

        if auth_header.startswith("Bearer "):
            user, error = get_user_from_token(request)
            if error:
                return jsonify({"ok": False, "error": error[0]}), error[1]
            site_ref = body.get("site_id") or body.get("site_ref") or "default"
            site = resolve_site_ref(user_id=str(user.id), site_ref=str(site_ref))
            site_id = str(site["id"])
            site_hostname = site.get("hostname")
            creds = get_site_db_credentials(site_id=site_id, user_id=str(user.id), include_admin=False)
        else:
            origin_host = _extract_host_from_header(request.headers.get("Origin"))
            referer_host = _extract_host_from_header(request.headers.get("Referer"))
            host = origin_host or referer_host
            if not host:
                return jsonify({"ok": False, "error": "Origin or Referer header is required"}), 400

            site = resolve_public_site_hostname(hostname=host)
            site_id = str(site["id"])
            site_hostname = site.get("hostname")
            creds = get_site_runtime_db_credentials(site_id=site_id)

        result = _execute_hrana_query(
            hostname=creds["hostname"],
            token=creds["rw_token"],
            sql=cleaned_sql,
            params=params,
        )
        return jsonify(
            {
                "ok": True,
                "site_id": site_id,
                "hostname": site_hostname,
                "result": result,
            }
        ), 200
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except PermissionError as e:
        return jsonify({"ok": False, "error": str(e)}), 403
    except Exception as e:
        logger.error(f"deploy/runtime/query failed: {e}", exc_info=True)
        return jsonify({"ok": False, "error": "runtime database query failed"}), 500


@api_bp.route('/project/workspace/tree', methods=['POST'])
def project_workspace_tree():
    """
    List workspace files from sandbox for the current conversation.
    body: { conversation_id, path? }
    """
    user, error = get_user_from_token(request)
    if error:
        return jsonify({"error": error[0]}), error[1]

    body = request.json or {}
    conversation_id = str(body.get("conversation_id") or "").strip()
    if not conversation_id:
        return jsonify({"error": "conversation_id is required"}), 400

    path = str(body.get("path") or "/home/sandboxuser/workspace").strip()
    if not path.startswith("/home/sandboxuser/workspace"):
        return jsonify({"error": "path must be under /home/sandboxuser/workspace"}), 400

    try:
        redis_client = redis.from_url(config.REDIS_URL, decode_responses=True)
        session_json = redis_client.get(f"session:{conversation_id}")
        if not session_json:
            return jsonify({"ok": True, "files": [], "sandbox_id": None}), 200

        session_data = json.loads(session_json) if isinstance(session_json, str) else (session_json or {})
        if str(session_data.get("user_id")) != str(user.id):
            return jsonify({"error": "Unauthorized session access"}), 403

        sandbox_id = session_data.get("active_sandbox_id")
        if not sandbox_id:
            sandbox_ids = session_data.get("sandbox_ids", []) or []
            sandbox_id = sandbox_ids[-1] if sandbox_ids else None

        if not sandbox_id:
            return jsonify({"ok": True, "files": [], "sandbox_id": None}), 200

        if not config.SANDBOX_API_URL:
            return jsonify({"error": "SANDBOX_API_URL not configured"}), 500

        resp = requests.get(
            f"{config.SANDBOX_API_URL}/sessions/{sandbox_id}/files",
            params={"path": path},
            timeout=20,
        )
        if resp.status_code != 200:
            return jsonify({"error": f"failed to list sandbox files (HTTP {resp.status_code})"}), 502

        rows = (resp.json() or {}).get("files", []) or []
        rel_rows = []
        prefix = "/home/sandboxuser/workspace/"
        for row in rows:
            abs_path = str(row.get("path", ""))
            rel_path = abs_path[len(prefix):] if abs_path.startswith(prefix) else abs_path
            rel_rows.append({
                "path": rel_path,
                "size": int(row.get("size", 0) or 0),
            })

        return jsonify({
            "ok": True,
            "sandbox_id": sandbox_id,
            "path": path,
            "files": rel_rows,
            "count": len(rel_rows),
        }), 200
    except Exception as e:
        logger.error(f"project/workspace/tree failed: {e}", exc_info=True)
        return jsonify({"error": "failed to load workspace tree"}), 500


@api_bp.route('/project/workspace/file-content', methods=['POST'])
def project_workspace_file_content():
    """
    Get file content from sandbox workspace for active conversation.
    body: { conversation_id, path }
    """
    user, error = get_user_from_token(request)
    if error:
        return jsonify({"error": error[0]}), error[1]

    body = request.json or {}
    conversation_id = str(body.get("conversation_id") or "").strip()
    rel_path = str(body.get("path") or "").strip().replace("\\", "/")
    if not conversation_id:
        return jsonify({"error": "conversation_id is required"}), 400
    if not rel_path:
        return jsonify({"error": "path is required"}), 400
    if ".." in rel_path.split("/"):
        return jsonify({"error": "Invalid path"}), 400

    try:
        redis_client = redis.from_url(config.REDIS_URL, decode_responses=True)
        session_json = redis_client.get(f"session:{conversation_id}")
        if not session_json:
            return jsonify({"error": "session not found"}), 404

        session_data = json.loads(session_json) if isinstance(session_json, str) else (session_json or {})
        if str(session_data.get("user_id")) != str(user.id):
            return jsonify({"error": "Unauthorized session access"}), 403

        sandbox_id = session_data.get("active_sandbox_id")
        if not sandbox_id:
            sandbox_ids = session_data.get("sandbox_ids", []) or []
            sandbox_id = sandbox_ids[-1] if sandbox_ids else None
        if not sandbox_id:
            return jsonify({"error": "sandbox not found"}), 404

        if not config.SANDBOX_API_URL:
            return jsonify({"error": "SANDBOX_API_URL not configured"}), 500

        abs_path = f"/home/sandboxuser/workspace/{rel_path.lstrip('/')}"
        resp = requests.get(
            f"{config.SANDBOX_API_URL}/sessions/{sandbox_id}/files/content",
            params={"filepath": abs_path},
            timeout=20,
        )
        if resp.status_code != 200:
            return jsonify({"error": f"failed to load sandbox file (HTTP {resp.status_code})"}), 502

        payload = resp.json() or {}
        encoded = payload.get("content", "") or ""
        data = base64.b64decode(encoded) if encoded else b""
        is_binary = b"\x00" in data
        if is_binary:
            return jsonify({
                "ok": True,
                "path": rel_path,
                "is_binary": True,
                "size_bytes": len(data),
                "content": None,
                "content_base64": encoded,
            }), 200

        text_content = data.decode("utf-8", errors="replace")
        lim = 300_000
        truncated = text_content[:lim]
        return jsonify({
            "ok": True,
            "path": rel_path,
            "is_binary": False,
            "size_bytes": len(data),
            "truncated": len(text_content) > len(truncated),
            "content": truncated,
            "content_base64": encoded,
        }), 200
    except Exception as e:
        logger.error(f"project/workspace/file-content failed: {e}", exc_info=True)
        return jsonify({"error": "failed to load workspace file content"}), 500


@api_bp.route('/project/workspace/deployment-status', methods=['POST'])
def project_workspace_deployment_status():
    """
    Compare current sandbox workspace against the selected deployment.
    body: { conversation_id, site_id, deployment_id }
    """
    user, error = get_user_from_token(request)
    if error:
        return jsonify({"error": error[0]}), error[1]

    body = request.json or {}
    conversation_id = str(body.get("conversation_id") or "").strip()
    site_ref = str(body.get("site_id") or body.get("site_ref") or "").strip()
    deployment_id = str(body.get("deployment_id") or "").strip()

    if not conversation_id:
        return jsonify({"error": "conversation_id is required"}), 400
    if not site_ref:
        return jsonify({"error": "site_id is required"}), 400
    if not deployment_id:
        return jsonify({"error": "deployment_id is required"}), 400

    try:
        ensure_deploy_tables()
        session_data = _load_project_workspace_session(conversation_id=conversation_id, user_id=str(user.id))
        sandbox_id = _resolve_project_workspace_sandbox_id(session_data)
        if not sandbox_id:
            return jsonify({
                "ok": True,
                "modified": False,
                "reason": "sandbox_unavailable",
                "summary": {"new_files": [], "changed_files": [], "deleted_files": []},
            }), 200

        site = resolve_site_ref(user_id=str(user.id), site_ref=site_ref)
        deployment = get_deployment_summary(
            site_id=str(site["id"]),
            user_id=str(user.id),
            deployment_id=deployment_id,
        )

        workspace_rows = _list_sandbox_workspace_rows(sandbox_id=sandbox_id, path=_PROJECT_WORKSPACE_ROOT)
        workspace_map: dict[str, dict[str, Any]] = {}
        workspace_hashes: dict[str, str] = {}

        for row in workspace_rows:
            abs_path = str(row.get("path", ""))
            prefix = _PROJECT_WORKSPACE_ROOT.rstrip("/") + "/"
            rel_path = abs_path[len(prefix):] if abs_path.startswith(prefix) else abs_path
            rel_path = rel_path.replace("\\", "/").lstrip("/")
            if not rel_path or ".." in rel_path.split("/"):
                continue
            workspace_map[rel_path] = row

        deployment_files = list_deployment_files(
            site_id=str(site["id"]),
            user_id=str(user.id),
            deployment_id=str(deployment["id"]),
        )
        deployment_paths = {str(item.get("path", "")).replace("\\", "/").lstrip("/") for item in deployment_files}
        workspace_paths = set(workspace_map.keys())

        new_files = sorted(workspace_paths - deployment_paths)
        deleted_files = sorted(deployment_paths - workspace_paths)
        changed_files: list[str] = []

        for item in deployment_files:
            rel_path = str(item.get("path", "")).replace("\\", "/").lstrip("/")
            if not rel_path or rel_path not in workspace_map:
                continue

            abs_path = str(workspace_map[rel_path].get("path", ""))
            workspace_bytes = _read_sandbox_workspace_bytes(sandbox_id=sandbox_id, abs_path=abs_path)
            workspace_hash = workspace_hashes.get(rel_path)
            if not workspace_hash:
                workspace_hash = hashlib.sha256(workspace_bytes).hexdigest()
                workspace_hashes[rel_path] = workspace_hash

            deployment_bytes = get_deployment_file_bytes(
                site_id=str(site["id"]),
                user_id=str(user.id),
                path=rel_path,
                deployment_id=str(deployment["id"]),
            )
            deployment_hash = hashlib.sha256(deployment_bytes).hexdigest()

            if workspace_hash != deployment_hash:
                changed_files.append(rel_path)

        summary = {
            "new_files": new_files,
            "changed_files": sorted(changed_files),
            "deleted_files": deleted_files,
        }
        return jsonify({
            "ok": True,
            "modified": bool(new_files or changed_files or deleted_files),
            "reason": "ok",
            "site_id": str(site["id"]),
            "deployment_id": str(deployment["id"]),
            "summary": summary,
        }), 200
    except PermissionError as e:
        return jsonify({"error": str(e)}), 403
    except LookupError as e:
        return jsonify({"error": str(e)}), 404
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error(f"project/workspace/deployment-status failed: {e}", exc_info=True)
        return jsonify({"error": "failed to compare workspace against deployment"}), 500


@api_bp.route('/project/workspace/redeploy', methods=['POST'])
def project_workspace_redeploy():
    """
    Redeploy the current cloud sandbox workspace for the selected site.
    body: { conversation_id, site_id }
    """
    user, error = get_user_from_token(request)
    if error:
        return jsonify({"error": error[0]}), error[1]

    body = request.json or {}
    conversation_id = str(body.get("conversation_id") or "").strip()
    site_ref = str(body.get("site_id") or body.get("site_ref") or "").strip()

    if not conversation_id:
        return jsonify({"error": "conversation_id is required"}), 400
    if not site_ref:
        return jsonify({"error": "site_id is required"}), 400

    try:
        ensure_deploy_tables()
        session_data = _load_project_workspace_session(conversation_id=conversation_id, user_id=str(user.id))
        sandbox_id = _resolve_project_workspace_sandbox_id(session_data)
        if not sandbox_id:
            return jsonify({"error": "sandbox not found"}), 404
        if not config.SANDBOX_API_URL:
            return jsonify({"error": "SANDBOX_API_URL not configured"}), 500

        site = resolve_site_ref(user_id=str(user.id), site_ref=site_ref)
        upload_files = _collect_workspace_upload_files(sandbox_id=sandbox_id, project_directory=_PROJECT_WORKSPACE_ROOT)
        if not upload_files:
            return jsonify({"error": "No deployable files found in workspace"}), 400

        has_index = any(str(item.get("path", "")).lower() == "index.html" for item in upload_files)
        if not has_index:
            return jsonify({"error": "Deployment must include index.html"}), 400

        upload = upload_site_files(site_id=str(site["id"]), user_id=str(user.id), files=upload_files)
        manifest = upsert_site_manifest(
            site_id=str(site["id"]),
            user_id=str(user.id),
            deployment_id=str(upload.deployment_id),
        )
        activation = activate_deployment(
            site_id=str(site["id"]),
            user_id=str(user.id),
            deployment_id=str(upload.deployment_id),
        )
        deployment = get_deployment_summary(
            site_id=str(site["id"]),
            user_id=str(user.id),
            deployment_id=str(upload.deployment_id),
        )
        return jsonify({
            "ok": True,
            "site_id": str(site["id"]),
            "deployment_id": str(upload.deployment_id),
            "files_uploaded": upload.files_uploaded,
            "version": deployment.get("version"),
            "r2_prefix": deployment.get("r2_prefix"),
            "deployment_status": deployment.get("status"),
            "manifest": manifest,
            **activation,
        }), 200
    except PermissionError as e:
        return jsonify({"error": str(e)}), 403
    except LookupError as e:
        return jsonify({"error": str(e)}), 404
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error(f"project/workspace/redeploy failed: {e}", exc_info=True)
        return jsonify({"error": "failed to redeploy workspace"}), 500


@api_bp.route('/deploy/activate', methods=['POST'])
def deploy_activate():
    """
    Activate a deployment and write slug manifest used by Worker routing.
    body: { site_id, deployment_id }
    """
    user, error = get_user_from_token(request)
    if error:
        return jsonify({"error": error[0]}), error[1]

    body = request.json or {}
    site_id = body.get("site_id")
    deployment_id = body.get("deployment_id")
    if not site_id or not deployment_id:
        return jsonify({"error": "site_id and deployment_id are required"}), 400

    try:
        ensure_deploy_tables()
        manifest = upsert_site_manifest(site_id=str(site_id), user_id=str(user.id), deployment_id=str(deployment_id))
        result = activate_deployment(site_id=str(site_id), user_id=str(user.id), deployment_id=str(deployment_id))
        CacheManager.invalidate_pattern(f"cache:deploy_projects:{user.id}:*")
        return jsonify({"ok": True, "manifest": manifest, **result}), 200
    except PermissionError as e:
        return jsonify({"error": str(e)}), 403
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error(f"deploy/activate failed: {e}", exc_info=True)
        return jsonify({"error": "failed to activate deployment"}), 500
    except Exception as e:
        logger.error(f"Error in health check: {e}")
        return jsonify({
            "status": "ok",
            "message": "Backend is running",
            "service": "aios-web"
        }), 200


@api_bp.route('/sandbox/artifacts', methods=['GET'])
def get_session_artifacts():
    """
    Get all artifacts for a session.
    Query params: session_id (required)
    """
    user, error = get_user_from_token(request)
    if error:
        return jsonify({"error": error[0]}), error[1]
    
    session_id = request.args.get('session_id')
    if not session_id:
        return jsonify({"error": "session_id is required"}), 400
    
    try:
        from sandbox_persistence import get_persistence_service
        persistence_service = get_persistence_service()
        
        artifacts = persistence_service.list_session_artifacts(
            session_id=session_id,
            user_id=str(user.id)
        )
        
        return jsonify({"artifacts": artifacts}), 200
        
    except Exception as e:
        logger.error(f"Error fetching session artifacts: {e}")
        return jsonify({"error": str(e)}), 500


@api_bp.route('/sandbox/artifacts/<artifact_id>', methods=['GET'])
def get_artifact_details(artifact_id):
    """
    Get details and download URL for a specific artifact.
    """
    user, error = get_user_from_token(request)
    if error:
        return jsonify({"error": error[0]}), error[1]
    
    try:
        from sandbox_persistence import get_persistence_service
        persistence_service = get_persistence_service()
        
        cache_key = f"cache:artifact_details:{user.id}:{artifact_id}"
        cached_data = CacheManager.get(cache_key)
        if cached_data:
            return jsonify(cached_data), 200
        
        # Get artifact metadata
        result = supabase_client.table('sandbox_artifacts').select(
            '*'
        ).eq('artifact_id', artifact_id).eq('user_id', str(user.id)).single().execute()
        
        if not result.data:
            return jsonify({"error": "Artifact not found"}), 404
        
        artifact = result.data
        
        # Generate download URL
        download_url = persistence_service.get_artifact_download_url(
            artifact_id=artifact_id,
            user_id=str(user.id),
            expiry=3600  # 1 hour
        )
        
        if not download_url:
            return jsonify({"error": "Failed to generate download URL"}), 500
        
        artifact['download_url'] = download_url
        response_data = {"artifact": artifact}
        
        # Cache for slightly less than the URL expiry (e.g. 50 minutes = 3000s)
        CacheManager.set(cache_key, response_data, ttl_seconds=3000)
        return jsonify(response_data), 200
        
    except Exception as e:
        logger.error(f"Error fetching artifact details: {e}")
        return jsonify({"error": str(e)}), 500


@api_bp.route('/sandbox/artifacts/<artifact_id>', methods=['DELETE'])
def delete_artifact(artifact_id):
    """
    Delete an artifact.
    """
    user, error = get_user_from_token(request)
    if error:
        return jsonify({"error": error[0]}), error[1]

    try:
        from sandbox_persistence import get_persistence_service
        persistence_service = get_persistence_service()

        success = persistence_service.delete_artifact(
            artifact_id=artifact_id,
            user_id=str(user.id)
        )

        if success:
            # Invalidate the per-artifact detail cache
            CacheManager.delete(f"cache:artifact_details:{user.id}:{artifact_id}")
            return jsonify({"message": "Artifact deleted"}), 200
        else:
            return jsonify({"error": "Failed to delete artifact"}), 500

    except Exception as e:
        logger.error(f"Error deleting artifact: {e}")
        return jsonify({"error": str(e)}), 500


@api_bp.route('/sandbox/executions/<execution_id>/artifacts', methods=['GET'])
def get_execution_artifacts(execution_id):
    """
    Get all artifacts created by a specific execution.
    """
    user, error = get_user_from_token(request)
    if error:
        return jsonify({"error": error[0]}), error[1]
    
    try:
        from sandbox_persistence import get_persistence_service
        persistence_service = get_persistence_service()
        
        artifacts = persistence_service.list_execution_artifacts(
            execution_id=execution_id,
            user_id=str(user.id)
        )
        
        return jsonify({"artifacts": artifacts}), 200
        
    except Exception as e:
        logger.error(f"Error fetching execution artifacts: {e}")
        return jsonify({"error": str(e)}), 500


@api_bp.route('/sessions/<session_id>/content', methods=['GET'])
def get_session_content(session_id):
    """
    Get all content (artifacts, executions, uploads) for a conversation session.
    This enables viewing historical content when reopening old conversations.

    Returns content with fresh presigned URLs for downloads.

    Note: Backend caching removed - frontend handles caching via sessionContentViewer.
    This ensures real-time content updates without race conditions.
    """
    user, error = get_user_from_token(request)
    if error:
        return jsonify({"error": error[0]}), error[1]

    try:
        from sandbox_persistence import get_persistence_service
        persistence_service = get_persistence_service()

        def _normalize_metadata(value: Any) -> dict[str, Any]:
            if isinstance(value, dict):
                return value
            if isinstance(value, str):
                try:
                    parsed = json.loads(value)
                    if isinstance(parsed, dict):
                        return parsed
                except Exception:
                    pass
            return {}

        def _normalize_value(value: Any) -> str:
            return str(value or '').strip().lower()

        def _normalize_path(value: Any) -> str:
            return _normalize_value(value).replace('\\', '/')

        def _content_dedupe_key(item: dict[str, Any]) -> str:
            metadata = _normalize_metadata(item.get('metadata'))
            file_id = _normalize_value(metadata.get('file_id'))
            if file_id:
                return f"file-id:{file_id}"

            storage_path = _normalize_path(metadata.get('path') or metadata.get('supabasePath'))
            if storage_path:
                return f"path:{storage_path}"

            relative_path = _normalize_path(metadata.get('relativePath') or metadata.get('relative_path'))
            if relative_path:
                return f"relative:{relative_path}"

            if item.get('content_type') == 'artifact' and item.get('reference_id'):
                return f"artifact:{_normalize_value(item.get('reference_id'))}"

            filename = _normalize_value(metadata.get('filename') or metadata.get('name') or 'unknown')
            size = _normalize_value(metadata.get('size') or 0)
            mime_type = _normalize_value(metadata.get('mime_type') or metadata.get('type') or '')
            return f"fallback:{filename}:{size}:{mime_type}"

        def _content_quality_score(item: dict[str, Any]) -> int:
            metadata = _normalize_metadata(item.get('metadata'))
            score = 0
            if metadata.get('relativePath') or metadata.get('relative_path'):
                score += 6
            if metadata.get('path') or metadata.get('supabasePath'):
                score += 5
            if metadata.get('size'):
                score += 2
            if metadata.get('mime_type') or metadata.get('type'):
                score += 2
            if item.get('source') == 'session_content':
                score += 1
            return score

        def _dedupe_content_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
            deduped: dict[str, dict[str, Any]] = {}
            passthrough: list[dict[str, Any]] = []

            for row in rows:
                if row.get('content_type') not in {'artifact', 'upload'}:
                    passthrough.append(row)
                    continue

                key = _content_dedupe_key(row)
                current = deduped.get(key)
                if current is None or _content_quality_score(row) > _content_quality_score(current):
                    deduped[key] = row

            return [*deduped.values(), *passthrough]

        # Get registry content for this session (artifacts/executions/uploads)
        content_rows = persistence_service.get_session_content(
            session_id=session_id,
            user_id=str(user.id)
        )

        normalized_rows: list[dict[str, Any]] = []
        for row in content_rows or []:
            row = dict(row)
            row['metadata'] = _normalize_metadata(row.get('metadata'))
            row['source'] = 'session_content'
            normalized_rows.append(row)

        # Also fetch all attachment rows linked to this session
        attachment_result = supabase_client.table('attachment').select(
            'id, metadata, created_at'
        ).eq('session_id', session_id).eq('user_id', str(user.id)).order(
            'created_at', desc=False
        ).execute()

        for attachment in (attachment_result.data or []):
            metadata = _normalize_metadata(attachment.get('metadata'))
            normalized_rows.append({
                'id': f"attachment:{attachment.get('id')}",
                'content_type': 'upload',
                'reference_id': str(attachment.get('id')),
                'message_id': None,
                'created_at': attachment.get('created_at'),
                'source': 'attachment',
                'metadata': {
                    # Normalize attachment metadata shape to match upload rows
                    'filename': metadata.get('filename') or metadata.get('name') or 'attachment',
                    'mime_type': metadata.get('mime_type') or metadata.get('type'),
                    'size': metadata.get('size', 0),
                    'relativePath': metadata.get('relativePath'),
                    'path': metadata.get('path') or metadata.get('supabasePath'),
                    'is_text': metadata.get('is_text', metadata.get('isText', False)),
                    'isMedia': metadata.get('isMedia', False),
                    'file_id': metadata.get('file_id'),
                },
            })

        # Preserve chronological playback
        normalized_rows = _dedupe_content_rows(normalized_rows)
        normalized_rows.sort(key=lambda item: str(item.get('created_at') or ''))

        # Enrich content with fresh presigned URLs
        enriched_content = []
        for item in normalized_rows:
            content_type = item['content_type']
            reference_id = item['reference_id']

            # Add download URLs based on content type
            if content_type == 'artifact':
                # Generate fresh presigned URL for artifact
                download_url = persistence_service.get_artifact_download_url(
                    artifact_id=reference_id,
                    user_id=str(user.id),
                    expiry=3600
                )
                item['download_url'] = download_url

            elif content_type == 'execution':
                # Generate fresh presigned URLs for execution logs
                urls = persistence_service.get_execution_logs_urls(
                    execution_id=reference_id,
                    user_id=str(user.id),
                    expiry=3600
                )
                if urls:
                    item['stdout_url'] = urls.get('stdout_url')
                    item['stderr_url'] = urls.get('stderr_url')
            elif content_type == 'upload':
                metadata = _normalize_metadata(item.get('metadata'))
                storage_path = str(metadata.get('path') or '').strip()
                if storage_path:
                    try:
                        signed_response = supabase_client.storage.from_('media-uploads').create_signed_url(
                            storage_path,
                            3600,
                        )
                        if isinstance(signed_response, dict):
                            item['signed_url'] = (
                                signed_response.get('signedURL')
                                or signed_response.get('signed_url')
                            )
                    except Exception as signed_error:
                        logger.warning("Failed to generate signed upload URL for %s: %s", storage_path, signed_error)

            enriched_content.append(item)

        response_payload = {
            "session_id": session_id,
            "content": enriched_content,
            "count": len(enriched_content)
        }

        return jsonify(response_payload), 200

    except Exception as e:
        logger.error(f"Error fetching session content: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500
