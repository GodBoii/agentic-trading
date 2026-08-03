# python-backend/sandbox_persistence.py

import logging
import json
from typing import Optional, Dict, Any, List
from datetime import datetime
from r2_client import get_r2_client
from supabase_client import supabase_client

logger = logging.getLogger(__name__)

class SandboxPersistenceService:
    """
    Service for persisting sandbox execution data to Postgres + R2.
    
    Architecture:
    - Postgres: Stores metadata (command, status, timestamps, R2 keys)
    - R2: Stores actual log content (stdout, stderr)
    """
    
    def __init__(self):
        """Initialize the persistence service."""
        self.r2_client = get_r2_client()
        self.db = supabase_client
        logger.info("SandboxPersistenceService initialized")
    
    def create_execution_record(
        self,
        user_id: str,
        session_id: str,
        sandbox_id: str,
        command: str,
        message_id: Optional[str] = None
    ) -> Optional[str]:
        """
        Create a new execution record in Postgres with status=RUNNING.
        
        Args:
            user_id: User ID from Supabase auth
            session_id: Conversation/session ID
            sandbox_id: Sandbox container ID
            command: The command being executed
            message_id: Frontend message ID for linking
            
        Returns:
            execution_id (str) if successful, None if failed
        """
        try:
            # Insert into Postgres
            result = self.db.table('sandbox_executions').insert({
                'user_id': user_id,
                'session_id': session_id,
                'sandbox_id': sandbox_id,
                'command': command,
                'message_id': message_id,
                'status': 'RUNNING',
                'started_at': datetime.utcnow().isoformat()
            }).execute()
            
            if result.data and len(result.data) > 0:
                execution_id = result.data[0]['execution_id']
                logger.info(f"Created execution record: {execution_id}")
                return str(execution_id)
            else:
                logger.error("Failed to create execution record: No data returned")
                return None
                
        except Exception as e:
            logger.error(f"Failed to create execution record: {e}", exc_info=True)
            return None
    
    def persist_execution_output(
        self,
        execution_id: str,
        stdout: str,
        stderr: str,
        exit_code: int
    ) -> bool:
        """
        Upload logs to R2 and update Postgres with keys and status.
        
        This is called AFTER command execution completes.
        
        Args:
            execution_id: The execution ID from create_execution_record
            stdout: Standard output text
            stderr: Standard error text
            exit_code: Command exit code (0 = success)
            
        Returns:
            True if successful, False if failed
        """
        try:
            # Get execution record to build R2 keys
            exec_record = self.db.table('sandbox_executions').select(
                'user_id, session_id, sandbox_id, command, message_id'
            ).eq('execution_id', execution_id).single().execute()
            
            if not exec_record.data:
                logger.error(f"Execution record not found: {execution_id}")
                return False
            
            user_id = exec_record.data['user_id']
            session_id = exec_record.data['session_id']
            sandbox_id = exec_record.data['sandbox_id']
            
            # Generate R2 keys
            keys = self.r2_client.generate_execution_keys(
                user_id, session_id, sandbox_id, execution_id
            )
            
            # Upload stdout to R2
            stdout_result = {'success': True, 'size': 0, 'checksum': ''}
            if stdout:
                stdout_result = self.r2_client.upload_text(
                    keys['stdout_key'],
                    stdout,
                    metadata={'execution_id': execution_id, 'type': 'stdout'}
                )
            
            # Upload stderr to R2
            stderr_result = {'success': True, 'size': 0, 'checksum': ''}
            if stderr:
                stderr_result = self.r2_client.upload_text(
                    keys['stderr_key'],
                    stderr,
                    metadata={'execution_id': execution_id, 'type': 'stderr'}
                )
            
            # Determine final status
            if stdout_result['success'] and stderr_result['success']:
                status = 'COMPLETED'
            else:
                status = 'PARTIAL'
                logger.warning(f"Partial upload for execution {execution_id}")
            
            # Update Postgres with R2 keys and final status
            update_data = {
                'status': status,
                'exit_code': exit_code,
                'finished_at': datetime.utcnow().isoformat(),
                'stdout_key': keys['stdout_key'] if stdout else None,
                'stderr_key': keys['stderr_key'] if stderr else None,
                'stdout_size': stdout_result.get('size', 0),
                'stderr_size': stderr_result.get('size', 0),
                'stdout_checksum': stdout_result.get('checksum'),
                'stderr_checksum': stderr_result.get('checksum')
            }
            
            self.db.table('sandbox_executions').update(update_data).eq(
                'execution_id', execution_id
            ).execute()
            
            logger.info(
                f"Persisted execution {execution_id}: "
                f"status={status}, exit_code={exit_code}, "
                f"stdout={stdout_result.get('size', 0)}B, "
                f"stderr={stderr_result.get('size', 0)}B"
            )
            
            # Register in session_content for conversation history
            # Get message_id from execution record
            message_id = exec_record.data.get('message_id')
            
            self.register_content(
                session_id=session_id,
                user_id=user_id,
                content_type='execution',
                reference_id=execution_id,
                message_id=message_id,
                metadata={
                    'command': exec_record.data.get('command', ''),
                    'exit_code': exit_code,
                    'status': status,
                    'stdout_size': stdout_result.get('size', 0),
                    'stderr_size': stderr_result.get('size', 0)
                }
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to persist execution output: {e}", exc_info=True)
            
            # Mark as PARTIAL in Postgres
            try:
                self.db.table('sandbox_executions').update({
                    'status': 'PARTIAL',
                    'finished_at': datetime.utcnow().isoformat(),
                    'metadata': {'error': str(e)}
                }).eq('execution_id', execution_id).execute()
            except:
                pass
            
            return False
    
    def get_execution_metadata(
        self,
        execution_id: str,
        user_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get execution metadata from Postgres.
        
        Args:
            execution_id: The execution ID
            user_id: User ID for security check
            
        Returns:
            Dict with execution metadata, or None if not found
        """
        try:
            result = self.db.table('sandbox_executions').select('*').eq(
                'execution_id', execution_id
            ).eq('user_id', user_id).single().execute()
            
            if result.data:
                return result.data
            else:
                return None
                
        except Exception as e:
            logger.error(f"Failed to get execution metadata: {e}")
            return None
    
    def get_execution_logs_urls(
        self,
        execution_id: str,
        user_id: str,
        expiry: int = 3600
    ) -> Optional[Dict[str, str]]:
        """
        Generate presigned URLs for downloading logs from R2.
        
        Args:
            execution_id: The execution ID
            user_id: User ID for security check
            expiry: URL validity in seconds (default 1 hour)
            
        Returns:
            Dict with stdout_url and stderr_url, or None if failed
        """
        try:
            # Get execution record
            metadata = self.get_execution_metadata(execution_id, user_id)
            if not metadata:
                logger.error(f"Execution not found or access denied: {execution_id}")
                return None
            
            urls = {}
            
            # Generate presigned URL for stdout
            if metadata.get('stdout_key'):
                urls['stdout_url'] = self.r2_client.generate_presigned_get_url(
                    metadata['stdout_key'],
                    expiry=expiry
                )
            
            # Generate presigned URL for stderr
            if metadata.get('stderr_key'):
                urls['stderr_url'] = self.r2_client.generate_presigned_get_url(
                    metadata['stderr_key'],
                    expiry=expiry
                )
            
            return urls
            
        except Exception as e:
            logger.error(f"Failed to generate presigned URLs: {e}")
            return None
    
    def list_session_executions(
        self,
        session_id: str,
        user_id: str,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        List all executions for a session.
        
        Args:
            session_id: The session ID
            user_id: User ID for security check
            limit: Maximum number of results
            
        Returns:
            List of execution metadata dicts
        """
        try:
            result = self.db.table('sandbox_executions').select(
                'execution_id, command, exit_code, status, '
                'started_at, finished_at, stdout_size, stderr_size, message_id'
            ).eq('session_id', session_id).eq('user_id', user_id).order(
                'created_at', desc=True
            ).limit(limit).execute()
            
            return result.data if result.data else []
            
        except Exception as e:
            logger.error(f"Failed to list session executions: {e}")
            return []
    
    def delete_execution(
        self,
        execution_id: str,
        user_id: str
    ) -> bool:
        """
        Delete an execution and its logs from both Postgres and R2.
        
        Args:
            execution_id: The execution ID
            user_id: User ID for security check
            
        Returns:
            True if successful, False if failed
        """
        try:
            # Get execution metadata
            metadata = self.get_execution_metadata(execution_id, user_id)
            if not metadata:
                logger.error(f"Execution not found: {execution_id}")
                return False
            
            # Delete from R2
            if metadata.get('stdout_key'):
                self.r2_client.delete_object(metadata['stdout_key'])
            
            if metadata.get('stderr_key'):
                self.r2_client.delete_object(metadata['stderr_key'])
            
            # Delete from Postgres
            self.db.table('sandbox_executions').delete().eq(
                'execution_id', execution_id
            ).eq('user_id', user_id).execute()
            
            logger.info(f"Deleted execution: {execution_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete execution: {e}")
            return False
    
    def cleanup_old_executions(
        self,
        user_id: str,
        days: int = 30
    ) -> int:
        """
        Delete executions older than specified days.
        
        This is a maintenance operation for lifecycle management.
        
        Args:
            user_id: User ID
            days: Delete executions older than this many days
            
        Returns:
            Number of executions deleted
        """
        try:
            from datetime import timedelta
            
            cutoff_date = (datetime.utcnow() - timedelta(days=days)).isoformat()
            
            # Get old executions
            result = self.db.table('sandbox_executions').select(
                'execution_id, stdout_key, stderr_key'
            ).eq('user_id', user_id).lt('created_at', cutoff_date).execute()
            
            if not result.data:
                return 0
            
            deleted_count = 0
            for execution in result.data:
                # Delete from R2
                if execution.get('stdout_key'):
                    self.r2_client.delete_object(execution['stdout_key'])
                if execution.get('stderr_key'):
                    self.r2_client.delete_object(execution['stderr_key'])
                
                # Delete from Postgres
                self.db.table('sandbox_executions').delete().eq(
                    'execution_id', execution['execution_id']
                ).execute()
                
                deleted_count += 1
            
            logger.info(f"Cleaned up {deleted_count} old executions for user {user_id}")
            return deleted_count
            
        except Exception as e:
            logger.error(f"Failed to cleanup old executions: {e}")
            return 0
    
    def create_artifact(
        self,
        execution_id: str,
        user_id: str,
        session_id: str,
        sandbox_id: str,
        file_path: str,
        file_content: bytes,
        mime_type: str = 'application/octet-stream',
        message_id: Optional[str] = None
    ) -> Optional[str]:
        """
        Create a file artifact by uploading to R2 and storing metadata in Postgres.
        
        Args:
            execution_id: The execution that created this file
            user_id: User ID
            session_id: Session ID
            sandbox_id: Sandbox ID
            file_path: Path of file in sandbox (e.g., /home/sandboxuser/script.py)
            file_content: Binary file content
            mime_type: MIME type of the file
            
        Returns:
            artifact_id (str) if successful, None if failed
        """
        try:
            import uuid
            import mimetypes
            import os
            
            # Generate artifact ID
            artifact_id = str(uuid.uuid4())
            
            # Extract filename from path
            filename = os.path.basename(file_path)
            
            # Detect MIME type if not provided
            if mime_type == 'application/octet-stream':
                guessed_type, _ = mimetypes.guess_type(filename)
                if guessed_type:
                    mime_type = guessed_type
            
            # Generate R2 key
            r2_key = self.r2_client.generate_artifact_key(
                user_id, session_id, sandbox_id, artifact_id, filename
            )
            
            # Upload to R2
            upload_result = self.r2_client.upload_file(
                r2_key,
                file_content,
                content_type=mime_type,
                metadata={
                    'artifact_id': artifact_id,
                    'execution_id': execution_id,
                    'original_path': file_path
                }
            )
            
            if not upload_result['success']:
                logger.error(f"Failed to upload artifact to R2: {upload_result.get('error')}")
                return None
            
            # Insert into Postgres
            result = self.db.table('sandbox_artifacts').insert({
                'artifact_id': artifact_id,
                'execution_id': execution_id,
                'user_id': user_id,
                'artifact_type': 'file',
                'file_path': file_path,
                'r2_key': r2_key,
                'size_bytes': upload_result['size'],
                'mime_type': mime_type,
                'checksum': upload_result['checksum'],
                'metadata': {
                    'filename': filename,
                    'sandbox_id': sandbox_id,
                    'session_id': session_id
                }
            }).execute()
            
            if result.data and len(result.data) > 0:
                logger.info(
                    f"Created artifact {artifact_id}: {filename} "
                    f"({upload_result['size']} bytes)"
                )
                
                # Register in session_content for conversation history
                self.register_content(
                    session_id=session_id,
                    user_id=user_id,
                    content_type='artifact',
                    reference_id=artifact_id,
                    message_id=message_id,
                    metadata={
                        'filename': filename,
                        'size': upload_result['size'],
                        'mime_type': mime_type,
                        'file_path': file_path
                    }
                )
                
                return artifact_id
            else:
                logger.error("Failed to create artifact record in Postgres")
                return None
                
        except Exception as e:
            logger.error(f"Failed to create artifact: {e}", exc_info=True)
            return None
    
    def list_execution_artifacts(
        self,
        execution_id: str,
        user_id: str
    ) -> List[Dict[str, Any]]:
        """
        List all artifacts created by a specific execution.
        
        Args:
            execution_id: The execution ID
            user_id: User ID for security check
            
        Returns:
            List of artifact metadata dicts
        """
        try:
            result = self.db.table('sandbox_artifacts').select(
                'artifact_id, artifact_type, file_path, size_bytes, '
                'mime_type, created_at, metadata'
            ).eq('execution_id', execution_id).eq('user_id', user_id).order(
                'created_at', desc=False
            ).execute()
            
            return result.data if result.data else []
            
        except Exception as e:
            logger.error(f"Failed to list execution artifacts: {e}")
            return []
    
    def list_session_artifacts(
        self,
        session_id: str,
        user_id: str,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        List all artifacts for a session.
        
        Args:
            session_id: The session ID
            user_id: User ID for security check
            limit: Maximum number of results
            
        Returns:
            List of artifact metadata dicts
        """
        try:
            # Query artifacts where metadata->session_id matches
            result = self.db.table('sandbox_artifacts').select(
                'artifact_id, execution_id, artifact_type, file_path, '
                'size_bytes, mime_type, created_at, metadata'
            ).eq('user_id', user_id).order(
                'created_at', desc=True
            ).limit(limit).execute()
            
            # Filter by session_id in metadata
            artifacts = []
            for artifact in (result.data or []):
                if artifact.get('metadata', {}).get('session_id') == session_id:
                    artifacts.append(artifact)
            
            return artifacts
            
        except Exception as e:
            logger.error(f"Failed to list session artifacts: {e}")
            return []
    
    def get_artifact_download_url(
        self,
        artifact_id: str,
        user_id: str,
        expiry: int = 3600
    ) -> Optional[str]:
        """
        Generate presigned URL for downloading an artifact.
        
        Args:
            artifact_id: The artifact ID
            user_id: User ID for security check
            expiry: URL validity in seconds (default 1 hour)
            
        Returns:
            Presigned URL string, or None if failed
        """
        try:
            # Get artifact record
            result = self.db.table('sandbox_artifacts').select(
                'r2_key'
            ).eq('artifact_id', artifact_id).eq('user_id', user_id).single().execute()
            
            if not result.data:
                logger.error(f"Artifact not found or access denied: {artifact_id}")
                return None
            
            r2_key = result.data['r2_key']
            
            # Generate presigned URL
            url = self.r2_client.generate_presigned_get_url(r2_key, expiry=expiry)
            
            return url
            
        except Exception as e:
            logger.error(f"Failed to generate artifact download URL: {e}")
            return None
    
    def delete_artifact(
        self,
        artifact_id: str,
        user_id: str
    ) -> bool:
        """
        Delete an artifact from both Postgres and R2.
        
        Args:
            artifact_id: The artifact ID
            user_id: User ID for security check
            
        Returns:
            True if successful, False if failed
        """
        try:
            # Get artifact metadata
            result = self.db.table('sandbox_artifacts').select(
                'r2_key'
            ).eq('artifact_id', artifact_id).eq('user_id', user_id).single().execute()
            
            if not result.data:
                logger.error(f"Artifact not found: {artifact_id}")
                return False
            
            # Delete from R2
            self.r2_client.delete_object(result.data['r2_key'])
            
            # Delete from Postgres
            self.db.table('sandbox_artifacts').delete().eq(
                'artifact_id', artifact_id
            ).eq('user_id', user_id).execute()
            
            logger.info(f"Deleted artifact: {artifact_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete artifact: {e}")
            return False
    
    # ========================================================================
    # SESSION CONTENT REGISTRY METHODS
    # ========================================================================
    
    def register_content(
        self,
        session_id: str,
        user_id: str,
        content_type: str,
        reference_id: str,
        message_id: Optional[str],
        metadata: Dict[str, Any]
    ) -> bool:
        """
        Register content in session_content table for conversation history.
        
        This creates a registry entry that links artifacts/executions to sessions,
        enabling content persistence when users reopen old conversations.
        
        Args:
            session_id: The conversation session ID
            user_id: User ID
            content_type: 'artifact', 'execution', or 'upload'
            reference_id: artifact_id or execution_id
            message_id: Frontend message ID for linking
            metadata: Flexible metadata (filename, command, size, etc.)
            
        Returns:
            True if successful, False if failed
        """
        try:
            # Insert into session_content table
            result = self.db.table('session_content').insert({
                'session_id': session_id,
                'user_id': user_id,
                'content_type': content_type,
                'reference_id': reference_id,
                'message_id': message_id,
                'metadata': metadata
            }).execute()
            
            if result.data and len(result.data) > 0:
                logger.info(
                    f"Registered {content_type} content: {reference_id} "
                    f"for session {session_id}"
                )
                return True
            else:
                logger.error("Failed to register content: No data returned")
                return False
                
        except Exception as e:
            # Log but don't fail - content registration is non-critical
            logger.warning(f"Failed to register content: {e}")
            return False
    
    def get_session_content(
        self,
        session_id: str,
        user_id: str
    ) -> List[Dict[str, Any]]:
        """
        Get all content (artifacts, executions, uploads) for a session.
        
        This is used when reopening old conversations to show all
        files, terminal outputs, and uploads from that session.
        
        Args:
            session_id: The conversation session ID
            user_id: User ID for security check
            
        Returns:
            List of content records with metadata
        """
        try:
            result = self.db.table('session_content').select(
                'id, content_type, reference_id, message_id, metadata, created_at'
            ).eq('session_id', session_id).eq('user_id', user_id).order(
                'created_at', desc=False
            ).execute()
            
            return result.data if result.data else []
            
        except Exception as e:
            logger.error(f"Failed to get session content: {e}")
            return []


# Singleton instance
_persistence_service = None

def get_persistence_service():
    """Get or create the persistence service singleton."""
    global _persistence_service
    if _persistence_service is None:
        _persistence_service = SandboxPersistenceService()
    return _persistence_service
