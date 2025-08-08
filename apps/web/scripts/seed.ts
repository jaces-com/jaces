#!/usr/bin/env tsx
import * as dotenv from 'dotenv';
import * as path from 'path';
import { fileURLToPath } from 'url';
import * as yaml from 'js-yaml';
import * as fs from 'fs';

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
  
  // No user creation needed for single-user app
  console.log('ℹ️  Single-user app - skipping user creation');

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
      
      // Map video files based on source name
      const videoMap: Record<string, string> = {
        google: 'google2.webm',
        ios: 'ios.webm',
        mac: 'mac2.webm',
        notion: 'notion.webm'
      };
      
      // Get OAuth proxy URL from the registry
      const authProxyUrl = sourceData.oauth?.auth_proxy;
      
      const configData = {
        name: sourceName,
        company: sourceData.company,
        platform: sourceData.platform || 'cloud',
        deviceType: sourceName === 'ios' ? 'ios' : 
                    sourceName === 'mac' ? 'macos' : undefined,
        displayName: sourceData.display_name,
        description: sourceData.description,
        icon: sourceData.icon,
        video: sourceData.video || videoMap[sourceName as string] || null,
        authType: sourceData.auth?.type || (sourceData.platform === 'device' ? 'device_token' : 'oauth2'),
        defaultSyncSchedule: sourceData.sync?.default_schedule || '0 * * * *', // Default hourly
        minSyncFrequency: sourceData.sync?.min_frequency || 300, // 5 minutes
        maxSyncFrequency: sourceData.sync?.max_frequency || 86400, // 24 hours
        oauthConfig: {
          authProxy: authProxyUrl,
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
      // Use ingestion type from registry or infer from source
      const ingestionType = streamData.ingestion?.type || 
                           (streamData.source === 'ios' || streamData.source === 'mac' ? 'push' : 'pull');
      
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
  } else {
    // Fallback for old registry format - infer semantics from streams
    const semanticStreams = Object.entries(registry.streams).filter(([streamName, streamData]) => {
      return streamData.output_type === 'semantics' || 
             (streamData.signals?.length === 0 && streamData.semantics?.length > 0);
    });
    
    for (const [streamName, streamData] of semanticStreams) {
      const semanticTypes = streamData.semantics || [];
      for (const semanticType of semanticTypes) {
        const semanticName = `${streamName}_${semanticType}`;
        const existing = await db
          .select()
          .from(semanticConfigs)
          .where(eq(semanticConfigs.semanticName, semanticName))
          .limit(1);
        
        if (existing.length === 0) {
          await db.insert(semanticConfigs).values({
            semanticName: semanticName,
            displayName: `${streamData.display_name} - ${semanticType}`,
            sourceName: streamData.source,
            streamName: streamName,
            semanticType: semanticType,
            status: 'active',
            description: streamData.description,
            settings: {
              sync: streamData.sync,
              processing: streamData.processing,
              storage: streamData.storage,
            },
          });
          console.log(`✅ Created semantic config: ${semanticName}`);
        }
      }
    }
  }

  console.log('✅ Database seeding complete!');
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