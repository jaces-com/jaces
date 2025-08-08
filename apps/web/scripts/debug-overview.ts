#!/usr/bin/env tsx
import { db } from '../src/lib/db/client';
import { signalConfigs, streamConfigs, semanticConfigs } from '../src/lib/db/schema';

async function debugOverview() {
  console.log('\n📊 Debugging Overview Data...\n');
  
  // Check Mac signals
  const macSignals = await db
    .select()
    .from(signalConfigs)
    .where(eq(signalConfigs.sourceName, 'mac'));
  
  console.log('Mac signals:');
  macSignals.forEach(s => {
    console.log(`  - Signal: ${s.signalName}, Display: ${s.displayName}, Stream: ${s.streamName}`);
  });
  
  // Check Mac streams
  const macStreams = await db
    .select()
    .from(streamConfigs)
    .where(eq(streamConfigs.sourceName, 'mac'));
  
  console.log('\nMac streams:');
  macStreams.forEach(s => {
    console.log(`  - Stream: ${s.streamName}, Display: ${s.displayName}, Source: ${s.sourceName}`);
  });
  
  // Check Google signals
  const googleSignals = await db
    .select()
    .from(signalConfigs)
    .where(eq(signalConfigs.sourceName, 'google'));
  
  console.log('\nGoogle signals:');
  googleSignals.forEach(s => {
    console.log(`  - Signal: ${s.signalName}, Display: ${s.displayName}, Stream: ${s.streamName}`);
  });
  
  // Check Google streams
  const googleStreams = await db
    .select()
    .from(streamConfigs)
    .where(eq(streamConfigs.sourceName, 'google'));
  
  console.log('\nGoogle streams:');
  googleStreams.forEach(s => {
    console.log(`  - Stream: ${s.streamName}, Display: ${s.displayName}`);
  });
  
  // Check Notion semantics
  const notionSemantics = await db
    .select()
    .from(semanticConfigs)
    .where(eq(semanticConfigs.sourceName, 'notion'));
  
  console.log('\nNotion semantics:');
  notionSemantics.forEach(s => {
    console.log(`  - Semantic: ${s.semanticName}, Display: ${s.displayName}, Stream: ${s.streamName}`);
  });
  
  process.exit(0);
}

import { eq } from 'drizzle-orm';

debugOverview().catch(console.error);