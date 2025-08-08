#!/usr/bin/env tsx
import * as dotenv from 'dotenv';
dotenv.config({ path: '../../.env' });

// Set DATABASE_URL for local development
process.env.DATABASE_URL = 'postgresql://jaces_user:jaces_password@localhost:5432/jaces';

import { db } from '../src/lib/db/client';
import { sourceConfigs } from '../src/lib/db/schema';
import { inArray } from 'drizzle-orm';

async function check() {
  const configs = await db.select().from(sourceConfigs).where(inArray(sourceConfigs.name, ['google', 'notion']));
  configs.forEach(c => {
    console.log(`${c.name}:`);
    console.log('  authType:', c.authType);
    console.log('  oauthConfig:', JSON.stringify(c.oauthConfig, null, 2));
  });
}

check().catch(console.error).then(() => process.exit(0));