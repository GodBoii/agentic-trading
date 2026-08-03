# python-backend/task_executor.py
"""
Autonomous Task Execution Service
Uses the main LLM-OS agent with user-selected tools + server-side browser
for background execution of scheduled tasks.
"""

import logging
import traceback
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from extensions import socketio
from supabase_client import supabase_client

logger = logging.getLogger(__name__)


def run_autonomous_task(task_id: str, user_id: str, sid: str = None):
    """
    Executes a task autonomously using the main LLM-OS agent (Aetheria AI Team).
    
    Reads the task metadata to determine which tools to enable,
    applies custom instructions, and runs the agent to completion.
    
    Args:
        task_id: UUID of the task to execute
        user_id: User ID who owns the task
        sid: Socket ID for status notifications (optional)
    """
    try:
        logger.info(f"🎯 Starting autonomous execution for task {task_id}")

        # Emit processing status
        if sid:
            socketio.emit("task_execution_status", {
                "task_id": task_id,
                "status": "processing",
                "message": "AI is working on your task..."
            }, room=sid)

        # Fetch task details
        response = supabase_client.table("tasks").select("*").eq("id", task_id).eq("user_id", user_id).single().execute()
        if not response.data:
            logger.error(f"❌ Task not found: {task_id}")
            if sid:
                socketio.emit("task_execution_status", {
                    "task_id": task_id, "status": "error", "message": "Task not found"
                }, room=sid)
            return

        task_data = response.data
        task_description = task_data.get('text', '')
        task_detail_description = task_data.get('description', '')
        task_priority = task_data.get('priority', 'medium')
        metadata = task_data.get('metadata', {}) or {}

        logger.info(f"📝 Task: {task_description}")
        logger.info(f"⚡ Priority: {task_priority}")
        logger.info(f"🔧 Metadata: {metadata}")

        # Extract tool configuration from metadata
        selected_tools = metadata.get('tools', ['internet_search'])
        custom_instructions = metadata.get('custom_instructions', '')
        use_main_agent = metadata.get('use_main_agent', True)

        # Map tool selections to assistant.py parameters
        enable_internet = 'internet_search' in selected_tools
        enable_browser = 'browser' in selected_tools
        enable_email = 'email' in selected_tools
        enable_drive = 'google_drive' in selected_tools
        enable_sheets = 'google_sheets' in selected_tools
        enable_github = 'github' in selected_tools

        logger.info(f"🛠️  Tools: search={enable_internet}, browser={enable_browser}, email={enable_email}, drive={enable_drive}, sheets={enable_sheets}, github={enable_github}")

        # Build the LLM-OS agent with selected tools
        from assistant import get_llm_os
        from browser_tools_server import ServerBrowserTools

        # Prepare browser config if browser tool is selected
        browser_tools_config = None
        if enable_browser:
            # For background tasks, use server-side browser without socket streaming
            browser_tools_config = {
                'socketio': socketio,
                'sid': sid,
                'redis_client': None,  # No redis needed for background tasks
            }

        # Create the main LLM-OS team with task-specific configuration
        team = get_llm_os(
            user_id=user_id,
            internet_search=enable_internet,
            enable_google_email=enable_email,
            enable_google_drive=enable_drive,
            enable_google_sheets=enable_sheets,
            enable_github=enable_github,
            enable_browser=enable_browser,
            browser_tools_config=browser_tools_config,
            enable_supabase=False,
            use_memory=True,
            debug_mode=False,
            session_id=f"task-{task_id}",
            message_id=f"task-exec-{task_id}",
        )

        # Build the execution prompt
        prompt_parts = [
            f"AUTONOMOUS TASK EXECUTION - Complete this task fully and save the result.",
            f"",
            f"TASK: {task_description}",
        ]
        if task_detail_description:
            prompt_parts.append(f"DETAILS: {task_detail_description}")
        if custom_instructions:
            prompt_parts.append(f"")
            prompt_parts.append(f"CUSTOM INSTRUCTIONS: {custom_instructions}")
        prompt_parts.extend([
            f"",
            f"PRIORITY: {task_priority}",
            f"",
            f"REQUIREMENTS:",
            f"- Complete this task fully and autonomously",
            f"- Use all available tools as needed",
            f"- Generate comprehensive, actionable output",
            f"- Provide results in well-structured format",
            f"- Do NOT ask questions or wait for input",
        ])

        kickoff_prompt = "\n".join(prompt_parts)

        logger.info(f"▶️  Running LLM-OS agent for task {task_id}...")

        # Run the team (non-streaming for background execution)
        run_response = team.run(
            input=kickoff_prompt,
            stream=False
        )

        # Extract the response content
        work_output = ""
        if run_response and hasattr(run_response, 'content') and run_response.content:
            work_output = run_response.content
            logger.info(f"📊 Agent response: {len(work_output)} characters")
        else:
            work_output = "Task execution completed but no output was generated."
            logger.warning(f"⚠️ No content in agent response for task {task_id}")

        # Save work output to task
        supabase_client.table("tasks").update({
            "task_work": work_output,
            "status": "completed",
            "completed_at": datetime.now(timezone.utc).isoformat()
        }).eq("id", task_id).execute()

        logger.info(f"✅ Task {task_id} completed and work saved")

        # Emit success
        if sid:
            socketio.emit("task_execution_status", {
                "task_id": task_id,
                "status": "completed",
                "message": "Task completed successfully!"
            }, room=sid)

    except Exception as e:
        logger.error(f"❌ Error executing task {task_id}: {e}")
        logger.error(f"   Traceback: {traceback.format_exc()}")

        # Revert status
        try:
            supabase_client.table("tasks").update({
                "status": "pending"
            }).eq("id", task_id).execute()
        except Exception as revert_error:
            logger.error(f"❌ Failed to revert task status: {revert_error}")

        if sid:
            socketio.emit("task_execution_status", {
                "task_id": task_id,
                "status": "error",
                "message": f"Execution failed: {str(e)}"
            }, room=sid)
