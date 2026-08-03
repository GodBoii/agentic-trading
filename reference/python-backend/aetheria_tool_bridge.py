# python-backend/aetheria_tool_bridge.py
"""
Aetheria Tool Bridge for Task Agent
Single tool that allows Task Agent to delegate any complex query to Aetheria AI
"""

import os
import logging
import uuid
import traceback
from typing import Optional, Dict, Any
from agno.tools import Toolkit

logger = logging.getLogger(__name__)


class AetheriaToolBridge(Toolkit):
    """
    Single bridge tool that allows Task Agent to ask Aetheria AI anything.
    Aetheria decides what tools to use (internet, email, drive, research, etc.)
    """
    
    def __init__(
        self,
        user_id: str,
        task_context: Optional[Dict[str, Any]] = None,
        debug_mode: bool = False
    ):
        super().__init__(name="aetheria_bridge")
        self.user_id = user_id
        self.task_context = task_context or {}
        self.debug_mode = debug_mode
        
        # Register only ONE tool
        self.register(self.ask_aetheria)
    
    def _get_aetheria_team(self):
        """
        Lazily create an Aetheria team instance for background execution.
        """
        from assistant import get_llm_os
        
        # Create Aetheria with all tools enabled for maximum capability
        team = get_llm_os(
            user_id=self.user_id,
            session_info=None,
            internet_search=True,
            coding_assistant=False,
            Planner_Agent=False,  # Skip planner for direct execution
            enable_supabase=False,
            use_memory=False,
            debug_mode=self.debug_mode,
            enable_github=False,
            enable_vercel=False,
            enable_google_email=True,
            enable_google_drive=True,
            enable_browser=False,
            browser_tools_config=None,
            custom_tool_config=None,
        )
        
        return team
    
    def ask_aetheria(self, query: str, context: Optional[str] = None) -> str:
        """
        Ask Aetheria AI to help with any complex query.
        
        Aetheria has access to:
        - Internet search (DuckDuckGo)
        - Email operations (read, search, send)
        - Google Drive (search, read, create files)
        
        Use this when you need information or capabilities beyond task management.
        
        Args:
            query: What you need Aetheria to do or find out
            context: Optional context about why you need this (e.g., task details)
        
        Returns:
            Aetheria's response with the requested information or action result
        
        Examples:
            ask_aetheria("Search for latest AI news and summarize the top 3 stories")
            ask_aetheria("Find my recent emails about project deadlines")
            ask_aetheria("Research best practices for Python async programming")
        """
        try:
            team = self._get_aetheria_team()
            
            # Build query with context
            full_query = query
            if context:
                full_query = f"Context: {context}\n\nRequest: {query}"
            
            if self.task_context:
                task_info = f"Task Context: {self.task_context}"
                full_query = f"{task_info}\n\n{full_query}"
            
            # Unique session for background query
            background_session_id = f"task-bg-{uuid.uuid4()}"
            
            logger.info(f"[AetheriaBridge] Asking Aetheria: {query[:100]}...")
            
            # Run without streaming
            run_response = team.run(
                input=full_query,
                session_id=background_session_id,
                stream=False,
                stream_intermediate_steps=False,
            )
            
            if run_response and hasattr(run_response, 'content'):
                logger.info(f"[AetheriaBridge] Response: {len(run_response.content)} chars")
                return run_response.content
            else:
                return "Unable to get response from Aetheria."
                
        except Exception as e:
            logger.error(f"[AetheriaBridge] Error: {e}")
            logger.error(traceback.format_exc())
            return f"Error asking Aetheria: {str(e)}"
