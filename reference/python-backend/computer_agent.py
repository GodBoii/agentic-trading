import os
from typing import Any, Dict, List, Optional, Union

from agno.agent import Agent
from agno.db.postgres import PostgresDb
from agno.models.groq import Groq
from openrouter_reasoning_model import get_openrouter_model
from agno.tools import Toolkit

from browser_tools import BrowserTools
from browser_tools_server import ServerBrowserTools
from computer_tools import ComputerTools
from google_drive_tools import GoogleDriveTools
from google_email_tools import GoogleEmailTools
from google_sheets_tools import GoogleSheetsTools
from database_config import get_sqlalchemy_database_url


def _db_url_sqlalchemy() -> str:
    return get_sqlalchemy_database_url()


def get_computer_agent(
    user_id: Optional[str] = None,
    session_info: Optional[Dict[str, Any]] = None,
    browser_tools_config: Optional[Dict[str, Any]] = None,
    computer_tools_config: Optional[Dict[str, Any]] = None,
    session_id: Optional[str] = None,
    message_id: Optional[str] = None,
    use_memory: bool = False,
    use_session_summaries: bool = False,
    debug_mode: bool = True,
    enable_google_email: bool = False,
    enable_google_drive: bool = False,
    enable_google_sheets: bool = False,
    delegation_id: Optional[str] = None,
    delegated_agent: Optional[str] = None,
    persist_session: bool = True,
) -> Agent:
    """
    Dedicated desktop/browser automation agent used for computer workspace mode.
    """
    db = (
        PostgresDb(
            db_url=_db_url_sqlalchemy(),
            db_schema="public",
        )
        if persist_session
        else None
    )

    tools: List[Union[Toolkit, callable]] = []

    if computer_tools_config:
        merged_computer_config = dict(computer_tools_config)
        if delegation_id and "delegation_id" not in merged_computer_config:
            merged_computer_config["delegation_id"] = delegation_id
        if delegated_agent and "delegated_agent" not in merged_computer_config:
            merged_computer_config["delegated_agent"] = delegated_agent
        tools.append(ComputerTools(**merged_computer_config))

    if browser_tools_config:
        device_type = (session_info or {}).get("device_type", "web")
        if device_type == "desktop":
            tools.append(BrowserTools(**browser_tools_config))
        else:
            tools.append(
                ServerBrowserTools(
                    session_id=session_id,
                    user_id=user_id,
                    socketio=browser_tools_config.get("socketio"),
                    sid=browser_tools_config.get("sid"),
                    redis_client=browser_tools_config.get("redis_client"),
                    message_id=message_id,
                )
            )

    if user_id and (enable_google_email or enable_google_drive or enable_google_sheets):
        if enable_google_email:
            tools.append(GoogleEmailTools(user_id=user_id))
        if enable_google_drive:
            tools.append(GoogleDriveTools(user_id=user_id))
        if enable_google_sheets:
            tools.append(GoogleSheetsTools(user_id=user_id))

    return Agent(
        name="Aetheria_Computer",
        model=get_openrouter_model("xiaomi/mimo-v2.5"),
        role=(
            "Dedicated computer control and browser automation agent. "
            "Executes local desktop actions and interactive browser tasks."
        ),
        tools=tools,
        instructions=[
            "<system_instructions>",
            "You are Aetheria Computer. Focus only on computer-control and browser-automation tasks.",
            "Always check capability/permission state before first control action.",
            "For file operations: never use placeholder paths like /path/to/folder.",
            "When user says 'this folder' or selected scope, call ComputerTools.get_status() and use scopes[0] as the base directory.",
            "For desktop actions: observe -> act -> verify loop with screenshots/status checks.",
            "For browser actions: ALWAYS call get_browser_status() FIRST to launch/connect browser, then execute navigation/interactions.",
            "when using the browser tools you will get screenshot of browser after using a tool and if you still want to see what is on the browser use (get_current_view) tool."
            "Use safe, reversible actions first; confirm destructive operations with user intent.",
            "Keep responses concise, action-oriented, and outcome-verified.",
            "When you use Browser_tools you get a dedicated chrome browser you can use all the browser_tools to control and operate the browser",
            "dont use computer_tools to complete any browser related task for eg. if you want to get screenshot of the browser use (get_current_view) tool this gives you screenshot of the browser you are operating",
            "dont get conffused with (take_screenshot) and (get_current_view) tools take_screenshot gives you the image of users computer and (get_current_view) gives you the image of the browser you are using to complete users task",
            "When asked to open or use a software application, first call list_installed_apps() to discover available applications. Verify the exact name or command, then call open_application(app_name).",
            "When asked how many apps or what apps are installed, use list_installed_apps() to get the complete list.",
            "For precise clicking: prefer find_element_by_text() or get_screen_elements() to locate exact coordinates of buttons and UI controls instead of guessing from screenshots. This uses the OS accessibility tree for pixel-perfect targeting.",
            "</system_instructions>",
            "",
            "<tools>",
            "ComputerTools: request_permission, get_status, screenshot/mouse/keyboard/window/system operations, list_installed_apps, get_screen_elements, find_element_by_text.",
            "BrowserTools/ServerBrowserTools: get_browser_status (call first!), navigation, interaction, extraction.",
            "GoogleEmailTools: read/send/search/reply/label emails.",
            "GoogleDriveTools: search/read/create/share files.",
            "GoogleSheetsTools: search sheets, list tabs, inspect sheet info, read/batch-read ranges, write/append/batch-write/clear ranges, add/rename/delete tabs, create spreadsheets.",
            "</tools>",
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
