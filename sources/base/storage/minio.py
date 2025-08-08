"""Unified MinIO storage service for all sources."""

from typing import Any, Optional, List, Dict
from datetime import datetime
import aioboto3
import os
import json
from pathlib import Path
from uuid import uuid4
from botocore.config import Config


def get_minio_config() -> Dict[str, Any]:
    """Get MinIO configuration from environment variables."""
    return {
        'endpoint': os.getenv('MINIO_ENDPOINT', 'localhost:9000'),
        'access_key': os.getenv('MINIO_ACCESS_KEY', 'minioadmin'),
        'secret_key': os.getenv('MINIO_SECRET_KEY', 'minioadmin'),
        'bucket': os.getenv('MINIO_BUCKET', 'jaces'),
        'use_ssl': os.getenv('MINIO_USE_SSL', 'false').lower() == 'true',
        'region': os.getenv('MINIO_REGION', 'us-east-1')
    }


class MinIOClient:
    """Async MinIO client for storing and retrieving raw source data."""
    
    def __init__(self):
        # Get MinIO configuration from centralized config
        config = get_minio_config()
        
        self.endpoint_url = config['endpoint']
        if not self.endpoint_url.startswith("http"):
            protocol = "https" if config['use_ssl'] else "http"
            self.endpoint_url = f"{protocol}://{self.endpoint_url}"
        
        self.access_key = config['access_key']
        self.secret_key = config['secret_key']
        self.use_ssl = config['use_ssl']
        self.default_bucket = config['bucket']
        
        self.session = aioboto3.Session()
    
    async def put_raw_data(
        self,
        source_name: str,
        connection_id: str,
        data: bytes,
        filename: str,
        timestamp: Optional[datetime] = None,
        content_type: str = "application/octet-stream",
        bucket: Optional[str] = None
    ) -> str:
        """
        Store raw source data with consistent key structure.
        
        Args:
            source_name: Name of the source (e.g., 'google_calendar')
            connection_id: UUID of the connection
            data: Raw data bytes to store
            filename: Name of the file
            timestamp: Optional timestamp (defaults to now)
            content_type: MIME type of the data
            bucket: Optional bucket name (defaults to configured bucket)
            
        Returns:
            The S3 key where the data was stored
        """
        if timestamp is None:
            timestamp = datetime.utcnow()
        
        # Create consistent key structure: source/date/connection/filename
        # This makes it easier to browse by date and keeps files organized
        key = f"{source_name}/{timestamp.strftime('%Y/%m/%d')}/{connection_id}/{filename}"
        
        await self.put_object(
            bucket=bucket or self.default_bucket,
            key=key,
            data=data,
            content_type=content_type
        )
        
        return key
    
    async def get_raw_data(
        self,
        key: str,
        bucket: Optional[str] = None
    ) -> bytes:
        """
        Retrieve raw data by key.
        
        Args:
            key: S3 key of the object
            bucket: Optional bucket name (defaults to configured bucket)
            
        Returns:
            Raw data bytes
        """
        return await self.get_object(
            bucket=bucket or self.default_bucket,
            key=key
        )
    
    async def list_source_files(
        self,
        source_name: str,
        connection_id: str,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        bucket: Optional[str] = None,
        max_keys: int = 1000
    ) -> List[Dict[str, Any]]:
        """
        List files for a specific source and connection with optional time filtering.
        
        Args:
            source_name: Name of the source
            connection_id: UUID of the connection
            since: Optional start timestamp
            until: Optional end timestamp
            bucket: Optional bucket name (defaults to configured bucket)
            max_keys: Maximum number of keys to return
            
        Returns:
            List of file metadata dictionaries
        """
        prefix = f"{source_name}/{connection_id}/"
        
        # If we have time bounds, we could optimize the prefix
        # For now, we'll list all and filter
        objects = await self.list_objects(
            bucket=bucket or self.default_bucket,
            prefix=prefix,
            max_keys=max_keys
        )
        
        # Filter by time if provided
        if since or until:
            filtered = []
            for obj in objects:
                last_modified = obj.get('LastModified')
                if last_modified:
                    if since and last_modified < since:
                        continue
                    if until and last_modified > until:
                        continue
                    filtered.append(obj)
            return filtered
        
        return objects
    
    async def delete_old_data(
        self,
        source_name: str,
        connection_id: str,
        older_than: datetime,
        bucket: Optional[str] = None
    ) -> int:
        """
        Delete old raw data for cleanup.
        
        Args:
            source_name: Name of the source
            connection_id: UUID of the connection
            older_than: Delete files older than this timestamp
            bucket: Optional bucket name (defaults to configured bucket)
            
        Returns:
            Number of objects deleted
        """
        objects = await self.list_source_files(
            source_name=source_name,
            connection_id=connection_id,
            until=older_than,
            bucket=bucket
        )
        
        if not objects:
            return 0
        
        # Delete objects in batches
        async with self.session.client(
            "s3",
            endpoint_url=self.endpoint_url,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            use_ssl=self.use_ssl
        ) as s3:
            delete_objects = [{"Key": obj["Key"]} for obj in objects]
            
            response = await s3.delete_objects(
                Bucket=bucket or self.default_bucket,
                Delete={"Objects": delete_objects}
            )
            
            return len(response.get("Deleted", []))
    
    # Lower-level methods (migrated from original MinIOStorage)
    
    async def put_object(
        self,
        bucket: str,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream"
    ) -> None:
        """Store an object in MinIO."""
        async with self.session.client(
            "s3",
            endpoint_url=self.endpoint_url,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            use_ssl=self.use_ssl
        ) as s3:
            await s3.put_object(
                Bucket=bucket,
                Key=key,
                Body=data,
                ContentType=content_type
            )
    
    async def get_object(self, bucket: str, key: str) -> bytes:
        """Retrieve an object from MinIO."""
        async with self.session.client(
            "s3",
            endpoint_url=self.endpoint_url,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            use_ssl=self.use_ssl
        ) as s3:
            response = await s3.get_object(Bucket=bucket, Key=key)
            return await response["Body"].read()
    
    async def list_objects(
        self,
        bucket: str,
        prefix: Optional[str] = None,
        max_keys: int = 1000
    ) -> list:
        """List objects in a bucket with optional prefix."""
        async with self.session.client(
            "s3",
            endpoint_url=self.endpoint_url,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            use_ssl=self.use_ssl
        ) as s3:
            params = {"Bucket": bucket, "MaxKeys": max_keys}
            if prefix:
                params["Prefix"] = prefix
            
            response = await s3.list_objects_v2(**params)
            return response.get("Contents", [])


# Standalone functions for backward compatibility
async def store_raw_data(
    stream_name: str,
    connection_id: str,
    data: Any,
    timestamp: datetime
) -> str:
    """Store raw data to MinIO and return the key."""
    # Generate key based on stream and date
    date_path = timestamp.strftime("%Y/%m/%d")
    file_id = uuid4().hex
    key = f"streams/{stream_name}/{date_path}/{file_id}.json"
    
    # Convert data to JSON
    json_data = json.dumps(data, default=str).encode('utf-8')
    
    # Get MinIO configuration
    config = get_minio_config()
    endpoint = config['endpoint'].replace('http://', '').replace('https://', '')
    
    # Create S3 client
    session = aioboto3.Session()
    async with session.client(
        's3',
        endpoint_url=f"{'https' if config['use_ssl'] else 'http'}://{endpoint}",
        aws_access_key_id=config['access_key'],
        aws_secret_access_key=config['secret_key'],
        config=Config(signature_version='s3v4'),
        region_name=config['region']
    ) as s3:
        # Upload to MinIO
        await s3.put_object(
            Bucket=config['bucket'],
            Key=key,
            Body=json_data,
            ContentType='application/json',
            Metadata={
                'connection_id': connection_id,
                'stream_name': stream_name,
                'timestamp': timestamp.isoformat()
            }
        )
    
    return key