import { type RequestHandler } from '@sveltejs/kit';
import { db } from '$lib/db/client';
import { signalConfigs } from '$lib/db/schema';
import { eq, and } from 'drizzle-orm';
import { queueCeleryTask } from '$lib/redis';

export const POST: RequestHandler = async ({ params, request }) => {
	try {
		const signalId = params.id;
		const body = await request.json();
		const userId = body.user_id;
		
		if (!signalId) {
			return new Response(JSON.stringify({ error: 'Signal ID is required' }), {
				status: 400,
				headers: { 'Content-Type': 'application/json' }
			});
		}
		
		// Get signal
		const [signal] = await db
			.select()
			.from(signalConfigs)
			.where(eq(signalConfigs.id, signalId))
			.limit(1);

		if (!signal) {
			return new Response(JSON.stringify({ error: 'Signal not found' }), {
				status: 404,
				headers: { 'Content-Type': 'application/json' }
			});
		}

		if (signal.status !== 'active') {
			return new Response(JSON.stringify({ error: 'Signal is not active' }), {
				status: 400,
				headers: { 'Content-Type': 'application/json' }
			});
		}

		// Map source names to Celery task names
		const taskMap: Record<string, string> = {
			'google': 'sync_google_calendar',
			'google_calendar': 'sync_google_calendar',
			'ios_coordinates': 'sync_ios_coordinates',
			'ios_environmental_sound': 'sync_ios_environmental_sound',
			'ios_mic_transcription': 'sync_ios_mic_transcription',
			'mac_apps': 'sync_mac_apps'
		};

		const taskName = taskMap[signal.sourceName];
		if (!taskName) {
			return new Response(JSON.stringify({ error: `Unsupported source: ${signal.sourceName}` }), {
				status: 400,
				headers: { 'Content-Type': 'application/json' }
			});
		}

		// Queue the Celery task
		const taskId = await queueCeleryTask(taskName, [signal.id, true]); // true indicates manual sync

		// Log for debugging
		console.log(`Manual sync triggered for ${signal.sourceName} (signal: ${signal.id}, task: ${taskId})`);

		return new Response(JSON.stringify({ 
			success: true,
			taskId,
			message: 'Sync started successfully'
		}), {
			headers: { 'Content-Type': 'application/json' }
		});

	} catch (error) {
		console.error('Failed to trigger sync:', error);
		return new Response(JSON.stringify({ error: 'Failed to trigger sync' }), {
			status: 500,
			headers: { 'Content-Type': 'application/json' }
		});
	}
};