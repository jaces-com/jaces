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
  
  // Load registry - use mounted path in Docker or local path
  const registryPath = fs.existsSync('/app/sources/_generated_registry.yaml') 
    ? '/app/sources/_generated_registry.yaml'
    : path.join(rootDir, 'sources/_generated_registry.yaml');
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
    
    if (existing.length === 0) {
      // Use full computation config from registry
      const computation = signalData.computation || {
        algorithm: signalData.algorithm || 'pelt',
        cost_function: signalData.cost_function || 'l2',
        value_type: signalData.value_type || 'continuous',
      };
      
      // Extract weights
      const macroWeight = signalData.weight?.macro || 0.5;
      const minTransitionGap = signalData.transitions?.min_gap_seconds || 300;
      
      await db.insert(signalConfigs).values({
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
      });
      console.log(`✅ Created signal config: ${signalName}`);
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
    status: 'paused' as const,  // Paused to prevent sync attempts
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
    status: 'paused' as const,  // Paused to prevent sync attempts with fake tokens
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
      
      // Get the stream ID for ios_location
      const [streamConfig] = await db
        .select()
        .from(streamConfigs)
        .where(eq(streamConfigs.streamName, 'ios_location'))
        .limit(1);
      
      // Queue processing task to create signals
      const { queueCeleryTask } = await import('../src/lib/redis');
      const taskId = await queueCeleryTask('process_stream_batch', [
        'ios_location',
        streamKey,
        'seed-activity-002', // Dummy pipeline activity ID for seeding
        streamConfig?.id || 'seed-stream-002'  // Use actual stream ID or dummy
      ]);
      
      console.log(`  📋 Queued iOS location processing task: ${taskId}`);
    }
  } catch (error) {
    console.log(`  ❌ iOS Location error:`, error);
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
      
      // Get the stream ID for google_calendar
      const [streamConfig] = await db
        .select()
        .from(streamConfigs)
        .where(eq(streamConfigs.streamName, 'google_calendar'))
        .limit(1);
      
      // Queue processing task to create signals
      const { queueCeleryTask } = await import('../src/lib/redis');
      const taskId = await queueCeleryTask('process_stream_batch', [
        'google_calendar',
        streamKey,
        'seed-activity-001', // Dummy pipeline activity ID for seeding
        streamConfig?.id || 'seed-stream-001'  // Use actual stream ID or dummy
      ]);
      
      console.log(`  📋 Queued Google Calendar processing task: ${taskId}`);
    }
  } catch (error) {
    console.log(`  ❌ Google Calendar error:`, error);
  }
  
  console.log('\n✨ Test data seeding complete!');
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