"""Celery tasks for syncing data sources - generic implementation."""

import asyncio
import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
import traceback
import importlib
from uuid import uuid4

from celery import Task
from sqlalchemy import text, select, update
from sqlalchemy.orm import sessionmaker
from croniter import croniter

from sources.base.scheduler.celery_app import app
from sources.base.storage.database import sync_engine, SyncSessionLocal as Session


def json_serializable(obj):
    """Convert objects to JSON-serializable format."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    elif isinstance(obj, dict):
        return {k: json_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [json_serializable(v) for v in obj]
    else:
        return obj


# Set up logger
logger = logging.getLogger(__name__)


class SourceRegistry:
    """Registry for dynamically loading source sync classes - explicit configuration only."""
    
    @staticmethod
    def get_sync_class(stream_name: str):
        """Get sync class from registry - explicit configuration required."""
        try:
            from sources._generated_registry import STREAMS
        except ImportError:
            raise ValueError("Generated registry not found. Run generate_registry.py")
        
        stream_config = STREAMS.get(stream_name)
        if not stream_config:
            raise ValueError(f"Stream '{stream_name}' not found in registry")
        
        # Check if this is a push stream (no sync needed)
        if stream_config.get('ingestion', {}).get('type') == 'push' and 'sync_module' not in stream_config:
            raise ValueError(f"Stream '{stream_name}' is push-only (no sync needed)")
        
        # Must have explicit sync_module and sync_class
        sync_module = stream_config.get('sync_module')
        sync_class = stream_config.get('sync_class')
        
        if not sync_module:
            raise ValueError(f"Stream '{stream_name}' missing 'sync_module' in registry")
        
        if not sync_class:
            raise ValueError(f"Stream '{stream_name}' missing 'sync_class' in registry")
        
        # Import and return the explicit class
        try:
            module = importlib.import_module(sync_module)
            return getattr(module, sync_class)
        except ImportError as e:
            raise ValueError(f"Failed to import {sync_module}: {e}")
        except AttributeError as e:
            raise ValueError(f"Class {sync_class} not found in {sync_module}: {e}")


@app.task(name="sync_stream", bind=True,
          autoretry_for=(Exception,), retry_kwargs={'max_retries': 3})
def sync_stream(self, stream_id: str, manual: bool = False):
    """Generic task to sync any data stream."""

    # Use sync database session
    db = Session()
    try:
        # Get stream details
        result = db.execute(
            text("""
                SELECT stc.*, src.company, src.platform, src.auth_type
                FROM stream_configs stc 
                JOIN source_configs src ON stc.source_name = src.name
                WHERE stc.id = :stream_id
            """),
            {"stream_id": stream_id}
        ).first()

        if not result:
            raise ValueError(f"Stream {stream_id} not found")

        stream = dict(result._mapping)
        source_name = stream['source_name']
        stream_name = stream['stream_name']
        platform = stream.get('platform', 'cloud')

        # Skip device sources - they push their own data
        if platform == 'device' and not manual:
            return {"status": "skipped", "reason": "device_source"}

        # Skip inactive streams unless manually triggered
        if stream['status'] != 'active' and not manual:
            return {"status": "skipped", "reason": "stream_inactive"}

        # Get the sync class for this stream (not source)
        try:
            sync_class = SourceRegistry.get_sync_class(stream_name)
        except ValueError as e:
            # Source doesn't have a sync implementation (might be webhook-only)
            return {"status": "skipped", "reason": str(e)}

        # Create ingestion run
        ingestion_run_id = uuid4()

        db.execute(
            text("""
                INSERT INTO pipeline_activities 
                (id, activity_type, activity_name, source_name, stream_id, 
                 status, started_at, created_at, updated_at) 
                VALUES (:id, :activity_type, :activity_name, :source_name, 
                        :stream_id, :status, :started_at, :created_at, :updated_at)
            """),
            {
                "id": str(ingestion_run_id),
                "activity_type": "ingestion",
                "activity_name": f"{source_name}_stream_ingestion",
                "source_name": source_name,
                "stream_id": stream_id,  # Include the stream_id
                "status": "running",
                "started_at": datetime.utcnow(),
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
        )
        db.commit()

        try:
            # Check if source requires credentials
            oauth_credentials = None
            if stream.get('auth_type') == 'oauth2':
                # Get OAuth tokens from the sources table
                source_result = db.execute(
                    text("""
                        SELECT id, oauth_access_token, oauth_refresh_token, oauth_expires_at, scopes
                        FROM sources
                        WHERE source_name = :source_name
                        AND oauth_access_token IS NOT NULL
                        AND is_active = true
                        LIMIT 1
                    """),
                    {
                        "source_name": source_name
                    }
                ).first()

                if source_result:
                    oauth_credentials = dict(source_result._mapping)
                    oauth_credentials['source_id'] = oauth_credentials['id']
                else:
                    raise ValueError(
                        f"No authenticated source found for {source_name}")

            # Create stream object with necessary fields
            stream_obj = StreamWrapper(stream, oauth_credentials)

            # Initialize sync class
            if oauth_credentials and hasattr(sync_class, '__init__') and oauth_credentials.get('oauth_access_token'):
                # For OAuth sources that need tokens
                sync = sync_class(
                    stream_obj,
                    oauth_credentials['oauth_access_token'],
                    token_refresher=create_token_refresher(
                        source_name, oauth_credentials, stream_obj, db) if oauth_credentials.get('oauth_refresh_token') else None
                )
            else:
                # For sources that don't need tokens (e.g., device-based)
                sync = sync_class(stream_obj)

            # Run sync - handle both async and sync implementations
            if asyncio.iscoroutinefunction(sync.run):
                # Async sync implementation
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    stats = loop.run_until_complete(sync.run())
                finally:
                    loop.close()
            else:
                # Sync implementation
                stats = sync.run()

            # Update stream last_ingestion_at
            db.execute(
                text("""
                    UPDATE stream_configs 
                    SET last_ingestion_at = :last_ingestion_at,
                        updated_at = :updated_at
                    WHERE id = :id
                """),
                {
                    "id": stream_id,
                    "last_ingestion_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow()
                }
            )

            # Update ingestion run
            db.execute(
                text("""
                    UPDATE pipeline_activities 
                    SET status = :status,
                        completed_at = :completed_at,
                        records_processed = :records_processed,
                        updated_at = :updated_at,
                        activity_metadata = :activity_metadata
                    WHERE id = :id
                """),
                {
                    "id": str(ingestion_run_id),
                    "status": "completed",
                    "completed_at": datetime.utcnow(),
                    "records_processed": stats.get("records_processed", stats.get("events_processed", stats.get("locations_processed", 0))),
                    "updated_at": datetime.utcnow(),
                    "activity_metadata": json.dumps(json_serializable(stats))
                }
            )

            db.commit()

            return {
                "status": "success",
                "stream_id": stream_id,
                "stream_name": stream['stream_name'],
                "source": source_name,
                "stats": stats
            }

        except Exception as e:
            # Log error
            error_message = f"{type(e).__name__}: {str(e)}"
            traceback.print_exc()

            # Classify errors - don't retry certain types
            non_retryable_errors = (
                'ProgrammingError',  # Database schema issues
                'UndefinedColumn',   # Missing columns
                'AuthenticationError', # OAuth/auth issues that need user intervention
                'PermissionError',   # Access denied
                'Unauthorized'       # 401 errors
            )
            
            should_retry = not any(error_type in error_message for error_type in non_retryable_errors)

            # Update pipeline activity
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
                    "id": str(ingestion_run_id),
                    "status": "failed",
                    "completed_at": datetime.utcnow(),
                    # Truncate if too long
                    "error_message": error_message[:1000],
                    "updated_at": datetime.utcnow()
                }
            )

            db.commit()
            
            # Custom retry logic with exponential backoff
            if should_retry and self.request.retries < self.max_retries:
                # Exponential backoff: 60s, 120s, 240s
                countdown = 60 * (2 ** self.request.retries)
                raise self.retry(countdown=countdown, exc=e)
            else:
                # Don't retry or max retries reached
                raise

    finally:
        db.close()


# Keep the old sync_source task for backward compatibility
@app.task(name="sync_source", bind=True,
          autoretry_for=(Exception,), retry_kwargs={'max_retries': 3})
def sync_source(self, signal_id: str, manual: bool = False):
    """Generic task to sync any data source."""

    # Use sync database session
    db = Session()
    try:
        # Get signal details
        result = db.execute(
            text("""
                SELECT s.*, src.company, src.platform
                FROM signals s 
                JOIN sources src ON s.source_name = src.name
                WHERE s.id = :signal_id
            """),
            {"signal_id": signal_id}
        ).first()

        if not result:
            raise ValueError(f"Signal {signal_id} not found")

        signal = dict(result._mapping)
        source_name = signal['source_name']
        platform = signal.get('platform', 'cloud')

        # Skip device sources - they push their own data
        if platform == 'device' and not manual:
            return {"status": "skipped", "reason": "device_source"}

        # Skip inactive signals unless manually triggered
        if signal['status'] != 'active' and not manual:
            return {"status": "skipped", "reason": "signal_inactive"}

        # Get the sync class for this source
        try:
            sync_class = SourceRegistry.get_sync_class(source_name)
        except ValueError as e:
            # Source doesn't have a sync implementation (might be webhook-only)
            return {"status": "skipped", "reason": str(e)}

        # Create ingestion run
        ingestion_run_id = uuid4()

        # Get source_name from signal
        signal_info = db.execute(
            text("SELECT source_name FROM signals WHERE id = :signal_id"),
            {"signal_id": signal_id}
        ).first()

        if not signal_info:
            raise ValueError(f"Signal {signal_id} not found")

        db.execute(
            text("""
                INSERT INTO pipeline_activities 
                (id, activity_type, activity_name, source_name, signal_id, 
                 status, started_at, created_at, updated_at) 
                VALUES (:id, :activity_type, :activity_name, :source_name, 
                        :signal_id, :status, :started_at, :created_at, :updated_at)
            """),
            {
                "id": str(ingestion_run_id),
                "activity_type": "ingestion",
                "activity_name": f"{signal_info.source_name}_ingestion",
                "source_name": signal_info.source_name,
                "signal_id": signal_id,
                "status": "running",
                "started_at": datetime.utcnow(),
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
        )
        db.commit()

        try:
            # Check if source requires credentials
            oauth_credentials = None
            if hasattr(sync_class, 'requires_credentials') and sync_class.requires_credentials:
                # Get OAuth tokens from the sources table
                source_result = db.execute(
                    text("""
                        SELECT oauth_access_token, oauth_refresh_token, oauth_expires_at, scopes
                        FROM sources
                        WHERE source_name = :source_name
                        AND oauth_access_token IS NOT NULL
                        LIMIT 1
                    """),
                    {
                        "source_name": source_name
                    }
                ).first()

                if source_result:
                    oauth_credentials = dict(source_result._mapping)

            # Create signal object with necessary fields
            signal_obj = SignalWrapper(signal, oauth_credentials)

            # Initialize sync class
            if oauth_credentials and hasattr(sync_class, '__init__') and oauth_credentials.get('oauth_access_token'):
                # For OAuth sources that need tokens
                sync = sync_class(
                    signal_obj,
                    oauth_credentials['oauth_access_token'],
                    token_refresher=create_token_refresher(
                        source_name, oauth_credentials, signal_obj, db) if oauth_credentials.get('oauth_refresh_token') else None
                )
            else:
                # For sources that don't need tokens (e.g., device-based)
                sync = sync_class(signal_obj)

            # Run sync - handle both async and sync implementations
            if asyncio.iscoroutinefunction(sync.run):
                # Async sync implementation
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    stats = loop.run_until_complete(sync.run())
                finally:
                    loop.close()
            else:
                # Sync implementation
                stats = sync.run()

            # Update signal
            update_data = {"last_successful_ingestion_at": datetime.utcnow()}
            if stats.get("next_sync_token"):
                update_data["sync_token"] = stats["next_sync_token"]

            db.execute(
                text("""
                    UPDATE signals 
                    SET last_successful_ingestion_at = :last_successful_ingestion_at,
                        sync_token = :sync_token,
                        updated_at = :updated_at
                    WHERE id = :id
                """),
                {
                    "id": signal_id,
                    "last_successful_ingestion_at": update_data["last_successful_ingestion_at"],
                    "sync_token": update_data.get("sync_token", signal.get('sync_token')),
                    "updated_at": datetime.utcnow()
                }
            )

            # Update ingestion run
            db.execute(
                text("""
                    UPDATE pipeline_activities 
                    SET status = :status,
                        completed_at = :completed_at,
                        records_processed = :records_processed,
                        updated_at = :updated_at,
                        activity_metadata = :activity_metadata
                    WHERE id = :id
                """),
                {
                    "id": str(ingestion_run_id),
                    "status": "completed",
                    "completed_at": datetime.utcnow(),
                    "records_processed": stats.get("records_processed", stats.get("events_processed", stats.get("locations_processed", 0))),
                    "updated_at": datetime.utcnow(),
                    "activity_metadata": json.dumps(json_serializable(stats))
                }
            )

            db.commit()

            return {
                "status": "success",
                "signal_id": signal_id,
                "source": source_name,
                "stats": stats
            }

        except Exception as e:
            # Log error
            error_message = f"{type(e).__name__}: {str(e)}"
            traceback.print_exc()

            # Update pipeline activity
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
                    "id": str(ingestion_run_id),
                    "status": "failed",
                    "completed_at": datetime.utcnow(),
                    # Truncate if too long
                    "error_message": error_message[:1000],
                    "updated_at": datetime.utcnow()
                }
            )

            db.commit()
            raise

    finally:
        db.close()


class SignalWrapper:
    """Wrapper to make dict behave like an object for compatibility."""

    def __init__(self, signal_dict: dict, oauth_credentials: Optional[dict] = None):
        self._dict = signal_dict
        self._oauth_credentials = oauth_credentials

    def __getattr__(self, name):
        return self._dict.get(name)

    def __getitem__(self, key):
        return self._dict[key]

    @property
    def id(self):
        return self._dict['id']

    @property
    def signal_id(self):
        return self._dict['signal_id']

    @property
    def source_name(self):
        return self._dict['source_name']

    @property
    def sync_token(self):
        return self._dict.get('sync_token')

    @property
    def last_successful_ingestion_at(self):
        return self._dict.get('last_successful_ingestion_at')

    @property
    def is_active(self):
        return self._dict.get('status') == 'active'

    @property
    def fidelity_score(self):
        return self._dict.get('fidelity_score', 0.5)

    @property
    def description(self):
        return self._dict.get('description')

    @property
    def settings(self):
        return self._dict.get('settings', {})

    @property
    def device_token(self):
        return self._dict.get('device_token')

    @property
    def device_id_fk(self):
        return self._dict.get('device_id_fk')

    @property
    def signal_type(self):
        return self._dict.get('signal_type')

    @property
    def unit(self):
        return self._dict.get('unit_ucum')

    @property
    def computation(self):
        return self._dict.get('computation')


class StreamWrapper:
    """Wrapper to make stream dict behave like a signal object for compatibility."""

    def __init__(self, stream_dict: dict, oauth_credentials: Optional[dict] = None):
        self._dict = stream_dict
        self._oauth_credentials = oauth_credentials

    def __getattr__(self, name):
        return self._dict.get(name)

    def __getitem__(self, key):
        return self._dict[key]

    @property
    def id(self):
        return self._dict['id']

    @property
    def source_name(self):
        return self._dict['source_name']

    @property
    def stream_name(self):
        return self._dict['stream_name']

    @property
    def last_successful_ingestion_at(self):
        # For streams, we use last_ingestion_at
        return self._dict.get('last_ingestion_at')

    @property
    def is_active(self):
        return self._dict.get('status') == 'active'

    @property
    def settings(self):
        return self._dict.get('settings', {})


def create_token_refresher(source_name: str, oauth_credentials: dict, source_config: dict, db):
    """Create a token refresher function for OAuth sources."""
    
    try:
        from sources._generated_registry import SOURCES
    except ImportError:
        logger.warning("Generated registry not found. Token refresh disabled.")
        return None
    
    # Get source config from registry
    source = SOURCES.get(source_name)
    if not source:
        logger.warning(f"Source '{source_name}' not found in registry")
        return None
    
    # Check if this is an OAuth source
    if source.get('auth', {}).get('type') != 'oauth2':
        return None
    
    # Dynamically import the auth module for this source
    try:
        # Construct auth module path from source path
        source_path = source['path'].rstrip('/')
        auth_module_path = f"sources.{source_path.replace('/', '.')}.auth"
        
        try:
            auth_module = importlib.import_module(auth_module_path)
        except ImportError:
            # Some sources might have auth at a different level
            # Try parent directory
            parts = source_path.split('/')
            if len(parts) > 1:
                parent_path = '/'.join(parts[:-1])
                auth_module_path = f"sources.{parent_path.replace('/', '.')}.auth"
                auth_module = importlib.import_module(auth_module_path)
            else:
                raise
        
        # Check for refresh_token function or refresh_google_token (backward compat)
        refresh_func = None
        if hasattr(auth_module, 'refresh_token'):
            refresh_func = auth_module.refresh_token
        elif hasattr(auth_module, 'refresh_google_token'):
            refresh_func = auth_module.refresh_google_token
        else:
            logger.warning(f"No token refresh function found in {auth_module_path}")
            return None
            
        async def token_refresher():
            """Generic token refresher."""
            try:
                # Call source-specific refresh logic
                new_tokens = await refresh_func(oauth_credentials['oauth_refresh_token'])
                
                # Update tokens in sources table
                db.execute(
                    text("""
                        UPDATE sources 
                        SET oauth_access_token = :access_token,
                            oauth_refresh_token = :refresh_token,
                            oauth_expires_at = :expires_at,
                            updated_at = :updated_at
                        WHERE id = :source_id
                    """),
                    {
                        "source_id": oauth_credentials.get('source_id'),
                        "access_token": new_tokens["access_token"],
                        "refresh_token": new_tokens.get("refresh_token", oauth_credentials['oauth_refresh_token']),
                        "expires_at": datetime.utcnow() + timedelta(seconds=new_tokens.get("expires_in", 3600)),
                        "updated_at": datetime.utcnow()
                    }
                )
                db.commit()
                
                return new_tokens["access_token"]
            except Exception as e:
                raise Exception(f"Failed to refresh {source_name} token: {str(e)}")
        
        return token_refresher
        
    except ImportError as e:
        # Source doesn't have an auth module - that's okay for non-OAuth sources
        logger.debug(f"No auth module found for {source_name}: {e}")
        return None
    except Exception as e:
        logger.error(f"Error creating token refresher for {source_name}: {e}")
        return None


@app.task(name="check_scheduled_syncs")
def check_scheduled_syncs():
    """Check for streams that need to be synced based on their schedule."""

    db = Session()
    try:
        # Get all active streams with cron schedules from cloud sources only
        # Device sources (mac, ios) push their own data
        result = db.execute(
            text("""
                SELECT stc.*, src.platform, src.auth_type
                FROM stream_configs stc
                JOIN source_configs src ON stc.source_name = src.name
                WHERE stc.status = 'active'
                AND stc.ingestion_type = 'pull'
                AND stc.cron_schedule IS NOT NULL
                AND src.platform = 'cloud'
            """)
        ).fetchall()

        triggered = []
        now = datetime.utcnow()

        for row in result:
            stream = dict(row._mapping)

            # Check if there's a connected source for this stream
            source_result = db.execute(
                text("""
                    SELECT id, is_active, oauth_access_token IS NOT NULL as has_token
                    FROM sources
                    WHERE source_name = :source_name
                    AND is_active = true
                    LIMIT 1
                """),
                {"source_name": stream['source_name']}
            ).first()

            if not source_result:
                logger.info(
                    f"No active source found for stream {stream['stream_name']}")
                continue

            if stream.get('auth_type') == 'oauth2' and not source_result.has_token:
                logger.info(
                    f"OAuth source {stream['source_name']} not authenticated")
                continue

            # Check if sync is due based on cron schedule
            if should_sync(stream, now):
                # Trigger sync for this stream
                sync_stream.delay(str(stream['id']))
                triggered.append({
                    "stream_id": str(stream['id']),
                    "stream_name": stream['stream_name'],
                    "source": stream['source_name']
                })

        return {
            "checked": len(result),
            "triggered": len(triggered),
            "streams": triggered
        }
    finally:
        db.close()


def should_sync(stream: dict, now: datetime) -> bool:
    """Check if a stream should sync based on its schedule."""
    cron_schedule = stream.get('cron_schedule')
    if not cron_schedule:
        return False

    # Parse cron expression
    try:
        # Use last_ingestion_at for streams
        last_sync = stream.get('last_ingestion_at')
        if last_sync is None:
            # If never synced, sync now
            return True

        # Ensure both datetimes are timezone-aware or both are naive
        if last_sync.tzinfo is None:
            # If last_sync is naive, assume it's UTC
            from datetime import timezone
            last_sync = last_sync.replace(tzinfo=timezone.utc)
        if now.tzinfo is None:
            # If now is naive, assume it's UTC
            from datetime import timezone
            now = now.replace(tzinfo=timezone.utc)

        cron = croniter(cron_schedule, last_sync)
        next_run = cron.get_next(datetime)
        return next_run <= now
    except Exception as e:
        logger.error(
            f"Invalid cron expression '{cron_schedule}' for stream {stream.get('stream_name')}: {e}")
        return False


# Note: sync_all_user_sources is deprecated - the system no longer uses user_id
# @app.task(name="sync_all_user_sources")
# def sync_all_user_sources(user_id: str):
#     """Sync all signals for a specific user."""
#
#     db = Session()
#     try:
#         result = db.execute(
#             text("""
#                 SELECT * FROM signals
#                 WHERE user_id = :user_id AND status = 'active'
#             """),
#             {"user_id": user_id}
#         ).fetchall()
#
#         triggered = []
#
#         for row in result:
#             signal = dict(row._mapping)
#             sync_source.delay(str(signal['id']))
#             triggered.append({
#                 "signal_id": str(signal['id']),
#                 "source": signal['source_name']
#             })
#
#         return {
#             "user_id": user_id,
#             "triggered": triggered
#         }
#     finally:
#         db.close()


@app.task(name="cleanup_old_runs")
def cleanup_old_runs(days_to_keep: int = 30):
    """Clean up old ingestion runs to prevent table bloat."""

    db = Session()
    try:
        cutoff_date = datetime.utcnow() - timedelta(days=days_to_keep)

        # Delete old runs
        result = db.execute(
            text("""
                DELETE FROM pipeline_activities 
                WHERE activity_type = 'ingestion' 
                AND started_at < :cutoff_date
                RETURNING id
            """),
            {"cutoff_date": cutoff_date}
        )

        deleted_count = result.rowcount
        db.commit()

        return {
            "deleted": deleted_count,
            "cutoff_date": cutoff_date.isoformat()
        }
    finally:
        db.close()


@app.task(name="refresh_expiring_tokens")
def refresh_expiring_tokens():
    """Proactively refresh tokens that are about to expire."""

    db = Session()
    try:
        # Find credentials that expire within the next hour
        expiry_threshold = datetime.utcnow() + timedelta(hours=1)

        # Find sources with tokens that need refreshing
        result = db.execute(
            text("""
                SELECT s.id, s.source_name, s.instance_name, s.oauth_access_token, 
                       s.oauth_refresh_token, s.oauth_expires_at, s.scopes
                FROM sources s
                WHERE s.oauth_expires_at IS NOT NULL
                AND s.oauth_expires_at < :expiry_threshold
                AND s.oauth_refresh_token IS NOT NULL
                AND s.is_active = true
            """),
            {"expiry_threshold": expiry_threshold}
        ).fetchall()

        refreshed = []
        failed = []

        for row in result:
            source_dict = dict(row._mapping)
            try:
                # Skip non-OAuth sources (e.g., device sources)
                if not source_dict.get('oauth_refresh_token'):
                    continue

                # For now, skip token refresh since the system architecture has changed
                # This would need to be reimplemented based on the new schema
                logger.warning(
                    f"Token refresh needed for source {source_dict['source_name']} "
                    f"(instance: {source_dict['instance_name']}), but refresh logic needs update"
                )

            except Exception as e:
                failed.append({
                    "source": source_dict['source_name'],
                    "instance": source_dict.get('instance_name', 'unknown'),
                    "error": str(e)
                })

        return {
            "refreshed": len(refreshed),
            "failed": len(failed),
            "refreshed_sources": refreshed,
            "failed_sources": failed
        }
    finally:
        db.close()
