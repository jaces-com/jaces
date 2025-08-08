#!/usr/bin/env tsx
import * as dotenv from 'dotenv';
dotenv.config({ path: '../../.env' });

// Set DATABASE_URL for local development
process.env.DATABASE_URL = 'postgresql://jaces_user:jaces_password@localhost:5432/jaces';

import { db } from '../src/lib/db/client';
import { sourceConfigs, streams } from '../src/lib/db/schema';

async function test() {
  console.log('Testing new schema fields...\n');
  
  // Check source configs
  const configs = await db.select().from(sourceConfigs);
  console.log('Source Configs with new fields:');
  configs.forEach(c => {
    console.log(`  ${c.name}:`);
    console.log(`    video: ${c.video}`);
    console.log(`    defaultSyncSchedule: ${c.defaultSyncSchedule}`);
    console.log(`    minSyncFrequency: ${c.minSyncFrequency}`);
    console.log(`    maxSyncFrequency: ${c.maxSyncFrequency}`);
  });
  
  // Check streams table
  const streamRecords = await db.select().from(streams);
  console.log(`\nStreams table has ${streamRecords.length} records`);
  
  console.log('\n✅ Schema test complete!');
}

test().catch(console.error);