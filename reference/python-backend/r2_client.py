# python-backend/r2_client.py

import os
import boto3
import hashlib
import logging
from botocore.exceptions import ClientError
from botocore.config import Config

logger = logging.getLogger(__name__)

class R2Client:
    """
    Client for interacting with Cloudflare R2 storage.
    Uses S3-compatible API via boto3.
    """
    
    def __init__(self):
        """Initialize R2 client with credentials from environment."""
        self.endpoint = os.getenv('R2_ENDPOINT')
        self.bucket = os.getenv('R2_BUCKET')
        self.access_key = os.getenv('R2_ACCESS_KEY_ID')
        self.secret_key = os.getenv('R2_SECRET_ACCESS_KEY')
        self.region = os.getenv('R2_REGION', 'auto')
        
        # Validate configuration
        if not all([self.endpoint, self.bucket, self.access_key, self.secret_key]):
            raise ValueError(
                "R2 configuration incomplete. Required: R2_ENDPOINT, R2_BUCKET, "
                "R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY"
            )
        
        # Initialize boto3 S3 client configured for R2
        self.client = boto3.client(
            's3',
            endpoint_url=self.endpoint,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            region_name=self.region,
            config=Config(
                signature_version='s3v4',
                retries={'max_attempts': 3, 'mode': 'adaptive'}
            )
        )
        
        logger.info(f"R2 client initialized for bucket: {self.bucket}")
    
    def generate_execution_keys(self, user_id, session_id, sandbox_id, execution_id):
        """
        Generate R2 object keys for an execution's logs.
        
        Returns:
            dict: Keys for stdout, stderr, and metadata
        """
        base_path = f"users/{user_id}/sessions/{session_id}/sandboxes/{sandbox_id}/executions/{execution_id}"
        return {
            'stdout_key': f"{base_path}/logs/stdout.txt",
            'stderr_key': f"{base_path}/logs/stderr.txt",
            'meta_key': f"{base_path}/meta/exec.json"
        }
    
    def generate_artifact_key(self, user_id, session_id, sandbox_id, artifact_id, filename):
        """
        Generate R2 object key for a file artifact.
        
        Args:
            user_id: User ID
            session_id: Session ID
            sandbox_id: Sandbox ID
            artifact_id: Artifact UUID
            filename: Original filename
            
        Returns:
            str: R2 object key
        """
        base_path = f"users/{user_id}/sessions/{session_id}/sandboxes/{sandbox_id}/artifacts"
        return f"{base_path}/{artifact_id}/{filename}"
    
    def upload_file(self, key, content_bytes, content_type='application/octet-stream', metadata=None):
        """
        Upload binary file content to R2 with checksum verification.
        
        Args:
            key (str): R2 object key (path)
            content_bytes (bytes): Binary content to upload
            content_type (str): MIME type
            metadata (dict): Optional metadata to attach
            
        Returns:
            dict: Upload result with size and checksum
        """
        try:
            # Calculate SHA256 checksum
            checksum = hashlib.sha256(content_bytes).hexdigest()
            
            # Prepare metadata
            upload_metadata = metadata or {}
            upload_metadata['checksum-sha256'] = checksum
            
            # Upload to R2
            self.client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=content_bytes,
                ContentType=content_type,
                Metadata=upload_metadata
            )
            
            logger.info(f"Uploaded {len(content_bytes)} bytes to {key}")
            
            return {
                'success': True,
                'size': len(content_bytes),
                'checksum': checksum,
                'key': key
            }
            
        except ClientError as e:
            logger.error(f"Failed to upload file to R2: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def upload_text(self, key, content, metadata=None):
        """
        Upload text content to R2 with checksum verification.
        
        Args:
            key (str): R2 object key (path)
            content (str): Text content to upload
            metadata (dict): Optional metadata to attach
            
        Returns:
            dict: Upload result with size and checksum
        """
        try:
            # Convert to bytes
            content_bytes = content.encode('utf-8')
            
            # Calculate SHA256 checksum
            checksum = hashlib.sha256(content_bytes).hexdigest()
            
            # Prepare metadata
            upload_metadata = metadata or {}
            upload_metadata['checksum-sha256'] = checksum
            
            # Upload to R2
            self.client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=content_bytes,
                ContentType='text/plain',
                Metadata=upload_metadata
            )
            
            logger.info(f"Uploaded {len(content_bytes)} bytes to {key}")
            
            return {
                'success': True,
                'size': len(content_bytes),
                'checksum': checksum,
                'key': key
            }
            
        except ClientError as e:
            logger.error(f"Failed to upload to R2: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def generate_presigned_get_url(self, key, expiry=3600):
        """
        Generate a presigned URL for downloading an object.
        
        Args:
            key (str): R2 object key
            expiry (int): URL validity in seconds (default 1 hour)
            
        Returns:
            str: Presigned URL
        """
        try:
            url = self.client.generate_presigned_url(
                'get_object',
                Params={'Bucket': self.bucket, 'Key': key},
                ExpiresIn=expiry
            )
            return url
        except ClientError as e:
            logger.error(f"Failed to generate presigned URL: {e}")
            return None
    
    def delete_object(self, key):
        """Delete a single object from R2."""
        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)
            logger.info(f"Deleted object: {key}")
            return True
        except ClientError as e:
            logger.error(f"Failed to delete object: {e}")
            return False
    
    def delete_prefix(self, prefix):
        """
        Delete all objects under a prefix (like a folder).
        Useful for cleanup operations.
        """
        try:
            # List all objects with the prefix
            paginator = self.client.get_paginator('list_objects_v2')
            pages = paginator.paginate(Bucket=self.bucket, Prefix=prefix)
            
            delete_count = 0
            for page in pages:
                if 'Contents' not in page:
                    continue
                    
                # Delete in batches of 1000 (S3 API limit)
                objects = [{'Key': obj['Key']} for obj in page['Contents']]
                if objects:
                    self.client.delete_objects(
                        Bucket=self.bucket,
                        Delete={'Objects': objects}
                    )
                    delete_count += len(objects)
            
            logger.info(f"Deleted {delete_count} objects under prefix: {prefix}")
            return True
            
        except ClientError as e:
            logger.error(f"Failed to delete prefix: {e}")
            return False
    
    def test_connection(self):
        """Test R2 connection by listing buckets."""
        try:
            response = self.client.head_bucket(Bucket=self.bucket)
            logger.info(f"R2 connection test successful: {self.bucket}")
            return True
        except ClientError as e:
            logger.error(f"R2 connection test failed: {e}")
            return False


# Singleton instance
_r2_client = None

def get_r2_client():
    """Get or create the R2 client singleton."""
    global _r2_client
    if _r2_client is None:
        _r2_client = R2Client()
    return _r2_client
