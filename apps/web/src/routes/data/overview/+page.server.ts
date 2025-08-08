import type { PageServerLoad } from './$types';
import { db } from '$lib/db/client';
import { sourceConfigs } from '$lib/db/schema/source_configs';
import { sources } from '$lib/db/schema/sources';
import { signalConfigs } from '$lib/db/schema/signal_configs';
import { streamConfigs } from '$lib/db/schema/stream_configs';
import { streams } from '$lib/db/schema/streams';
import { semanticConfigs } from '$lib/db/schema/semantic_configs';
import { eq, and, desc } from 'drizzle-orm';

export const load: PageServerLoad = async () => {
	try {
		console.log('Loading overview data...');
		console.log('db object:', db);
		console.log('sourceConfigs:', sourceConfigs);
		
		// Get all source configurations
		let allSourceConfigs = [];
		try {
			console.log('Loading source configs...');
			allSourceConfigs = await db
				.select()
				.from(sourceConfigs);
			console.log('Source configs loaded:', allSourceConfigs?.length);
		} catch (err) {
			console.error('Error loading source configs:', err);
		}

		// Get all connected source instances
		console.log('Loading connected sources...');
		const connectedSources = await db
			.select()
			.from(sources);
		console.log('Connected sources loaded:', connectedSources?.length);

		// Create a map of connected sources by source name
		const connectedByName = new Map<string, typeof connectedSources>();
		for (const source of connectedSources) {
			if (!connectedByName.has(source.sourceName)) {
				connectedByName.set(source.sourceName, []);
			}
			connectedByName.get(source.sourceName)!.push(source);
		}

		// Get all signals with streamName
		console.log('Loading signals...');
		const allSignals = await db
			.select()
			.from(signalConfigs)
			.orderBy(desc(signalConfigs.createdAt));
		console.log('Signals loaded:', allSignals?.length);

		// Get all active streams from database
		console.log('Loading streams...');
		const allStreams = await db
			.select()
			.from(streamConfigs);
		console.log('Streams loaded:', allStreams?.length);

		// Get all semantic configs
		console.log('Loading semantics...');
		const allSemantics = await db
			.select()
			.from(semanticConfigs);
		console.log('Semantics loaded:', allSemantics?.length);

		// Get connected stream instances with source and stream config data
		console.log('Loading connected stream instances...');
		const connectedStreamInstances = await db
			.select({
				streamId: streams.id,
				streamConfigId: streams.streamConfigId,
				sourceId: streams.sourceId,
				enabled: streams.enabled,
				syncSchedule: streams.syncSchedule,
				lastSyncAt: streams.lastSyncAt,
				lastSyncStatus: streams.lastSyncStatus,
				lastSyncError: streams.lastSyncError,
				streamCreatedAt: streams.createdAt,
				streamUpdatedAt: streams.updatedAt,
				// Stream config data
				streamName: streamConfigs.streamName,
				streamDisplayName: streamConfigs.displayName,
				streamStatus: streamConfigs.status,
				cronSchedule: streamConfigs.cronSchedule,
				// Source data
				sourceName: sources.sourceName,
				sourceInstanceName: sources.instanceName,
				sourceIsActive: sources.isActive,
				// Source config data
				sourceDisplayName: sourceConfigs.displayName,
				sourceCompany: sourceConfigs.company,
				sourcePlatform: sourceConfigs.platform,
			})
			.from(streams)
			.innerJoin(streamConfigs, eq(streams.streamConfigId, streamConfigs.id))
			.innerJoin(sources, eq(streams.sourceId, sources.id))
			.innerJoin(sourceConfigs, eq(sources.sourceName, sourceConfigs.name))
			.where(
				and(
					eq(sources.isActive, true),  // Only active sources
					eq(streams.enabled, true)    // Only enabled streams
				)
			)
			.orderBy(desc(streams.lastSyncAt));
		console.log('Connected stream instances loaded:', connectedStreamInstances?.length);

		console.log('Data loaded:', {
			sources: allSourceConfigs?.length,
			signals: allSignals?.length,
			streams: allStreams?.length,
			semantics: allSemantics?.length
		});

		// Process streams from database
		const processedStreams = allStreams.map(stream => {
			// Get signals that belong to this stream from database
			const streamSignals = allSignals.filter(signal => 
				signal.streamName === stream.streamName
			);
			
			// Check if this stream has semantics
			const streamSemantics = allSemantics.filter(semantic =>
				semantic.streamName === stream.streamName
			);

			return {
				streamName: stream.streamName,
				displayName: stream.displayName,
				sourceName: stream.sourceName,
				producesSignals: streamSignals.map(s => s.signalName),
				producesSemantics: streamSemantics.map(s => s.semanticName),
				ingestionType: stream.ingestionType,
				isEnabled: stream.status === 'active',
				status: stream.status
			};
		});

		// Process sources to include display names
		// Include all configured sources, regardless of whether they have signals
		const processedSources = allSourceConfigs
			.map(sourceConfig => {
				const instances = connectedByName.get(sourceConfig.name) || [];
				const latestInstance = instances[0]; // Get first instance if any

				return {
					name: sourceConfig.name,
					displayName: latestInstance?.instanceName || sourceConfig.displayName || sourceConfig.name,
					company: sourceConfig.company,
					platform: sourceConfig.platform,
					deviceType: sourceConfig.deviceType,
					isActive: instances.length > 0 && instances.some(i => i.isActive),
					icon: getSourceIcon(sourceConfig.name),
				};
			});

		// Group signals by source
		const signalsBySource = new Map<string, typeof allSignals>();
		for (const signal of allSignals) {
			if (!signalsBySource.has(signal.sourceName)) {
				signalsBySource.set(signal.sourceName, []);
			}
			signalsBySource.get(signal.sourceName)!.push(signal);
		}

		// Group streams by source
		const streamsBySource = new Map<string, typeof processedStreams>();
		for (const stream of processedStreams) {
			if (!streamsBySource.has(stream.sourceName)) {
				streamsBySource.set(stream.sourceName, []);
			}
			streamsBySource.get(stream.sourceName)!.push(stream);
		}

		// Create a map of which signals come from which streams
		const signalsByStream = new Map<string, string[]>();
		for (const stream of processedStreams) {
			signalsByStream.set(stream.streamName, stream.producesSignals);
		}

		// Create map of semantics by stream
		const semanticsByStream = new Map<string, typeof allSemantics>();
		for (const semantic of allSemantics) {
			if (!semanticsByStream.has(semantic.streamName)) {
				semanticsByStream.set(semantic.streamName, []);
			}
			semanticsByStream.get(semantic.streamName)!.push(semantic);
		}

		// Build the node diagram data structure
		const diagramData = {
			sources: processedSources || [],
			streams: processedStreams || [],
			signals: allSignals || [],
			semantics: allSemantics || [],
			connectedStreams: connectedStreamInstances || [],
			signalsBySource: Object.fromEntries(signalsBySource || []),
			streamsBySource: Object.fromEntries(streamsBySource || []),
			signalsByStream: Object.fromEntries(signalsByStream || []),
			semanticsByStream: Object.fromEntries(semanticsByStream || []),
			stats: {
				totalSources: processedSources?.length || 0,
				totalStreams: processedStreams?.length || 0,
				totalSignals: allSignals?.length || 0,
				totalSemantics: allSemantics?.length || 0,
				connectedStreams: connectedStreamInstances?.length || 0,
				activeSignals: allSignals?.filter(s => s.status === 'active')?.length || 0,
				activeStreams: processedStreams?.filter(s => s.isEnabled)?.length || 0,
				activeSemantics: allSemantics?.filter(s => s.status === 'active')?.length || 0,
				signalsByValueType: {
					continuous: allSignals?.filter(s => s.computation?.value_type === 'continuous')?.length || 0,
					spatial: allSignals?.filter(s => s.computation?.value_type === 'spatial')?.length || 0,
					count: allSignals?.filter(s => s.computation?.value_type === 'count')?.length || 0,
					event: allSignals?.filter(s => s.computation?.value_type === 'event')?.length || 0,
					categorical: allSignals?.filter(s => s.computation?.value_type === 'categorical')?.length || 0,
					binary: allSignals?.filter(s => s.computation?.value_type === 'binary')?.length || 0
				}
			}
		};

		return {
			diagramData
		};

	} catch (error) {
		console.error('Error loading overview data:', error);
		return {
			diagramData: {
				sources: [],
				streams: [],
				signals: [],
				semantics: [],
				connectedStreams: [],
				signalsBySource: {},
				streamsBySource: {},
				signalsByStream: {},
				semanticsByStream: {},
				stats: {
					totalSources: 0,
					totalStreams: 0,
					totalSignals: 0,
					totalSemantics: 0,
					connectedStreams: 0,
					activeSignals: 0,
					activeStreams: 0,
					activeSemantics: 0,
					signalsByValueType: {
						continuous: 0,
						spatial: 0,
						count: 0,
						event: 0,
						categorical: 0,
						binary: 0
					}
				}
			},
			error: 'Failed to load overview data'
		};
	}
};

// Helper function to get source icon
function getSourceIcon(sourceName: string): string {
	const iconMap: Record<string, string> = {
		'ios': 'ri:smartphone-line',
		'google': 'ri:google-fill',
		'mac': 'ri:mac-line',
		'android': 'ri:android-line'
	};
	return iconMap[sourceName] || 'ri:database-2-line';
}
