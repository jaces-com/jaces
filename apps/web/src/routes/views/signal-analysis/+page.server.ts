import type { PageServerLoad } from './$types';
import { db } from '$lib/db/client';
import { signals, signalConfigs, sourceConfigs, signalTransitions, events } from '$lib/db/schema';
import { eq, and, gte, lte, sql } from 'drizzle-orm';
import { parseDate, toZoned, now } from '@internationalized/date';

export const load: PageServerLoad = async ({ url, depends }) => {
	// Register dependencies for granular invalidation
	depends('signal-analysis:ambient-signals');
	depends('signal-analysis:episodic-signals');
	depends('signal-analysis:transitions');
	depends('signal-analysis:boundaries');

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

		// Episodic signals are now stored in ambient_signals with event visualization type
		const episodicData: any[] = [];

		// Group ambient signals by sourceName + signalName to avoid duplicates
		const ambientSignalsBySignalName = ambientData.reduce((acc, { ambientSignal, signal, source }) => {
			// Skip old signal names that don't match the registered signal
			if (ambientSignal.signalName !== signal.signalName) {
				return acc;
			}

			const groupKey = `${ambientSignal.sourceName}_${ambientSignal.signalName}`;
			if (!acc[groupKey]) {
				const wizardConfig = source.wizardConfig as any;
				acc[groupKey] = {
					signalName: ambientSignal.signalName,
					displayName: signal.displayName,
					sourceName: ambientSignal.sourceName,
					signalId: signal.signalName,
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
				signalType: signal.computation?.value_type || 'continuous',
				unit: signal.unitUcum
			});

			return acc;
		}, {} as Record<string, any>);

		// Episodic signals no longer exist as a separate table
		const episodicSignalsBySignalId = {} as Record<string, any>;

		// Query for signal statistics to show contributing signals
		const signalStats = await db
			.select({
				sourceName: signalConfigs.sourceName,
				signalId: signalConfigs.signalName,
				signalType: sql<string>`${signalConfigs.computation}->>'value_type'`,
				displayName: signalConfigs.displayName,
				type: sql<string>`CASE WHEN ${signalConfigs.computation}->>'value_type' = 'event' THEN 'episodic' ELSE 'ambient' END`,
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
			.groupBy(signalConfigs.sourceName, signalConfigs.signalName, signalConfigs.computation, signalConfigs.displayName);

		// Calculate coverage percentage for each signal
		const contributingSignals = signalStats
			.filter(stat => stat.eventCount > 0)
			.map(stat => ({
				...stat,
				displayName: stat.displayName,
				coverage: Math.min(100, Math.round((stat.eventCount / 288) * 100)) // 288 = 24 hours * 12 (5-min intervals)
			}));

		// Boundary detection removed - focusing on transitions
		const boundaryEvents: any[] = [];
		
		// Original boundary detection code commented out:
		/*
		const consolidatedBoundaryResults = await db
			.select()
			.from(boundaryDetections)
			.where(
				and(
					eq(boundaryDetections.userId, userId),
					lte(boundaryDetections.startTime, endOfDay),
					gte(boundaryDetections.endTime, startOfDay),
					// Only show consolidated boundaries at the top
					sql`${boundaryDetections.boundaryScope} IN ('multi_signal', 'all_signals')`
				)
			)
			.orderBy(boundaryDetections.startTime);

		// Format consolidated boundary events for the UI
		const boundaryEvents = consolidatedBoundaryResults.map(boundary => ({
			id: boundary.id,
			startTime: boundary.startTime.toISOString(),
			endTime: boundary.endTime.toISOString(),
			confidence: boundary.confidence,
			contributingSources: boundary.contributingSources,
			detectionMethod: boundary.detectionMethod,
			boundaryScope: boundary.boundaryScope,
			sourceSignal: boundary.sourceSignal ?? undefined
		}));
		*/

		// Initialize empty signalBoundariesBySource for compatibility
		const signalBoundariesBySource: Record<string, any[]> = {};

		/* Commented out single signal boundaries
		// Query single-signal boundaries grouped by source signal
		// These show up in the individual signals section as "COMPUTED EVENTS"
		const singleSignalBoundaries = await db
			.select()
			.from(boundaryDetections)
			.where(
				and(
					eq(boundaryDetections.userId, userId),
					lte(boundaryDetections.startTime, endOfDay),
					gte(boundaryDetections.endTime, startOfDay),
					eq(boundaryDetections.boundaryScope, 'single_signal')
				)
			)
			.orderBy(boundaryDetections.sourceSignal, boundaryDetections.startTime);

		// Group single signal boundaries by source signal
		const signalBoundariesBySource = singleSignalBoundaries.reduce((acc, boundary) => {
			const key = boundary.sourceSignal || 'unknown';
			if (!acc[key]) {
				acc[key] = [];
			}
			acc[key].push({
				id: boundary.id,
				startTime: boundary.startTime.toISOString(),
				endTime: boundary.endTime.toISOString(),
				confidence: boundary.confidence,
				summary: 'Computed boundary', // Will be enhanced with metadata
				detectionMethod: boundary.detectionMethod,
				metadata: {} // Will be populated from signal_boundaries if needed
			});
			return acc;
		}, {} as Record<string, any[]>);
		*/

		/* Also comment out signal boundaries metadata query
		// Query the detailed signal boundaries table for richer metadata
		const signalBoundaryResults = await db
			.select()
			.from(signalBoundaries)
			.where(
				and(
					eq(signalBoundaries.userId, userId),
					// Get boundaries that overlap with the selected day
					// A boundary overlaps if it starts before end of day AND ends after start of day
					lte(signalBoundaries.startTime, endOfDay),
					gte(signalBoundaries.endTime, startOfDay)
				)
			)
			.orderBy(signalBoundaries.sourceName, signalBoundaries.startTime);

		// If no single-signal boundaries in boundary_detections, use signal_boundaries as fallback
		signalBoundaryResults.forEach(boundary => {

			// Key should match frontend expectation: sourceName_signalName
			// For iOS speed: sourceName="ios", signalName="ios_speed" -> key should be "ios_speed"
			// The signalName already contains the full signal identifier
			const key = boundary.signalName;

			// Parse metadata if it's a string
			let metadata: any = boundary.boundaryMetadata;
			if (typeof metadata === 'string') {
				try {
					metadata = JSON.parse(metadata);
				} catch (e) {
					metadata = {};
				}
			}

			// Always add to signalBoundariesBySource (don't try to match with existing)
			if (!signalBoundariesBySource[key]) {
				signalBoundariesBySource[key] = [];
			}
			signalBoundariesBySource[key].push({
				id: boundary.id,
				startTime: boundary.startTime.toISOString(),
				endTime: boundary.endTime.toISOString(),
				confidence: boundary.confidence,
				summary: metadata?.description || metadata?.state || 'Unknown',
				detectionMethod: boundary.detectionMethod,
				metadata: metadata || {}
			});
		});
		*/

		// Query signal transitions for ambient signals
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
			let metadata: any = transition.metadata;
			if (typeof metadata === 'string') {
				try {
					metadata = JSON.parse(metadata);
				} catch (e) {
					metadata = {};
				}
			}

			acc[key].push({
				id: transition.id,
				transitionTime: transition.transitionTime.toISOString(),
				fromState: transition.fromState,
				toState: transition.toState,
				confidence: transition.confidence,
				detectionMethod: transition.detectionMethod,
				metadata: metadata || {}
			});

			return acc;
		}, {} as Record<string, any[]>);

		// Query HDBSCAN events for the day
		const eventsResults = await db
			.select()
			.from(events)
			.where(eq(events.date, `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`))
			.orderBy(events.startTime);

		// Format events for the UI
		const hdbscanEvents = eventsResults.map(event => ({
			id: event.id,
			clusterId: event.clusterId,
			startTime: event.startTime,
			endTime: event.endTime,
			coreDensity: event.coreDensity,
			clusterSize: event.clusterSize,
			persistence: event.persistence,
			transitionIds: event.transitionIds,
			signalContributions: typeof event.signalContributions === 'string' 
				? JSON.parse(event.signalContributions as string)
				: event.signalContributions,
			metadata: typeof event.metadata === 'string'
				? JSON.parse(event.metadata as string)
				: event.metadata,
			eventType: event.eventType || 'activity'
		}));

		return {
			ambientSignalsBySignalName: Object.values(ambientSignalsBySignalName),
			episodicSignalsBySignalId: Object.values(episodicSignalsBySignalId),
			selectedDate: `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`,
			contributingSignals,
			boundaryEvents,
			signalBoundariesBySource,
			signalTransitionsBySource,
			hdbscanEvents,
			userTimezone
		};

	} catch (error) {
		console.error('Signal analysis page error:', error);
		return {
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