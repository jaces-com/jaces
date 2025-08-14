"""Celery tasks for processing stream batches from MinIO."""

import os
import json
import traceback
import importlib
from datetime import datetime, timedelta, timezone as tz
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
    stream_id: str,
    db
) -> Dict[str, Any]:
    """Generic stream processor for all streams."""
    
    # Get stream and source info from database
    stream_info = db.execute(
        text("""
            SELECT sc.source_name, sc.stream_name
            FROM streams s
            JOIN stream_configs sc ON s.stream_config_id = sc.id
            WHERE s.id = :stream_id
        """),
        {"stream_id": stream_id}
    )
    stream_record = stream_info.fetchone()
    if not stream_record:
        raise ValueError(f"Stream not found: {stream_id}")
    
    source_name = stream_record.source_name
    db_stream_name = stream_record.stream_name
    
    # Get the stream's enabled_signals configuration
    stream_result = db.execute(
        text("""
            SELECT enabled_signals 
            FROM streams 
            WHERE id = :stream_id
        """),
        {"stream_id": stream_id}
    )
    stream_record = stream_result.fetchone()
    
    # Parse enabled_signals (it's stored as JSON)
    enabled_signals = None
    if stream_record and stream_record.enabled_signals:
        import json
        if isinstance(stream_record.enabled_signals, str):
            enabled_signals = json.loads(stream_record.enabled_signals)
        else:
            enabled_signals = stream_record.enabled_signals
    
    # Get active signals for this stream from database
    signal_configs = {}
    
    # Query signal configs for this stream, filtered by enabled_signals
    if enabled_signals is not None and len(enabled_signals) > 0:
        # Only get signals that are enabled
        # Build IN clause for proper filtering
        placeholders = ', '.join([f':signal_{i}' for i in range(len(enabled_signals))])
        query_params = {"stream_name": db_stream_name}
        for i, signal in enumerate(enabled_signals):
            query_params[f"signal_{i}"] = signal
        
        signals_result = db.execute(
            text(f"""
                SELECT signal_name, id 
                FROM signal_configs 
                WHERE stream_name = :stream_name
                AND signal_name IN ({placeholders})
            """),
            query_params
        )
        print(f"Filtering signals for stream {db_stream_name}: enabled_signals={enabled_signals}")
    else:
        # If enabled_signals is null/empty, get all signals for this stream
        print(f"Getting all signals for stream {db_stream_name} (enabled_signals is null/empty)")
        signals_result = db.execute(
            text("""
                SELECT signal_name, id 
                FROM signal_configs 
                WHERE stream_name = :stream_name
            """),
            {
                "stream_name": db_stream_name
            }
        )
    
    for row in signals_result:
        signal_configs[row.signal_name] = row.id
    
    print(f"Signal configs being passed to processor for {db_stream_name}: {list(signal_configs.keys())}")
    
    # Load and run processor
    # Derive processor path from naming convention
    # e.g., ios_location -> sources.ios.location.stream_processor
    stream_parts = db_stream_name.split('_', 1)
    if len(stream_parts) == 2 and stream_parts[0] == source_name:
        # Remove source prefix from stream name for path
        stream_subdir = stream_parts[1]
    else:
        # Use full stream name if no source prefix
        stream_subdir = db_stream_name
    
    processor_path = f"sources.{source_name}.{stream_subdir}.stream_processor"
    module_path = processor_path
    
    print(f"[DEBUG] Loading processor module: {module_path} for stream {db_stream_name}")
    
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
    
    print(f"[DEBUG] process_stream_batch called with: stream_name={stream_name}, stream_key={stream_key}, stream_id={stream_id}")
    
    db = Session()
    signal_creation_id = None
    
    try:
        # Get source from database, including stream_config_id for FK
        stream_result = db.execute(
            text("""
                SELECT sc.id as stream_config_id, sc.source_name, sc.stream_name as db_stream_name
                FROM streams s
                JOIN stream_configs sc ON s.stream_config_id = sc.id
                WHERE s.id = :stream_id
            """),
            {"stream_id": stream_id}
        )
        stream_record = stream_result.fetchone()
        if not stream_record:
            raise ValueError(f"Stream not found: {stream_id}")
        
        stream_config_id = stream_record.stream_config_id
        source_name = stream_record.source_name
        actual_stream_name = stream_record.db_stream_name
        print(f"[DEBUG] Database lookup: stream_id={stream_id} -> stream_name={actual_stream_name}, source_name={source_name}, stream_config_id={stream_config_id}")
        
        # Create a new pipeline activity for signal creation
        signal_creation_id = str(uuid4())
        # Note: stream_id in pipeline_activities expects stream_configs.id, not streams.id
        # For now, we'll set it to NULL since it's optional
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
                "stream_id": stream_id,  # Use stream_id (streams.id) for the FK
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
        print(f"[DEBUG] About to process with process_stream_generic: stream_name={stream_name}, stream_id={stream_id}")
        result = process_stream_generic(stream_data, stream_name, stream_id, db)
        
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
        # Queue signal-specific transition detection for better performance
        from celery import signature
        
        # Extract time window from the batch
        batch_start = None
        batch_end = None
        
        # Try to get time range from signals created
        total_signals = sum(result['signals_created'].values()) if isinstance(result['signals_created'], dict) else result['signals_created']
        if total_signals > 0:
            # Query the time range of signals just created
            time_range_result = db.execute(
                text("""
                    SELECT MIN(timestamp) as min_time, MAX(timestamp) as max_time
                    FROM signals
                    WHERE created_at >= :pipeline_start
                    AND source_name = :source_name
                """),
                {
                    "pipeline_start": datetime.utcnow() - timedelta(minutes=5),
                    "source_name": source_name
                }
            )
            time_range = time_range_result.fetchone()
            if time_range and time_range.min_time and time_range.max_time:
                batch_start = time_range.min_time
                batch_end = time_range.max_time
        
        # Queue transition detection for each signal type that was created
        if batch_start and batch_end and total_signals > 0:
            date = batch_start.strftime('%Y-%m-%d')
            
            # Get timezone from single user record
            tz_result = db.execute(
                text("SELECT timezone FROM users LIMIT 1"),
                {}
            )
            tz_record = tz_result.fetchone()
            timezone = tz_record[0] if tz_record and tz_record[0] else 'America/Chicago'
            
            # Get the signals that were just created for this stream
            for signal_name in result.get('signals_created', {}).keys():
                # Queue single signal transition detection
                transition_task = signature(
                    'run_single_signal_transition_detection',
                    args=[
                        signal_name,
                        date,
                        batch_start.isoformat(),
                        batch_end.isoformat(),
                        timezone
                    ],
                    queue='celery'
                )
                task_result = transition_task.apply_async()
                print(f"[ProcessStream] Queued transition detection for {signal_name}: {task_result.id}")
        
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