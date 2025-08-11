"""Celery tasks for processing stream batches from MinIO."""

import os
import json
import traceback
import importlib
from datetime import datetime, timezone as tz
from typing import Dict, Any, Optional
from uuid import uuid4

import aioboto3
import asyncio
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker
from botocore.config import Config

from sources.base.scheduler.celery_app import app
from sources.base.generated_models.signals import Signals
from sources.base.storage.minio import get_minio_config
from sources.base.storage.database import sync_engine, SyncSessionLocal as Session
from sources._generated_registry import STREAM_REGISTRY

# Get MinIO configuration
_minio_config = get_minio_config()
MINIO_ENDPOINT = _minio_config['endpoint']
MINIO_ACCESS_KEY = _minio_config['access_key']
MINIO_SECRET_KEY = _minio_config['secret_key']
MINIO_BUCKET = _minio_config['bucket']
MINIO_USE_SSL = _minio_config['use_ssl']

# Stream processor registry is now imported from generated registry
# The registry maps stream names to their processor modules and signals


async def get_stream_data(stream_key: str) -> Dict[str, Any]:
    """Retrieve stream data from MinIO."""
    session = aioboto3.Session()
    async with session.client(
        's3',
        endpoint_url=MINIO_ENDPOINT,  # Already includes protocol
        aws_access_key_id=MINIO_ACCESS_KEY,
        aws_secret_access_key=MINIO_SECRET_KEY,
        config=Config(signature_version='s3v4'),
        region_name='us-east-1'
    ) as s3:
        response = await s3.get_object(Bucket=MINIO_BUCKET, Key=stream_key)
        data = await response['Body'].read()
        return json.loads(data.decode('utf-8'))


def process_stream_generic(
    stream_data: Dict[str, Any],
    stream_name: str,
    db
) -> Dict[str, Any]:
    """Generic stream processor for all streams."""
    
    # Get processor info from registry
    processor_info = STREAM_REGISTRY.get(stream_name)
    if not processor_info:
        raise ValueError(f"Unknown stream: {stream_name}")
    
    # Get active signals for this stream
    signal_configs = {}
    
    # Query for specific signals this stream produces
    produces_signals = processor_info.get('produces_signals', [])
    if produces_signals:
        signals_result = db.execute(
            text("""
                SELECT signal_name, id 
                FROM signal_configs 
                WHERE signal_name = ANY(:signal_names)
            """),
            {
                "signal_names": produces_signals
            }
        )
        
        for row in signals_result:
            signal_configs[row.signal_name] = row.id
    
    # Load and run processor
    # Parse processor path to get module and class
    processor_path = processor_info['processor']
    module_path = processor_path
    
    # Import the module and get the processor class
    # Assuming naming convention: StreamProcessor suffix
    module = importlib.import_module(module_path)
    
    # Find the processor class - look for the StreamProcessor class
    processor_class = None
    for item_name in dir(module):
        item = getattr(module, item_name)
        if isinstance(item, type) and item_name == 'StreamProcessor':
            processor_class = item
            break
    
    if not processor_class:
        raise ValueError(f"No StreamProcessor class found in {module_path}")
    
    processor = processor_class()
    
    return processor.process(stream_data, signal_configs, db)


@app.task(name="process_stream_batch", bind=True,
          autoretry_for=(Exception,), retry_kwargs={'max_retries': 3})
def process_stream_batch(
    self, 
    stream_name: str, 
    stream_key: str, 
    pipeline_activity_id: str,
    stream_id: str
):
    """
    Process a stream batch from MinIO storage.
    
    Args:
        stream_name: Name of the stream (e.g., 'apple_ios_core_location')
        stream_key: MinIO key where the stream data is stored
        pipeline_activity_id: ID of the pipeline activity from ingestion
        stream_id: ID of the stream configuration
    """
    
    db = Session()
    signal_creation_id = None
    
    try:
        # Get source from registry
        processor_info = STREAM_REGISTRY.get(stream_name)
        if not processor_info:
            raise ValueError(f"Unknown stream: {stream_name}")
        
        source_name = processor_info['source']
        
        # Create a new pipeline activity for signal creation
        signal_creation_id = str(uuid4())
        db.execute(
            text("""
                INSERT INTO pipeline_activities 
                (id, activity_type, activity_name, source_name, stream_id,
                 status, started_at, created_at, updated_at) 
                VALUES (:id, :activity_type, :activity_name, :source_name, 
                        :stream_id, :status, :started_at, :created_at, :updated_at)
            """),
            {
                "id": signal_creation_id,
                "activity_type": "signal_creation",
                "activity_name": f"{stream_name}_signal_creation",
                "source_name": source_name,
                "stream_id": stream_id,
                "status": "running",
                "started_at": datetime.utcnow(),
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
        )
        db.commit()
        
        # Get stream data from MinIO
        loop = asyncio.new_event_loop()
        try:
            stream_data = loop.run_until_complete(get_stream_data(stream_key))
        finally:
            loop.close()
        
        # Process using generic function
        result = process_stream_generic(stream_data, stream_name, db)
        
        # Update signal creation pipeline activity
        db.execute(
            text("""
                UPDATE pipeline_activities 
                SET status = :status,
                    completed_at = :completed_at,
                    output_path = :output_path,
                    updated_at = :updated_at,
                    records_processed = :records_processed
                WHERE id = :id
            """),
            {
                "id": signal_creation_id,
                "status": "completed",
                "completed_at": datetime.utcnow(),
                "output_path": stream_key,
                "updated_at": datetime.utcnow(),
                "records_processed": result.get("records_processed", 0)
            }
        )
        
        # Also update the stream's last successful processing time
        db.execute(
            text("""
                UPDATE stream_configs 
                SET last_ingestion_at = :last_ingestion_at,
                    updated_at = :updated_at
                WHERE id = :stream_id
            """),
            {
                "stream_id": stream_id,
                "last_ingestion_at": datetime.now(tz.utc),
                "updated_at": datetime.now(tz.utc)
            }
        )
        
        db.commit()
        
        # Chain transition detection after successful signal creation
        from celery import signature
        
        # Get today's date for transition detection
        # TODO: In the future, get actual user_id from the pipeline context
        user_id = "00000000-0000-0000-0000-000000000001"  # Default user for now
        date = datetime.now(tz.utc).strftime('%Y-%m-%d')
        
        # Queue transition detection for the signals just created
        transition_task = signature(
            'start_transition_detection',
            args=[user_id, date, 'automatic'],
            queue='celery'
        )
        task_result = transition_task.apply_async()
        print(f"Queued transition detection task: {task_result.id}")
        
        return result
        
    except Exception as e:
        error_message = f"{type(e).__name__}: {str(e)}"
        traceback.print_exc()
        
        # Update signal creation pipeline activity with failure if we created one
        if signal_creation_id:
            db.execute(
                text("""
                    UPDATE pipeline_activities 
                    SET status = :status,
                        completed_at = :completed_at,
                        error_message = :error_message,
                        updated_at = :updated_at
                    WHERE id = :id
                """),
                {
                    "id": signal_creation_id,
                    "status": "failed",
                    "completed_at": datetime.utcnow(),
                    "error_message": error_message,
                    "updated_at": datetime.utcnow()
                }
            )
            db.commit()
        raise
    finally:
        db.close()