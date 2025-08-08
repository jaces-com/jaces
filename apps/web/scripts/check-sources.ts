#!/usr/bin/env tsx
import * as dotenv from 'dotenv';
dotenv.config({ path: '../../.env' });

// Set DATABASE_URL for local development
process.env.DATABASE_URL = 'postgresql://jaces_user:jaces_password@localhost:5432/jaces';

import { db } from '../src/lib/db/client';
import { sources, sourceConfigs } from '../src/lib/db/schema';

async function check() {
  const allSources = await db.select().from(sources);
  console.log('Connected sources:', allSources.length);
  for (const source of allSources) {
    console.log(`- ${source.sourceName}: ${source.instanceName} (scopes: ${source.scopes?.length || 0})`);
  }
  
  console.log('\nAvailable source configs:');
  const configs = await db.select().from(sourceConfigs);
  for (const config of configs) {
    const scopesCount = config.oauthConfig?.requiredScopes?.length || 0;
    console.log(`- ${config.name}: ${scopesCount} required scopes`);
  }
}

check().catch(console.error).then(() => process.exit(0));