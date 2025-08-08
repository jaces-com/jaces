#!/usr/bin/env tsx
import * as dotenv from 'dotenv';
dotenv.config({ path: '../../.env' });

// Set DATABASE_URL for local development
process.env.DATABASE_URL = 'postgresql://jaces_user:jaces_password@localhost:5432/jaces';

import { db } from '../src/lib/db/client';
import { sourceConfigs } from '../src/lib/db/schema';
import { eq } from 'drizzle-orm';

async function test() {
  const [googleConfig] = await db.select().from(sourceConfigs).where(eq(sourceConfigs.name, 'google'));
  
  const oauthConfig = googleConfig.oauthConfig as any || {};
  const authProxyUrl = oauthConfig.authProxy;
  const returnUrl = 'http://localhost:3000/oauth/callback';
  const state = '/data/sources/new';
  
  const oauthUrl = `${authProxyUrl}?return_url=${encodeURIComponent(returnUrl)}&state=${encodeURIComponent(state)}`;
  
  console.log('Generated OAuth URL:');
  console.log(oauthUrl);
  console.log('\nDecoded:');
  console.log('- Auth Proxy:', authProxyUrl);
  console.log('- Return URL:', returnUrl);
  console.log('- State:', state);
}

test().catch(console.error).then(() => process.exit(0));