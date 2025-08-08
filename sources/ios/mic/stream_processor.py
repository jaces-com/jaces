"""Stream processor for Apple iOS Mic Audio stream data."""

from datetime import datetime, timezone as tz
from typing import Dict, Any, List
from uuid import uuid4
import json
import base64
import numpy as np
import av
import io
from sqlalchemy import text
from sources.base.processing.dedup import generate_source_event_id


class MicAudioStreamProcessor:
    """Process iOS mic audio stream data."""
    
    def __init__(self):
        self.source_name = "ios"
    
    def calculate_audio_level(self, audio_data_base64: str) -> float:
        """
        Calculate RMS dB level from AAC audio data.
        
        Decodes AAC audio to PCM using pyav, then calculates RMS level.
        
        Args:
            audio_data_base64: Base64 encoded AAC audio data
            
        Returns:
            Audio level in dB (range: -60 to 0)
        """
        try:
            # Decode base64
            audio_bytes = base64.b64decode(audio_data_base64)
            
            # Create in-memory file for pyav
            audio_buffer = io.BytesIO(audio_bytes)
            
            # Open container with pyav
            container = av.open(audio_buffer, format='caf')  # iOS uses CAF container
            
            # Get the audio stream
            audio_stream = container.streams.audio[0]
            
            # Collect all audio samples
            all_samples = []
            
            for frame in container.decode(audio_stream):
                # Convert audio frame to numpy array
                # pyav returns normalized float32 samples
                array = frame.to_ndarray()
                
                # Handle multi-channel audio by averaging channels
                if array.ndim > 1:
                    array = np.mean(array, axis=0)
                
                all_samples.extend(array.flatten())
            
            container.close()
            
            if len(all_samples) == 0:
                return -60.0
            
            # Convert to numpy array
            audio_array = np.array(all_samples, dtype=np.float32)
            
            # Calculate RMS (Root Mean Square)
            rms = np.sqrt(np.mean(audio_array**2))
            
            # Convert to dB
            if rms > 0:
                # pyav returns normalized samples, so max value is 1.0
                db = 20 * np.log10(rms)
            else:
                db = -60.0  # Silent
                
            # Clamp to reasonable range
            return max(min(db, 0.0), -60.0)
            
        except av.AVError as e:
            print(f"Error decoding audio with pyav: {e}")
            # Try alternative format if CAF fails
            try:
                audio_buffer.seek(0)
                container = av.open(audio_buffer)  # Let pyav auto-detect format
                # ... rest of processing (could extract to helper method)
                return -40.0
            except:
                return -40.0
        except Exception as e:
            print(f"Error calculating audio level: {e}")
            # Return a default quiet level on error
            return -40.0
    
    def process(
        self,
        stream_data: Dict[str, Any],
        signal_configs: Dict[str, str],
        db
    ) -> Dict[str, Any]:
        """
        Process mic audio stream data.
        
        This processor primarily handles storing audio chunks and metadata.
        The actual transcription happens asynchronously in a separate task.
        
        Args:
            stream_data: Raw stream data from MinIO
            signal_configs: Mapping of signal names to signal IDs
            db: Database session
            
        Returns:
            Processing result with chunk counts
        """
        # Extract audio chunks
        chunks = stream_data.get('chunks', [])
        device_id = stream_data.get('device_id')
        batch_metadata = stream_data.get('batch_metadata', {})
        
        # Check if we have the signal config
        if 'apple_ios_mic_transcription' not in signal_configs:
            return {
                "status": "skipped",
                "reason": "apple_ios_mic_transcription signal not configured",
                "stream_name": "apple_ios_mic_audio",
                "records_processed": 0
            }
        
        signal_id = signal_configs['apple_ios_mic_transcription']
        chunks_processed = 0
        audio_records_created = 0
        
        # Process each audio chunk
        for chunk in chunks:
            # Use provided chunk ID or generate a UUID
            original_chunk_id = chunk.get('id', str(uuid4()))
            
            # Parse timestamps
            timestamp_start = datetime.fromisoformat(chunk['timestamp_start'].replace('Z', '+00:00'))
            timestamp_end = datetime.fromisoformat(chunk['timestamp_end'].replace('Z', '+00:00'))
            
            if timestamp_start.tzinfo:
                timestamp_start = timestamp_start.astimezone(tz.utc).replace(tzinfo=None)
            if timestamp_end.tzinfo:
                timestamp_end = timestamp_end.astimezone(tz.utc).replace(tzinfo=None)
            
            duration = chunk.get('duration', 0)
            overlap_duration = chunk.get('overlap_duration', 2.0)
            
            # Audio data is already stored in MinIO by the ingestion endpoint
            # Here we just create a reference record for tracking
            
            # Generate deterministic source event ID (voice transcription is parallel type)
            # Using the original chunk ID to ensure consistency
            chunk_data = {
                'id': original_chunk_id,
                'duration': duration
            }
            source_event_id = generate_source_event_id('parallel', timestamp_start, chunk_data)
            
            # Create metadata for the audio chunk
            chunk_metadata = {
                'device_id': device_id,
                'original_chunk_id': original_chunk_id,
                'duration_ms': duration,
                'overlap_duration': overlap_duration,
                'audio_format': chunk.get('audio_format', 'caf'),
                'sample_rate': chunk.get('sample_rate', 16000),
                'batch_info': batch_metadata
            }
            
            # Create a placeholder signal for the audio chunk
            # The actual transcription will be added later
            db.execute(
                text("""
                    INSERT INTO signals 
                    (id, signal_id, source_name, timestamp, 
                     confidence, signal_name, signal_value, source_event_id, 
                     source_metadata, created_at, updated_at)
                    VALUES (:id, :signal_id, :source_name, :timestamp, 
                            :confidence, :signal_name, :signal_value, :source_event_id, 
                            :source_metadata, :created_at, :updated_at)
                    ON CONFLICT (source_name, source_event_id, signal_name) DO NOTHING
                """),
                {
                    "id": str(uuid4()),
                    "signal_id": signal_id,
                    "source_name": self.source_name,
                    "timestamp": timestamp_start,
                    "confidence": 0.9,  # Initial confidence, will be updated after transcription
                    "signal_name": "apple_ios_mic_transcription",
                    "signal_value": f"[Audio chunk {original_chunk_id}: {duration}ms, processing...]",
                    "source_event_id": source_event_id,
                    "source_metadata": json.dumps(chunk_metadata),
                    "created_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow()
                }
            )
            
            audio_records_created += 1
            
            # Process audio level if signal is configured
            if 'apple_ios_audio_level' in signal_configs:
                try:
                    # Calculate audio level from the chunk
                    audio_level_db = self.calculate_audio_level(chunk.get('audio_data', ''))
                    
                    # Generate source event ID for audio level (continuous type, uses timestamp only)
                    audio_level_event_id = generate_source_event_id('continuous', timestamp_start, {})
                    
                    # Create audio level signal
                    db.execute(
                        text("""
                            INSERT INTO signals 
                            (id, signal_id, source_name, timestamp, 
                             confidence, signal_name, signal_value, source_event_id, 
                             source_metadata, created_at, updated_at)
                            VALUES (:id, :signal_id, :source_name, :timestamp, 
                                    :confidence, :signal_name, :signal_value, :source_event_id, 
                                    :source_metadata, :created_at, :updated_at)
                            ON CONFLICT (source_name, source_event_id, signal_name) DO NOTHING
                        """),
                        {
                            "id": str(uuid4()),
                            "signal_id": signal_configs['apple_ios_audio_level'],
                            "source_name": self.source_name,
                            "timestamp": timestamp_start,
                            "confidence": 0.95,
                            "signal_name": "apple_ios_audio_level",
                            "signal_value": str(round(audio_level_db, 1)),
                            "source_event_id": audio_level_event_id,
                            "source_metadata": json.dumps({
                                'device_id': device_id,
                                'chunk_duration_seconds': duration / 1000.0,
                                'calculation_method': 'rms',
                                'audio_format': chunk.get('audio_format', 'caf'),
                                'sample_rate': chunk.get('sample_rate', 16000)
                            }),
                            "created_at": datetime.utcnow(),
                            "updated_at": datetime.utcnow()
                        }
                    )
                except Exception as e:
                    print(f"Failed to process audio level for chunk {original_chunk_id}: {e}")
            
            chunks_processed += 1
            
            # TODO: Queue transcription task for this chunk
            # This would typically queue a Celery task to:
            # 1. Retrieve audio from MinIO
            # 2. Send to transcription service
            # 3. Update the signal with transcribed text
        
        # Commit all records
        db.commit()
        
        return {
            "status": "success",
            "stream_name": "apple_ios_mic_audio",
            "records_processed": len(chunks),
            "chunks_processed": chunks_processed,
            "audio_records_created": audio_records_created,
            "note": "Audio chunks stored, transcription pending"
        }

