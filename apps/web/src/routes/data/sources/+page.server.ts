import type { PageServerLoad } from './$types';
import { db } from '$lib/db/client';
import { sourceConfigs, sources, signalConfigs } from '$lib/db/schema';
import { eq, desc } from 'drizzle-orm';

export const load: PageServerLoad = async () => {
	try {
		// Get all source configurations (templates)
		const allSourceConfigs = await db
			.select()
			.from(sourceConfigs);
		
		// Get all connected source instances
		const connectedSources = await db
			.select()
			.from(sources);
		
		// Create a map of connected sources by source name
		const connectedByName = new Map<string, typeof connectedSources>();
		for (const source of connectedSources) {
			if (!connectedByName.has(source.sourceName)) {
				connectedByName.set(source.sourceName, []);
			}
			connectedByName.get(source.sourceName)!.push(source);
		}
		
		// Build sources list with connection status
		const sourcesList = allSourceConfigs.map(sourceConfig => {
			const connectedInstances = connectedByName.get(sourceConfig.name) || [];
			const isConnected = connectedInstances.length > 0;
			
			// Get OAuth config
			const oauthConfig = (sourceConfig.oauthConfig as any) || {};
			
			// For connected sources, get the most recent instance
			const latestInstance = connectedInstances.sort((a, b) => 
				(b.updatedAt?.getTime() || 0) - (a.updatedAt?.getTime() || 0)
			)[0];
			
			return {
				name: sourceConfig.name,
				display_name: sourceConfig.displayName || sourceConfig.name,
				description: sourceConfig.description || "",
				icon: sourceConfig.icon || "",
				platform: sourceConfig.platform,
				enabled: true,
				auth_type: sourceConfig.authType,
				company: sourceConfig.company,
				device_type: sourceConfig.deviceType,
				// Instance-specific data from connected sources
				device_name: latestInstance?.instanceName,
				last_seen: latestInstance?.lastSyncAt,
				oauth_expires_at: latestInstance?.oauthExpiresAt,
				scopes: latestInstance?.scopes,
				is_active: latestInstance?.isActive ?? false,
				fidelity_options: [],
				insider_tip_prompt: "",
				wizard: {},
				required_scopes: oauthConfig.requiredScopes || [],
				auth_proxy: oauthConfig.authProxy,
				is_connected: isConnected,
				connected_count: connectedInstances.length,
				// Multiple connections support (for future use)
				multiple_connections: false
			};
		});
		
		// Sort: connected sources first, then alphabetically
		sourcesList.sort((a, b) => {
			if (a.is_connected !== b.is_connected) {
				return a.is_connected ? -1 : 1;
			}
			return a.display_name.localeCompare(b.display_name);
		});
		
		// Get signals to show count per source
		const allSignals = await db
			.select({
				sourceName: signalConfigs.sourceName
			})
			.from(signalConfigs);
		
		// Count signals per source (all signals are considered active if they exist)
		const activeSignalCounts = new Map<string, number>();
		for (const signal of allSignals) {
			const count = activeSignalCounts.get(signal.sourceName) || 0;
			activeSignalCounts.set(signal.sourceName, count + 1);
		}
		
		// Add signal counts to sources
		const sourcesWithSignals = sourcesList.map(source => ({
			...source,
			active_signals_count: activeSignalCounts.get(source.name) || 0
		}));
		
		return {
			sources: sourcesWithSignals
		};
	} catch (error) {
		console.error('Error loading sources:', error);
		return {
			sources: [],
			error: 'Failed to load sources'
		};
	}
};