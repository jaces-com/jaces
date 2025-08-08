import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { z } from 'zod';

const runSingleSignalTransitionDetectionSchema = z.object({
  userId: z.string().uuid(),
  signalName: z.string(),
  startTime: z.string().datetime(),
  endTime: z.string().datetime(),
  timezone: z.string().optional()
});

export const POST: RequestHandler = async ({ request }) => {
  try {
    const body = await request.json();
    console.log('[API] Single signal transition detection request:', body);

    const { userId, signalName, startTime, endTime, timezone } = runSingleSignalTransitionDetectionSchema.parse(body);

    console.log('[API] Parsed data:', { userId, signalName, startTime, endTime, timezone });

    // Convert start/end times to date string (YYYY-MM-DD)
    const date = new Date(startTime).toISOString().split('T')[0];
    console.log('[API] Extracted date:', date);

    // Import the queueCeleryTask function
    const { queueCeleryTask } = await import('$lib/redis');

    // Queue the single signal transition detection task
    const taskArgs = [userId, signalName, date, startTime, endTime, timezone || 'America/Chicago'];
    console.log('[API] Queueing Celery task with args:', taskArgs);

    const taskId = await queueCeleryTask(
      'run_single_signal_transition_detection',
      taskArgs,
      {}
    );

    console.log('[API] Task queued successfully with ID:', taskId);

    return json({
      success: true,
      taskId,
      message: `Single signal transition detection queued for ${signalName}`,
      signalName
    });

  } catch (error) {
    console.error('[API] Single signal transition detection error:', error);

    if (error instanceof z.ZodError) {
      console.error('[API] Validation error:', error.errors);
      return json({
        success: false,
        error: 'Invalid request data',
        details: error.errors
      }, { status: 400 });
    }

    return json({
      success: false,
      error: 'Failed to queue single signal transition detection',
      message: error instanceof Error ? error.message : 'Unknown error'
    }, { status: 500 });
  }
};