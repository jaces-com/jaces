#!/usr/bin/env tsx
import * as dotenv from 'dotenv';
import * as path from 'path';
import { fileURLToPath } from 'url';
import * as yaml from 'js-yaml';
import * as fs from 'fs';
import * as crypto from 'crypto';

// Make crypto globally available for MinIO
if (typeof globalThis.crypto === 'undefined') {
	globalThis.crypto = crypto as any;
}

// Load environment variables BEFORE importing db client
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const rootDir = path.resolve(__dirname, '../../..');
dotenv.config({ path: path.join(rootDir, '.env') });

// Set DATABASE_URL to use localhost for local development
if (!process.env.DATABASE_URL) {
  process.env.DATABASE_URL = 'postgresql://jaces_user:jaces_password@localhost:5432/jaces';
}

import { db } from '../src/lib/db/client';
import { sourceConfigs, streamConfigs, signalConfigs, semanticConfigs } from '../src/lib/db/schema';
import { eq } from 'drizzle-orm';

async function seedDatabase() {
  console.log('🌱 Seeding development database...');
  
  // Load registry from sources directory (mounted at /sources in Docker)
  const registryPath = fs.existsSync('/sources/_generated_registry.yaml') 
    ? '/sources/_generated_registry.yaml'
    : path.join(rootDir, 'sources', '_generated_registry.yaml');
  const registryContent = fs.readFileSync(registryPath, 'utf-8');
  const registry = yaml.load(registryContent) as any;
  
  // Create default user for single-user app
  console.log('👤 Creating default user...');
  const { users } = await import('../src/lib/db/schema');
  
  // Check if user already exists
  const existingUser = await db
    .select()
    .from(users)
    .where(eq(users.email, 'user@jaces.app'))
    .limit(1);
  
  if (existingUser.length === 0) {
    await db.insert(users).values({
      firstName: 'Default',
      lastName: 'User',
      email: 'user@jaces.app',
      timezone: 'America/Chicago'
    });
    console.log('  ✅ Created default user');
  } else {
    console.log('  ℹ️  Default user already exists');
  }

  // Seed source configs
  for (const [sourceName, sourceData] of Object.entries(registry.sources)) {
    const existing = await db
      .select()
      .from(sourceConfigs)
      .where(eq(sourceConfigs.name, sourceName))
      .limit(1);
    
    // Always update or insert to ensure latest config
    if (true) { // Changed from: if (existing.length === 0)
      // Collect all required scopes from streams_config
      const streamScopes: string[] = [];
      const streamsConfig = (sourceData as any).streams_config;
      if (streamsConfig && Array.isArray(streamsConfig)) {
        for (const streamConfig of streamsConfig) {
          if (streamConfig.required_scopes && Array.isArray(streamConfig.required_scopes)) {
            streamScopes.push(...streamConfig.required_scopes);
          }
        }
      }
      
      const configData = {
        name: sourceName,
        company: sourceData.company,
        platform: sourceData.platform || 'cloud',
        deviceType: sourceData.device_type || undefined,
        displayName: sourceData.display_name,
        description: sourceData.description,
        icon: sourceData.icon,
        video: sourceData.video || null,
        authType: sourceData.auth?.type || 'oauth2',
        defaultSyncSchedule: sourceData.sync?.default_schedule || '0 * * * *', // Default hourly
        minSyncFrequency: sourceData.sync?.min_frequency || 300, // 5 minutes
        maxSyncFrequency: sourceData.sync?.max_frequency || 86400, // 24 hours
        oauthConfig: {
          authProxy: sourceData.auth?.auth_proxy,
          requiredScopes: [...new Set(streamScopes)] // Deduplicate scopes
        },
        syncConfig: sourceData.sync,
      };
      
      if (existing.length > 0) {
        // Update existing config
        await db.update(sourceConfigs)
          .set(configData)
          .where(eq(sourceConfigs.name, sourceName));
        console.log(`✅ Updated source config: ${sourceName}`);
      } else {
        // Insert new config
        await db.insert(sourceConfigs).values(configData);
        console.log(`✅ Created source config: ${sourceName}`);
      }
    }
  }

  // Seed stream configs
  for (const [streamName, streamData] of Object.entries(registry.streams)) {
    const existing = await db
      .select()
      .from(streamConfigs)
      .where(eq(streamConfigs.streamName, streamName))
      .limit(1);
    
    if (existing.length === 0) {
      // Use ingestion type from registry data
      const ingestionType = streamData.ingestion?.type || 'pull';
      
      // Extract cron schedule from sync config if available
      const cronSchedule = streamData.sync?.schedule || 
                          (ingestionType === 'pull' ? '0 */6 * * *' : null);
      
      await db.insert(streamConfigs).values({
        streamName: streamName,
        sourceName: streamData.source,
        displayName: streamData.display_name,
        description: streamData.description,
        ingestionType: ingestionType,
        status: 'active',
        cronSchedule: cronSchedule,
        settings: {
          ingestion: streamData.ingestion,
          sync: streamData.sync,
          processing: streamData.processing,
          storage: streamData.storage,
          output_type: streamData.output_type,
        },
      });
      console.log(`✅ Created stream config: ${streamName}`);
    }
  }

  // Seed signal configs
  for (const [signalName, signalData] of Object.entries(registry.signals)) {
    const existing = await db
      .select()
      .from(signalConfigs)
      .where(eq(signalConfigs.signalName, signalName))
      .limit(1);
    
    // Use full computation config from registry
    const computation = signalData.computation || {
      algorithm: signalData.algorithm || 'pelt',
      cost_function: signalData.cost_function || 'l2',
      value_type: signalData.value_type || 'continuous',
    };
    
    // Extract weights
    const macroWeight = signalData.weight?.macro || 0.5;
    const minTransitionGap = signalData.transitions?.min_gap_seconds || 300;
    
    const signalConfigData = {
      signalName: signalName,
      displayName: signalData.display_name,
      unitUcum: signalData.unit?.ucum?.toString() || '',
      computation: computation,
      fidelityScore: 1.0,
      macroWeight: macroWeight,
      minTransitionGap: minTransitionGap,
      sourceName: signalData.source,
      streamName: signalData.stream,
      description: signalData.description,
      settings: {
        unit: signalData.unit,
        weight: signalData.weight,
        transitions: signalData.transitions,
        zones: signalData.zones,
        metadata: signalData.metadata,
        schedule: signalData.schedule,
      },
    };
    
    if (existing.length === 0) {
      await db.insert(signalConfigs).values(signalConfigData);
      console.log(`✅ Created signal config: ${signalName}`);
    } else {
      // Update existing signal config to ensure it has latest computation config
      await db.update(signalConfigs)
        .set(signalConfigData)
        .where(eq(signalConfigs.signalName, signalName));
      console.log(`✅ Updated signal config: ${signalName}`);
    }
  }

  // Seed semantic configs
  if (registry.semantics) {
    for (const [semanticName, semanticData] of Object.entries(registry.semantics)) {
      const existing = await db
        .select()
        .from(semanticConfigs)
        .where(eq(semanticConfigs.semanticName, semanticName))
        .limit(1);
      
      if (existing.length === 0) {
        await db.insert(semanticConfigs).values({
          semanticName: semanticName,
          displayName: semanticData.display_name,
          sourceName: semanticData.source,
          streamName: semanticData.stream,
          semanticType: semanticData.semantic_type,
          status: 'active',
          description: semanticData.description,
          settings: {
            syncConfig: semanticData.sync_config,
            processingConfig: semanticData.processing_config,
            storageConfig: semanticData.storage_config,
          },
        });
        console.log(`✅ Created semantic config: ${semanticName}`);
      }
    }
  } 

  // Create test source instances for development
  console.log('🧪 Creating test source instances...');
  
  // Import sources table
  const { sources } = await import('../src/lib/db/schema');
  
  // Create test iOS device for development
  const testIosDevice = {
    id: '00000000-0000-0000-0000-000000000101',
    sourceName: 'ios',
    instanceName: "Test iPhone (Demo)",
    status: 'active' as const,  // Set to active for transition detection to work
    deviceId: 'dev_iphone_001',
    deviceToken: 'DEV_TOKEN_001',
    deviceType: 'ios' as const,
    deviceLastSeen: new Date(),
    sourceMetadata: {
      os_version: '17.0',
      model: 'iPhone 15 Pro',
      app_version: '1.0.0',
      isTest: true  // Mark as test source
    }
  };
  
  const existingIos = await db
    .select()
    .from(sources)
    .where(eq(sources.deviceId, 'dev_iphone_001'))
    .limit(1);
  
  if (existingIos.length === 0) {
    await db.insert(sources).values(testIosDevice);
    console.log('  ✅ Created test iOS device');
  } else {
    console.log('  ℹ️  Test iOS device already exists');
  }
  
  // Create test Google Calendar source
  const testGoogleSource = {
    id: '00000000-0000-0000-0000-000000000102',
    sourceName: 'google',
    instanceName: "Test Google Account (Demo)",
    status: 'active' as const,  // Set to active for transition detection to work
    deviceId: 'test_google_account',
    oauthAccessToken: 'test_access_token_google',
    oauthRefreshToken: 'test_refresh_token_google',
    oauthExpiresAt: new Date(Date.now() + 3600000), // 1 hour from now
    scopes: [
      'https://www.googleapis.com/auth/calendar.readonly',
      'https://www.googleapis.com/auth/calendar.events.readonly'
    ],
    sourceMetadata: {
      email: 'testuser@example.com',
      name: 'Test User',
      isTest: true  // Mark as test source
    }
  };
  
  const existingGoogle = await db
    .select()
    .from(sources)
    .where(eq(sources.deviceId, 'test_google_account'))
    .limit(1);
  
  if (existingGoogle.length === 0) {
    await db.insert(sources).values(testGoogleSource);
    console.log('  ✅ Created test Google source');
  } else {
    console.log('  ℹ️  Test Google source already exists');
  }
  
  // Create stream instances for test sources
  console.log('📊 Creating stream instances for test sources...');
  const { streams } = await import('../src/lib/db/schema');
  
  // Create iOS location stream
  const [iosLocationConfig] = await db
    .select()
    .from(streamConfigs)
    .where(eq(streamConfigs.streamName, 'ios_location'))
    .limit(1);
  
  if (iosLocationConfig) {
    const existingLocationStream = await db
      .select()
      .from(streams)
      .where(eq(streams.sourceId, testIosDevice.id))
      .where(eq(streams.streamConfigId, iosLocationConfig.id))
      .limit(1);
    
    if (existingLocationStream.length === 0) {
      await db.insert(streams).values({
        sourceId: testIosDevice.id,
        streamConfigId: iosLocationConfig.id,
        enabled: true,
        enabledSignals: null // null means all signals enabled
      });
      console.log('  ✅ Created iOS location stream');
    }
  }
  
  // Create iOS mic stream with disabled transcription
  const [iosMicConfig] = await db
    .select()
    .from(streamConfigs)
    .where(eq(streamConfigs.streamName, 'ios_mic'))
    .limit(1);
  
  if (iosMicConfig) {
    const existingMicStream = await db
      .select()
      .from(streams)
      .where(eq(streams.sourceId, testIosDevice.id))
      .where(eq(streams.streamConfigId, iosMicConfig.id))
      .limit(1);
    
    if (existingMicStream.length === 0) {
      await db.insert(streams).values({
        sourceId: testIosDevice.id,
        streamConfigId: iosMicConfig.id,
        enabled: true,
        enabledSignals: ['ios_audio_level'] // Only enable audio level, not transcription
      });
      console.log('  ✅ Created iOS mic stream (transcription disabled)');
    }
  }
  
  // Create Google Calendar stream
  const [googleCalendarConfig] = await db
    .select()
    .from(streamConfigs)
    .where(eq(streamConfigs.streamName, 'google_calendar'))
    .limit(1);
  
  if (googleCalendarConfig) {
    const existingCalendarStream = await db
      .select()
      .from(streams)
      .where(eq(streams.sourceId, testGoogleSource.id))
      .where(eq(streams.streamConfigId, googleCalendarConfig.id))
      .limit(1);
    
    if (existingCalendarStream.length === 0) {
      await db.insert(streams).values({
        sourceId: testGoogleSource.id,
        streamConfigId: googleCalendarConfig.id,
        enabled: true,
        enabledSignals: null // null means all signals enabled
      });
      console.log('  ✅ Created Google Calendar stream');
    }
  }
  
  console.log('✅ Database seeding complete!');
  
  // Seed test data via ingest endpoint
  await seedTestData();
}

async function seedTestData() {
  console.log('\n📤 Seeding test data via ingest endpoint...');
  
  const testDir = fs.existsSync('/app/tests') ? '/app/tests' : path.join(rootDir, 'tests');
  const baseUrl = process.env.FRONTEND_URL || 'http://localhost:3000';
  
  // Seed iOS Location data directly to MinIO
  try {
    const iosLocationFile = path.join(testDir, 'test_data_ios_location.json');
    if (fs.existsSync(iosLocationFile)) {
      const testData = JSON.parse(fs.readFileSync(iosLocationFile, 'utf-8'));
      
      // Set MinIO endpoint for local access
      if (!process.env.MINIO_ENDPOINT) {
        process.env.MINIO_ENDPOINT = 'localhost:9000';
      }
      
      // Store directly to MinIO via the MinIO client library
      const { storeStreamData } = await import('../src/lib/minio');
      
      // Create a proper stream data format
      const streamData = {
        stream_name: 'ios_location',
        source_name: 'ios',
        device_id: 'dev_iphone_001',
        data: testData.data,
        batch_metadata: {
          total_points: testData.data.length,
          date: '2025-07-01',
          start_time: testData.data[0].timestamp,
          end_time: testData.data[testData.data.length - 1].timestamp
        },
        timestamp: new Date().toISOString()
      };
      
      // Store to MinIO
      const { key: streamKey, sizeBytes } = await storeStreamData(
        'ios_location',
        streamData,
        {
          'x-source-id': '00000000-0000-0000-0000-000000000101', // Use the test iOS device ID
          'x-stream-name': 'ios_location',
          'x-device-id': 'dev_iphone_001'
        }
      );
      
      console.log(`  ✅ iOS Location: Stored ${testData.data.length} location points to MinIO (${formatBytes(sizeBytes)})`);
      
      // Get the actual stream record for ios_location
      const { streams } = await import('../src/lib/db/schema');
      
      // First get the stream_config_id for ios_location
      const [iosLocationConfig] = await db
        .select()
        .from(streamConfigs)
        .where(eq(streamConfigs.streamName, 'ios_location'))
        .limit(1);
      
      if (iosLocationConfig) {
        // Now get the stream using both source_id and stream_config_id
        const [iosLocationStream] = await db
          .select()
          .from(streams)
          .where(eq(streams.sourceId, '00000000-0000-0000-0000-000000000101'))
          .where(eq(streams.streamConfigId, iosLocationConfig.id))
          .limit(1);
        
        if (iosLocationStream) {
          console.log(`  🔍 Found iOS location stream with ID: ${iosLocationStream.id}`);
          // Queue processing task to create signals
          const { queueCeleryTask } = await import('../src/lib/redis');
          const taskId = await queueCeleryTask('process_stream_batch', [
            'ios_location',
            streamKey,
            'seed-activity-002', // Dummy pipeline activity ID for seeding
            iosLocationStream.id  // Use the stream ID directly
          ]);
          console.log(`  📋 Queued iOS location processing task: ${taskId}`);
        } else {
          console.log('  ⚠️  iOS location stream not found, skipping processing');
        }
      } else {
        console.log('  ⚠️  iOS location stream config not found');
      }
    }
  } catch (error) {
    console.log(`  ❌ iOS Location error:`, error);
  }
  
  // Seed iOS Audio data directly to MinIO
  try {
    const iosAudioFile = path.join(testDir, 'test_data_ios_audio.json.gz');
    const iosAudioFileUncompressed = path.join(testDir, 'test_data_ios_audio.json');
    
    // Try compressed first, fallback to uncompressed
    let testData;
    if (fs.existsSync(iosAudioFile)) {
      const zlib = await import('zlib');
      const gunzip = zlib.gunzipSync;
      const compressedData = fs.readFileSync(iosAudioFile);
      testData = JSON.parse(gunzip(compressedData).toString());
    } else if (fs.existsSync(iosAudioFileUncompressed)) {
      testData = JSON.parse(fs.readFileSync(iosAudioFileUncompressed, 'utf-8'));
    }
    
    if (testData) {
      // Set MinIO endpoint for local access
      if (!process.env.MINIO_ENDPOINT) {
        process.env.MINIO_ENDPOINT = 'localhost:9000';
      }
      
      // Store directly to MinIO via the MinIO client library
      const { storeStreamData } = await import('../src/lib/minio');
      
      // Create a proper stream data format matching the iOS mic structure
      const streamData = {
        stream_name: 'ios_mic',
        source_name: 'ios',
        device_id: testData.device_id,
        chunks: testData.data, // iOS mic uses 'chunks' not 'data'
        batch_metadata: testData.batch_metadata,
        pipeline_activity_id: testData.pipeline_activity_id,
        timestamp: testData.timestamp
      };
      
      // Store to MinIO
      const { key: streamKey, sizeBytes } = await storeStreamData(
        'ios_mic',
        streamData,
        {
          'x-source-id': '00000000-0000-0000-0000-000000000101', // Use the test iOS device ID
          'x-stream-name': 'ios_mic',
          'x-device-id': testData.device_id
        }
      );
      
      console.log(`  ✅ iOS Audio: Stored ${testData.data.length} audio chunks to MinIO (${formatBytes(sizeBytes)})`);
      
      // Get the actual stream record for ios_mic
      const { streams } = await import('../src/lib/db/schema');
      
      // First get the stream_config_id for ios_mic
      const [iosMicConfig] = await db
        .select()
        .from(streamConfigs)
        .where(eq(streamConfigs.streamName, 'ios_mic'))
        .limit(1);
      
      if (iosMicConfig) {
        // Now get the stream using both source_id and stream_config_id
        const [iosMicStream] = await db
          .select()
          .from(streams)
          .where(eq(streams.sourceId, '00000000-0000-0000-0000-000000000101'))
          .where(eq(streams.streamConfigId, iosMicConfig.id))
          .limit(1);
        
        if (iosMicStream) {
          console.log(`  🔍 Found iOS mic stream with ID: ${iosMicStream.id}`);
          // Queue processing task to create signals
          const { queueCeleryTask } = await import('../src/lib/redis');
          const taskId = await queueCeleryTask('process_stream_batch', [
            'ios_mic',
            streamKey,
            testData.pipeline_activity_id || 'seed-activity-003', // Use actual pipeline ID or dummy
            iosMicStream.id  // Use the stream ID directly
          ]);
          console.log(`  📋 Queued iOS audio processing task: ${taskId}`);
        } else {
          console.log('  ⚠️  iOS mic stream not found, skipping processing');
        }
      } else {
        console.log('  ⚠️  iOS mic stream config not found');
      }
    }
  } catch (error) {
    console.log(`  ❌ iOS Audio error:`, error);
  }
  
  // Seed Google Calendar data directly to MinIO
  try {
    const googleCalendarFile = path.join(testDir, 'test_data_google_calendar.json');
    if (fs.existsSync(googleCalendarFile)) {
      const testData = JSON.parse(fs.readFileSync(googleCalendarFile, 'utf-8'));
      
      // Set MinIO endpoint for local access
      if (!process.env.MINIO_ENDPOINT) {
        process.env.MINIO_ENDPOINT = 'localhost:9000';
      }
      
      // Store directly to MinIO via the MinIO client library
      const { storeStreamData } = await import('../src/lib/minio');
      
      // Create a proper stream data format
      const streamData = {
        stream_name: 'google_calendar',
        source_name: 'google',
        events: testData.events,
        batch_metadata: {
          total_records: testData.events.length,
          date: '2025-07-01',
          sync_type: 'full'
        },
        timestamp: new Date().toISOString()
      };
      
      // Store to MinIO
      const { key: streamKey, sizeBytes } = await storeStreamData(
        'google_calendar',
        streamData,
        {
          'x-source-id': '00000000-0000-0000-0000-000000000102', // Use the test Google source ID
          'x-stream-name': 'google_calendar'
        }
      );
      
      console.log(`  ✅ Google Calendar: Stored ${testData.events.length} events to MinIO (${formatBytes(sizeBytes)})`);
      
      // Get the actual stream record for google_calendar
      const { streams } = await import('../src/lib/db/schema');
      
      // First get the stream_config_id for google_calendar
      const [googleCalendarConfig] = await db
        .select()
        .from(streamConfigs)
        .where(eq(streamConfigs.streamName, 'google_calendar'))
        .limit(1);
      
      if (googleCalendarConfig) {
        // Now get the stream using both source_id and stream_config_id
        const [googleCalendarStream] = await db
          .select()
          .from(streams)
          .where(eq(streams.sourceId, '00000000-0000-0000-0000-000000000102'))
          .where(eq(streams.streamConfigId, googleCalendarConfig.id))
          .limit(1);
        
        if (googleCalendarStream) {
          console.log(`  🔍 Found Google Calendar stream with ID: ${googleCalendarStream.id}`);
          // Queue processing task to create signals
          const { queueCeleryTask } = await import('../src/lib/redis');
          const taskId = await queueCeleryTask('process_stream_batch', [
            'google_calendar',
            streamKey,
            'seed-activity-001', // Dummy pipeline activity ID for seeding
            googleCalendarStream.id  // Use the stream ID directly
          ]);
          console.log(`  📋 Queued Google Calendar processing task: ${taskId}`);
        } else {
          console.log('  ⚠️  Google Calendar stream not found, skipping processing');
        }
      } else {
        console.log('  ⚠️  Google Calendar stream config not found');
      }
    }
  } catch (error) {
    console.log(`  ❌ Google Calendar error:`, error);
  }
  
  console.log('\n✨ Test data seeding complete!');
  
  // Wait for stream processing to complete before triggering transition detection
  console.log('\n⏳ Waiting for stream processing to complete (20 seconds)...');
  await new Promise(resolve => setTimeout(resolve, 20000)); // Wait 20 seconds
  
  // Queue transition detection task directly via Celery for the test data date (July 1st, 2025)
  console.log('🔍 Triggering transition detection for July 1st test data...');
  try {
    const { queueCeleryTask } = await import('../src/lib/redis');
    
    // Queue the transition detection task with proper parameters
    const transitionTaskId = await queueCeleryTask('start_transition_detection', [
      '2025-07-01',    // date
      'manual',        // run_type
      null,            // custom_start_time
      null,            // custom_end_time
      'America/Chicago' // timezone (using default)
    ]);
    
    console.log(`  ✅ Transition detection task queued successfully: ${transitionTaskId}`);
    console.log(`  📊 Task will process signals from July 1st, 2025`);
    
    // Wait for transition detection to complete before running HDBSCAN
    console.log('\n⏳ Waiting for transition detection to complete (15 seconds)...');
    await new Promise(resolve => setTimeout(resolve, 15000)); // Wait 15 seconds
    
    // Queue HDBSCAN event generation for the test data day in Central Time
    // Test data runs from July 1 00:00 to 23:38 Central Time (spans two UTC days)
    console.log('\n🎯 Triggering HDBSCAN event detection for test data (July 1 Central Time)...');
    
    // Process July 1 in Central Time (which spans two UTC days)
    const eventTaskId = await queueCeleryTask('generate_events_hdbscan', 
      ['2025-07-01'],  // positional args: just the date
      {                // kwargs including timezone
        timezone: 'America/Chicago',
        min_cluster_size: null,
        epsilon: null,
        target_min_events: 8,
        target_max_events: 24
      }
    );
    console.log(`  ✅ July 1 Central Time event detection queued: ${eventTaskId}`);
    
    console.log(`  🎯 Target: 8-24 events for the full Central Time day`);
    console.log(`  📊 Algorithm will auto-tune parameters to achieve target`);
    console.log(`  ⏱️  Check Celery logs for event detection results`);
    
  } catch (error) {
    console.error('  ❌ Failed to queue detection tasks:', error);
    console.log('  ℹ️  You can manually trigger detection later using:');
    console.log('      docker compose exec scheduler celery -A sources.base.scheduler.celery_app call start_transition_detection');
    console.log('      docker compose exec scheduler celery -A sources.base.scheduler.celery_app call generate_events_hdbscan');
  }
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 Bytes';
  const k = 1024;
  const sizes = ['Bytes', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

async function main() {
  try {
    await seedDatabase();
    process.exit(0);
  } catch (error) {
    console.error('❌ Seeding failed:', error);
    process.exit(1);
  }
}

main();