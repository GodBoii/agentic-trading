# python-backend/session_service.py

import logging
import json
import requests
import datetime
from typing import Optional, Dict, Any

# Import from our centralized config and extensions modules
import config
from extensions import RedisClient

logger = logging.getLogger(__name__)

class ConnectionManager:
    """
    Manages the lifecycle of user sessions, including creation, retrieval,
    and termination. It uses Redis for session storage and handles the cleanup
    of associated resources like sandbox environments.
    
    Memory Optimizations:
    - Reduced TTL from 24h to 2h for inactive sessions
    - Automatic cleanup of old sessions
    - Sandbox ID limit enforcement
    - Memory-based session eviction
    """
    
    # Configuration constants
    SESSION_TTL = 7200  # 2 hours (reduced from 24h)
    MAX_SANDBOX_IDS = 5  # Maximum sandboxes per session
    CLEANUP_BATCH_SIZE = 100  # Sessions to check per cleanup cycle
    
    def __init__(self, redis_client: RedisClient):
        """
        Initializes the ConnectionManager with a Redis client instance.

        Args:
            redis_client (RedisClient): An initialized Redis client.
        """
        self.redis_client = redis_client
        self.http_session = requests.Session()

    def create_session(self, conversation_id: str, user_id: str, agent_config: dict, device_type: str = 'web') -> dict:
        """
        Creates a new session record in Redis with optimized TTL and cleanup.

        Args:
            conversation_id (str): The unique ID for the conversation.
            user_id (str): The ID of the user starting the session.
            agent_config (dict): The agent configuration for this session.
            device_type (str): The device type ('desktop', 'mobile', 'web').

        Returns:
            dict: The newly created session data.
        """
        # Cleanup old sessions before creating new one (memory optimization)
        self._cleanup_expired_sessions(user_id)
        
        # Ensure a default set of tools exists for a new session while preserving
        # explicit frontend selections (including disabled tools).
        agent_config = dict(agent_config or {})
        default_tool_config = {
            'enable_github': True,
            'enable_google_email': True,
            'enable_google_drive': True,
            'enable_google_sheets': True,
            'enable_browser': True,
            'enable_vercel': True,
            'enable_supabase': True,
            'enable_computer_control': True  # NEW: Enable computer control by default for desktop
        }
        for key, value in default_tool_config.items():
            agent_config.setdefault(key, value)
        
        session_data = {
            "user_id": user_id,
            "config": agent_config,
            "device_type": device_type,  # NEW: Store device type
            "created_at": datetime.datetime.now().isoformat(),
            "last_accessed": datetime.datetime.now().isoformat(),
            "sandbox_ids": [],
            "memory_usage_mb": 0  # Track memory usage
        }
        
        # Store with reduced TTL (2 hours instead of 24)
        self.redis_client.set(
            f"session:{conversation_id}", 
            json.dumps(session_data), 
            ex=self.SESSION_TTL
        )
        
        # Add to user's session index for cleanup
        self.redis_client.sadd(f"user_sessions:{user_id}", conversation_id)
        self.redis_client.expire(f"user_sessions:{user_id}", self.SESSION_TTL)
        
        return session_data

    def terminate_session(self, conversation_id: str):
        """
        Terminates a session, cleans up associated resources (like sandboxes),
        and removes the session record from Redis.

        Args:
            conversation_id (str): The ID of the session to terminate.
        """
        session_json = self.redis_client.get(f"session:{conversation_id}")
        if not session_json:
            return
            
        session_data = json.loads(session_json)
        user_id = session_data.get("user_id")
        
        # Clean up sandboxes with improved error handling
        if config.SANDBOX_API_URL:
            sandbox_ids = session_data.get("sandbox_ids", [])
            if sandbox_ids:
                for sandbox_id in sandbox_ids:
                    try:
                        self.http_session.delete(
                            f"{config.SANDBOX_API_URL}/sessions/{sandbox_id}", 
                            timeout=10
                        )
                    except requests.RequestException as e:
                        logger.error(f"Sandbox cleanup failed ({sandbox_id}): {e}")
        
        # Remove from user's session index
        if user_id:
            self.redis_client.srem(f"user_sessions:{user_id}", conversation_id)
        
        # Delete the session from Redis
        self.redis_client.delete(f"session:{conversation_id}")

    def get_session(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves a session's data from Redis and updates last accessed time.

        Args:
            conversation_id (str): The ID of the session to retrieve.

        Returns:
            dict | None: The session data as a dictionary, or None if not found.
        """
        session_json = self.redis_client.get(f"session:{conversation_id}")
        if not session_json:
            return None
            
        session_data = json.loads(session_json)
        
        # Update last accessed time and refresh TTL
        session_data["last_accessed"] = datetime.datetime.now().isoformat()
        self.redis_client.set(
            f"session:{conversation_id}", 
            json.dumps(session_data), 
            ex=self.SESSION_TTL
        )
        
        return session_data
    
    def add_sandbox_to_session(self, conversation_id: str, sandbox_id: str) -> bool:
        """
        Adds a sandbox ID to a session with limit enforcement.
        
        Args:
            conversation_id (str): The session ID
            sandbox_id (str): The sandbox ID to add
            
        Returns:
            bool: True if added, False if limit reached
        """
        session_data = self.get_session(conversation_id)
        if not session_data:
            logger.error(f"Sandbox add failed: session not found")
            return False
        
        sandbox_ids = session_data.get("sandbox_ids", [])
        
        # Enforce sandbox limit
        if len(sandbox_ids) >= self.MAX_SANDBOX_IDS:
            # Clean up oldest sandbox
            oldest_sandbox = sandbox_ids.pop(0)
            self._cleanup_sandbox(oldest_sandbox)
        
        # Add new sandbox
        sandbox_ids.append(sandbox_id)
        session_data["sandbox_ids"] = sandbox_ids
        
        # Save updated session
        self.redis_client.set(
            f"session:{conversation_id}", 
            json.dumps(session_data), 
            ex=self.SESSION_TTL
        )
        
        return True
    
    def _cleanup_sandbox(self, sandbox_id: str):
        """
        Helper method to clean up a single sandbox.
        
        Args:
            sandbox_id (str): The sandbox ID to clean up
        """
        if not config.SANDBOX_API_URL:
            return
            
        try:
            self.http_session.delete(
                f"{config.SANDBOX_API_URL}/sessions/{sandbox_id}", 
                timeout=5
            )
        except requests.RequestException as e:
            logger.error(f"Sandbox cleanup failed ({sandbox_id[:8]}): {e}")
    
    def _cleanup_expired_sessions(self, user_id: str):
        """
        Cleans up expired sessions for a user to prevent memory accumulation.
        
        Args:
            user_id (str): The user ID to clean up sessions for
        """
        try:
            # Get all session IDs for this user
            session_ids = self.redis_client.smembers(f"user_sessions:{user_id}")
            if not session_ids:
                return
            
            cleaned = 0
            for session_id in session_ids:
                # Check if session still exists in Redis
                if not self.redis_client.exists(f"session:{session_id}"):
                    # Remove from index if session expired
                    self.redis_client.srem(f"user_sessions:{user_id}", session_id)
                    cleaned += 1
            
            if cleaned > 0:
                logger.info(f"Cleaned {cleaned} expired sessions")
                
        except Exception as e:
            logger.error(f"Session cleanup error: {e}")
    
    def get_active_session_count(self, user_id: str) -> int:
        """
        Gets the count of active sessions for a user.
        
        Args:
            user_id (str): The user ID
            
        Returns:
            int: Number of active sessions
        """
        try:
            session_ids = self.redis_client.smembers(f"user_sessions:{user_id}")
            # Filter to only existing sessions
            active = sum(1 for sid in session_ids if self.redis_client.exists(f"session:{sid}"))
            return active
        except Exception as e:
            logger.error(f"Session count error: {e}")
            return 0
    
    def cleanup_all_expired_sessions(self):
        """
        Global cleanup of all expired sessions (can be called periodically).
        This is a maintenance operation to prevent Redis memory bloat.
        """
        try:
            # Get all user session indexes
            user_keys = self.redis_client.keys("user_sessions:*")
            total_cleaned = 0
            
            for user_key in user_keys[:self.CLEANUP_BATCH_SIZE]:  # Limit batch size
                user_id = user_key.decode('utf-8').split(':')[1]
                session_ids = self.redis_client.smembers(user_key)
                
                for session_id in session_ids:
                    if not self.redis_client.exists(f"session:{session_id}"):
                        self.redis_client.srem(user_key, session_id)
                        total_cleaned += 1
            
            if total_cleaned > 0:
                logger.info(f"Global cleanup: {total_cleaned} expired sessions")
                
        except Exception as e:
            logger.error(f"Global cleanup error: {e}")
