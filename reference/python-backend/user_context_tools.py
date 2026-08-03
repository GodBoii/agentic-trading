# python-backend/user_context_tools.py
"""
User Context Management Tools for Aetheria AI
Stores user personal information and preferences in agno_memories table
"""

import logging
import json
import uuid
import time
from typing import Optional, Dict, Any
from agno.tools import Toolkit
from supabase_client import supabase_client

logger = logging.getLogger(__name__)


class UserContextTools(Toolkit):
    """Tools for managing user context and personal information in memories"""
    
    def __init__(self, user_id: str, team_id: str = "aetheria-ai"):
        super().__init__(name="user_context_tools")
        self.user_id = user_id
        self.team_id = team_id
        self.register(self.save_user_context)
        self.register(self.get_user_context)
        self.register(self.update_user_context)
    
    def save_user_context(self, context_data: Dict[str, Any]) -> str:
        """
        Save or update user context information in agno_memories.
        
        Args:
            context_data: Dictionary containing user context with keys:
                - personal: {name, email, location, timezone, language}
                - preferences: {workingHours, communicationPreference, notificationPreference, taskPrioritization}
                - capabilities: {allowedActions, restrictedDomains, apiKeys, tools}
                - goals: {shortTerm, longTerm, constraints}
                - systemAccess: {filesystemAccess, networkAccess, apiAccess, credentials}
        
        Returns:
            Success or error message
        """
        try:
            # Create a structured memory entry for user context
            memory_content = self._format_context_as_memory(context_data)
            
            # Check if user context memory already exists
            # Note: Using contains instead of ilike since memory is JSON
            existing = supabase_client.table("agno_memories").select("*").eq(
                "user_id", self.user_id
            ).eq("team_id", self.team_id).execute()
            
            # Filter for user context entries
            user_context_entry = None
            if existing.data:
                for entry in existing.data:
                    topics = entry.get("topics", [])
                    if isinstance(topics, str):
                        topics = json.loads(topics)
                    if "user_context" in topics:
                        user_context_entry = entry
                        break
            
            current_timestamp = int(time.time())
            
            if user_context_entry:
                # Update existing memory
                memory_id = user_context_entry["memory_id"]
                
                update_data = {
                    "memory": memory_content,  # Store as plain string (Supabase will handle JSON encoding)
                    "input": "User context updated",
                    "updated_at": current_timestamp,
                    "topics": ["user_context", "personal_info", "preferences"]  # Store as JSON array
                }
                
                response = supabase_client.table("agno_memories").update(update_data).eq(
                    "memory_id", memory_id
                ).execute()
                
                logger.info(f"User context updated for user {self.user_id}: {response}")
                return "✅ User context updated successfully!"
            else:
                # Create new memory
                memory_id = str(uuid.uuid4())
                
                memory_data = {
                    "memory_id": memory_id,
                    "memory": memory_content,  # Store as plain string (Supabase will handle JSON encoding)
                    "input": "User context saved",
                    "team_id": self.team_id,
                    "user_id": self.user_id,
                    "topics": ["user_context", "personal_info", "preferences"],  # Store as JSON array
                    "updated_at": current_timestamp
                }
                
                response = supabase_client.table("agno_memories").insert(memory_data).execute()
                
                logger.info(f"User context created for user {self.user_id}: {response}")
                return "✅ User context saved successfully!"
                
        except Exception as e:
            logger.error(f"Error saving user context: {e}", exc_info=True)
            return f"❌ Error saving user context: {str(e)}"
    
    def get_user_context(self) -> str:
        """
        Retrieve user context information from agno_memories.
        
        Returns:
            Formatted user context or message if not found
        """
        try:
            response = supabase_client.table("agno_memories").select("*").eq(
                "user_id", self.user_id
            ).eq("team_id", self.team_id).execute()
            
            # Filter for user context entries
            user_context_entry = None
            if response.data:
                for entry in response.data:
                    topics = entry.get("topics", [])
                    if isinstance(topics, str):
                        topics = json.loads(topics)
                    if "user_context" in topics:
                        user_context_entry = entry
                        break
            
            if not user_context_entry:
                return "📋 No user context found. User can provide their information for personalized assistance."
            
            memory_content = user_context_entry["memory"]
            # Memory is stored as a string in the JSON field
            return f"📋 **User Context:**\n\n{memory_content}"
            
        except Exception as e:
            logger.error(f"Error retrieving user context: {e}", exc_info=True)
            return f"❌ Error retrieving user context: {str(e)}"
    
    def update_user_context(self, field: str, value: Any) -> str:
        """
        Update a specific field in user context.
        
        Args:
            field: Field path to update (e.g., 'personal.name', 'preferences.workingHours')
            value: New value for the field
        
        Returns:
            Success or error message
        """
        try:
            # Get existing context
            response = supabase_client.table("agno_memories").select("*").eq(
                "user_id", self.user_id
            ).eq("team_id", self.team_id).execute()
            
            # Filter for user context entries
            user_context_entry = None
            if response.data:
                for entry in response.data:
                    topics = entry.get("topics", [])
                    if isinstance(topics, str):
                        topics = json.loads(topics)
                    if "user_context" in topics:
                        user_context_entry = entry
                        break
            
            if not user_context_entry:
                return "❌ No user context found. Please save context first."
            
            # Parse existing memory to extract context data
            memory_content = user_context_entry["memory"]
            if isinstance(memory_content, str):
                memory_content = json.loads(memory_content)
            
            context_data = self._parse_memory_to_context(memory_content)
            
            # Update the specific field
            field_parts = field.split('.')
            current = context_data
            for part in field_parts[:-1]:
                if part not in current:
                    current[part] = {}
                current = current[part]
            current[field_parts[-1]] = value
            
            # Save updated context
            return self.save_user_context(context_data)
            
        except Exception as e:
            logger.error(f"Error updating user context field: {e}", exc_info=True)
            return f"❌ Error updating user context: {str(e)}"
    
    def _format_context_as_memory(self, context_data: Dict[str, Any]) -> str:
        """Format context data as a readable memory string"""
        memory_lines = ["User Context:"]
        
        # Personal Information
        personal = context_data.get("personal", {})
        if any(personal.values()):
            memory_lines.append("\nPersonal Information:")
            if personal.get("name"):
                memory_lines.append(f"  • Name: {personal['name']}")
            if personal.get("email"):
                memory_lines.append(f"  • Email: {personal['email']}")
            if personal.get("location"):
                memory_lines.append(f"  • Location: {personal['location']}")
            if personal.get("timezone"):
                memory_lines.append(f"  • Timezone: {personal['timezone']}")
            if personal.get("language"):
                memory_lines.append(f"  • Language: {personal['language']}")
        
        # Preferences
        preferences = context_data.get("preferences", {})
        if any(preferences.values()):
            memory_lines.append("\nPreferences:")
            if preferences.get("workingHours"):
                memory_lines.append(f"  • Working Hours: {preferences['workingHours']}")
            if preferences.get("communicationPreference"):
                memory_lines.append(f"  • Communication: {preferences['communicationPreference']}")
            if preferences.get("notificationPreference"):
                memory_lines.append(f"  • Notifications: {preferences['notificationPreference']}")
            if preferences.get("taskPrioritization"):
                memory_lines.append(f"  • Task Prioritization: {preferences['taskPrioritization']}")
        
        # Goals
        goals = context_data.get("goals", {})
        if any(goals.values()):
            memory_lines.append("\nGoals:")
            if goals.get("shortTerm"):
                memory_lines.append(f"  • Short-term: {', '.join(goals['shortTerm'])}")
            if goals.get("longTerm"):
                memory_lines.append(f"  • Long-term: {', '.join(goals['longTerm'])}")
            if goals.get("constraints"):
                memory_lines.append(f"  • Constraints: {', '.join(goals['constraints'])}")
        
        # Capabilities
        capabilities = context_data.get("capabilities", {})
        if any(capabilities.values()):
            memory_lines.append("\nCapabilities:")
            if capabilities.get("allowedActions"):
                memory_lines.append(f"  • Allowed Actions: {', '.join(capabilities['allowedActions'])}")
            if capabilities.get("tools"):
                memory_lines.append(f"  • Tools: {', '.join(capabilities['tools'])}")
        
        return "\n".join(memory_lines)
    
    def _parse_memory_to_context(self, memory_content: str) -> Dict[str, Any]:
        """Parse memory string back to context dictionary (simplified)"""
        # This is a simplified parser - in production, you might want to store JSON in metadata
        context = {
            "personal": {},
            "preferences": {},
            "capabilities": {},
            "goals": {},
            "systemAccess": {}
        }
        
        # For now, return empty structure - the actual parsing would be more complex
        # In practice, you might want to store the full JSON in a metadata field
        return context
