import { type RequestHandler } from '@sveltejs/kit';
import { db } from '$lib/db/client';
import { signalConfigs, sourceConfigs, pipelineActivities } from '$lib/db/schema';
import { eq, and, desc } from 'drizzle-orm';
import { CronExpressionParser } from 'cron-parser';

// Helper function to calculate next sync time using cron-parser
function calculateNextSync(cronExpression: string, lastSync?: Date | null): Date | null {
	try {
		if (!cronExpression) return null;
		
		// Handle special cases
		if (cronExpression === 'realtime') return null;
		if (cronExpression === 'manual') return null;
		
		// Use cron-parser to get the next execution time
		const interval = CronExpressionParser.parse(cronExpression, {
			currentDate: new Date(),
			tz: 'UTC' // Use UTC for consistency
		});
		
		return interval.next().toDate();
	} catch (error) {
		console.error('Error calculating next sync for cron:', cronExpression, 'error:', error);
		return null;
	}
}

export const GET: RequestHandler = async ({ params, url }) => {
	try {
		const signalId = params.id;
		
		if (!signalId) {
			return new Response(JSON.stringify({ error: 'Signal ID is required' }), {
				status: 400,
				headers: { 'Content-Type': 'application/json' }
			});
		}

		// Get signal with source
		const [result] = await db
			.select({
				signal: signals,
				source: sources
			})
			.from(signalConfigs)
			.innerJoin(sources, eq(signalConfigs.sourceName, sourceConfigs.name))
			.where(eq(signalConfigs.id, signalId))
			.limit(1);

		if (!result) {
			return new Response(JSON.stringify({ error: 'Signal not found' }), {
				status: 404,
				headers: { 'Content-Type': 'application/json' }
			});
		}

		const { signal, source } = result;

		// Get latest ingestion activity
		const [lastRun] = await db
			.select()
			.from(pipelineActivities)
			.where(and(
				eq(pipelineActivities.signalId, signalId),
				eq(pipelineActivities.activityType, 'ingestion')
			))
			.orderBy(desc(pipelineActivities.createdAt))
			.limit(1);

		const lastSync = signal.lastSuccessfulIngestionAt;
		const nextSync = calculateNextSync(signal.syncSchedule, lastSync);
		
		// Determine display status based on signal status and latest run
		let displayStatus = signal.status;
		let isSyncing = false;
		let errorMessage = null;

		if (signal.status === 'active') {
			if (lastRun?.status === 'running') {
				displayStatus = 'syncing';
				isSyncing = true;
			} else if (lastRun?.status === 'failed') {
				displayStatus = 'error';
				errorMessage = lastRun.errorMessage;
			}
		}

		// Get display name from wizard config
		const wizardConfig = source.wizardConfig as any;
		const displayName = wizardConfig?.display_name || source.name;

		const response = {
			id: signal.id,
			signal_id: signal.signalId,
			signal_type: signal.signalType,
			unit: signal.unitUcum,
			computation: signal.computation,
			source_name: signal.sourceName,
			display_name: displayName,
			status: signal.status,
			display_status: displayStatus,
			fidelity_score: signal.fidelityScore,
			insider_tip: signal.description,
			last_sync: lastSync,
			sync_schedule: signal.syncSchedule,
			next_sync: nextSync,
			created_at: signal.createdAt,
			updated_at: signal.updatedAt,
			is_syncing: isSyncing,
			error_message: errorMessage
		};

		return new Response(JSON.stringify(response), {
			headers: { 'Content-Type': 'application/json' }
		});

	} catch (error) {
		console.error('Failed to fetch signal:', error);
		return new Response(JSON.stringify({ error: 'Failed to fetch signal' }), {
			status: 500,
			headers: { 'Content-Type': 'application/json' }
		});
	}
};

export const PATCH: RequestHandler = async ({ params, request }) => {
	try {
		const signalId = params.id;
		const body = await request.json();
		
		if (!signalId) {
			return new Response(JSON.stringify({ error: 'Signal ID is required' }), {
				status: 400,
				headers: { 'Content-Type': 'application/json' }
			});
		}

		// Check if signal exists
		const [existingSignal] = await db
			.select()
			.from(signalConfigs)
			.where(eq(signalConfigs.id, signalId))
			.limit(1);

		if (!existingSignal) {
			return new Response(JSON.stringify({ error: 'Signal not found' }), {
				status: 404,
				headers: { 'Content-Type': 'application/json' }
			});
		}

		// Prepare update data
		const updateData: any = {};
		
		if ('fidelity_score' in body) {
			updateData.fidelityScore = body.fidelity_score;
		}
		
		if ('insider_tip' in body) {
			updateData.description = body.insider_tip;
		}
		
		if ('sync_schedule' in body) {
			updateData.syncSchedule = body.sync_schedule;
		}
		
		if ('status' in body) {
			updateData.status = body.status;
		}
		
		if ('settings' in body) {
			updateData.settings = body.settings;
		}

		// Update timestamp
		updateData.updatedAt = new Date();

		// Update signal
		const [updatedSignal] = await db
			.update(signalConfigs)
			.set(updateData)
			.where(eq(signalConfigs.id, signalId))
			.returning();

		// Get source info for response
		const [source] = await db
			.select()
			.from(sourceConfigs)
			.where(eq(sourceConfigs.name, updatedSignal.sourceName))
			.limit(1);

		// Get display name from wizard config
		const wizardConfig = source?.wizardConfig as any;
		const displayName = wizardConfig?.display_name || source?.name || updatedSignal.sourceName;

		const response = {
			id: updatedSignal.id,
			signal_id: updatedSignal.signalId,
			signal_type: updatedSignal.signalType,
			unit: updatedSignal.unitUcum,
			computation: updatedSignal.computation,
			source_name: updatedSignal.sourceName,
			display_name: displayName,
			status: updatedSignal.status,
			display_status: updatedSignal.status,
			fidelity_score: updatedSignal.fidelityScore,
			insider_tip: updatedSignal.description,
			last_sync: updatedSignal.lastSuccessfulIngestionAt,
			sync_schedule: updatedSignal.syncSchedule,
			next_sync: calculateNextSync(updatedSignal.syncSchedule, updatedSignal.lastSuccessfulIngestionAt),
			created_at: updatedSignal.createdAt,
			updated_at: updatedSignal.updatedAt,
			is_syncing: false,
			error_message: null
		};

		return new Response(JSON.stringify(response), {
			headers: { 'Content-Type': 'application/json' }
		});

	} catch (error) {
		console.error('Failed to update signal:', error);
		return new Response(JSON.stringify({ error: 'Failed to update signal' }), {
			status: 500,
			headers: { 'Content-Type': 'application/json' }
		});
	}
};

export const DELETE: RequestHandler = async ({ params }) => {
	try {
		const signalId = params.id;
		
		if (!signalId) {
			return new Response(JSON.stringify({ error: 'Signal ID is required' }), {
				status: 400,
				headers: { 'Content-Type': 'application/json' }
			});
		}

		// Soft delete by setting status to inactive
		const [result] = await db
			.update(signalConfigs)
			.set({
				status: 'inactive',
				updatedAt: new Date()
			})
			.where(eq(signalConfigs.id, signalId))
			.returning({ id: signalConfigs.id });

		if (!result) {
			return new Response(JSON.stringify({ error: 'Signal not found' }), {
				status: 404,
				headers: { 'Content-Type': 'application/json' }
			});
		}

		return new Response(JSON.stringify({ success: true, id: result.id }), {
			headers: { 'Content-Type': 'application/json' }
		});

	} catch (error) {
		console.error('Failed to delete signal:', error);
		return new Response(JSON.stringify({ error: 'Failed to delete signal' }), {
			status: 500,
			headers: { 'Content-Type': 'application/json' }
		});
	}
};