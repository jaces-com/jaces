// src/routes/location/+page.server.ts

import type { PageServerLoad } from './$types';
import { db } from '$lib/db/client';
import { signals } from '$lib/db/schema';
import { eq, and, gte, lte, isNotNull } from 'drizzle-orm';

// Correctly import the necessary functions
import { now, parseDate, toZoned } from '@internationalized/date';

export const load: PageServerLoad = async () => {
	try {
		// Default timezone for single-user app
		const userTimezone = 'America/Chicago';

		// Get today's date in the user's timezone
		const todayZoned = now(userTimezone);

		// Create a CalendarDate object for today (year, month, day only)
		const calendarDate = parseDate(
			`${todayZoned.year}-${String(todayZoned.month).padStart(2, '0')}-${String(
				todayZoned.day
			).padStart(2, '0')}`
		);

		// Convert the CalendarDate to a ZonedDateTime to get the start of the day
		const zonedStart = toZoned(calendarDate, userTimezone);

		// Add time to the start to get the end of the day
		const zonedEnd = zonedStart.add({ hours: 23, minutes: 59, seconds: 59, milliseconds: 999 });

		// Convert to standard JS Date objects for the database query
		const startOfDayUTC = zonedStart.toDate();
		const endOfDayUTC = zonedEnd.toDate();

		const rawCoordinateSignals = await db
			.select({
				coordinates: signals.coordinates,
				timestamp: signals.timestamp,
				signalValue: signals.signalValue,
				confidence: signals.confidence
			})
			.from(signals)
			.where(
				and(
					eq(signals.signalName, 'apple_ios_coordinates'),
					gte(signals.timestamp, startOfDayUTC),
					lte(signals.timestamp, endOfDayUTC),
					isNotNull(signals.coordinates)
				)
			)
			.orderBy(signals.timestamp);

		// Filter out records without valid coordinates and ensure proper format
		const coordinateSignals = rawCoordinateSignals
			.filter(signal => signal.coordinates !== null)
			.map(signal => ({
				...signal,
				// Ensure coordinates are in [longitude, latitude] format
				coordinates: signal.coordinates as [number, number]
			}));

		return {
			coordinateSignals,
			selectedDate: calendarDate.toString(),
			userTimezone
		};
	} catch (error) {
		console.error('Failed to load coordinate signals:', error);
		return {
			coordinateSignals: [],
			selectedDate: now('America/Chicago').toString().split('T')[0],
			userTimezone: 'America/Chicago',
			error: error instanceof Error ? error.message : 'Failed to load data'
		};
	}
};