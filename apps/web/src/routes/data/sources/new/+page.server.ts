import type { PageServerLoad } from './$types';
import { db } from '$lib/db/client';
import { sourceConfigs, streamConfigs, signalConfigs, sources } from '$lib/db/schema';
import { eq, inArray } from 'drizzle-orm';
import { error } from '@sveltejs/kit';

export const load: PageServerLoad = async ({ url }) => {
	const sourceName = url.searchParams.get('source');
	
	if (!sourceName) {
		throw error(400, 'Source parameter is required');
	}
	
	try {
		// Get the source configuration
		const [sourceConfig] = await db
			.select()
			.from(sourceConfigs)
			.where(eq(sourceConfigs.name, sourceName))
			.limit(1);
		
		if (!sourceConfig) {
			throw error(404, `Source '${sourceName}' not found`);
		}
		
		// Check if this source is already connected
		const [existingSource] = await db
			.select()
			.from(sources)
			.where(eq(sources.sourceName, sourceName))
			.limit(1);
		
		const isConnected = !!existingSource;
		const connectionSuccessful = url.searchParams.get('connected') === sourceName;
		
		// Get all stream configurations for this source
		const streams = await db
			.select()
			.from(streamConfigs)
			.where(eq(streamConfigs.sourceName, sourceName));
		
		// Get all stream names for signal lookup
		const streamNames = streams.map(s => s.streamName);
		
		// Get all signals produced by these streams
		let signals = [];
		if (streamNames.length > 0) {
			signals = await db
				.select()
				.from(signalConfigs)
				.where(inArray(signalConfigs.streamName, streamNames));
		}
		
		// Parse OAuth config
		const oauthConfig = (sourceConfig.oauthConfig as any) || {};
		
		// Build OAuth URL if this is an OAuth source
		let oauthUrl = null;
		if (sourceConfig.authType === 'oauth2' && oauthConfig.authProxy) {
			// Construct the OAuth initiation URL
			const authProxyUrl = oauthConfig.authProxy;
			const returnUrl = `${url.origin}/oauth/callback`;
			const state = `/data/sources/new?source=${sourceName}`; // Include source parameter
			
			oauthUrl = `${authProxyUrl}?return_url=${encodeURIComponent(returnUrl)}&state=${encodeURIComponent(state)}`;
			console.log('Generated OAuth URL for', sourceName, ':', oauthUrl);
		}
		
		return {
			source: {
				name: sourceConfig.name,
				displayName: sourceConfig.displayName || sourceConfig.name,
				description: sourceConfig.description || '',
				icon: sourceConfig.icon || '',
				platform: sourceConfig.platform,
				authType: sourceConfig.authType,
				company: sourceConfig.company,
				deviceType: sourceConfig.deviceType,
				requiredScopes: oauthConfig.requiredScopes || [],
				oauthUrl,
				isConnected,
				connectionSuccessful,
				existingSource: existingSource ? {
					id: existingSource.id,
					instanceName: existingSource.instanceName,
					isActive: existingSource.isActive,
					lastSyncAt: existingSource.lastSyncAt
				} : null,
				// Add any sync configuration
				syncConfig: (sourceConfig.syncConfig as any) || {}
			},
			streams: streams.map(stream => ({
				id: stream.id,
				name: stream.streamName,
				displayName: stream.displayName,
				description: stream.description,
				ingestionType: stream.ingestionType,
				cronSchedule: stream.cronSchedule,
				settings: stream.settings || {},
				// Add signals for this stream
				signals: signals.filter(s => s.streamName === stream.streamName).map(s => ({
					name: s.signalName,
					displayName: s.displayName,
					description: s.description,
					signalType: s.signalType
				}))
			})),
			signals: signals.map(signal => ({
				name: signal.signalName,
				displayName: signal.displayName || signal.signalName,
				description: signal.description,
				streamName: signal.streamName,
				signalType: signal.signalType
			}))
		};
	} catch (err) {
		console.error('Error loading source configuration:', err);
		if (err && typeof err === 'object' && 'status' in err) {
			throw err;
		}
		throw error(500, 'Failed to load source configuration');
	}
};