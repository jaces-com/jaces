import type { PageServerLoad } from './$types';
import { db } from '$lib/db/client';
import { signals, signalConfigs, sourceConfigs, events } from '$lib/db/schema';
import { eq, and, gte, lte } from 'drizzle-orm';
import { parseDate, toZoned, now } from '@internationalized/date';

export const load: PageServerLoad = async ({ url }) => {
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
		
		// Query events that overlap with the selected day in user's timezone
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
		const timelineEvents = eventsResults.map(event => {
			// Parse signal contributions to generate summary
			let signalContributions = {};
			if (event.signalContributions) {
				try {
					signalContributions = typeof event.signalContributions === 'string' 
						? JSON.parse(event.signalContributions as string)
						: event.signalContributions;
				} catch (e) {
					console.error('Failed to parse signal contributions:', e);
				}
			}
			
			// Parse event metadata
			let metadata = {};
			if (event.eventMetadata) {
				try {
					metadata = typeof event.eventMetadata === 'string'
						? JSON.parse(event.eventMetadata as string)
						: event.eventMetadata;
				} catch (e) {
					console.error('Failed to parse event metadata:', e);
				}
			}
			
			// Generate summary from dominant signal
			let summary = 'Unknown Activity';
			if (Object.keys(signalContributions).length > 0) {
				// Find the dominant signal
				const dominantSignal = Object.entries(signalContributions)
					.sort(([,a], [,b]) => (b as number) - (a as number))[0];
				
				if (dominantSignal) {
					const [signalName] = dominantSignal;
					// Map signal names to user-friendly summaries
					const signalSummaryMap: Record<string, string> = {
						'ios_speed': 'Movement',
						'ios_coordinates': 'Location Activity',
						'ios_activity': 'Physical Activity',
						'ios_environmental_sound': 'Environmental Activity',
						'ios_mic_transcription': 'Conversation',
						'mac_apps': 'Computer Work',
						'google_calendar_events': 'Calendar Event'
					};
					summary = signalSummaryMap[signalName] || signalName.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
				}
			}
			
			// Use event type if it's a special type
			if (event.eventType && event.eventType !== 'activity') {
				if (event.eventType === 'unknown') {
					summary = 'Unknown Activity';
				} else {
					summary = event.eventType.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
				}
			}
			
			return {
				id: event.id,
				clusterId: event.clusterId,
				startTime: event.startTime.toISOString(),
				endTime: event.endTime.toISOString(),
				summary,
				confidence: metadata.avg_confidence || event.coreDensity || 0.5,
				coreDensity: event.coreDensity,
				clusterSize: event.clusterSize,
				persistence: event.persistence,
				transitionIds: event.transitionIds,
				signalContributions,
				metadata,
				eventType: event.eventType || 'activity'
			};
		});
		
		return {
			ambientSignalsBySignalName: Object.values(ambientSignalsBySignalName),
			episodicSignalsBySignalId: Object.values(episodicSignalsBySignalId),
			timelineEvents,
			selectedDate: `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`,
			userTimezone
		};
		
	} catch (error) {
		console.error('Error loading signals:', error);
		return {
			ambientSignalsBySignalName: [],
			episodicSignalsBySignalId: [],
			selectedDate: new Date().toISOString(),
			timelineEvents: [],
			userTimezone: 'America/Chicago',
			error: 'Failed to load signals'
		};
	}
};