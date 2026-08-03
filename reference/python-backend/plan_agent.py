import logging
from typing import Any, Dict, Iterable, List, Optional

from agno.agent import Agent
from agno.run.agent import RunEvent
from agno.run.team import TeamRunEvent
from agno.tools.duckduckgo import DuckDuckGoTools

from tool_event_payload import serialize_tool_event

logger = logging.getLogger(__name__)


def _summarize_files(files: Iterable[Dict[str, Any]]) -> str:
    lines: List[str] = []
    for file_data in files or []:
        name = file_data.get("name") or file_data.get("filename") or "unnamed file"
        mime_type = file_data.get("type") or file_data.get("mime_type") or "unknown type"
        size = file_data.get("size")
        text_hint = "text-readable" if file_data.get("isText") else "binary/media"
        size_text = f", {size} bytes" if size else ""
        lines.append(f"- {name} ({mime_type}{size_text}, {text_hint})")
    return "\n".join(lines) if lines else "- No attached files."


def _summarize_context_sessions(sessions: Iterable[Dict[str, Any]]) -> str:
    lines: List[str] = []
    for index, session in enumerate(sessions or [], start=1):
        title = session.get("title") or session.get("name") or session.get("session_id") or f"Session {index}"
        interactions = session.get("interactions") or []
        lines.append(f"- {title}: {len(interactions)} prior interaction(s) selected.")
    return "\n".join(lines) if lines else "- No selected chat-history sessions."


def build_plan_prompt(
    message: str,
    config: Optional[Dict[str, Any]] = None,
    files: Optional[List[Dict[str, Any]]] = None,
    selected_sessions: Optional[List[Dict[str, Any]]] = None,
    workspace_context: Optional[Dict[str, Any]] = None,
) -> str:
    enabled_config = {
        key: value
        for key, value in (config or {}).items()
        if isinstance(value, bool) and value
    }
    return f"""
<user_request>
{message}
</user_request>

<selected_context>
{_summarize_context_sessions(selected_sessions or [])}
</selected_context>

<attached_files>
{_summarize_files(files or [])}
</attached_files>

<enabled_capabilities>
{enabled_config or "No enabled capability flags were provided."}
</enabled_capabilities>

<workspace_context>
{workspace_context or "No workspace context was provided."}
</workspace_context>

Create the final plan-mode output now.
""".strip()


PLAN_OUTPUT_SECTIONS = [
    "Refined Request",
    "Execution Plan",
    "Agents And Tools To Use",
    "Context To Preserve",
    "Verification And Success Criteria",
    "Final Prompt For Aetheria",
]


def create_plan_agent(debug_mode: bool = True, enable_read_only_tools: bool = True) -> Agent:
    from openrouter_reasoning_model import get_openrouter_model
    return Agent(
        name="plan_agent",
        model=get_openrouter_model("xiaomi/mimo-v2.5"),
        tools=[DuckDuckGoTools()] if enable_read_only_tools else [],
        instructions=[
            "<system_instructions>",
            "You are Aetheria's Plan Mode agent.",
            "Your job is to transform a user's raw request into a clear, high-signal execution plan for Aetheria AI's main llm_os.",
            "You understand this hierarchy: Aetheria_AI is the main team; it can use direct read/write tools, delegate coding tasks to a coder agent, delegate desktop/browser-control tasks to a computer agent, route GitHub/Vercel/Supabase work to a platform operations assistant, and route PowerPoint work to a presentation agent.",
            "Use read-only investigation only. You may search the web for current or ambiguous facts. Do not perform writes, mutations, external account changes, file changes, or user-visible side effects.",
            "Reason carefully about the user's intent, missing context, relevant tools, required agents, risk points, dependencies, and verification.",
            "Output a plan the user can edit and then submit as an improved prompt to llm_os.",
            "Keep the result practical and explicit. Include enough detail for the execution agent to act without guessing.",
            "Do not claim work has been completed. This is planning only.",
            "</system_instructions>",
            "",
            "<output_format>",
            "Return markdown with these sections:",
            "1. Refined Request",
            "2. Execution Plan",
            "3. Agents And Tools To Use",
            "4. Context To Preserve",
            "5. Verification And Success Criteria",
            "6. Final Prompt For Aetheria",
            "The Final Prompt section must be a self-contained instruction that can be sent directly to llm_os.",
            "</output_format>",
        ],
        debug_mode=debug_mode,
    )


def generate_plan(
    message: str,
    config: Optional[Dict[str, Any]] = None,
    files: Optional[List[Dict[str, Any]]] = None,
    selected_sessions: Optional[List[Dict[str, Any]]] = None,
    workspace_context: Optional[Dict[str, Any]] = None,
    debug_mode: bool = True,
) -> str:
    prompt = build_plan_prompt(
        message=message,
        config=config,
        files=files,
        selected_sessions=selected_sessions,
        workspace_context=workspace_context,
    )
    last_error: Optional[Exception] = None
    for enable_read_only_tools in (True, False):
        try:
            agent = create_plan_agent(
                debug_mode=debug_mode,
                enable_read_only_tools=enable_read_only_tools,
            )
            response = agent.run(prompt)
            content = getattr(response, "content", response)
            if isinstance(content, list):
                content = "\n".join(str(item) for item in content)
            plan = str(content or "").strip()
            if plan:
                return plan
        except Exception as exc:
            last_error = exc
            logger.warning(
                "Plan agent failed with read_only_tools=%s: %s",
                enable_read_only_tools,
                exc,
                exc_info=True,
            )

    logger.error("Plan agent unavailable; returning local fallback plan: %s", last_error)
    return build_local_fallback_plan(
        message=message,
        config=config,
        files=files,
        selected_sessions=selected_sessions,
        workspace_context=workspace_context,
    )


def stream_plan(
    message: str,
    config: Optional[Dict[str, Any]] = None,
    files: Optional[List[Dict[str, Any]]] = None,
    selected_sessions: Optional[List[Dict[str, Any]]] = None,
    workspace_context: Optional[Dict[str, Any]] = None,
    debug_mode: bool = True,
):
    prompt = build_plan_prompt(
        message=message,
        config=config,
        files=files,
        selected_sessions=selected_sessions,
        workspace_context=workspace_context,
    )
    last_error: Optional[Exception] = None
    for enable_read_only_tools in (True, False):
        final_chunks: List[str] = []
        emitted_reasoning_content: Dict[str, str] = {}
        emitted_content: Dict[str, str] = {}
        try:
            agent = create_plan_agent(
                debug_mode=debug_mode,
                enable_read_only_tools=enable_read_only_tools,
            )
            for chunk in agent.run(
                prompt,
                stream=True,
                stream_intermediate_steps=True,
            ):
                if not chunk or not hasattr(chunk, "event"):
                    continue

                owner_name = getattr(chunk, "agent_name", None) or getattr(chunk, "team_name", None) or "plan_agent"
                owner_reasoning_key = owner_name
                chunk_reasoning_content = getattr(chunk, "reasoning_content", None)
                if chunk_reasoning_content:
                    reasoning_text = str(chunk_reasoning_content)
                    previous_reasoning = emitted_reasoning_content.get(owner_reasoning_key, "")
                    reasoning_delta = reasoning_text
                    if previous_reasoning and reasoning_text.startswith(previous_reasoning):
                        reasoning_delta = reasoning_text[len(previous_reasoning):]
                    if reasoning_delta.strip():
                        yield {
                            "type": "reasoning",
                            "agent_name": owner_name,
                            "content": reasoning_delta,
                        }
                    emitted_reasoning_content[owner_reasoning_key] = reasoning_text

                if chunk.event in (RunEvent.run_content.value, TeamRunEvent.run_content.value):
                    if chunk.content:
                        text = str(chunk.content)
                        previous_content = emitted_content.get(owner_name, "")
                        content_delta = text
                        if previous_content and text.startswith(previous_content):
                            content_delta = text[len(previous_content):]
                        elif previous_content and previous_content.endswith(text):
                            content_delta = ""
                        emitted_content[owner_name] = text if text.startswith(previous_content) else f"{previous_content}{text}"
                        if not content_delta:
                            continue
                        final_chunks.append(content_delta)
                        yield {
                            "type": "content",
                            "agent_name": owner_name,
                            "content": content_delta,
                        }
                elif chunk.event in (RunEvent.tool_call_started.value, TeamRunEvent.tool_call_started.value):
                    tool_obj = getattr(chunk, "tool", None)
                    yield {
                        "type": "tool_start",
                        "agent_name": owner_name,
                        "name": getattr(tool_obj, "tool_name", None),
                        "tool": serialize_tool_event(tool_obj, chunk_obj=chunk),
                    }
                elif chunk.event in (RunEvent.tool_call_completed.value, TeamRunEvent.tool_call_completed.value):
                    tool_obj = getattr(chunk, "tool", None)
                    yield {
                        "type": "tool_end",
                        "agent_name": owner_name,
                        "name": getattr(tool_obj, "tool_name", None),
                        "tool": serialize_tool_event(tool_obj, chunk_obj=chunk),
                    }
                elif chunk.event in (RunEvent.reasoning_step.value, TeamRunEvent.reasoning_step.value):
                    reasoning_step = getattr(chunk, "reasoning_step", None) or getattr(chunk, "reasoning_content", None)
                    if reasoning_step and not chunk_reasoning_content:
                        yield {
                            "type": "reasoning",
                            "agent_name": owner_name,
                            "content": str(reasoning_step),
                        }

            plan = "".join(final_chunks).strip()
            if plan:
                yield {"type": "done", "plan": plan}
                return
        except Exception as exc:
            last_error = exc
            logger.warning(
                "Plan stream failed with read_only_tools=%s: %s",
                enable_read_only_tools,
                exc,
                exc_info=True,
            )
            if enable_read_only_tools:
                yield {
                    "type": "reasoning",
                    "agent_name": "plan_agent",
                    "content": "The read-only research pass was unavailable, so I am preparing the plan without external lookup.",
                }

    logger.error("Plan stream unavailable; returning local fallback plan: %s", last_error)
    yield {
        "type": "done",
        "plan": build_local_fallback_plan(
            message=message,
            config=config,
            files=files,
            selected_sessions=selected_sessions,
            workspace_context=workspace_context,
        ),
    }


def _enabled_capability_names(config: Optional[Dict[str, Any]]) -> List[str]:
    labels = {
        "internet_search": "internet search",
        "coding_assistant": "coder agent",
        "enable_github": "GitHub tools",
        "enable_google_email": "Google Email tools",
        "enable_vercel": "Vercel tools",
        "enable_google_drive": "Google Drive tools",
        "enable_google_sheets": "Google Sheets tools",
        "enable_supabase": "Supabase tools",
        "enable_composio_whatsapp": "WhatsApp tools",
        "enable_computer_control": "computer-control agent",
    }
    enabled = []
    for key, label in labels.items():
        if (config or {}).get(key):
            enabled.append(label)
    return enabled


def build_local_fallback_plan(
    message: str,
    config: Optional[Dict[str, Any]] = None,
    files: Optional[List[Dict[str, Any]]] = None,
    selected_sessions: Optional[List[Dict[str, Any]]] = None,
    workspace_context: Optional[Dict[str, Any]] = None,
) -> str:
    enabled = _enabled_capability_names(config)
    file_count = len(files or [])
    context_count = len(selected_sessions or [])
    capability_text = ", ".join(enabled) if enabled else "the default Aetheria AI capabilities"
    request_text = message.strip() or "Use the attached files and selected context to infer and complete the user's task."

    return f"""## Refined Request
{request_text}

## Execution Plan
1. Read the user's request, selected chat context, workspace context, and any attached files before taking action.
2. Identify whether the task needs coding, browser/computer control, platform operations, document/media generation, or normal reasoning.
3. Use the smallest capable agent/tool path for each part of the task.
4. Preserve user intent while converting ambiguous parts into concrete implementation steps.
5. Complete the task, verify the result, and summarize the important outcome clearly.

## Agents And Tools To Use
Use {capability_text}. Prefer the coder agent for codebase changes, the computer-control agent for desktop/browser actions, the platform operations assistant for GitHub/Vercel/Supabase work, and the presentation agent for PowerPoint tasks.

## Context To Preserve
- Original user request: {request_text}
- Attached files available: {file_count}
- Selected chat-history sessions available: {context_count}
- Workspace context: {workspace_context or "none provided"}

## Verification And Success Criteria
- The final work satisfies the user's stated request.
- Any changed files or external actions are verified with appropriate tests, checks, screenshots, or inspection.
- The response explains what changed and calls out anything that could not be verified.

## Final Prompt For Aetheria
{request_text}

Use the available context, files, and enabled tools to complete this task end to end. Plan the work internally, choose the correct specialized agents when useful, implement the needed changes or actions, verify the result, and report the outcome clearly."""
