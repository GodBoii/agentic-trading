import os
from typing import Any, Dict, List, Optional, Union

from agno.agent import Agent
from agno.db.postgres import PostgresDb
from openrouter_reasoning_model import get_openrouter_model
from agno.models.groq import Groq
from agno.tools import Toolkit

from user_file_vault_tools import UserFileVaultTools
from deployed_project_tools import DeployedProjectTools
from github_tools import GitHubTools
from agno.models.google import Gemini
from local_coder_tools import LocalCoderTools
from sandbox_persistence import get_persistence_service
from sandbox_tools import SandboxTools
from database_config import get_sqlalchemy_database_url


def _db_url_sqlalchemy() -> str:
    return get_sqlalchemy_database_url()


def get_coder_agent(
    user_id: Optional[str] = None,
    session_info: Optional[Dict[str, Any]] = None,
    browser_tools_config: Optional[Dict[str, Any]] = None,
    custom_tool_config: Optional[Dict[str, Any]] = None,
    session_id: Optional[str] = None,
    message_id: Optional[str] = None,
    use_memory: bool = False,
    use_session_summaries: bool = False,
    debug_mode: bool = True,
    enable_github: bool = True,
    coder_execution_target: str = "cloud",
    delegation_id: Optional[str] = None,
    delegated_agent: Optional[str] = None,
    persist_session: bool = True,
) -> Agent:
    """
    Dedicated coding-only Agent used for project workspace mode.
    Persists sessions/runs in Postgres when persist_session is enabled.
    """
    _ = custom_tool_config

    db = (
        PostgresDb(
            db_url=_db_url_sqlalchemy(),
            db_schema="public",
        )
        if persist_session
        else None
    )

    persistence_service = get_persistence_service()
    socketio_instance = browser_tools_config.get("socketio") if browser_tools_config else None
    sid = browser_tools_config.get("sid") if browser_tools_config else None
    redis_client_instance = browser_tools_config.get("redis_client") if browser_tools_config else None

    session_config = (session_info or {}).get("config", {}) if isinstance(session_info, dict) else {}
    workspace_context = session_config.get("workspace_context", {}) if isinstance(session_config, dict) else {}
    local_context = workspace_context.get("local_context", {}) if isinstance(workspace_context, dict) else {}
    local_root = local_context.get("root_path")

    normalized_target = str(coder_execution_target or "cloud").strip().lower()
    if normalized_target not in ("cloud", "local"):
        normalized_target = "cloud"

    if normalized_target == "local":
        coder_tools: List[Union[Toolkit, callable]] = [
            LocalCoderTools(
                sid=sid,
                socketio=socketio_instance,
                redis_client=redis_client_instance,
                workspace_root=local_root,
                message_id=message_id,
                conversation_id=session_id,
                delegation_id=delegation_id,
                delegated_agent=delegated_agent,
            )
        ]
    else:
        coder_tools = [
            SandboxTools(
                session_info=session_info or {},
                persistence_service=persistence_service,
                user_id=user_id,
                session_id=session_id,
                message_id=message_id,
                socketio=socketio_instance,
                sid=sid,
                redis_client=redis_client_instance,
                delegation_id=delegation_id,
                delegated_agent=delegated_agent,
            )
        ]

    if user_id:
        coder_tools.append(DeployedProjectTools(user_id=user_id))
        coder_tools.append(UserFileVaultTools(user_id=user_id))
        if enable_github:
            coder_tools.append(GitHubTools(user_id=user_id))

    return Agent(
        name="Aetheria_Coder",
        model=get_openrouter_model("xiaomi/mimo-v2.5"),
        role=(
            "Dedicated software engineering agent for project mode. "
            "Executes coding, repository, sandbox, file-vault, and deployment operations."
        ),
        tools=coder_tools,
        instructions=[
            "<system_instructions>",
            "You are Aetheria Coder. Focus only on software engineering tasks.",
            "Use deterministic implementation flow: inspect -> edit -> verify -> summarize.",
            "Cloud workspace root: /home/sandboxuser/workspace. In local mode, use provided local workspace root only.",
            "Prefer surgical edits over full-file rewrites.",
            "Before deployment operations, resolve project context first.",
            "For persistent user documents/assets, use UserFileVaultTools list/get/read methods.",
            "For deployed-site changes: copy_deployed_project -> edit -> redeploy_project.",
            "Keep responses concise, implementation-first, and verifiable.",
            "</system_instructions>",
            "",
            "<frontend>",
            "Build responsive, production-grade UI and preserve existing design language unless user requests redesign.",
            "Use semantic HTML and reusable CSS classes.",
            "When touching interaction flows, keep backward compatibility for existing controls.",
            "For file preview/edit features, handle large content safely and avoid blocking UI.",
            "Preserve accessibility basics (labels, keyboard behavior, focus states).",
            "</frontend>",
            "",
            "<backend>",
            "Validate/sanitize all inputs at API boundaries.",
            "Keep API response shapes stable for existing clients.",
            "Enforce ownership/auth checks for project/session/file access.",
            "Use explicit error handling and actionable error messages.",
            "Use parameterized data access patterns and avoid inline secrets.",
            "Protect deployment/runtime boundaries and avoid unsafe data exposure.",
            "</backend>",
        ],
        user_id=user_id,
        db=db,
        enable_agentic_memory=use_memory,
        enable_user_memories=use_memory,
        enable_session_summaries=use_session_summaries,
        stream_intermediate_steps=True,
        search_knowledge=False,
        add_history_to_context=True,
        num_history_runs=40,
        store_events=True,
        add_datetime_to_context=True,
        debug_mode=debug_mode,
    )
