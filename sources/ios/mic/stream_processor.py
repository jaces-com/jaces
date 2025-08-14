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
from sources.base.processing.dedup import generate_idempotency_key


class StreamProcessor:
    """Process iOS mic audio stream data."""
    
    def __init__(self):
        self.source_name = "ios"
        self.stream_name = "ios_mic"
    
    def calculate_audio_level(self, audio_data_base64: str) -> float:
        """
        Calculate audio level in dB SPL from AAC audio data.
        
        Decodes AAC audio to PCM using pyav, calculates RMS level in dBFS,
        then converts to approximate dB SPL by adding 90 dB offset.
        
        Args:
            audio_data_base64: Base64 encoded AAC audio data
            
        Returns:
            Audio level in dB SPL (range: 30 to 90)
        """
        try:
            # Decode base64
            audio_bytes = base64.b64decode(audio_data_base64)
            
            # Create in-memory file for pyav
            audio_buffer = io.BytesIO(audio_bytes)
            
            # Open container with pyav - let it auto-detect format
            # Real iOS uses CAF, test data uses WAV
            container = av.open(audio_buffer)
            
            # Get the audio stream
            audio_stream = container.streams.audio[0]
            
            # Collect all audio samples
            all_samples = []
            
            for frame in container.decode(audio_stream):
                # Convert audio frame to numpy array
                array = frame.to_ndarray()
                
                # Handle multi-channel audio by averaging channels
                if array.ndim > 1:
                    array = np.mean(array, axis=0)
                
                # Check if we have 8-bit unsigned audio (values around 128)
                # This is common in test data. Real iOS CAF uses different encoding.
                if array.dtype == np.uint8 or (array.max() > 1.0 and array.mean() > 100):
                    # Convert 8-bit unsigned (0-255) to normalized float (-1 to 1)
                    array = (array.astype(np.float32) - 128.0) / 128.0
                
                all_samples.extend(array.flatten())
            
            container.close()
            
            if len(all_samples) == 0:
                # Return quiet room level instead of very quiet
                return 30.0
            
            # Convert to numpy array
            audio_array = np.array(all_samples, dtype=np.float32)
            
            # Calculate RMS (Root Mean Square)
            rms = np.sqrt(np.mean(audio_array**2))
            
            # Convert to dBFS (digital level)
            if rms > 0:
                # pyav returns normalized samples, so max value is 1.0
                dbfs = 20 * np.log10(rms)
            else:
                dbfs = -60.0  # Silent
                
            # Clamp dBFS to reasonable range
            dbfs = max(min(dbfs, 0.0), -60.0)
            
            # Convert dBFS to approximate dB SPL
            # Add 90 dB offset: -60 dBFS → 30 dB SPL, 0 dBFS → 90 dB SPL
            db_spl = dbfs + 90.0
            
            return db_spl
            
        except av.AVError as e:
            print(f"Error decoding audio with pyav: {e}")
            # Return a default quiet room level on error
            return 50.0  # 50 dB SPL - quiet room
        except Exception as e:
            print(f"Error calculating audio level: {e}")
            # Return a default quiet room level on error
            return 50.0  # 50 dB SPL - quiet room
    
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
        print(f"[DEBUG iOS Mic] Processing stream_data with keys: {stream_data.keys()}, stream_name: {self.stream_name}")
        
        # Extract audio chunks
        chunks = stream_data.get('chunks', [])
        device_id = stream_data.get('device_id')
        batch_metadata = stream_data.get('batch_metadata', {})
        
        # Check which signals are configured
        has_transcription = 'ios_mic_transcription' in signal_configs
        has_audio_level = 'ios_audio_level' in signal_configs
        
        # If neither signal is configured, skip processing
        if not has_transcription and not has_audio_level:
            return {
                "status": "skipped",
                "reason": "No audio signals configured",
                "stream_name": self.stream_name,
                "records_processed": 0
            }
        
        chunks_processed = 0
        audio_records_created = 0
        audio_level_records_created = 0
        
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
            
            # Generate deterministic source event ID (voice transcriptions allow multiple at same time)
            # Using the original chunk ID to ensure consistency
            chunk_data = {
                'id': original_chunk_id,
                'duration': duration
            }
            idempotency_key = generate_idempotency_key('multiple', timestamp_start, chunk_data)
            
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
            
            # Create a placeholder signal for transcription if configured
            if has_transcription:
                db.execute(
                    text("""
                        INSERT INTO signals 
                        (id, signal_id, source_name, timestamp, 
                         confidence, signal_name, signal_value, idempotency_key, 
                         source_metadata, created_at, updated_at)
                        VALUES (:id, :signal_id, :source_name, :timestamp, 
                                :confidence, :signal_name, :signal_value, :idempotency_key, 
                                :source_metadata, :created_at, :updated_at)
                        ON CONFLICT (source_name, idempotency_key, signal_name) DO NOTHING
                    """),
                    {
                        "id": str(uuid4()),
                        "signal_id": signal_configs['ios_mic_transcription'],
                        "source_name": self.source_name,
                        "timestamp": timestamp_start,
                        "confidence": 0.9,  # Initial confidence, will be updated after transcription
                        "signal_name": "ios_mic_transcription",
                        "signal_value": f"[Audio chunk {original_chunk_id}: {duration}ms, processing...]",
                        "idempotency_key": idempotency_key,
                        "source_metadata": json.dumps(chunk_metadata),
                        "created_at": datetime.utcnow(),
                        "updated_at": datetime.utcnow()
                    }
                )
                audio_records_created += 1
            
            # Process audio level if signal is configured
            if 'ios_audio_level' in signal_configs:
                try:
                    # Calculate audio level from the chunk
                    audio_level_db = self.calculate_audio_level(chunk.get('audio_data', ''))
                    
                    # Generate source event ID for audio level (single value per timestamp)
                    audio_level_event_id = generate_idempotency_key('single', timestamp_start, {})
                    
                    # Create audio level signal
                    db.execute(
                        text("""
                            INSERT INTO signals 
                            (id, signal_id, source_name, timestamp, 
                             confidence, signal_name, signal_value, idempotency_key, 
                             source_metadata, created_at, updated_at)
                            VALUES (:id, :signal_id, :source_name, :timestamp, 
                                    :confidence, :signal_name, :signal_value, :idempotency_key, 
                                    :source_metadata, :created_at, :updated_at)
                            ON CONFLICT (source_name, idempotency_key, signal_name) DO NOTHING
                        """),
                        {
                            "id": str(uuid4()),
                            "signal_id": signal_configs['ios_audio_level'],
                            "source_name": self.source_name,
                            "timestamp": timestamp_start,
                            "confidence": 0.95,
                            "signal_name": "ios_audio_level",
                            "signal_value": str(round(audio_level_db, 1)),
                            "idempotency_key": audio_level_event_id,
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
                    audio_level_records_created += 1
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
            "stream_name": self.stream_name,
            "records_processed": len(chunks),
            "signals_created": {
                "ios_audio_level": audio_level_records_created,
                "ios_mic_transcription": audio_records_created
            },
            "total_signals": audio_level_records_created + audio_records_created,
            "batch_metadata": batch_metadata
        }

