# python-backend/system_assistant.py

import logging
from typing import Any, Dict, Optional

from agno.agent import Agent
from agno.db.postgres import PostgresDb
from openrouter_reasoning_model import get_openrouter_model
from agno.models.groq import Groq

from database_config import get_sqlalchemy_database_url
from mobile_tools import MobileTools

logger = logging.getLogger(__name__)


def get_system_assistant(
    mobile_tools_config: Optional[Dict[str, Any]] = None,
    user_id: Optional[str] = None,
    debug_mode: bool = False,
) -> Agent:
    """
    Constructs the lightweight System Assistant Agent.

    Persists short conversation history so follow-up voice requests retain
    context while keeping long-term user memory disabled.
    Supports multimodal inputs (text + images).
    """
    system_instructions = [
        "You are Aetheria, an AI assistant for mobile voice and visual interactions.",
        "",
        "RESPONSE STYLE:",
        "- BE CONCISE - users are on mobile devices",
        "- Direct answers, no lengthy explanations",
        "- Natural, conversational language",
        "- Focus on being helpful and accurate",
        "- Analyze screenshots and images from Circle to Search",
        "",
        "VISUAL ANALYSIS (Circle to Search):",
        "- When provided with a screenshot, analyze what is visible and give short concise response",
        "- Identify text, UI elements, content, or objects in the image",
        "- Provide helpful context or explanations about what you see",
        "- If text is visible, read and explain it",
        "- If it is a UI element, explain what it does",
        "- Keep visual descriptions brief and actionable",
        "- Combine visual context with the user question for best results",
    ]

    tools = []
    if mobile_tools_config:
        sid = mobile_tools_config.get("sid")
        socketio = mobile_tools_config.get("socketio")
        redis_client = mobile_tools_config.get("redis_client")

        if sid and socketio and redis_client:
            tools.append(MobileTools(**mobile_tools_config))
            system_instructions.extend(
                [
                    "",
                    "MOBILE TOOLING:",
                    "- You can use native mobile tools to inspect and control the phone.",
                    "- Always start with context: get_active_app_context or get_device_state.",
                    "- For app launching: call list_apps first if app name is ambiguous, then open_app.",
                    "- For toggles use act_settings (wifi/bluetooth/location/auto_rotate/dnd where supported).",
                    "- For value changes use modify_settings (volume, brightness, dnd filter).",
                    "- For reminders/time tasks: use set_alarm and set_timer.",
                    "- For notes tasks: use create_note, search_notes, get_note, append_note.",
                    "- For communication tasks: use send_message with requested channel and recipient.",
                    "- Prefer semantic UI actions (tap_text, input_text) before coordinate gestures (tap, swipe).",
                    "- Use navigation helpers when needed: press_back, open_notifications, open_quick_settings, open_recents.",
                    "- Keep actions safe and intentional; avoid repetitive destructive loops.",
                ]
            )
        else:
            logger.warning(
                "System assistant mobile tools config incomplete. sid=%s socketio=%s redis=%s",
                bool(sid),
                bool(socketio),
                bool(redis_client),
            )

    agent = Agent(
        name="Aetheria_System_Assistant",
        model=get_openrouter_model("xiaomi/mimo-v2.5"),
        instructions=system_instructions,
        tools=tools,
        user_id=user_id,
        db=PostgresDb(
            db_url=get_sqlalchemy_database_url(),
            db_schema="public",
        ),
        add_history_to_context=True,
        num_history_runs=12,
        store_events=True,
        markdown=True,
        debug_mode=debug_mode,
    )

    return agent
