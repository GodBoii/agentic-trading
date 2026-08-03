# python-backend/task_tools.py
"""
Task Management Tools for Aetheria AI
Provides CRUD operations for user tasks stored in Supabase
"""

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime
from agno.tools import Toolkit
from supabase_client import supabase_client

logger = logging.getLogger(__name__)


class TaskTools(Toolkit):
    """Tools for managing user tasks in the database"""
    
    def __init__(self, user_id: str):
        super().__init__(name="task_tools")
        self.user_id = user_id
        self.register(self.create_task)
        self.register(self.list_tasks)
        self.register(self.get_task)
        self.register(self.update_task)
        self.register(self.delete_task)
        self.register(self.mark_task_complete)
        self.register(self.search_tasks)
        self.register(self.save_task_work)
    
    def create_task(
        self,
        text: str,
        description: Optional[str] = None,
        priority: str = "medium",
        deadline: Optional[str] = None,
        tags: Optional[List[str]] = None,
        session_id: Optional[str] = None
    ) -> str:
        """
        Create a new task for the user.
        
        Args:
            text: Task title/summary (required)
            description: Detailed task description
            priority: Task priority - 'low', 'medium', or 'high' (default: 'medium')
            deadline: Task deadline in ISO format (e.g., '2025-12-31T23:59:59')
            tags: List of tags for categorization
            session_id: Optional session ID if task created during conversation
        
        Returns:
            Success message with task ID
        """
        try:
            task_data = {
                "user_id": self.user_id,
                "text": text,
                "description": description,
                "priority": priority,
                "status": "pending",
                "deadline": deadline,
                "tags": tags or [],
                "session_id": session_id,
                "metadata": {}
            }
            
            response = supabase_client.table("tasks").insert(task_data).execute()
            
            if response.data:
                task_id = response.data[0]["id"]
                logger.info(f"Task created: {task_id} for user {self.user_id}")
                return f"✅ Task created successfully! Task ID: {task_id}"
            else:
                return "❌ Failed to create task"
                
        except Exception as e:
            logger.error(f"Error creating task: {e}")
            return f"❌ Error creating task: {str(e)}"
    
    def list_tasks(
        self,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        limit: int = 50
    ) -> str:
        """
        List user's tasks with optional filtering.
        
        Args:
            status: Filter by status - 'pending', 'in_progress', 'completed', 'cancelled'
            priority: Filter by priority - 'low', 'medium', 'high'
            limit: Maximum number of tasks to return (default: 50)
        
        Returns:
            Formatted list of tasks
        """
        try:
            query = supabase_client.table("tasks").select("*").eq("user_id", self.user_id)
            
            if status:
                query = query.eq("status", status)
            if priority:
                query = query.eq("priority", priority)
            
            query = query.order("created_at", desc=True).limit(limit)
            response = query.execute()
            
            if not response.data:
                return "📋 No tasks found"
            
            tasks = response.data
            result = f"📋 Found {len(tasks)} task(s):\n\n"
            
            for task in tasks:
                status_emoji = {
                    "pending": "⏳",
                    "in_progress": "🔄",
                    "completed": "✅",
                    "cancelled": "❌"
                }.get(task["status"], "📌")
                
                priority_emoji = {
                    "low": "🟢",
                    "medium": "🟡",
                    "high": "🔴"
                }.get(task["priority"], "⚪")
                
                result += f"{status_emoji} {priority_emoji} **{task['text']}**\n"
                result += f"   ID: {task['id']}\n"
                result += f"   Status: {task['status']} | Priority: {task['priority']}\n"
                
                if task.get("description"):
                    result += f"   Description: {task['description']}\n"
                if task.get("deadline"):
                    result += f"   Deadline: {task['deadline']}\n"
                if task.get("tags"):
                    result += f"   Tags: {', '.join(task['tags'])}\n"
                
                result += "\n"
            
            return result
            
        except Exception as e:
            logger.error(f"Error listing tasks: {e}")
            return f"❌ Error listing tasks: {str(e)}"
    
    def get_task(self, task_id: str) -> str:
        """
        Get detailed information about a specific task.
        
        Args:
            task_id: UUID of the task
        
        Returns:
            Detailed task information
        """
        try:
            response = supabase_client.table("tasks").select("*").eq("id", task_id).eq("user_id", self.user_id).execute()
            
            if not response.data:
                return f"❌ Task not found: {task_id}"
            
            task = response.data[0]
            result = f"📌 **Task Details**\n\n"
            result += f"**Title:** {task['text']}\n"
            result += f"**ID:** {task['id']}\n"
            result += f"**Status:** {task['status']}\n"
            result += f"**Priority:** {task['priority']}\n"
            
            if task.get("description"):
                result += f"**Description:** {task['description']}\n"
            if task.get("deadline"):
                result += f"**Deadline:** {task['deadline']}\n"
            if task.get("tags"):
                result += f"**Tags:** {', '.join(task['tags'])}\n"
            if task.get("session_id"):
                result += f"**Created in session:** {task['session_id']}\n"
            
            result += f"**Created:** {task['created_at']}\n"
            result += f"**Updated:** {task['updated_at']}\n"
            
            if task.get("completed_at"):
                result += f"**Completed:** {task['completed_at']}\n"
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting task: {e}")
            return f"❌ Error getting task: {str(e)}"
    
    def update_task(
        self,
        task_id: str,
        text: Optional[str] = None,
        description: Optional[str] = None,
        priority: Optional[str] = None,
        status: Optional[str] = None,
        deadline: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> str:
        """
        Update an existing task.
        
        Args:
            task_id: UUID of the task to update
            text: New task title
            description: New description
            priority: New priority ('low', 'medium', 'high')
            status: New status ('pending', 'in_progress', 'completed', 'cancelled')
            deadline: New deadline in ISO format
            tags: New list of tags
        
        Returns:
            Success or error message
        """
        try:
            update_data = {}
            
            if text is not None:
                update_data["text"] = text
            if description is not None:
                update_data["description"] = description
            if priority is not None:
                update_data["priority"] = priority
            if status is not None:
                update_data["status"] = status
            if deadline is not None:
                update_data["deadline"] = deadline
            if tags is not None:
                update_data["tags"] = tags
            
            if not update_data:
                return "❌ No fields to update"
            
            response = supabase_client.table("tasks").update(update_data).eq("id", task_id).eq("user_id", self.user_id).execute()
            
            if response.data:
                logger.info(f"Task updated: {task_id}")
                return f"✅ Task updated successfully!"
            else:
                return f"❌ Task not found or update failed"
                
        except Exception as e:
            logger.error(f"Error updating task: {e}")
            return f"❌ Error updating task: {str(e)}"
    
    def delete_task(self, task_id: str) -> str:
        """
        Delete a task permanently.
        
        Args:
            task_id: UUID of the task to delete
        
        Returns:
            Success or error message
        """
        try:
            response = supabase_client.table("tasks").delete().eq("id", task_id).eq("user_id", self.user_id).execute()
            
            if response.data:
                logger.info(f"Task deleted: {task_id}")
                return f"✅ Task deleted successfully!"
            else:
                return f"❌ Task not found"
                
        except Exception as e:
            logger.error(f"Error deleting task: {e}")
            return f"❌ Error deleting task: {str(e)}"
    
    def mark_task_complete(self, task_id: str) -> str:
        """
        Mark a task as completed.
        
        Args:
            task_id: UUID of the task to complete
        
        Returns:
            Success or error message
        """
        try:
            response = supabase_client.table("tasks").update({
                "status": "completed"
            }).eq("id", task_id).eq("user_id", self.user_id).execute()
            
            if response.data:
                logger.info(f"Task marked complete: {task_id}")
                return f"✅ Task marked as completed!"
            else:
                return f"❌ Task not found"
                
        except Exception as e:
            logger.error(f"Error marking task complete: {e}")
            return f"❌ Error marking task complete: {str(e)}"
    
    def search_tasks(self, query: str, limit: int = 20) -> str:
        """
        Search tasks by text content in title or description.
        
        Args:
            query: Search query string
            limit: Maximum number of results (default: 20)
        
        Returns:
            Formatted list of matching tasks
        """
        try:
            # Search in both text and description fields
            response = supabase_client.table("tasks").select("*").eq("user_id", self.user_id).or_(
                f"text.ilike.%{query}%,description.ilike.%{query}%"
            ).order("created_at", desc=True).limit(limit).execute()
            
            if not response.data:
                return f"🔍 No tasks found matching '{query}'"
            
            tasks = response.data
            result = f"🔍 Found {len(tasks)} task(s) matching '{query}':\n\n"
            
            for task in tasks:
                status_emoji = {
                    "pending": "⏳",
                    "in_progress": "🔄",
                    "completed": "✅",
                    "cancelled": "❌"
                }.get(task["status"], "📌")
                
                result += f"{status_emoji} **{task['text']}**\n"
                result += f"   ID: {task['id']} | Status: {task['status']}\n\n"
            
            return result
            
        except Exception as e:
            logger.error(f"Error searching tasks: {e}")
            return f"❌ Error searching tasks: {str(e)}"
    
    def save_task_work(self, task_id: str, work_output: str) -> str:
        """
        Save the completed work/deliverable for a task.
        This should be called BEFORE marking the task as complete.
        
        Args:
            task_id: UUID of the task
            work_output: The actual work completed (report content, code, document, etc.)
        
        Returns:
            Success or error message
        """
        try:
            response = supabase_client.table("tasks").update({
                "task_work": work_output
            }).eq("id", task_id).eq("user_id", self.user_id).execute()
            
            if response.data:
                logger.info(f"Task work saved for task: {task_id}")
                return f"✅ Work saved successfully for task! You can now mark it as complete."
            else:
                return f"❌ Task not found: {task_id}"
                
        except Exception as e:
            logger.error(f"Error saving task work: {e}")
            return f"❌ Error saving task work: {str(e)}"
