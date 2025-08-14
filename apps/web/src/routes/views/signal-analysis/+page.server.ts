import type { PageServerLoad } from './$types';
import { db } from '$lib/db/client';
import { signals, signalConfigs, sourceConfigs, signalTransitions, events } from '$lib/db/schema';
import { eq, and, gte, lte, sql } from 'drizzle-orm';
import { parseDate, toZoned, now, parseAbsolute } from '@internationalized/date';

export const load: PageServerLoad = async ({ url, depends }) => {
	// Register dependencies for granular invalidation
	depends('signal-analysis:signals');
	depends('signal-analysis:transitions');
	depends('signal-analysis:events');

	try {
		// Default timezone - in a single-user system, this could be configured elsewhere
		const userTimezone = 'America/Chicago';

		// Get date from query params or use today
		const dateParam = url.searchParams.get('date');

		// Parse the date and create timezone-aware start/end times
		let year, month, day;
		if (dateParam) {
			[year, month, day] = dateParam.split('-').map(Number);
		} else {
			// Get today in user's timezone
			const todayZoned = now(userTimezone);
			year = todayZoned.year;
			month = todayZoned.month;
			day = todayZoned.day;
		}

		// Create start and end of day in user's timezone
		const calendarDate = parseDate(`${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`);
		const zonedStart = toZoned(calendarDate, userTimezone);
		const zonedEnd = zonedStart.add({ hours: 23, minutes: 59, seconds: 59, milliseconds: 999 });

		// Convert to UTC Date objects for database queries
		const startOfDay = zonedStart.toDate();
		const endOfDay = zonedEnd.toDate();

		// Query all signals for the day with their configurations
		const signalsData = await db
			.select({
				signal: signals,
				config: signalConfigs,
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
		
		console.log(`Found ${signalsData.length} signals for ${dateParam || 'today'} between ${startOfDay.toISOString()} and ${endOfDay.toISOString()}`);

		// Group signals by sourceName + signalName
		const signalsByName = signalsData.reduce((acc, { signal, config, source }) => {
			// Skip if signal names don't match (data integrity check)
			if (signal.signalName !== config.signalName) {
				return acc;
			}

			const groupKey = `${signal.sourceName}_${signal.signalName}`;
			if (!acc[groupKey]) {
				// Extract visualization type from computation JSON
				const computation = config.computation as any;
				const visualizationType = computation?.value_type || 'continuous';
				
				// Use the streamName directly from the config
				const streamName = config.streamName;
				
				acc[groupKey] = {
					signalName: signal.signalName,
					displayName: config.displayName,
					sourceName: signal.sourceName,
					streamName,
					signalId: config.signalName,
					visualizationType,
					unit: config.unitUcum,
					signals: []
				};
			}

			acc[groupKey].signals.push({
				id: signal.id,
				timestamp: signal.timestamp,
				signalName: signal.signalName,
				signalValue: signal.signalValue,
				coordinates: signal.coordinates,
				confidence: signal.confidence,
				sourceEventId: signal.sourceEventId,
				sourceMetadata: signal.sourceMetadata,
				unit: config.unitUcum
			});

			return acc;
		}, {} as Record<string, any>);

		// Query for signal statistics to show contributing signals
		// Note: We use MAX for the JSON field extraction to avoid GROUP BY issues
		const signalStats = await db
			.select({
				sourceName: signalConfigs.sourceName,
				signalId: signalConfigs.signalName,
				signalType: sql<string>`MAX(${signalConfigs.computation}->>'value_type')`,
				displayName: signalConfigs.displayName,
				eventCount: sql<number>`COUNT(DISTINCT ${signals.id})`,
			})
			.from(signalConfigs)
			.innerJoin(sourceConfigs, eq(signalConfigs.sourceName, sourceConfigs.name))
			.leftJoin(
				signals,
				and(
					eq(signalConfigs.id, signals.signalId),
					gte(signals.timestamp, startOfDay),
					lte(signals.timestamp, endOfDay)
				)
			)
			.groupBy(signalConfigs.sourceName, signalConfigs.signalName, signalConfigs.displayName);

		// Calculate coverage percentage for each signal
		const contributingSignals = signalStats
			.filter(stat => stat.eventCount > 0)
			.map(stat => ({
				...stat,
				displayName: stat.displayName,
				coverage: Math.min(100, Math.round((stat.eventCount / 288) * 100)) // 288 = 24 hours * 12 (5-min intervals)
			}));

		// Query signal transitions
		const transitionResults = await db
			.select()
			.from(signalTransitions)
			.where(
				and(
					gte(signalTransitions.transitionTime, startOfDay),
					lte(signalTransitions.transitionTime, endOfDay)
				)
			)
			.orderBy(signalTransitions.sourceName, signalTransitions.transitionTime);

		// Group transitions by signal
		const signalTransitionsBySource = transitionResults.reduce((acc, transition) => {
			const key = transition.signalName;
			if (!acc[key]) {
				acc[key] = [];
			}

			// Parse metadata if it's a string
			let metadata: any = transition.transitionMetadata;
			if (typeof metadata === 'string') {
				try {
					metadata = JSON.parse(metadata);
				} catch (e) {
					metadata = {};
				}
			}

			// Map database fields to expected frontend format
			// Use before/after means as state representation
			const fromState = transition.beforeMean !== null ? transition.beforeMean.toString() : 'unknown';
			const toState = transition.afterMean !== null ? transition.afterMean.toString() : 'unknown';

			acc[key].push({
				id: transition.id,
				transitionTime: transition.transitionTime.toISOString(),
				fromState: fromState,
				toState: toState,
				transitionType: transition.transitionType,
				changeMagnitude: transition.changeMagnitude,
				changeDirection: transition.changeDirection,
				beforeMean: transition.beforeMean,
				beforeStd: transition.beforeStd,
				afterMean: transition.afterMean,
				afterStd: transition.afterStd,
				confidence: transition.confidence,
				detectionMethod: transition.detectionMethod,
				metadata: metadata || {}
			});

			return acc;
		}, {} as Record<string, any[]>);

		// Query HDBSCAN events that overlap with the selected day in user's timezone
		// This catches events that may start in the previous UTC day or end in the next UTC day
		// but are part of the user's experience of this day in their timezone
		const eventsResults = await db
			.select()
			.from(events)
			.where(
				and(
					lte(events.startTime, endOfDay),
					gte(events.endTime, startOfDay)
				)
			)
			.orderBy(events.startTime);

		// Format events for the UI
		const hdbscanEvents = eventsResults.map(event => ({
			id: event.id,
			clusterId: event.clusterId,
			startTime: event.startTime.toISOString(),
			endTime: event.endTime.toISOString(),
			coreDensity: event.coreDensity,
			clusterSize: event.clusterSize,
			persistence: event.persistence,
			transitionIds: event.transitionIds,
			signalContributions: typeof event.signalContributions === 'string'
				? JSON.parse(event.signalContributions as string)
				: event.signalContributions,
			metadata: typeof event.eventMetadata === 'string'
				? JSON.parse(event.eventMetadata as string)
				: event.eventMetadata,
			eventType: event.eventType || 'activity'
		}));

		return {
			signalsByName: Object.values(signalsByName),
			selectedDate: `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`,
			contributingSignals,
			signalTransitionsBySource,
			hdbscanEvents,
			userTimezone,
			// Keep these for backward compatibility with the frontend
			ambientSignalsBySignalName: Object.values(signalsByName),
			episodicSignalsBySignalId: [],
			boundaryEvents: [],
			signalBoundariesBySource: {}
		};
	} catch (error) {
		console.error('Signal analysis page error:', error);
		return {
			signalsByName: [],
			ambientSignalsBySignalName: [],
			episodicSignalsBySignalId: [],
			selectedDate: new Date().toISOString(),
			contributingSignals: [],
			boundaryEvents: [],
			signalBoundariesBySource: {},
			signalTransitionsBySource: {},
			hdbscanEvents: [],
			userTimezone: 'America/Chicago',
			error: error instanceof Error ? error.message : 'Failed to load signal analysis data'
		};
	}
};