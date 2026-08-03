# python-backend/agent_runner.py (Corrected for Dependency Injection)

import logging
import json
import re
import traceback
import inspect
import base64
from typing import Dict, Any, List, Tuple
from redis import Redis
import requests

# --- Local Module Imports ---
from extensions import socketio
from assistant import get_llm_os
from system_assistant import get_system_assistant
from coder_agent import get_coder_agent
from computer_agent import get_computer_agent
from convex_usage_service import get_convex_usage_service
from subscription_service import get_usage_window_descriptor
from supabase_client import supabase_client
from session_service import ConnectionManager
from run_state_manager import RunStateManager
from cache_manager import CacheManager
from assistant_stream_utils import build_system_assistant_terminal_message
from tool_event_payload import serialize_tool_event
from deploy_platform import (
    get_deployment_file_bytes,
    get_deployment_summary,
    list_deployment_files,
    resolve_site_ref,
)
import config

# --- Agno Framework Imports ---
from agno.media import Image, Audio, Video, File
from agno.run.agent import RunEvent, RunOutput
from agno.run.team import TeamRunEvent, TeamRunOutput

logger = logging.getLogger(__name__)

_WORKSPACE_ROOT = "/home/sandboxuser/workspace"

_ALLOWED_AGNO_FILE_MIME_TYPES = {
    "application/pdf",
    "application/x-javascript",
    "text/javascript",
    "application/x-python",
    "text/x-python",
    "text/plain",
    "text/html",
    "text/css",
    "text/md",
    "text/csv",
    "text/xml",
    "text/rtf",
}

_EXTENSION_TO_SAFE_TEXT_MIME = {
    "js": "text/javascript",
    "mjs": "text/javascript",
    "cjs": "text/javascript",
    "py": "text/x-python",
    "txt": "text/plain",
    "md": "text/md",
    "markdown": "text/md",
    "html": "text/html",
    "htm": "text/html",
    "css": "text/css",
    "csv": "text/csv",
    "xml": "text/xml",
    "rtf": "text/rtf",
}


def _file_extension(file_name: str) -> str:
    if not file_name or "." not in file_name:
        return ""
    return file_name.rsplit(".", 1)[-1].strip().lower()


def _normalize_agno_mime_type(file_name: str, file_type: Any) -> str:
    candidate = str(file_type or "").strip().lower()
    if candidate in _ALLOWED_AGNO_FILE_MIME_TYPES:
        return candidate

    extension = _file_extension(file_name)
    if extension == "pdf":
        return "application/pdf"
    if extension in _EXTENSION_TO_SAFE_TEXT_MIME:
        return _EXTENSION_TO_SAFE_TEXT_MIME[extension]
    if candidate.startswith("text/"):
        return "text/plain"
    return "text/plain"


def build_inline_text_files_prompt(files_data: List[Dict[str, Any]]) -> str:
    """
    Build a deterministic plain-text block for all inline text/code attachments.
    This block is prepended to the user message so the LLM always sees text files
    as part of the prompt, regardless of model file-attachment support.
    """
    if not files_data:
        return ""

    entries: List[str] = []
    for file_data in files_data:
        if not file_data.get("isText"):
            continue

        content = file_data.get("content")
        if content is None:
            continue

        if isinstance(content, bytes):
            content_text = content.decode("utf-8", errors="replace")
        else:
            content_text = str(content)

        file_name = str(file_data.get("name") or "untitled")
        entries.append(
            f"file name :- {file_name}\n"
            f"content :-\n"
            f"{content_text}\n"
        )

    if not entries:
        return ""

    return "ATTACHED TEXT FILES:\n[\n" + "\n".join(entries) + "]\n"


def _filter_kwargs_for_callable(fn: Any, kwargs: Dict[str, Any], label: str = "kwargs") -> Dict[str, Any]:
    """
    Keep only kwargs accepted by the callable (unless it supports **kwargs).
    Prevents runtime TypeError when session metadata is present in config.
    """
    try:
        signature = inspect.signature(fn)
    except (TypeError, ValueError):
        return dict(kwargs)

    if any(param.kind == inspect.Parameter.VAR_KEYWORD for param in signature.parameters.values()):
        return dict(kwargs)

    accepted = {
        name
        for name, param in signature.parameters.items()
        if param.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
    }
    filtered = {key: value for key, value in kwargs.items() if key in accepted}
    dropped = sorted(set(kwargs.keys()) - set(filtered.keys()))
    if dropped:
        logger.info(
            "Dropped unsupported %s for %s: %s",
            label,
            getattr(fn, "__name__", str(fn)),
            dropped,
        )
    return filtered


def build_sandbox_workspace_context(session_data: Dict[str, Any]) -> str:
    """
    Build a concise workspace file-tree context from the latest known sandbox.
    This reduces repetitive ls/find calls in coding turns.
    """
    try:
        if not config.SANDBOX_API_URL:
            return ""
        sandbox_ids = session_data.get("sandbox_ids", []) or []
        if not sandbox_ids:
            return ""

        sandbox_id = str(sandbox_ids[-1]).strip()
        if not sandbox_id:
            return ""

        workspace_root = "/home/sandboxuser/workspace"
        response = requests.get(
            f"{config.SANDBOX_API_URL}/sessions/{sandbox_id}/files",
            params={"path": workspace_root},
            timeout=12
        )
        if response.status_code != 200:
            return ""

        files = (response.json() or {}).get("files", []) or []
        if not files:
            return f"SANDBOX WORKSPACE CONTEXT\nsandbox_id: {sandbox_id}\nroot: {workspace_root}\nfiles: (empty)\n"

        files = sorted(files, key=lambda f: str(f.get("path", "")))
        max_files = 120
        shown = files[:max_files]
        lines = [
            "SANDBOX WORKSPACE CONTEXT",
            f"sandbox_id: {sandbox_id}",
            f"root: {workspace_root}",
            f"total_files: {len(files)}",
            f"showing_files: {len(shown)}",
        ]
        for item in shown:
            abs_path = str(item.get("path", ""))
            rel_path = abs_path[len(workspace_root) + 1:] if abs_path.startswith(workspace_root + "/") else abs_path
            size = int(item.get("size", 0))
            lines.append(f"- {rel_path} ({size} bytes)")

        if len(files) > max_files:
            lines.append(f"... {len(files) - max_files} more files omitted")

        return "\n".join(lines) + "\n"
    except Exception as exc:
        logger.debug("Unable to build sandbox workspace context: %s", exc)
        return ""


def _list_sandbox_workspace_files(sandbox_id: str) -> List[dict]:
    if not config.SANDBOX_API_URL or not sandbox_id:
        return []
    response = requests.get(
        f"{config.SANDBOX_API_URL}/sessions/{sandbox_id}/files",
        params={"path": _WORKSPACE_ROOT},
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json() or {}
    files = payload.get("files", []) or []
    return files if isinstance(files, list) else []


def _write_sandbox_workspace_file(sandbox_id: str, absolute_path: str, content_bytes: bytes) -> None:
    if not config.SANDBOX_API_URL:
        raise RuntimeError("SANDBOX_API_URL is not configured")

    payload = {
        "filepath": absolute_path,
        "content_base64": base64.b64encode(content_bytes).decode("utf-8"),
        "make_dirs": True,
    }
    try:
        response = requests.put(
            f"{config.SANDBOX_API_URL}/sessions/{sandbox_id}/files/content",
            json=payload,
            timeout=60,
        )
        if response.status_code == 405:
            raise requests.HTTPError("405 Method Not Allowed", response=response)
        response.raise_for_status()
        return
    except requests.HTTPError as exc:
        status_code = getattr(getattr(exc, "response", None), "status_code", None)
        if status_code not in (405, 501):
            raise
    except Exception:
        logger.info("[Bootstrap] Falling back to exec-based sandbox write for %s", absolute_path)

    b64 = base64.b64encode(content_bytes).decode("utf-8")
    if len(b64) > 1_500_000:
        raise RuntimeError(
            "Sandbox file-write fallback hit payload limit. Restart sandbox-manager with updated PUT /files/content endpoint."
        )

    command = (
        "python3 - <<'PY'\n"
        "import base64, pathlib\n"
        f"p = pathlib.Path(r'''{absolute_path}''')\n"
        "p.parent.mkdir(parents=True, exist_ok=True)\n"
        f"p.write_bytes(base64.b64decode('''{b64}'''))\n"
        "print('ok')\n"
        "PY"
    )
    response = requests.post(
        f"{config.SANDBOX_API_URL}/sessions/{sandbox_id}/exec",
        json={"command": command},
        timeout=90,
    )
    response.raise_for_status()


def _ensure_project_workspace_bootstrap(
    *,
    session_data: Dict[str, Any],
    conversation_id: str,
    connection_manager: ConnectionManager,
    requested_mode: str,
    requested_coder_target: str,
) -> Dict[str, Any]:
    """
    Ensure a deployed project is copied into the cloud sandbox workspace before
    coder edits begin. This prevents the agent from editing an empty sandbox
    while the frontend is still showing deployment files.
    """
    if requested_mode != "coder" or requested_coder_target != "cloud":
        return session_data

    session_config = dict(session_data.get("config", {}) or {})
    workspace_context = session_config.get("workspace_context", {}) or {}
    if not isinstance(workspace_context, dict):
        return session_data

    cloud_context = workspace_context.get("cloud_context", {}) or {}
    if not isinstance(cloud_context, dict):
        cloud_context = {}

    site_ref = (
        workspace_context.get("site_id")
        or cloud_context.get("site_id")
        or workspace_context.get("slug")
        or workspace_context.get("hostname")
    )
    deployment_id = (
        workspace_context.get("deployment_id")
        or cloud_context.get("deployment_id")
    )
    if not site_ref:
        return session_data

    bootstrap_key = f"{site_ref}::{deployment_id or 'latest'}"
    if cloud_context.get("bootstrapped_key") == bootstrap_key and cloud_context.get("bootstrapped") is True:
        return session_data

    try:
        resolved_site = resolve_site_ref(user_id=str(session_data["user_id"]), site_ref=str(site_ref))
        resolved_site_id = str(resolved_site["id"])
        deployment = get_deployment_summary(
            site_id=resolved_site_id,
            user_id=str(session_data["user_id"]),
            deployment_id=str(deployment_id) if deployment_id else None,
        )
        files = list_deployment_files(
            site_id=resolved_site_id,
            user_id=str(session_data["user_id"]),
            deployment_id=str(deployment["id"]),
        )
        if not files:
            logger.info(
                "[Bootstrap] Deployment %s for site %s has no files; skipping sandbox bootstrap",
                deployment["id"],
                resolved_site_id,
            )
            return session_data

        sandbox_ids = list(session_data.get("sandbox_ids", []) or [])
        active_sandbox_id = str(session_data.get("active_sandbox_id") or "").strip()
        sandbox_id = active_sandbox_id or (str(sandbox_ids[-1]).strip() if sandbox_ids else "")

        if not sandbox_id:
            response = requests.post(f"{config.SANDBOX_API_URL}/sessions", timeout=30)
            response.raise_for_status()
            created = response.json() or {}
            sandbox_id = str(created.get("sandbox_id") or "").strip()
            if not sandbox_id:
                raise RuntimeError("Sandbox creation returned no sandbox_id")
            connection_manager.add_sandbox_to_session(conversation_id, sandbox_id)
            session_data = connection_manager.get_session(conversation_id) or session_data
            session_data["active_sandbox_id"] = sandbox_id
        else:
            session_data["active_sandbox_id"] = sandbox_id

        current_files = _list_sandbox_workspace_files(sandbox_id)
        current_rel_paths = {
            str(item.get("path", "")).replace("\\", "/")
            for item in current_files
        }
        current_rel_paths = {
            p[len(_WORKSPACE_ROOT) + 1:] if p.startswith(_WORKSPACE_ROOT + "/") else p
            for p in current_rel_paths if p
        }

        copied = 0
        for item in files:
            rel_path = str(item.get("path", "")).replace("\\", "/").lstrip("/")
            if not rel_path or ".." in rel_path.split("/"):
                continue
            if rel_path in current_rel_paths:
                continue
            content_bytes = get_deployment_file_bytes(
                site_id=resolved_site_id,
                user_id=str(session_data["user_id"]),
                path=rel_path,
                deployment_id=str(deployment["id"]),
            )
            dest_path = f"{_WORKSPACE_ROOT}/{rel_path}"
            _write_sandbox_workspace_file(sandbox_id, dest_path, content_bytes)
            copied += 1

        latest_session = connection_manager.get_session(conversation_id) or session_data
        latest_config = dict(latest_session.get("config", {}) or {})
        latest_workspace_context = latest_config.get("workspace_context", {}) or {}
        if not isinstance(latest_workspace_context, dict):
            latest_workspace_context = {}
        latest_cloud_context = latest_workspace_context.get("cloud_context", {}) or {}
        if not isinstance(latest_cloud_context, dict):
            latest_cloud_context = {}
        latest_cloud_context["bootstrapped"] = True
        latest_cloud_context["bootstrapped_key"] = bootstrap_key
        latest_cloud_context["bootstrapped_site_id"] = resolved_site_id
        latest_cloud_context["bootstrapped_deployment_id"] = str(deployment["id"])
        latest_workspace_context["cloud_context"] = latest_cloud_context
        latest_config["workspace_context"] = latest_workspace_context
        latest_session["config"] = latest_config
        latest_session["active_sandbox_id"] = sandbox_id
        connection_manager.redis_client.set(
            f"session:{conversation_id}",
            json.dumps(latest_session),
            ex=connection_manager.SESSION_TTL,
        )
        logger.info(
            "[Bootstrap] Ensured deployment files in sandbox for conv=%s site=%s deployment=%s copied=%s existing=%s sandbox=%s",
            conversation_id,
            resolved_site_id,
            deployment["id"],
            copied,
            len(current_rel_paths),
            sandbox_id,
        )
        return latest_session
    except Exception as exc:
        logger.error(
            "[Bootstrap] Failed to prepare deployed project workspace for conv=%s: %s",
            conversation_id,
            exc,
            exc_info=True,
        )
        return session_data


def _to_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _extract_metrics_from_run_output(
    run_output: RunOutput | TeamRunOutput | None,
) -> Dict[str, int]:
    if not run_output:
        logger.info("[TOKENS] Source run_output unavailable: run_output is None")
        return {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

    metrics = getattr(run_output, "metrics", None)
    if not metrics:
        logger.info("[TOKENS] Source run_output unavailable: run_output.metrics missing")
        return {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

    if isinstance(metrics, dict):
        input_tokens = _to_int(metrics.get("input_tokens"))
        output_tokens = _to_int(metrics.get("output_tokens"))
        total_tokens = _to_int(metrics.get("total_tokens"))
    else:
        input_tokens = _to_int(getattr(metrics, "input_tokens", 0))
        output_tokens = _to_int(getattr(metrics, "output_tokens", 0))
        total_tokens = _to_int(getattr(metrics, "total_tokens", 0))

    if total_tokens <= 0:
        total_tokens = input_tokens + output_tokens

    logger.info(
        "[TOKENS] Source run_output selected: input=%s output=%s total=%s",
        input_tokens,
        output_tokens,
        total_tokens,
    )
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
    }


def _extract_metrics_from_agno_session(conversation_id: str) -> Dict[str, int]:
    try:
        response = (
            supabase_client
            .from_("agno_sessions")
            .select("session_data,runs")
            .eq("session_id", conversation_id)
            .maybe_single()
            .execute()
        )
        row = response.data or {}
    except Exception as e:
        logger.warning(f"Token logging fallback query failed for session {conversation_id}: {e}")
        return {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

    # Prefer per-run metrics (delta for latest run). Session metrics can be cumulative.
    # We aggregate latest top-level run + all child member runs for this turn.
    input_tokens = 0
    output_tokens = 0
    total_tokens = 0

    runs = row.get("runs") or []
    if isinstance(runs, str):
        try:
            runs = json.loads(runs)
        except Exception:
            runs = []
    if isinstance(runs, list) and runs:
        # Choose latest top-level run for the current turn.
        top_level_runs = [r for r in runs if not (r or {}).get("parent_run_id")]
        if top_level_runs:
            root_run = max(top_level_runs, key=lambda r: _to_int((r or {}).get("created_at")))
        else:
            root_run = max(runs, key=lambda r: _to_int((r or {}).get("created_at")))

        root_run_id = (root_run or {}).get("run_id")
        if root_run_id:
            children_by_parent: Dict[str, List[Dict[str, Any]]] = {}
            for run in runs:
                parent = (run or {}).get("parent_run_id")
                if parent:
                    children_by_parent.setdefault(parent, []).append(run)

            aggregated_runs: List[Dict[str, Any]] = []
            stack = [root_run]
            seen_run_ids = set()
            while stack:
                current = stack.pop()
                current_id = (current or {}).get("run_id")
                if not current_id or current_id in seen_run_ids:
                    continue
                seen_run_ids.add(current_id)
                aggregated_runs.append(current)
                stack.extend(children_by_parent.get(current_id, []))

            for run in aggregated_runs:
                run_metrics = (run or {}).get("metrics") or {}
                input_tokens += _to_int(run_metrics.get("input_tokens"))
                output_tokens += _to_int(run_metrics.get("output_tokens"))
                total_tokens += _to_int(run_metrics.get("total_tokens"))

            logger.info(
                "[TOKENS] Fallback aggregated run tree for %s: root_run_id=%s run_count=%s input=%s output=%s total=%s",
                conversation_id,
                root_run_id,
                len(aggregated_runs),
                input_tokens,
                output_tokens,
                total_tokens,
            )
        else:
            latest_run_metrics = (runs[-1] or {}).get("metrics") or {}
            input_tokens = _to_int(latest_run_metrics.get("input_tokens"))
            output_tokens = _to_int(latest_run_metrics.get("output_tokens"))
            total_tokens = _to_int(latest_run_metrics.get("total_tokens"))
            logger.info(
                "[TOKENS] Fallback latest agno run metrics for %s: input=%s output=%s total=%s",
                conversation_id,
                input_tokens,
                output_tokens,
                total_tokens,
            )

    if input_tokens <= 0 and output_tokens <= 0:
        session_data = row.get("session_data") or {}
        if isinstance(session_data, str):
            try:
                session_data = json.loads(session_data)
            except Exception:
                session_data = {}
        session_metrics = (session_data.get("session_metrics") or {}) if isinstance(session_data, dict) else {}
        input_tokens = _to_int(session_metrics.get("input_tokens"))
        output_tokens = _to_int(session_metrics.get("output_tokens"))
        total_tokens = _to_int(session_metrics.get("total_tokens"))
        logger.info(
            "[TOKENS] Fallback session_metrics for %s (can be cumulative): input=%s output=%s total=%s",
            conversation_id,
            input_tokens,
            output_tokens,
            total_tokens,
        )

    if total_tokens <= 0:
        total_tokens = input_tokens + output_tokens

    logger.info(
        "[TOKENS] Fallback selected for %s: input=%s output=%s total=%s",
        conversation_id,
        input_tokens,
        output_tokens,
        total_tokens,
    )
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
    }


def _log_request_tokens(
    user_id: str,
    conversation_id: str,
    message_id: str,
    run_output: RunOutput | TeamRunOutput | None,
) -> None:
    metrics = _extract_metrics_from_run_output(run_output)
    source = "run_output"
    if metrics["input_tokens"] <= 0 and metrics["output_tokens"] <= 0:
        metrics = _extract_metrics_from_agno_session(conversation_id)
        source = "agno_session_fallback"

    if metrics["input_tokens"] <= 0 and metrics["output_tokens"] <= 0:
        logger.info(
            f"Skipping token usage logging for session {conversation_id}: no token metrics found."
        )
        return

    logger.info(
        "[TOKENS] Final metrics for logging session %s from %s: input=%s output=%s total=%s",
        conversation_id,
        source,
        metrics["input_tokens"],
        metrics["output_tokens"],
        metrics["total_tokens"],
    )
    try:
        convex_service = get_convex_usage_service()
        usage_window = get_usage_window_descriptor(user_id=str(user_id), refresh_window=False)
        convex_result = convex_service.record_token_usage(
            user_id=str(user_id),
            conversation_id=str(conversation_id),
            message_id=str(message_id),
            metrics=metrics,
            usage_window=usage_window,
            source=f"agent_runner:{source}",
        )
        logger.info(
            "[TOKENS][CONVEX] Logged token usage event for user=%s conversation=%s message=%s window=%s result=%s",
            user_id,
            conversation_id,
            message_id,
            usage_window.get("window_key"),
            bool(convex_result),
        )
    except Exception as convex_error:
        logger.warning(
            "[TOKENS][CONVEX] Failed to log token usage for user=%s conversation=%s message=%s: %s",
            user_id,
            conversation_id,
            message_id,
            convex_error,
        )


def process_files(files_data: List[Dict[str, Any]]) -> Tuple[List[Image], List[Audio], List[Video], List[File]]:
    """
    Processes a list of file data from the frontend, downloading media from
    Supabase storage and converting them into Agno media objects.
    Inline text/code attachments are intentionally handled via prompt injection
    (see build_inline_text_files_prompt) and are skipped here.
    """
    images, audio, videos, other_files = [], [], [], []
    if not files_data:
        return images, audio, videos, other_files

    for file_data in files_data:
        file_name = file_data.get('name', 'untitled')
        file_type = str(file_data.get('type') or '').strip()
        is_text_file = bool(file_data.get('isText'))
        storage_path = str(file_data.get('path') or '').strip()

        if is_text_file:
            logger.info("Queuing inline text file for prompt injection: %s", file_name)
            continue

        if storage_path:
            try:
                logger.info(f"Downloading file from Supabase storage: {storage_path}")
                file_bytes = supabase_client.storage.from_('media-uploads').download(storage_path)

                if file_type.startswith('image/'):
                    images.append(Image(content=file_bytes, name=file_name))
                elif file_type.startswith('audio/'):
                    audio.append(Audio(content=file_bytes, format=file_type.split('/')[-1], name=file_name))
                elif file_type.startswith('video/'):
                    videos.append(Video(content=file_bytes, name=file_name))
                else:
                    safe_mime_type = _normalize_agno_mime_type(file_name=file_name, file_type=file_type)
                    if safe_mime_type != file_type:
                        logger.warning(
                            "Coerced unsupported mime_type '%s' to '%s' for file %s",
                            file_type,
                            safe_mime_type,
                            file_name,
                        )
                    other_files.append(File(content=file_bytes, name=file_name, mime_type=safe_mime_type))
            except Exception as e:
                logger.error(f"Error downloading file {storage_path} from Supabase: {e}")
            continue

        logger.warning("Attachment %s had no valid storage path; skipping.", file_name)

    return images, audio, videos, other_files


def run_agent_and_stream(
    sid: str,
    conversation_id: str,
    message_id: str,
    turn_data: dict,
    browser_tools_config: dict,
    context_session_ids: List[str],
    agent_mode: str,
    connection_manager: ConnectionManager,
    redis_client: Redis,
    run_state_manager: RunStateManager = None,  # NEW: optional, safe for assistant path
):
    """
    FUNCTION DESCRIPTION:
    Orchestrates the lifecycle of a single prompt-response turn for the agent. It retrieves user configuration,
    bootstraps the local workspace files, loads historical chat context, constructs prompt prefixes,
    initializes the proper Agno agent team (based on active layout mode), processes file attachments,
    streams live reasoning/output chunks, and updates database run summaries and token counts on completion.

    UPSTREAM CALLER:
    - Called asynchronously within a background runner thread by `on_send_message()` in `python-backend/sockets.py`.

    DOWNSTREAM IMPACT & WEBSOCKET EMISSIONS:
    - Emits real-time chunks to `conv:{conversation_id}` room, which triggers frontend render routines in `js/chat.js`
      (specifically matching listeners: `reasoning_step`, `agent_step`, `response`, and `run_completed`).
    - Modifies database runs in Supabase ('agno_sessions') via connection_manager.
    - Triggers Convex database writes for billing/usage telemetry via `convex_usage_service.record_token_usage`.

    COMPONENTS & HELPERS CALLED:
    - `connection_manager.get_session()` to fetch Redis configurations.
    - `_ensure_project_workspace_bootstrap()` to copy project files from storage into the sandbox.
    - `get_coder_agent()`, `get_computer_agent()`, `get_system_assistant()`, or `get_llm_os()` in `assistant.py` (and relevant files) to build the Agno Team.
    - `_log_request_tokens()` to aggregate run/session usage and invoke Convex recording.
    """
    # Durable room name - survives SID changes
    room_name = f"conv:{conversation_id}"
    try:
        # --- DEBUG LOG ---
        print(f"[AGENT_RUNNER] START RUN: message_id={message_id}, sid={sid}, room={room_name}")
        logger.info(f"[AGENT_RUNNER] START RUN: message_id={message_id}, sid={sid}, room={room_name}")

        # 1. Retrieve Session and User Data
        session_data = connection_manager.get_session(conversation_id)
        if not session_data:
            raise Exception(f"Session data not found for conversation {conversation_id}")
        user_id = session_data['user_id']

        # --- Mark run as STARTED (we now have user_id) ---
        if run_state_manager:
            run_state_manager.start_run(conversation_id, message_id, user_id)

        # --- MODIFICATION START: Create a dedicated config for real-time tools ---
        # This new dictionary will contain ALL dependencies needed by any tool that
        # communicates directly with the frontend or uses Redis Pub/Sub.
        realtime_tool_config = {
            'socketio': socketio,
            'sid': sid,
            'message_id': message_id,
            'conversation_id': conversation_id,
            'redis_client': redis_client,
            'user_id': user_id,
        }
        # --- DEBUG LOG ---
        print(f"[AGENT_RUNNER] Created realtime_tool_config: { {k: type(v).__name__ for k, v in realtime_tool_config.items()} }")
        logger.info(f"[AGENT_RUNNER] Created realtime_tool_config with keys: {list(realtime_tool_config.keys())}")

        # 2. Initialize the Agent
        # --- MODIFICATION START: Pass session_id and message_id for persistence ---
        session_config = dict(session_data.get("config", {}))
        # Native Google Sheets now follows the same integration pattern as Gmail/Drive.
        session_config.setdefault("enable_google_sheets", True)

        # Legacy key migration for previously persisted sessions.
        if "enable_composio_google_sheets" in session_config:
            session_config.setdefault(
                "enable_google_sheets",
                bool(session_config.get("enable_composio_google_sheets")),
            )
            session_config.pop("enable_composio_google_sheets", None)

        session_config.setdefault(
            "enable_composio_whatsapp",
            config.COMPOSIO_ENABLE_WHATSAPP,
        )
        # Session summaries are expensive and disabled by default unless explicitly requested.
        session_config.setdefault("use_session_summaries", False)

        # Backward compatibility for legacy frontend key.
        if "computer_control" in session_config:
            session_config.setdefault(
                "enable_computer_control",
                bool(session_config.get("computer_control")),
            )
            session_config.pop("computer_control", None)

        # Internal routing metadata should not be forwarded to get_llm_os kwargs.
        session_agent_mode = str(session_config.pop("agent_mode", "default")).strip().lower()
        session_coder_target = str(session_config.pop("coder_execution_target", "cloud")).strip().lower()
        if session_coder_target not in ("local", "cloud"):
            session_coder_target = "cloud"

        requested_mode = str(agent_mode or "").strip().lower()
        if requested_mode not in ("coder", "computer", "default", "system-assistant"):
            requested_mode = session_agent_mode
        if requested_mode not in ("coder", "computer", "default", "system-assistant"):
            requested_mode = "default"

        requested_coder_target = str(
            turn_data.get("coder_execution_target")
            or session_data.get("config", {}).get("coder_execution_target")
            or session_coder_target
            or "cloud"
        ).strip().lower()
        if requested_coder_target not in ("local", "cloud"):
            requested_coder_target = "cloud"

        session_data = _ensure_project_workspace_bootstrap(
            session_data=session_data,
            conversation_id=conversation_id,
            connection_manager=connection_manager,
            requested_mode=requested_mode,
            requested_coder_target=requested_coder_target,
        )

        if requested_mode == "coder":
            agent = get_coder_agent(
                user_id=user_id,
                session_info=session_data,
                browser_tools_config=realtime_tool_config,
                custom_tool_config=realtime_tool_config,
                session_id=conversation_id,
                message_id=message_id,
                use_memory=session_config.get("use_memory", False),
                use_session_summaries=session_config.get("use_session_summaries", False),
                debug_mode=config.AGNO_DEBUG_MODE,
                enable_github=session_config.get("enable_github", True),
                coder_execution_target=requested_coder_target,
            )
        elif requested_mode == "computer":
            agent = get_computer_agent(
                user_id=user_id,
                session_info=session_data,
                browser_tools_config=realtime_tool_config,
                computer_tools_config=realtime_tool_config,
                session_id=conversation_id,
                message_id=message_id,
                use_memory=session_config.get("use_memory", False),
                use_session_summaries=session_config.get("use_session_summaries", False),
                debug_mode=config.AGNO_DEBUG_MODE,
                enable_google_email=bool(session_config.get("enable_google_email", True)),
                enable_google_drive=bool(session_config.get("enable_google_drive", True)),
                enable_google_sheets=bool(session_config.get("enable_google_sheets", True)),
            )
        elif requested_mode == "system-assistant":
            mobile_tools_config = {
                "sid": sid,
                "socketio": socketio,
                "redis_client": redis_client,
                "conversation_id": conversation_id,
                "message_id": message_id,
            }
            agent = get_system_assistant(
                mobile_tools_config=mobile_tools_config,
                user_id=user_id,
                debug_mode=config.SYSTEM_ASSISTANT_DEBUG_MODE,
            )
        else:
            llm_os_config = _filter_kwargs_for_callable(
                get_llm_os,
                session_config,
                label="session_config keys",
            )
            llm_os_config.setdefault("debug_mode", config.AGNO_DEBUG_MODE)
            agent = get_llm_os(
                user_id=user_id,
                session_info=session_data,
                browser_tools_config=realtime_tool_config,
                custom_tool_config=realtime_tool_config,
                session_id=conversation_id,  # NEW: For persistence
                message_id=message_id,  # NEW: For persistence
                **llm_os_config
            )
        # --- MODIFICATION END ---

        # 3. Process Input Data
        incoming_files = turn_data.get('files', []) or []
        images, audio, videos, other_files = process_files(incoming_files)
        inline_text_files_prompt = build_inline_text_files_prompt(incoming_files)
        current_session_state = {'turn_context': turn_data}
        user_message = turn_data.get("user_message", "")

        # 4. Fetch and Prepend Historical Context
        historical_context_str = ""
        if context_session_ids:
            logger.info(f"Fetching context from {len(context_session_ids)} sessions.")
            historical_context_str = "CONTEXT FROM PREVIOUS CHATS:\n---\n"
            for session_id in context_session_ids:
                try:
                    # Fetch conversation runs
                    response = supabase_client.from_('agno_sessions').select('runs').eq('session_id', session_id).single().execute()
                    if response.data and response.data.get('runs'):
                        runs = response.data['runs']
                        top_level_runs = [run for run in runs if not run.get('parent_run_id')]
                        for run in top_level_runs:
                            user_input = run.get('input', {}).get('input_content', '')
                            assistant_output = run.get('content', '')
                            if user_input:
                                historical_context_str += f"User: {user_input}\nAssistant: {assistant_output}\n---\n"

                    # Fetch file metadata from session_content
                    content_response = supabase_client.from_('session_content').select(
                        'content_type, reference_id, metadata'
                    ).eq('session_id', session_id).eq('user_id', user_id).execute()

                    if content_response.data and len(content_response.data) > 0:
                        files_context = []
                        for item in content_response.data:
                            content_type = item.get('content_type', '')
                            metadata = item.get('metadata', {}) or {}

                            if content_type == 'artifact':
                                filename = metadata.get('filename', 'Unknown file')
                                files_context.append(f"[Generated file: {filename}]")
                            elif content_type == 'upload':
                                filename = metadata.get('filename', 'Unknown file')
                                mime_type = metadata.get('mime_type', '')
                                files_context.append(f"[Attached file: {filename} ({mime_type})]")

                        if files_context:
                            historical_context_str += f"Files in this conversation:\n{chr(10).join(files_context)}\n---\n"

                except Exception as e:
                    logger.error(f"Failed to fetch or process context for session_id {session_id}: {e}")
            historical_context_str += "\n"

        sandbox_workspace_context = ""
        if session_data.get("config", {}).get("coding_assistant", False):
            sandbox_workspace_context = build_sandbox_workspace_context(session_data)

        contextual_prefix = ""
        if historical_context_str:
            contextual_prefix += historical_context_str
        if sandbox_workspace_context:
            contextual_prefix += f"{sandbox_workspace_context}\n"

        composed_user_message = user_message
        if inline_text_files_prompt:
            user_message_body = user_message or "(No additional user input message provided.)"
            inline_text_file_count = sum(
                1 for file_data in incoming_files
                if file_data.get('isText') and file_data.get('content') is not None
            )
            composed_user_message = (
                f"{inline_text_files_prompt}\n"
                f"USER INPUT MESSAGE:\n"
                f"{user_message_body}"
            )
            logger.info("Injected %s inline text file(s) into prompt.", inline_text_file_count)

        final_user_message = (
            f"{contextual_prefix}CURRENT QUESTION:\n{composed_user_message}"
            if contextual_prefix else composed_user_message
        )

        # 5. Run the Agent and Stream Results
        # --- DEBUG LOG ---
        print(f"[AGENT_RUNNER] Starting agent.run() for message_id={message_id}")
        logger.info(f"[AGENT_RUNNER] Starting agent.run() for message_id={message_id}")
        run_output: RunOutput | TeamRunOutput | None = None
        accumulated_content: list[str] = []
        accumulated_events: list[dict] = []
        accumulated_log_content: Dict[str, List[str]] = {}
        log_owner_order: List[str] = []
        completed_tool_history: List[Dict[str, Any]] = []
        final_owner_name = None
        emitted_reasoning_content: Dict[str, str] = {}
        content_chunk_count = 0
        reasoning_event_count = 0
        tool_call_count = 0
        for chunk in agent.run(
            input=final_user_message,
            images=images or None,
            audio=audio or None,
            videos=videos or None,
            files=other_files or None,
            session_id=conversation_id,
            session_state=current_session_state,
            stream=True,
            stream_intermediate_steps=True,
            add_history_to_context=True
        ):
            if isinstance(chunk, (RunOutput, TeamRunOutput)):
                run_output = chunk
                metrics_preview = _extract_metrics_from_run_output(run_output)
                logger.info(
                    "[TOKENS] Captured run output for session %s: input=%s output=%s total=%s",
                    conversation_id,
                    metrics_preview["input_tokens"],
                    metrics_preview["output_tokens"],
                    metrics_preview["total_tokens"],
                )

            if not chunk or not hasattr(chunk, 'event'):
                continue

            if (
                chunk.event
                in (RunEvent.run_completed.value, TeamRunEvent.run_completed.value)
                and getattr(chunk, "metrics", None)
            ):
                run_output = chunk
                logger.info(
                    "[TOKENS] Captured completed Agno output/event for session %s",
                    conversation_id,
                )

            owner_name = getattr(chunk, 'agent_name', None) or getattr(chunk, 'team_name', None)
            owner_reasoning_key = owner_name or "Aetheria_AI"
            chunk_reasoning_content = getattr(chunk, 'reasoning_content', None)
            if chunk_reasoning_content:
                reasoning_text = str(chunk_reasoning_content)
                previous_reasoning = emitted_reasoning_content.get(owner_reasoning_key, "")
                reasoning_delta = reasoning_text
                if previous_reasoning and reasoning_text.startswith(previous_reasoning):
                    reasoning_delta = reasoning_text[len(previous_reasoning):]

                if reasoning_delta.strip():
                    reasoning_event_count += 1
                    socketio.emit("reasoning_step", {
                        "id": message_id,
                        "agent_name": owner_name,
                        "step": reasoning_delta
                    }, room=room_name)
                    accumulated_events.append({
                        "type": "reasoning_step",
                        "agent_name": owner_name,
                        "step": reasoning_delta,
                    })

                emitted_reasoning_content[owner_reasoning_key] = reasoning_text

            if chunk.event in (RunEvent.run_content.value, TeamRunEvent.run_content.value):
                if chunk.content:
                    content_chunk_count += 1
                is_final = (
                    owner_name in ("Aetheria_AI", "Aetheria_Coder", "Aetheria_Computer", "Aetheria_System_Assistant")
                    and not getattr(chunk, 'member_responses', [])
                )
                # Include reasoning_content if present
                reasoning_content = getattr(chunk, 'reasoning_content', None)
                # Accumulate main content for catch-up buffer
                if is_final and chunk.content:
                    accumulated_content.append(str(chunk.content))
                    final_owner_name = owner_name
                elif (not is_final) and chunk.content and owner_name:
                    if owner_name not in accumulated_log_content:
                        accumulated_log_content[owner_name] = []
                        log_owner_order.append(owner_name)
                    accumulated_log_content[owner_name].append(str(chunk.content))
                socketio.emit("response", {
                    "content": chunk.content,
                    "streaming": True,
                    "id": message_id,
                    "agent_name": owner_name,
                    "is_log": not is_final,
                    "reasoning_content": reasoning_content
                }, room=room_name)  # <-- ROOM, not SID
            elif chunk.event in (RunEvent.tool_call_started.value, TeamRunEvent.tool_call_started.value):
                tool_call_count += 1
                tool_name = getattr(chunk.tool, 'tool_name', None)
                tool_payload = serialize_tool_event(getattr(chunk, "tool", None), chunk_obj=chunk)
                accumulated_content.clear()
                final_owner_name = None
                socketio.emit("assistant_response_reset", {
                    "id": message_id,
                }, room=room_name)
                socketio.emit("agent_step", {
                    "type": "tool_start",
                    "name": tool_name,
                    "agent_name": owner_name,
                    "id": message_id,
                    "tool": tool_payload,
                }, room=room_name)
                accumulated_events.append({
                    "type": "agent_step",
                    "step_type": "tool_start",
                    "name": tool_name,
                    "agent_name": owner_name,
                    "tool": tool_payload,
                })
            elif chunk.event in (RunEvent.tool_call_completed.value, TeamRunEvent.tool_call_completed.value):
                tool_name = getattr(chunk.tool, 'tool_name', None)
                tool_payload = serialize_tool_event(getattr(chunk, "tool", None), chunk_obj=chunk)
                tool_output = tool_payload.get("tool_output") if isinstance(tool_payload, dict) else None
                if isinstance(tool_output, dict):
                    tool_metadata = tool_output.get("metadata")
                elif isinstance(tool_payload, dict):
                    tool_metadata = tool_payload.get("metadata")
                else:
                    tool_metadata = None
                logger.info(
                    "[ToolEvent] tool_end name=%s owner=%s has_tool_payload=%s has_tool_output=%s has_metadata=%s preview_type=%s",
                    tool_name,
                    owner_name,
                    bool(tool_payload),
                    bool(tool_output),
                    bool(tool_metadata),
                    (tool_metadata or {}).get("preview_type") if isinstance(tool_metadata, dict) else None,
                )
                socketio.emit("agent_step", {
                    "type": "tool_end",
                    "name": tool_name,
                    "agent_name": owner_name,
                    "id": message_id,
                    "tool": tool_payload,
                }, room=room_name)
                accumulated_events.append({
                    "type": "agent_step",
                    "step_type": "tool_end",
                    "name": tool_name,
                    "agent_name": owner_name,
                    "tool": tool_payload,
                })
                completed_tool_history.append({
                    "name": tool_name,
                    "payload": tool_payload,
                })
            # Handle reasoning events
            elif chunk.event in (RunEvent.reasoning_step.value, TeamRunEvent.reasoning_step.value):
                reasoning_step = getattr(chunk, 'reasoning_step', None) or getattr(chunk, 'reasoning_content', None)
                if reasoning_step and not chunk_reasoning_content:
                    reasoning_text = str(reasoning_step)
                    reasoning_event_count += 1
                    socketio.emit("reasoning_step", {
                        "id": message_id,
                        "agent_name": owner_name,
                        "step": reasoning_text
                    }, room=room_name)
                    accumulated_events.append({
                        "type": "reasoning_step",
                        "agent_name": owner_name,
                        "step": reasoning_text,
                    })

        # 6. Finalize the Stream and Log Metrics
        final_content = "".join(accumulated_content) if accumulated_content else None
        if requested_mode == "system-assistant" and completed_tool_history and not final_content:
            final_content = build_system_assistant_terminal_message(completed_tool_history)
            if final_content:
                final_owner_name = "Aetheria_System_Assistant"
                socketio.emit("response", {
                    "content": final_content,
                    "streaming": True,
                    "id": message_id,
                    "agent_name": final_owner_name,
                    "is_log": False,
                }, room=room_name)

        socketio.emit("response", {"done": True, "id": message_id}, room=room_name)

        # --- Mark run as COMPLETED and store result for catch-up ---
        for owner_name in log_owner_order:
            log_content = "".join(accumulated_log_content.get(owner_name, []))
            if log_content:
                accumulated_events.append({
                    "type": "response",
                    "content": log_content,
                    "agent_name": owner_name,
                    "is_log": True,
                })
        if final_content:
            accumulated_events.append({
                "type": "response",
                "content": final_content,
                "agent_name": final_owner_name or "Aetheria_AI",
                "is_log": False,
            })
        if run_state_manager:
            # Fetch session title for notification
            conversation_title = None
            try:
                title_resp = supabase_client.from_("session_titles").select("tittle").eq("session_id", conversation_id).maybe_single().execute()
                if title_resp and title_resp.data:
                    conversation_title = title_resp.data.get("tittle")
            except Exception:
                pass
            run_state_manager.complete_run(
                conversation_id,
                message_id,
                final_content=final_content,
                events=accumulated_events,
                conversation_title=conversation_title,
            )
            # Session content cache removed - frontend handles caching
            # Broadcast completion notification to the conversation room
            # so the client can show a local notification if in background
            _preview_raw = (final_content or "").strip()
            _preview_clean = re.sub(r"^[#*_`>~\-\s]+", "", _preview_raw, flags=re.MULTILINE)
            _preview_clean = re.sub(r"\n+", " ", _preview_clean).strip()
            _preview = _preview_clean[:400] if _preview_clean else ""
            socketio.emit("run_completed", {
                "conversationId": conversation_id,
                "messageId": message_id,
                "title": conversation_title,
                "preview": _preview,
            }, room=room_name)

        logger.info(
            "[AGENT_RUNNER] COMPLETED RUN mode=%s message_id=%s "
            "content_chunks=%s reasoning_events=%s tool_calls=%s "
            "final_response_length=%s metrics_captured=%s",
            requested_mode,
            message_id,
            content_chunk_count,
            reasoning_event_count,
            tool_call_count,
            len(final_content or ""),
            run_output is not None,
        )

        try:
            _log_request_tokens(
                user_id=user_id,
                conversation_id=conversation_id,
                message_id=message_id,
                run_output=run_output,
            )
        except Exception as e:
            logger.error(f"Failed to write token usage logs for session {conversation_id}: {e}")

    except Exception as e:
        logger.error(f"Agent run failed for conversation {conversation_id}: {e}\n{traceback.format_exc()}")
        if run_state_manager:
            run_state_manager.fail_run(conversation_id, message_id, str(e))
            # Session content cache removed - frontend handles caching
        socketio.emit("error", {"message": f"An error occurred: {str(e)}. Your conversation is preserved."}, room=room_name)
