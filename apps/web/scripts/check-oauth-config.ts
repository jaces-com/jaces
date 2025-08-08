#!/usr/bin/env tsx
import * as dotenv from 'dotenv';
dotenv.config({ path: '../../.env' });

// Set DATABASE_URL for local development
process.env.DATABASE_URL = 'postgresql://jaces_user:jaces_password@localhost:5432/jaces';

import { db } from '../src/lib/db/client';
import { sourceConfigs } from '../src/lib/db/schema';
import { eq } from 'drizzle-orm';

async function check() {
  const configs = await db.select().from(sourceConfigs).where(eq(sourceConfigs.name, 'google'));
  console.log('Google config from DB:');
  console.log('oauthConfig:', JSON.stringify(configs[0]?.oauthConfig, null, 2));
  
  const notionConfig = await db.select().from(sourceConfigs).where(eq(sourceConfigs.name, 'notion'));
  console.log('\nNotion config from DB:');
  console.log('oauthConfig:', JSON.stringify(notionConfig[0]?.oauthConfig, null, 2));
}

check().catch(console.error).then(() => process.exit(0));