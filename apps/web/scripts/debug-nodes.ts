#!/usr/bin/env tsx
import { load } from '../src/routes/data/overview/+page.server';

async function debugNodes() {
  // Silence console logs
  const originalLog = console.log;
  console.log = () => {};
  
  const result = await load({} as any);
  
  // Restore console.log
  console.log = originalLog;
  
  console.log('\n📊 Node Display Debug:\n');
  
  // Check Mac related nodes
  console.log('Mac Source:');
  const macSource = result.diagramData?.sources?.find(s => s.name === 'mac');
  console.log(`  - ${macSource?.displayName || macSource?.name}`);
  
  console.log('\nMac Streams:');
  const macStreams = result.diagramData?.streams?.filter(s => s.sourceName === 'mac');
  macStreams?.forEach(s => {
    console.log(`  - ${s.displayName} (${s.streamName})`);
  });
  
  console.log('\nMac Signals:');
  const macSignals = result.diagramData?.signals?.filter(s => s.sourceName === 'mac');
  macSignals?.forEach(s => {
    console.log(`  - ${s.displayName} (${s.signalName})`);
  });
  
  // Check Google related nodes
  console.log('\n\nGoogle Source:');
  const googleSource = result.diagramData?.sources?.find(s => s.name === 'google');
  console.log(`  - ${googleSource?.displayName || googleSource?.name}`);
  
  console.log('\nGoogle Streams:');
  const googleStreams = result.diagramData?.streams?.filter(s => s.sourceName === 'google');
  googleStreams?.forEach(s => {
    console.log(`  - ${s.displayName} (${s.streamName})`);
  });
  
  console.log('\nGoogle Signals:');
  const googleSignals = result.diagramData?.signals?.filter(s => s.sourceName === 'google');
  googleSignals?.forEach(s => {
    console.log(`  - ${s.displayName} (${s.signalName})`);
  });
  
  process.exit(0);
}

debugNodes().catch(console.error);