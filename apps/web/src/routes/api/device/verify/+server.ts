import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { db } from '$lib/db/client';
import { sources, streamConfigs } from '$lib/db/schema';
import { eq, and } from 'drizzle-orm';

export const POST: RequestHandler = async ({ request }) => {
	const deviceToken = request.headers.get('x-device-token');
	
	if (!deviceToken || !deviceToken.startsWith('dev_tk_')) {
		return json({ 
			success: false,
			error: 'Invalid or missing device token' 
		}, { status: 401 });
	}

	try {
		// Parse request body for device info
		let deviceInfo: any = {};
		try {
			deviceInfo = await request.json();
		} catch {
			// Body is optional
		}

		// Find device source by token
		const [deviceSource] = await db
			.select()
			.from(sources)
			.where(eq(sources.deviceToken, deviceToken))
			.limit(1);

		if (!deviceSource) {
			return json({ 
				success: false,
				error: 'Device token not found. Please generate a new token in the web app.' 
			}, { status: 404 });
		}

		// Get stream configurations for this source
		const streams = await db
			.select()
			.from(streamConfigs)
			.where(eq(streamConfigs.sourceName, deviceSource.sourceName));

		// Update device source with connection info
		await db
			.update(sources)
			.set({ 
				lastSyncStatus: 'success',
				lastSyncAt: new Date(),
				sourceMetadata: {
					...deviceSource.sourceMetadata,
					deviceInfo: deviceInfo,
					firstVerifiedAt: deviceSource.sourceMetadata?.firstVerifiedAt || new Date().toISOString(),
					lastVerifiedAt: new Date().toISOString(),
				}
			})
			.where(eq(sources.id, deviceSource.id));

		// Build sync intervals from stream configs
		const syncIntervals: Record<string, string> = {};
		streams.forEach(stream => {
			// Use the stream name without the source prefix for the key
			const streamKey = stream.streamName.replace(`${deviceSource.sourceName}_`, '');
			syncIntervals[streamKey] = stream.cronSchedule || '0 * * * *'; // Default to hourly
		});

		// Return success with configuration
		return json({
			success: true,
			source: {
				id: deviceSource.id,
				name: deviceSource.instanceName,
				sourceName: deviceSource.sourceName,
				status: 'active'
			},
			streams: streams.map(s => ({
				name: s.streamName,
				displayName: s.displayName,
				ingestionType: s.ingestionType,
				cronSchedule: s.cronSchedule,
				status: s.status
			})),
			configuration: {
				syncIntervals,
				endpoints: {
					ingest: '/api/ingest',
					verify: '/api/device/verify'
				}
			},
			message: 'Device verified successfully'
		});

	} catch (error) {
		console.error('Device verification error:', error);
		return json({ 
			success: false,
			error: 'Failed to verify device' 
		}, { status: 500 });
	}
};

// GET endpoint for checking device status
export const GET: RequestHandler = async ({ url }) => {
	const deviceToken = url.searchParams.get('token');
	
	if (!deviceToken) {
		return json({ 
			success: false,
			error: 'Token parameter required' 
		}, { status: 400 });
	}

	try {
		const [deviceSource] = await db
			.select({
				id: sources.id,
				lastSyncStatus: sources.lastSyncStatus,
				instanceName: sources.instanceName,
				lastSyncAt: sources.lastSyncAt,
				sourceMetadata: sources.sourceMetadata
			})
			.from(sources)
			.where(eq(sources.deviceToken, deviceToken))
			.limit(1);

		if (!deviceSource) {
			return json({ 
				success: false,
				connected: false,
				error: 'Device not found' 
			}, { status: 404 });
		}

		const isConnected = deviceSource.lastSyncStatus === 'success' && 
			deviceSource.sourceMetadata?.lastVerifiedAt;

		return json({
			success: true,
			connected: isConnected,
			device: {
				id: deviceSource.id,
				name: deviceSource.instanceName,
				status: deviceSource.lastSyncStatus || 'pending',
				lastSyncAt: deviceSource.lastSyncAt,
				verifiedAt: deviceSource.sourceMetadata?.lastVerifiedAt || null
			}
		});

	} catch (error) {
		console.error('Device status check error:', error);
		return json({ 
			success: false,
			error: 'Failed to check device status' 
		}, { status: 500 });
	}
};