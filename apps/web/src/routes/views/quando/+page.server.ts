import type { PageServerLoad } from './$types';
import { db } from '$lib/db/client';
import { signals, signalConfigs, sourceConfigs } from '$lib/db/schema';
import { eq, and, gte, lte } from 'drizzle-orm';

export const load: PageServerLoad = async ({ url }) => {
	try {
		// Get date from query params or use today
		const dateParam = url.searchParams.get('date');
		const selectedDate = dateParam ? new Date(dateParam) : new Date();
		
		// Set start and end of day
		const startOfDay = new Date(selectedDate);
		startOfDay.setHours(0, 0, 0, 0);
		
		const endOfDay = new Date(selectedDate);
		endOfDay.setHours(23, 59, 59, 999);
		
		// Query ambient signals for the day
		const ambientData = await db
			.select({
				ambientSignal: signals,
				signal: signalConfigs,
				source: sourceConfigs
			})
			.from(signals)
			.innerJoin(signalConfigs, eq(signals.signalId, signalConfigs.id))
			.innerJoin(sourceConfigs, eq(signals.sourceName, sourceConfigs.name))
			.where(
				and(
					gte(signals.timestamp, startOfDay),
					lte(signals.timestamp, endOfDay)
				)
			)
			.orderBy(signals.timestamp);
		
		// Episodic signals no longer exist as a separate table
		const episodicData: any[] = [];
		
		// Group ambient signals by sourceName + signalName to avoid duplicates
		const ambientSignalsBySignalName = ambientData.reduce((acc, { ambientSignal, signal, source }) => {
			const groupKey = `${ambientSignal.sourceName}_${ambientSignal.signalName}`;
			if (!acc[groupKey]) {
				const wizardConfig = source.wizardConfig as any;
				acc[groupKey] = {
					signalName: ambientSignal.signalName,
					displayName: signal.displayName || ambientSignal.signalName,
					sourceName: ambientSignal.sourceName,
					signalId: signal.id,
					visualizationType: signal.computation?.value_type || 'continuous',
					unit: signal.unitUcum,
					type: 'ambient' as const,
					signals: []
				};
			}
			
			acc[groupKey].signals.push({
				id: ambientSignal.id,
				timestamp: ambientSignal.timestamp,
				signalName: ambientSignal.signalName,
				signalValue: ambientSignal.signalValue,
				coordinates: ambientSignal.coordinates,
				confidence: ambientSignal.confidence,
				sourceEventId: ambientSignal.sourceEventId,
				// Add signal metadata
				valueType: signal.computation?.value_type || 'continuous',
				unit: signal.unitUcum
			});
			
			return acc;
		}, {} as Record<string, any>);
		
		// Episodic signals no longer exist as a separate table
		const episodicSignalsBySignalId = {} as Record<string, any>;
		
		return {
			ambientSignalsBySignalName: Object.values(ambientSignalsBySignalName),
			episodicSignalsBySignalId: Object.values(episodicSignalsBySignalId),
			selectedDate: selectedDate.toISOString()
		};
		
	} catch (error) {
		console.error('Error loading signals:', error);
		return {
			ambientSignalsBySignalName: [],
			episodicSignalsBySignalId: [],
			selectedDate: new Date().toISOString(),
			error: 'Failed to load signals'
		};
	}
};