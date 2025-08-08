import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { z } from 'zod';
import { db } from '$lib/db/client';
import { signalConfigs } from '$lib/db/schema';
import { eq } from 'drizzle-orm';

const detectSignalSchema = z.object({
  userId: z.string().uuid(),
  signalName: z.string(),
  startTime: z.string().datetime(),
  endTime: z.string().datetime(),
  timezone: z.string().optional()
});

export const POST: RequestHandler = async ({ request }) => {
  try {
    const body = await request.json();
    console.log('[SignalAnalysis] Detection request:', body);

    const { userId, signalName, startTime, endTime, timezone } = detectSignalSchema.parse(body);

    // Query signal info to determine computation type
    const signalInfo = await db
      .select({
        id: signalConfigs.id,
        computation: signalConfigs.computation,
        sourceName: signalConfigs.sourceName,
        displayName: signalConfigs.displayName
      })
      .from(signalConfigs)
      .where(eq(signalConfigs.signalName, signalName))
      .limit(1);

    if (!signalInfo || signalInfo.length === 0) {
      return json({
        success: false,
        error: `Signal ${signalName} not found for user`
      }, { status: 404 });
    }

    const signal = signalInfo[0];
    console.log('[SignalAnalysis] Signal info:', signal);

    // Always use transition detection for all signal types
    const detectionType = 'transition';

    console.log(`[SignalAnalysis] Signal ${signalName} uses ${signal.computation?.algorithm || 'default'} algorithm, using transition detection`);

    // Convert start/end times to date string for the task
    const date = new Date(startTime).toISOString().split('T')[0];

    // Import Redis queue function
    const { queueCeleryTask } = await import('$lib/redis');

    // Queue the appropriate detection task
    // For now, we'll use the existing task name but log the detection type
    const taskArgs = [userId, signalName, date, startTime, endTime, timezone || 'America/Chicago'];

    const taskId = await queueCeleryTask(
      'run_single_signal_transition_detection',
      taskArgs,
      {}  // Empty kwargs - the Python function doesn't accept extra parameters
    );

    console.log(`[SignalAnalysis] ${detectionType} detection task queued with ID:`, taskId);

    return json({
      success: true,
      taskId,
      message: `Transition detection queued for ${signal.displayName}`,
      signalName,
      detectionType,
      computation: signal.computation
    });

  } catch (error) {
    console.error('[SignalAnalysis] Detection error:', error);

    if (error instanceof z.ZodError) {
      return json({
        success: false,
        error: 'Invalid request data',
        details: error.errors
      }, { status: 400 });
    }

    return json({
      success: false,
      error: 'Failed to queue signal analysis',
      message: error instanceof Error ? error.message : 'Unknown error'
    }, { status: 500 });
  }
};