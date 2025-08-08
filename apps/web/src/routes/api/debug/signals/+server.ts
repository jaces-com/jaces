import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { db } from '$lib/db/client';
import { signalConfigs } from '$lib/db/schema';
import { eq } from 'drizzle-orm';

export const GET: RequestHandler = async ({ url }) => {
  try {
    const userId = url.searchParams.get('userId') || '00000000-0000-0000-0000-000000000000';
    
    // Get all signals for the user
    const userSignals = await db
      .select({
        id: signalConfigs.id,
        signalName: signalConfigs.signalName,
        sourceName: signalConfigs.sourceName,
        computation: signalConfigs.computation,
        status: signalConfigs.status,
        displayName: signalConfigs.displayName,
      })
      .from(signalConfigs);
    
    // Filter for apple_ios_speed specifically
    const speedSignal = userSignals.find(s => s.signalName === 'apple_ios_speed');
    
    return json({
      success: true,
      totalSignals: userSignals.length,
      signals: userSignals,
      speedSignal: speedSignal || null,
      speedSignalExists: !!speedSignal
    });
    
  } catch (error) {
    console.error('Debug signals error:', error);
    return json({ 
      success: false, 
      error: error instanceof Error ? error.message : 'Unknown error'
    }, { status: 500 });
  }
};