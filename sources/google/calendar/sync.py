"""Google Calendar incremental sync logic."""

import json
import asyncio
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from uuid import uuid4
import httpx

from .client import GoogleCalendarClient
from sources.base.storage.minio import store_raw_data
from sources.base.generated_models.signals import Signals
from sources.base.generated_models.episodic_signals import EpisodicSignals
from sources.base.storage.database import AsyncSessionLocal


class GoogleCalendarSync:
    """Handles incremental sync of Google Calendar data."""

    MAX_RETRIES = 3
    RETRY_DELAY = 1.0  # seconds
    requires_credentials = True  # This source requires OAuth credentials

    # Sync time windows
    INITIAL_SYNC_YEARS_PAST = 2  # How far back to look on first sync
    INITIAL_SYNC_YEARS_FUTURE = 1  # How far ahead to look on first sync
    INCREMENTAL_SYNC_DAYS_PAST = 30  # Fallback for incremental sync without token
    INCREMENTAL_SYNC_DAYS_FUTURE = 14  # How far ahead for incremental sync

    def __init__(self, signal: Signals, access_token: str, token_refresher=None):
        self.signal = signal
        self.client = GoogleCalendarClient(access_token, token_refresher)
        # Normalizer removed - now using stream processors
        # self.normalizer = GoogleCalendarNormalizer(
        #     fidelity_score=signal.fidelity_score,
        #     insider_tip=signal.description  # Using description field for insider tips
        # )
        # Storage will be handled via streams

    async def run(self) -> Dict[str, Any]:
        """
        Execute incremental sync for Google Calendar.

        Returns:
            Dict with sync statistics (events_processed, errors, etc.)
        """
        stats = {
            "events_processed": 0,
            "calendars_synced": 0,
            "errors": [],
            "started_at": datetime.utcnow(),
            "completed_at": None
        }

        try:
            # List all calendars
            calendars = await self.client.list_calendars()
            
            # Get selected calendar IDs from signal settings
            selected_calendar_ids = None
            if self.signal.settings and "calendar_ids" in self.signal.settings:
                selected_calendar_ids = self.signal.settings["calendar_ids"]
                print(f"Using selected calendars from settings: {selected_calendar_ids}")

            # Store the next sync token we'll save at the end
            next_sync_token = None
            calendar_sync_tokens = {}  # Store sync tokens per calendar

            for calendar in calendars:
                calendar_id = calendar["id"]
                
                # If we have selected calendars, only sync those
                if selected_calendar_ids is not None:
                    if calendar_id not in selected_calendar_ids:
                        print(f"Skipping calendar {calendar_id} - not in selected list")
                        continue
                else:
                    # Use the calendar's 'selected' property as fallback
                    if not calendar.get("selected", True):
                        print(f"Skipping unselected calendar {calendar_id}")
                        continue
                
                print(f"Processing calendar: {calendar_id}")
                stats["calendars_synced"] += 1

                # Try incremental sync with token first
                use_sync_token = self.signal.sync_token if hasattr(self.signal, 'sync_token') else None
                fallback_to_time_sync = False

                # Paginate through events
                page_token = None
                while True:
                    try:
                        if use_sync_token and not fallback_to_time_sync:
                            # Try sync token approach
                            try:
                                result = await self.client.list_events(
                                    calendar_id=calendar_id,
                                    sync_token=use_sync_token,
                                    page_token=page_token
                                )
                            except httpx.HTTPStatusError as e:
                                if e.response.status_code == 410:
                                    # Sync token invalid - fall back to time-based sync
                                    print(
                                        f"Sync token expired for calendar {calendar_id}, falling back to time-based sync")
                                    stats["errors"].append({
                                        "calendar_id": calendar_id,
                                        "error": "Sync token expired (410), using time-based sync",
                                        "type": "sync_token_expired"
                                    })
                                    fallback_to_time_sync = True
                                    use_sync_token = None
                                    page_token = None  # Reset pagination
                                    continue  # Retry with time-based sync
                                else:
                                    raise
                        else:
                            # Time-based sync (fallback or no sync token)
                            is_initial_sync = self.signal.last_successful_ingestion_at is None if hasattr(self.signal, 'last_successful_ingestion_at') else True

                            if is_initial_sync:
                                # First sync - get comprehensive historical data
                                time_min = datetime.utcnow() - timedelta(days=365 * self.INITIAL_SYNC_YEARS_PAST)
                                time_max = datetime.utcnow() + timedelta(days=365 * self.INITIAL_SYNC_YEARS_FUTURE)
                                print(
                                    f"Initial sync for calendar {calendar_id}: fetching {self.INITIAL_SYNC_YEARS_PAST} years past to {self.INITIAL_SYNC_YEARS_FUTURE} year future")
                            else:
                                # Incremental fallback (when sync token fails)
                                time_min = self.signal.last_successful_ingestion_at if hasattr(self.signal, 'last_successful_ingestion_at') else datetime.utcnow() - timedelta(days=self.INCREMENTAL_SYNC_DAYS_PAST)
                                time_max = datetime.utcnow() + timedelta(days=self.INCREMENTAL_SYNC_DAYS_FUTURE)

                            result = await self.client.list_events(
                                calendar_id=calendar_id,
                                time_min=time_min,
                                time_max=time_max,
                                page_token=page_token,
                                single_events=True,
                                show_deleted=True  # Include deleted events
                            )

                        events = result.get("items", [])
                        print(
                            f"Calendar {calendar_id}: Found {len(events)} events in this page")

                        # Just count events - they're already collected
                        stats["events_processed"] += len(events)

                        # Log progress for large syncs
                        if stats["events_processed"] > 0 and stats["events_processed"] % 100 == 0:
                            print(
                                f"Progress: Processed {stats['events_processed']} events from calendar {calendar_id}")

                        # Collect all events for this calendar
                        if not hasattr(self, '_all_events'):
                            self._all_events = []
                        
                        for event in events:
                            self._all_events.append({
                                "calendar": {
                                    "id": calendar["id"],
                                    "summary": calendar.get("summary"),
                                    "timeZone": calendar.get("timeZone")
                                },
                                "event": event
                            })
                        
                        # Store the sync token from the last page
                        if "nextSyncToken" in result and not result.get("nextPageToken"):
                            calendar_sync_tokens[calendar_id] = result["nextSyncToken"]
                            print(
                                f"Received sync token for calendar {calendar_id}")

                        # Check for next page
                        page_token = result.get("nextPageToken")
                        if not page_token:
                            print(f"No more pages for calendar {calendar_id}")
                            break

                    except httpx.HTTPStatusError as e:
                        if e.response.status_code == 404:
                            # Calendar not found or no access - skip it
                            print(
                                f"Calendar {calendar_id} not found or no access (404), skipping")
                            stats["errors"].append({
                                "calendar_id": calendar_id,
                                "error": "Calendar not found or no access (404)",
                                "type": "calendar_not_found"
                            })
                            break  # Skip to next calendar
                        else:
                            stats["errors"].append({
                                "calendar_id": calendar_id,
                                "error": str(e),
                                "type": "http_error"
                            })
                            break
                    except Exception as e:
                        stats["errors"].append({
                            "calendar_id": calendar_id,
                            "error": str(e),
                            "type": "general_error"
                        })
                        break

            # Use the sync token from the primary calendar (first non-failed calendar)
            # Prefer the user's main calendar over other calendars like holidays
            for cal_id, token in calendar_sync_tokens.items():
                if "@jaces.com" in cal_id or not next_sync_token:  # Prefer primary calendar
                    next_sync_token = token

            # Store all events as a stream batch
            if hasattr(self, '_all_events') and self._all_events:
                stream_data = {
                    "source": "google_calendar",
                    "user_id": str(self.signal.user_id),
                    "signal_id": str(self.signal.id),
                    "events": self._all_events,
                    "batch_metadata": {
                        "total_events": len(self._all_events),
                        "calendars_synced": stats["calendars_synced"],
                        "sync_type": "incremental" if next_sync_token else "full",
                        "fetched_at": datetime.utcnow().isoformat()
                    }
                }
                
                # Store to stream
                stream_key = await store_raw_data(
                    stream_name="google_calendar_events",
                    connection_id=str(self.signal.id),
                    data=stream_data,
                    timestamp=datetime.utcnow()
                )
                
                # Process the stream immediately
                # In production, this would be queued via Celery
                # For now, just pass - stream processing will be handled separately
                
                stats["stream_key"] = stream_key
            
            stats["completed_at"] = datetime.utcnow()
            stats["next_sync_token"] = next_sync_token
            stats["is_initial_sync"] = self.signal.last_successful_ingestion_at is None if hasattr(self.signal, 'last_successful_ingestion_at') else True

        except Exception as e:
            stats["errors"].append({
                "error": str(e),
                "type": "sync_error"
            })
            raise

        return stats

    async def _process_event(self, event: Dict[str, Any], calendar: Dict[str, Any]) -> None:
        """Add event to batch for stream storage."""
        # Events will be collected and stored as a batch
        # Actual signal processing will happen in the stream processor
        pass  # Events are collected in the main run() method


    async def _persist_signal(self, signal: Dict[str, Any]) -> None:
        """Persist episodic signal to database."""
        async with AsyncSessionLocal() as db:
            # Add user_id and signal_id to the signal
            signal["user_id"] = str(self.signal.user_id)
            signal["signal_id"] = str(self.signal.id)

            # Parse timestamps with robust datetime handling
            from datetime import timezone

            # Parse start timestamp
            start_timestamp_str = signal["start_timestamp"]
            try:
                # Handle 'Z' UTC suffix
                if start_timestamp_str.endswith("Z"):
                    start_timestamp_str = start_timestamp_str[:-1] + "+00:00"

                start_timestamp = datetime.fromisoformat(start_timestamp_str)
                # Ensure we have a timezone-aware datetime
                if start_timestamp.tzinfo is None:
                    start_timestamp = start_timestamp.replace(tzinfo=timezone.utc)
            except Exception as e:
                print(f"Warning: Could not parse start timestamp '{start_timestamp_str}': {e}, using current time")
                start_timestamp = datetime.now(timezone.utc)

            # Parse end timestamp
            end_timestamp_str = signal["end_timestamp"]
            try:
                # Handle 'Z' UTC suffix
                if end_timestamp_str.endswith("Z"):
                    end_timestamp_str = end_timestamp_str[:-1] + "+00:00"

                end_timestamp = datetime.fromisoformat(end_timestamp_str)
                # Ensure we have a timezone-aware datetime
                if end_timestamp.tzinfo is None:
                    end_timestamp = end_timestamp.replace(tzinfo=timezone.utc)
            except Exception as e:
                print(f"Warning: Could not parse end timestamp '{end_timestamp_str}': {e}, using start time")
                end_timestamp = start_timestamp

            # Convert timezone-aware datetimes to naive UTC for database storage
            if start_timestamp.tzinfo is not None:
                start_timestamp = start_timestamp.astimezone(timezone.utc).replace(tzinfo=None)
            if end_timestamp.tzinfo is not None:
                end_timestamp = end_timestamp.astimezone(timezone.utc).replace(tzinfo=None)

            # Create EpisodicSignal object directly from normalized signal
            db_signal = EpisodicSignals(
                id=signal["id"],
                user_id=signal["user_id"],
                signal_id=signal["signal_id"],
                source_name=signal["source_name"],
                start_timestamp=start_timestamp,
                end_timestamp=end_timestamp,
                summary=signal.get("summary", ""),
                # ID arrays - these can be populated later with entity resolution
                what_ids=signal.get("what_ids", []),
                where_ids=signal.get("where_ids", []),
                who_ids=signal.get("who_ids", []),
                when_ids=signal.get("when_ids", []),
                how_ids=signal.get("how_ids", []),
                why_ids=signal.get("why_ids", []),
                target_ids=signal.get("target_ids", []),
                # Text arrays from the normalized signal
                what_text=signal.get("what_text", []),
                where_text=signal.get("where_text", []),
                who_text=signal.get("who_text", []),
                when_text=signal.get("when_text", []),
                how_text=signal.get("how_text", []),
                why_text=signal.get("why_text", []),
                target_text=signal.get("target_text", []),
                confidence=signal["confidence"]
            )

            db.add(db_signal)
            await db.commit()
