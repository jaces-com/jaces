import { type RequestHandler } from '@sveltejs/kit';
import { db } from '$lib/db/client';
import { signalConfigs, sourceConfigs, sources, ingestionRuns, users } from '$lib/db/schema';
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

export const GET: RequestHandler = async ({ url, request }) => {
	try {
		// Check for device token in headers
		const deviceToken = request.headers.get('x-device-token');
		
		// Get query parameters
		let userId = url.searchParams.get('user_id');
		const status = url.searchParams.get('status');

		// If device token provided, find the device's source
		let deviceSource = null;
		if (deviceToken) {
			const [source] = await db
				.select()
				.from(sourceConfigs)
				.where(eq(sourceConfigs.pairedDeviceToken, deviceToken))
				.limit(1);
			
			if (source) {
				deviceSource = source;
				// Use the device's user ID if not explicitly provided
				if (!userId && source.userId) {
					userId = source.userId;
				}
			}
		}

		// If no userId provided, get the first user (single-user system)
		if (!userId) {
			const [firstUser] = await db.select().from(users).limit(1);
			if (!firstUser) {
				return new Response(JSON.stringify({ error: 'No users found' }), {
					status: 404,
					headers: { 'Content-Type': 'application/json' }
				});
			}
			userId = firstUser.id;
		}

		// Build base query conditions
		const conditions = [];
		if (status !== null) {
			conditions.push(eq(signalConfigs.status, status));
		}

		// Get signals with sources
		const signalsWithSources = await db
			.select({
				signal: signalConfigs,
				source: sources
			})
			.from(signalConfigs)
			.leftJoin(sources, eq(signalConfigs.sourceId, sources.id))
			.where(conditions.length > 0 ? and(...conditions) : undefined);

		// Get latest ingestion run for each signal
		const signalIds = signalsWithSources.map(r => r.signal.id);
		const runMap = new Map();
		
		if (signalIds.length > 0) {
			// Get latest run for each signal
			for (const signalId of signalIds) {
				const [latestRun] = await db
					.select()
					.from(ingestionRuns)
					.where(eq(ingestionRuns.signalId, signalId))
					.orderBy(desc(ingestionRuns.createdAt))
					.limit(1);
				
				if (latestRun) {
					runMap.set(signalId, latestRun);
				}
			}
		}

		const results = signalsWithSources.map(({ signal, source }) => ({
			signal,
			source,
			lastRun: runMap.get(signal.id) || null
		}));

		// Transform to response format
		const signalsResponse = results.map(({ signal, source, lastRun }) => {
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

			return {
				id: signal.id,
				signal_name: signal.signalName,
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
		});

		return new Response(JSON.stringify(signalsResponse), {
			headers: { 'Content-Type': 'application/json' }
		});

	} catch (error) {
		console.error('Failed to fetch signals:', error);
		return new Response(JSON.stringify({ error: 'Failed to fetch signals' }), {
			status: 500,
			headers: { 'Content-Type': 'application/json' }
		});
	}
};

export const POST: RequestHandler = async ({ request }) => {
	try {
		const body = await request.json();
		
		// Validate required fields
		const { user_id, source_name, signal_name, unit_ucum, computation, fidelity_score, insider_tip, sync_schedule, device_id_fk } = body;
		
		if (!user_id || !source_name || !signal_name || !unit_ucum || !computation) {
			return new Response(JSON.stringify({ error: 'user_id, source_name, signal_name, unit_ucum, and computation are required' }), {
				status: 400,
				headers: { 'Content-Type': 'application/json' }
			});
		}

		// Check if source exists
		const [source] = await db
			.select()
			.from(sourceConfigs)
			.where(eq(sourceConfigs.name, source_name))
			.limit(1);

		if (!source) {
			return new Response(JSON.stringify({ error: 'Source not found' }), {
				status: 404,
				headers: { 'Content-Type': 'application/json' }
			});
		}

		// For device-based sources, validate device_id_fk
		if (source.authType === 'device_token' && !device_id_fk) {
			return new Response(JSON.stringify({ error: 'device_id_fk is required for device-based sources' }), {
				status: 400,
				headers: { 'Content-Type': 'application/json' }
			});
		}

		// Check if signal already exists
		const conditions = [
			eq(signalConfigs.userId, user_id),
			eq(signalConfigs.signalName, signal_name)
		];
		
		// For device-based sources, check for existing signal with same device
		if (device_id_fk) {
			conditions.push(eq(signalConfigs.deviceIdFk, device_id_fk));
		}
		
		const [existingSignal] = await db
			.select()
			.from(signalConfigs)
			.where(and(...conditions))
			.limit(1);

		if (existingSignal) {
			return new Response(JSON.stringify({ error: 'Signal already exists' }), {
				status: 409,
				headers: { 'Content-Type': 'application/json' }
			});
		}

		// Create new signal
		const signalData: any = {
			userId: user_id,
			sourceName: source_name,
			signalName: signal_name,
			unitUcum: unit_ucum,
			computation: computation,
			status: body.status || 'pending_setup', // Default to pending_setup
			fidelityScore: fidelity_score ?? source.defaultFidelityScore,
			syncSchedule: sync_schedule ?? source.defaultSyncSchedule,
			description: insider_tip,
			settings: body.settings || {}
		};
		
		// Add device reference if provided
		if (device_id_fk) {
			signalData.deviceIdFk = device_id_fk;
		}
		
		const [newSignal] = await db
			.insert(signalConfigs)
			.values(signalData)
			.returning();

		// Get display name from wizard config
		const wizardConfig = source.wizardConfig as any;
		const displayName = wizardConfig?.display_name || source.name;

		// Return response in expected format
		const response = {
			id: newSignal.id,
			signal_name: newSignal.signalName,
			unit: newSignal.unitUcum,
			computation: newSignal.computation,
			source_name: newSignal.sourceName,
			display_name: displayName,
			status: newSignal.status,
			display_status: newSignal.status,
			fidelity_score: newSignal.fidelityScore,
			insider_tip: newSignal.description,
			last_sync: null,
			sync_schedule: newSignal.syncSchedule,
			next_sync: calculateNextSync(newSignal.syncSchedule),
			created_at: newSignal.createdAt,
			is_syncing: false,
			error_message: null
		};

		return new Response(JSON.stringify(response), {
			status: 201,
			headers: { 'Content-Type': 'application/json' }
		});

	} catch (error) {
		console.error('Failed to create signal:', error);
		return new Response(JSON.stringify({ error: 'Failed to create signal' }), {
			status: 500,
			headers: { 'Content-Type': 'application/json' }
		});
	}
};