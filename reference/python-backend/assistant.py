# python-backend/assistant.py

import logging
import os
from typing import Any, Dict, List, Optional, Union

from agno.agent import Agent
from agno.db.postgres import PostgresDb
from agno.run.team import TeamRunEvent
from agno.team import Team
from agno.tools import Toolkit
from agno.tools.duckduckgo import DuckDuckGoTools

from agent_delegation_tools import AgentDelegationTools
from browser_tools import BrowserTools
from browser_tools_server import ServerBrowserTools
from composio_tools import ComposioWhatsAppTools, has_active_whatsapp_connection
from database_config import get_sqlalchemy_database_url
from github_tools import GitHubTools
from google_drive_tools import GoogleDriveTools
from google_email_tools import GoogleEmailTools
from google_sheets_tools import GoogleSheetsTools
from media_tools import MediaTools
from ppt_tools import build_presentation_agent
from supabase_tools import SupabaseTools
from user_file_vault_tools import UserFileVaultTools
from vercel_tools import VercelTools

logger = logging.getLogger(__name__)


# FUNCTION DESCRIPTION:
# Factory function that builds and returns the core Aetheria AI Agent Team (Team class instance).
# It compiles system prompts, configures agentic database memory (PostgresDb), and dynamically
# registers specialized toolkits (Gmail, Drive, Sheets, Browser, Media Tools, WhatsApp) and
# binds platform operations sub-agents (GitHub, Vercel, Supabase) and presentation specialists based on active parameters.
#
# UPSTREAM CALLER:
# - Called by `run_agent_and_stream()` in `python-backend/agent_runner.py` during session execution initialization.
#
# DOWNSTREAM IMPACT:
# - Changing registered tool arguments here directly impacts the LLM's system instructions and action capabilities.
# - Tool parameters (e.g. `enable_google_sheets`) must correspond directly with the config keys synchronized in
#   `on_send_message()` (`python-backend/sockets.py`) and toggled on the UI panel in `js/chat.js`.
def get_llm_os(
    user_id: Optional[str] = None,
    session_info: Optional[Dict[str, Any]] = None,
    internet_search: bool = False,
    coding_assistant: bool = False,
    Planner_Agent: bool = True,
    enable_supabase: bool = False,
    use_memory: bool = False,
    use_session_summaries: bool = False,
    debug_mode: bool = True,
    enable_github: bool = False,
    enable_vercel: bool = False,
    enable_google_email: bool = False,
    enable_google_drive: bool = False,
    enable_google_sheets: bool = False,
    enable_composio_whatsapp: bool = False,
    enable_browser: bool = False,
    enable_computer_control: bool = False,
    browser_tools_config: Optional[Dict[str, Any]] = None,
    computer_tools_config: Optional[Dict[str, Any]] = None,
    custom_tool_config: Optional[Dict[str, Any]] = None,
    session_id: Optional[str] = None,
    message_id: Optional[str] = None,
    enable_user_file_vault: bool = True,
) -> Team:
    """
    Build the main Aetheria AI team.

    Planner_Agent is kept in the signature for compatibility with existing
    callers, but planner/dev-team sub-agents have been removed. Coding now
    flows through the explicit delegate_to_coder tool when realtime context is
    available.
    """
    _ = Planner_Agent
    _ = computer_tools_config

    from openrouter_reasoning_model import get_openrouter_model

    direct_tools: List[Union[Toolkit, callable]] = []
    members: List[Union[Agent, Team]] = []
    db = PostgresDb(
        db_url=get_sqlalchemy_database_url(),
        db_schema="public",
    )

    connected_platform_tools: List[Union[Toolkit, callable]] = []
    connected_platform_instructions = [
        "<system_instructions>",
        "You are assistant, Aetheria AI's platform operations specialist.",
        "Own GitHub, Vercel, and Supabase work when those integrations are available.",
        "Be precise with identifiers, repository names, project names, organization scopes, branch names, deployment IDs, domains, database refs, bucket names, and environment variable keys.",
        "Before mutating external services, inspect current state and choose the smallest reversible action that satisfies the user request.",
        "For destructive actions, risky production changes, secret changes, database deletion, project deletion, domain reassignment, or forceful git operations, ask for explicit confirmation.",
        "Return a concise operational result that Aetheria AI can present naturally to the user.",
        "</system_instructions>",
        "",
        "<available_tools>",
    ]

    if enable_github and user_id:
        connected_platform_tools.append(GitHubTools(user_id=user_id))
        connected_platform_instructions.extend(
            [
                "- GitHubTools are available.",
                "  Use GitHubTools for repository discovery, file reads, branch operations, commits, pull requests, issues, and GitHub metadata.",
                "  Prefer reading repository state before writing. For code changes, use a branch and clear commit/PR messages unless the user explicitly requests direct changes.",
            ]
        )

    if enable_vercel and user_id:
        connected_platform_tools.append(VercelTools(user_id=user_id))
        connected_platform_instructions.extend(
            [
                "- VercelTools are available.",
                "  Use VercelTools for deployments, project lookup, environment variables, domains, aliases, and deployment status.",
                "  When a Vercel action depends on source code or repository metadata, resolve the GitHub repository/project relationship first if GitHubTools are also available.",
                "  Never expose secret values. Treat environment variable names as okay to mention, but values as sensitive.",
            ]
        )

    if enable_supabase and user_id:
        connected_platform_tools.append(SupabaseTools(user_id=user_id))
        connected_platform_instructions.extend(
            [
                "- SupabaseTools are available.",
                "  Use SupabaseTools for project management, storage buckets, secrets, edge functions, and Supabase platform operations.",
                "  Verify project identity before making changes. Be especially careful with production databases, auth settings, secrets, storage policies, and edge functions.",
            ]
        )

    if connected_platform_tools:
        connected_platform_instructions.append("</available_tools>")
        members.append(
            Agent(
                name="assistant",
                model=get_openrouter_model("xiaomi/mimo-v2.5"),
                role=(
                    "Platform operations assistant for GitHub, Vercel, and Supabase. "
                    "Handles repository, deployment, and backend platform tasks delegated by Aetheria AI."
                ),
                tools=connected_platform_tools,
                instructions=connected_platform_instructions,
                debug_mode=debug_mode,
            )
        )

    if (enable_google_email or enable_google_drive or enable_google_sheets) and user_id:
        if enable_google_email:
            direct_tools.append(GoogleEmailTools(user_id=user_id))
        if enable_google_drive:
            direct_tools.append(GoogleDriveTools(user_id=user_id))
        if enable_google_sheets:
            direct_tools.append(GoogleSheetsTools(user_id=user_id))

    if internet_search:
        direct_tools.append(DuckDuckGoTools())

    if enable_browser and browser_tools_config:
        device_type = session_info.get("device_type", "web") if session_info else "web"
        if device_type == "desktop":
            logger.info("[Browser Tool] Using CLIENT-SIDE browser for desktop (session: %s)", session_id)
            direct_tools.append(BrowserTools(**browser_tools_config))
        else:
            logger.info("[Browser Tool] Using SERVER-SIDE browser for %s (session: %s)", device_type, session_id)
            direct_tools.append(
                ServerBrowserTools(
                    session_id=session_id,
                    user_id=user_id,
                    socketio=browser_tools_config.get("socketio"),
                    sid=browser_tools_config.get("sid"),
                    redis_client=browser_tools_config.get("redis_client"),
                    message_id=message_id,
                )
            )

    if enable_composio_whatsapp and user_id and os.getenv("COMPOSIO_API_KEY"):
        if has_active_whatsapp_connection(user_id=user_id):
            direct_tools.append(ComposioWhatsAppTools(user_id=user_id))
        else:
            logger.info("Composio WhatsApp not active for user %s. Toolkit not injected.", user_id)
    if custom_tool_config:
        direct_tools.append(MediaTools(custom_tool_config=custom_tool_config))
    if enable_user_file_vault and user_id:
        direct_tools.append(UserFileVaultTools(user_id=user_id))

    socketio_instance = browser_tools_config.get("socketio") if browser_tools_config else None
    sid = browser_tools_config.get("sid") if browser_tools_config else None
    redis_client_instance = browser_tools_config.get("redis_client") if browser_tools_config else None
    has_socket_context = bool(socketio_instance and sid and session_id and message_id)
    can_delegate_coder = bool(has_socket_context and coding_assistant)
    can_delegate_computer = bool(has_socket_context and enable_computer_control and redis_client_instance)

    if has_socket_context:
        members.append(
            build_presentation_agent(
                user_id=user_id,
                session_id=session_id,
                message_id=message_id,
                socketio=socketio_instance,
                sid=sid,
                debug_mode=debug_mode,
            )
        )

    if can_delegate_coder or can_delegate_computer:
        direct_tools.append(
            AgentDelegationTools(
                user_id=user_id,
                session_info=session_info,
                session_id=session_id,
                message_id=message_id,
                socketio=socketio_instance,
                sid=sid,
                redis_client=redis_client_instance,
                use_memory=use_memory,
                use_session_summaries=use_session_summaries,
                debug_mode=debug_mode,
                enable_github=enable_github,
                enable_coder=can_delegate_coder,
                enable_computer=can_delegate_computer,
            )
        )

    aetheria_instructions = [
        "<system_instructions>",
        "You are Aetheria AI, providing deeply personalized responses using all available user context.",
        "Access context via session_state['turn_context'].",
        "Users talk directly to you. Use direct tools and explicit delegation tools silently and effectively.",
        "When delegation tools are available in main mode, use `delegate_to_coder(task_description)` for coding tasks and `delegate_to_computer(task_description)` for desktop/browser control tasks.",
        "Use DuckDuckGoTools for current internet data when needed.",
        "BrowserTools gives you access to a complete browser. Always call get_browser_status() first before browser actions.",
        "Use every available tool and method to fulfil user demands. If a tool fails, silently try alternatives before giving up.",
        "If the user asks for diagrams, provide Mermaid diagrams. Generate images only when explicitly asked or when it is the most logical choice.",
        "Never use phrases like 'I will now', 'based on my knowledge', 'I was informed by', 'delegating to', or any language that exposes internal processes.",
        "Deliver every result as if you personally completed it: natural, direct, and focused entirely on user value.",
        "Never explain what tools you used, which agents you called, or what happened internally.",
        "</system_instructions>",
        "",
        "<tools>",
        "You directly own and execute these tools; do not delegate tasks that require them:",
        "- BrowserTools: browser automation; always call get_browser_status() first",
        "- GoogleEmailTools: read, send, search, reply, label emails",
        "- GoogleDriveTools: search, read, create, share files",
        "- GoogleSheetsTools: search sheets, inspect tabs, read/write ranges, create spreadsheets",
        "- MediaTools: generate_image(prompt) and generate_video(prompt)",
        "- composio_whatsapp_tools: list_whatsapp_actions() first, then execute with exact tool_slug",
        "- DuckDuckGoTools: fast web search",
        "- delegate_to_coder: dedicated coding-agent execution in realtime main-mode sessions",
        "- delegate_to_computer: dedicated computer-agent execution when computer control is enabled",
        "</tools>",
    ]

    if members:
        aetheria_instructions.extend(
            [
                "",
                "<members>",
                "- assistant: platform operations specialist. Route GitHub, Vercel, and Supabase work to this member instead of trying to perform those operations directly.",
                "- presentation_agent: native PowerPoint specialist. Route requests to create, edit, outline, or download PowerPoint/PPT/PPTX decks to this member. The member creates editable .pptx files using native PowerPoint elements, not HTML/CSS slide exports.",
                "- If a presentation request includes a hidden presentation template instruction, preserve that exact template id when routing the task to presentation_agent.",
                "</members>",
            ]
        )

    return Team(
        name="Aetheria_AI",
        model=get_openrouter_model("xiaomi/mimo-v2.5"),
        members=members,
        tools=direct_tools,
        instructions=aetheria_instructions,
        user_id=user_id,
        db=db,
        enable_agentic_memory=use_memory,
        enable_user_memories=use_memory,
        enable_session_summaries=use_session_summaries,
        stream_intermediate_steps=True,
        search_knowledge=use_memory,
        send_media_to_model=True,
        store_media=True,
        events_to_skip=[
            TeamRunEvent.run_started,
            TeamRunEvent.run_completed,
            TeamRunEvent.memory_update_started,
            TeamRunEvent.memory_update_completed,
        ],
        read_team_history=True,
        add_history_to_context=True,
        num_history_runs=40,
        store_events=True,
        add_datetime_to_context=True,
        debug_mode=debug_mode,
    )
