<script lang="ts">
    import { Page, Button } from "$lib/components";
    import type { PageData } from "./$types";

    let { data }: { data: PageData } = $props();

    // Timeline configuration
    let containerWidth = $state(1200); // Will be updated dynamically
    const timeRange = 24; // Always show full day
    const minutesInRange = $derived(timeRange * 60);
    const pixelsPerMinute = $derived((containerWidth - 40) / minutesInRange); // Subtract padding to prevent scroll

    // Mock data types
    interface TimelineEvent {
        id: string;
        startTime: Date;
        endTime: Date;
        summary?: string;
        confidence: number;
        source?: string;
        type?: "master" | "episodic" | "ambient" | "felt";
    }

    interface RawSignal {
        timestamp: Date;
        value: number | string;
        label?: string;
    }

    interface SourceTimeline {
        name: string;
        displayName: string;
        company: "apple" | "google";
        type: "episodic" | "ambient";
        visualizationType?:
            | "continuous"
            | "binary"
            | "categorical"
            | "spatial"
            | "episodic";
        events: TimelineEvent[];
        feltEvents?: TimelineEvent[]; // For ambient sources - FELT processed events
        rawSignals?: RawSignal[]; // For ambient sources - raw data points
        signalRange?: {
            // Min/max values for normalization
            min: number;
            max: number;
            unit: string;
        };
    }

    // State
    let selectedDate = $state(
        data.selectedDate
            ? new Date(data.selectedDate).toISOString().split("T")[0]
            : new Date().toISOString().split("T")[0],
    ); // Format as YYYY-MM-DD
    let timelineContainer: HTMLDivElement;
    let currentTimePosition = $state(0);
    let selectedMasterEventId = $state<string | null>(null);
    let hoveredEventId = $state<string | null>(null);
    // Initialize with all ambient source names to show raw signals by default
    let expandedAmbientSources = $state(new Set<string>());
    let expandedEpisodicSources = $state(new Set<string>());

    // Will be populated after mock data is generated
    function initializeExpandedSources() {
        // Clear and re-add all ambient source names
        expandedAmbientSources.clear();
        sourceTimelines
            .filter((s) => s.type === "ambient")
            .forEach((source) => {
                expandedAmbientSources.add(source.name);
            });

        // Clear and re-add all episodic source names to show raw data by default
        expandedEpisodicSources.clear();
        sourceTimelines
            .filter((s) => s.type === "episodic")
            .forEach((source) => {
                expandedEpisodicSources.add(source.name);
            });
    }

    // Mock master events (result of FELT + sweep line)
    let masterEvents = $state<TimelineEvent[]>([]);

    // Mock source timelines
    let sourceTimelines = $state<SourceTimeline[]>([]);

    // Separate episodic and ambient sources
    const episodicSources = $derived(
        sourceTimelines.filter((s) => s.type === "episodic"),
    );
    const ambientSources = $derived(
        sourceTimelines.filter((s) => s.type === "ambient"),
    );

    // Convert time to pixel position
    function timeToPixel(date: Date): number {
        const hours = date.getHours();
        const minutes = date.getMinutes();
        const totalMinutes = hours * 60 + minutes;

        // If showing less than 24 hours, offset based on time range
        if (timeRange < 24) {
            const startHour = 12 - timeRange / 2; // Center around noon
            const startMinutes = startHour * 60;
            return (totalMinutes - startMinutes) * pixelsPerMinute;
        }

        return totalMinutes * pixelsPerMinute;
    }

    // Get event width in pixels
    function getEventWidth(start: Date, end: Date): number {
        return timeToPixel(end) - timeToPixel(start);
    }

    // Toggle ambient source expansion
    function toggleAmbientSource(sourceName: string) {
        if (expandedAmbientSources.has(sourceName)) {
            expandedAmbientSources.delete(sourceName);
        } else {
            expandedAmbientSources.add(sourceName);
        }
    }

    // Toggle episodic source expansion
    function toggleEpisodicSource(sourceName: string) {
        if (expandedEpisodicSources.has(sourceName)) {
            expandedEpisodicSources.delete(sourceName);
        } else {
            expandedEpisodicSources.add(sourceName);
        }
    }

    // Format time for display
    function formatTime(date: Date): string {
        return date.toLocaleTimeString("en-US", {
            hour: "numeric",
            minute: "2-digit",
            hour12: true,
        });
    }

    // Get visualization height based on type
    function getVisualizationHeight(type: string): number {
        const heights: Record<string, number> = {
            binary: 32,
            continuous: 48,
            categorical: 64,
            spatial: 40,
            episodic: 48,
        };
        return heights[type] || 40;
    }

    // Generate consistent color from string
    function stringToColor(str: string): string {
        if (!str) return "hsl(0, 0%, 50%)";
        const hash = str
            .split("")
            .reduce((acc, char) => char.charCodeAt(0) + ((acc << 5) - acc), 0);
        return `hsl(${Math.abs(hash) % 360}, 70%, 50%)`;
    }

    // Get unique categories from signals
    function getUniqueCategories(signals: any[]): string[] {
        const categories = new Set<string>();
        signals.forEach((signal) => {
            if (signal.category || signal.value) {
                categories.add(signal.category || signal.value);
            }
        });
        return Array.from(categories);
    }

    // Cluster binary signals into continuous activity periods
    function clusterBinarySignals(
        signals: any[],
        gapThreshold: number = 5 * 60 * 1000,
    ) {
        if (!signals || signals.length === 0) return [];

        const sorted = [...signals].sort(
            (a, b) =>
                new Date(a.timestamp).getTime() -
                new Date(b.timestamp).getTime(),
        );

        const clusters = [];
        let currentCluster = {
            startTime: new Date(sorted[0].timestamp),
            endTime: new Date(sorted[0].timestamp),
            label: sorted[0].label || sorted[0].value,
            count: 1,
        };

        for (let i = 1; i < sorted.length; i++) {
            const signal = sorted[i];
            const timestamp = new Date(signal.timestamp);
            const gap = timestamp.getTime() - currentCluster.endTime.getTime();

            if (gap <= gapThreshold && signal.label === currentCluster.label) {
                // Extend current cluster
                currentCluster.endTime = timestamp;
                currentCluster.count++;
            } else {
                // Start new cluster
                clusters.push(currentCluster);
                currentCluster = {
                    startTime: timestamp,
                    endTime: timestamp,
                    label: signal.label || signal.value,
                    count: 1,
                };
            }
        }

        // Add the last cluster
        clusters.push(currentCluster);

        return clusters;
    }

    // Group categorical signals into continuous events
    function categorizeContinuousEvents(
        signals: any[],
        gapThreshold: number = 2 * 60 * 1000,
    ) {
        if (!signals || signals.length === 0) return [];

        const sorted = [...signals].sort(
            (a, b) =>
                new Date(a.timestamp).getTime() -
                new Date(b.timestamp).getTime(),
        );

        const events = [];
        let currentEvent = {
            startTime: new Date(sorted[0].timestamp),
            endTime: new Date(sorted[0].timestamp),
            category: sorted[0].category || sorted[0].value || "Unknown",
            count: 1,
        };

        for (let i = 1; i < sorted.length; i++) {
            const signal = sorted[i];
            const timestamp = new Date(signal.timestamp);
            const category = signal.category || signal.value || "Unknown";
            const gap = timestamp.getTime() - currentEvent.endTime.getTime();

            if (gap <= gapThreshold && category === currentEvent.category) {
                // Extend current event
                currentEvent.endTime = timestamp;
                currentEvent.count++;
            } else {
                // Start new event
                if (
                    currentEvent.endTime.getTime() -
                        currentEvent.startTime.getTime() ===
                    0
                ) {
                    // Single point, extend by 1 minute for visibility
                    currentEvent.endTime = new Date(
                        currentEvent.endTime.getTime() + 60 * 1000,
                    );
                }
                events.push(currentEvent);
                currentEvent = {
                    startTime: timestamp,
                    endTime: timestamp,
                    category: category,
                    count: 1,
                };
            }
        }

        // Add the last event
        if (
            currentEvent.endTime.getTime() -
                currentEvent.startTime.getTime() ===
            0
        ) {
            currentEvent.endTime = new Date(
                currentEvent.endTime.getTime() + 60 * 1000,
            );
        }
        events.push(currentEvent);

        return events;
    }

    // Calculate distance between two GPS coordinates using Haversine formula
    function calculateDistance(
        lat1: number,
        lon1: number,
        lat2: number,
        lon2: number,
    ): number {
        const R = 6371000; // Earth's radius in meters
        const φ1 = (lat1 * Math.PI) / 180;
        const φ2 = (lat2 * Math.PI) / 180;
        const Δφ = ((lat2 - lat1) * Math.PI) / 180;
        const Δλ = ((lon2 - lon1) * Math.PI) / 180;

        const a =
            Math.sin(Δφ / 2) * Math.sin(Δφ / 2) +
            Math.cos(φ1) * Math.cos(φ2) * Math.sin(Δλ / 2) * Math.sin(Δλ / 2);
        const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));

        return R * c; // Distance in meters
    }

    // Analyze spatial movement patterns
    function analyzeSpatialMovement(
        signals: any[],
        speedThreshold: number = 0.5,
    ) {
        if (!signals || signals.length === 0) return [];

        const sorted = [...signals].sort(
            (a, b) =>
                new Date(a.timestamp).getTime() -
                new Date(b.timestamp).getTime(),
        );

        const segments = [];
        let currentSegment = {
            startTime: new Date(sorted[0].timestamp),
            endTime: new Date(sorted[0].timestamp),
            isMoving: false,
            speed: 0,
            distance: 0,
            points: 1,
        };

        for (let i = 1; i < sorted.length; i++) {
            const prevSignal = sorted[i - 1];
            const signal = sorted[i];
            const timestamp = new Date(signal.timestamp);

            // Calculate speed and distance from actual coordinates
            let speed = 0;
            let distance = 0;

            if (signal.coordinates && prevSignal.coordinates) {
                // Parse coordinates - they might be stored as JSON string or object
                let coords1, coords2;

                try {
                    coords1 =
                        typeof prevSignal.coordinates === "string"
                            ? JSON.parse(prevSignal.coordinates)
                            : prevSignal.coordinates;
                    coords2 =
                        typeof signal.coordinates === "string"
                            ? JSON.parse(signal.coordinates)
                            : signal.coordinates;
                } catch (e) {
                    console.error("Failed to parse coordinates:", e);
                    continue;
                }

                // Extract lat/lon - handle different possible formats
                const lat1 = coords1.latitude || coords1.lat || coords1[0];
                const lon1 =
                    coords1.longitude ||
                    coords1.lon ||
                    coords1.lng ||
                    coords1[1];
                const lat2 = coords2.latitude || coords2.lat || coords2[0];
                const lon2 =
                    coords2.longitude ||
                    coords2.lon ||
                    coords2.lng ||
                    coords2[1];

                if (lat1 && lon1 && lat2 && lon2) {
                    // Calculate actual distance
                    distance = calculateDistance(lat1, lon1, lat2, lon2);

                    // Calculate speed in m/s
                    const timeDiff =
                        (timestamp.getTime() -
                            new Date(prevSignal.timestamp).getTime()) /
                        1000; // seconds
                    if (timeDiff > 0) {
                        speed = distance / timeDiff;
                    }
                }
            }

            const isMoving = speed > speedThreshold;

            // Check if we should continue current segment or start new one
            if (isMoving === currentSegment.isMoving) {
                // Continue segment
                currentSegment.endTime = timestamp;
                currentSegment.speed =
                    (currentSegment.speed * currentSegment.points + speed) /
                    (currentSegment.points + 1);
                currentSegment.distance += distance;
                currentSegment.points++;
            } else {
                // Start new segment
                if (
                    currentSegment.endTime.getTime() -
                        currentSegment.startTime.getTime() ===
                    0
                ) {
                    currentSegment.endTime = new Date(
                        currentSegment.endTime.getTime() + 60 * 1000,
                    );
                }
                segments.push(currentSegment);
                currentSegment = {
                    startTime: timestamp,
                    endTime: timestamp,
                    isMoving: isMoving,
                    speed: speed,
                    distance: distance,
                    points: 1,
                };
            }
        }

        // Add the last segment
        if (
            currentSegment.endTime.getTime() -
                currentSegment.startTime.getTime() ===
            0
        ) {
            currentSegment.endTime = new Date(
                currentSegment.endTime.getTime() + 60 * 1000,
            );
        }
        segments.push(currentSegment);

        return segments;
    }

    // Check if a source event overlaps with selected master event
    function isContributingToMasterEvent(
        sourceEvent: TimelineEvent,
        masterEvent: TimelineEvent,
    ): boolean {
        return (
            sourceEvent.startTime < masterEvent.endTime &&
            sourceEvent.endTime > masterEvent.startTime
        );
    }

    // Get contributing sources for a master event
    function getContributingSources(masterEventId: string): Set<string> {
        const masterEvent = masterEvents.find((e) => e.id === masterEventId);
        if (!masterEvent) return new Set();

        const sources = new Set<string>();
        sourceTimelines.forEach((timeline) => {
            // Check regular events for episodic sources
            timeline.events.forEach((event) => {
                if (isContributingToMasterEvent(event, masterEvent)) {
                    sources.add(timeline.name);
                }
            });

            // Check FELT events for ambient sources
            if (timeline.feltEvents) {
                timeline.feltEvents.forEach((event) => {
                    if (isContributingToMasterEvent(event, masterEvent)) {
                        sources.add(timeline.name);
                    }
                });
            }
        });
        return sources;
    }

    // Handle master event click
    function handleMasterEventClick(eventId: string) {
        selectedMasterEventId =
            selectedMasterEventId === eventId ? null : eventId;
    }

    // Generate mock data
    /* Commented out - using real data from database
	function generateMockData() {
		// Parse the YYYY-MM-DD string to create a local date
		const [year, month, day] = selectedDate.split('-').map(Number);
		const today = new Date(year, month - 1, day); // month is 0-indexed
		today.setHours(0, 0, 0, 0);

			// Generate exactly 16 master events to fill 24-hour period
		const masterEventTemplates = [
			// Early morning - 6 hours
			{ start: 0, duration: 6, summary: 'Sleep', confidence: 0.75 },

			// Morning - 3 hours
			{ start: 6, duration: 1, summary: 'Morning Routine', confidence: 0.85 },
			{ start: 7, duration: 1, summary: 'Breakfast', confidence: 0.92 },
			{ start: 8, duration: 1, summary: 'Commute to Work', confidence: 0.25 }, // RED - low confidence

			// Work morning - 3 hours
			{ start: 9, duration: 1, summary: 'Team Standup', confidence: 0.95 },
			{ start: 10, duration: 2, summary: 'Deep Work Session', confidence: 0.82 },

			// Lunch - 2 hours
			{ start: 12, duration: 1, summary: 'Lunch Break', confidence: 0.95 },
			{ start: 13, duration: 1, summary: 'Walk / Break', confidence: 0.45 }, // YELLOW - medium confidence

			// Afternoon work - 4 hours
			{ start: 14, duration: 2, summary: 'Client Meeting & Work', confidence: 0.9 },
			{ start: 16, duration: 2, summary: 'Project Work', confidence: 0.85 },

			// Evening - 3 hours
			{ start: 18, duration: 1, summary: 'Commute Home', confidence: 0.88 },
			{ start: 19, duration: 2, summary: 'Dinner & Family Time', confidence: 0.9 },

			// Night - 3 hours
			{ start: 21, duration: 1.5, summary: 'Personal Time', confidence: 0.55 }, // YELLOW - medium confidence
			{ start: 22.5, duration: 1.5, summary: 'Evening Routine', confidence: 0.85 }
		];

		// Verify no overlaps and fill gaps to ensure exactly 16 events covering 24 hours
		let lastEndTime = 0;
		const finalEvents = [];

		for (let i = 0; i < masterEventTemplates.length; i++) {
			const template = masterEventTemplates[i];

			// Fill gap if there is one
			if (template.start > lastEndTime) {
				finalEvents.push({
					start: lastEndTime,
					duration: template.start - lastEndTime,
					summary: 'Unknown Activity',
					confidence: 0.25
				});
			}

			finalEvents.push(template);
			lastEndTime = template.start + template.duration;
		}

		// Fill remaining time to reach 24 hours
		if (lastEndTime < 24) {
			finalEvents.push({
				start: lastEndTime,
				duration: 24 - lastEndTime,
				summary: 'Sleep',
				confidence: 0.75
			});
		}

		// Create master events from final templates
		masterEvents = finalEvents
			.sort((a, b) => a.start - b.start)
			.map((template, index) => ({
				id: `master-${index + 1}`,
				startTime: new Date(today.getTime() + template.start * 60 * 60 * 1000),
				endTime: new Date(today.getTime() + (template.start + template.duration) * 60 * 60 * 1000),
				summary: template.summary,
				confidence: template.confidence,
				type: 'master' as const
			}));

		// Verify no overlaps
		for (let i = 1; i < masterEvents.length; i++) {
			const prev = masterEvents[i - 1];
			const curr = masterEvents[i];
			if (prev.endTime > curr.startTime) {
				console.error(`Overlap detected between events ${i} and ${i + 1}`);
			}
		}

		// Helper function to convert real ambient signals to RawSignal format with range
		const convertAmbientSignalsToRaw = (sourceName: string): { signals: RawSignal[], range?: { min: number, max: number, unit: string } } => {
			const sourceData = data.ambientSignalsBySource?.find(s => s.sourceName === sourceName);
			if (!sourceData) {
				// Fallback to mock data if no real data
				const generateRawSignals = (startHour: number, endHour: number, interval: number = 5): RawSignal[] => {
					const signals: RawSignal[] = [];
					for (let h = startHour; h < endHour; h++) {
						for (let m = 0; m < 60; m += interval) {
							signals.push({
								timestamp: new Date(today.getTime() + (h * 60 + m) * 60 * 1000),
								value: Math.random() * 30, // Mock speeds 0-30 m/s
								label: ''
							});
						}
					}
					return signals;
				};
				// Default intervals for different sources
				let mockSignals: RawSignal[] = [];
				if (sourceName === 'apple_watch_heart_rate') mockSignals = generateRawSignals(6, 22, 2);
				else if (sourceName === 'apple_ios_sound_classification') mockSignals = generateRawSignals(8, 20, 1);
				else if (sourceName === 'apple_ios_gps') mockSignals = generateRawSignals(0, 24, 10);
				else mockSignals = generateRawSignals(0, 24, 5);

				// Calculate range for mock data
				const values = mockSignals.map(s => s.value as number);
				return {
					signals: mockSignals,
					range: values.length > 0 ? {
						min: Math.min(...values),
						max: Math.max(...values),
						unit: 'm/s'
					} : undefined
				};
			}

			// Convert real signals to RawSignal format - only show speed for movement visualization
			const speedSignals = sourceData.signals
				.filter((signal: any) => signal.signalName === 'speed')
				.map((signal: any) => {
					// Speed values are already numeric
					const value = parseFloat(signal.signalValue) || 0;

					return {
						timestamp: new Date(signal.timestamp),
						value,
						label: 'speed'
					};
				});

			// Calculate min/max for real data
			const values = speedSignals.map(s => s.value as number);
			const range = values.length > 0 ? {
				min: Math.min(...values),
				max: Math.max(...values),
				unit: 'm/s'
			} : undefined;

			return { signals: speedSignals, range };
		};

		sourceTimelines = [
			// Episodic Sources
			{
				name: 'google_api_calendar',
				displayName: 'Google Calendar',
				company: 'google' as const,
				type: 'episodic' as const,
				events: [
					{
						id: 'gcal-1',
						startTime: new Date(today.getTime() + 9 * 60 * 60 * 1000),
						endTime: new Date(today.getTime() + 10 * 60 * 60 * 1000),
						summary: 'Team Standup',
						confidence: 0.95,
						source: 'google_api_calendar',
						type: 'episodic' as const
					},
					{
						id: 'gcal-2',
						startTime: new Date(today.getTime() + 12 * 60 * 60 * 1000),
						endTime: new Date(today.getTime() + 13 * 60 * 60 * 1000),
						summary: 'Lunch Meeting',
						confidence: 0.95,
						source: 'google_api_calendar',
						type: 'episodic' as const
					},
					{
						id: 'gcal-3',
						startTime: new Date(today.getTime() + 14 * 60 * 60 * 1000),
						endTime: new Date(today.getTime() + 15 * 60 * 60 * 1000),
						summary: 'Client Review',
						confidence: 0.95,
						source: 'google_api_calendar',
						type: 'episodic' as const
					}
				]
			},
			{
				name: 'mac_apps',
				displayName: 'Mac Activity',
				company: 'apple' as const,
				type: 'episodic' as const,
				events: [
					{
						id: 'mac-1',
						startTime: new Date(today.getTime() + 9 * 60 * 60 * 1000),
						endTime: new Date(today.getTime() + 12 * 60 * 60 * 1000),
						summary: 'Xcode - iOS Development',
						confidence: 0.92,
						source: 'mac_apps',
						type: 'episodic' as const
					},
					{
						id: 'mac-2',
						startTime: new Date(today.getTime() + 13 * 60 * 60 * 1000),
						endTime: new Date(today.getTime() + 14 * 60 * 60 * 1000),
						summary: 'Safari - Research',
						confidence: 0.88,
						source: 'mac_apps',
						type: 'episodic' as const
					},
					{
						id: 'mac-3',
						startTime: new Date(today.getTime() + 14.5 * 60 * 60 * 1000),
						endTime: new Date(today.getTime() + 17 * 60 * 60 * 1000),
						summary: 'VS Code - Frontend Dev',
						confidence: 0.90,
						source: 'mac_apps',
						type: 'episodic' as const
					}
				]
			},
			// Ambient Sources - dynamically generate from available data
			...(data.ambientSignalsBySource || []).map(sourceData => {
				const { signals, range } = convertAmbientSignalsToRaw(sourceData.sourceName);
				return {
					name: sourceData.sourceName,
					displayName: sourceData.displayName,
					company: sourceData.sourceName.includes('apple') ? 'apple' as const : 'google' as const,
					type: 'ambient' as const,
					events: [],
					feltEvents: [], // Empty as requested
					rawSignals: signals,
					signalRange: range
				};
			}),
			// Add any ambient sources that don't have data yet but should be shown
			...[
				{ name: 'apple_watch_heart_rate', displayName: 'Apple Watch Heart Rate' },
				{ name: 'apple_ios_sound_classification', displayName: 'iOS Sound Classification' },
				{ name: 'apple_ios_gps', displayName: 'iOS GPS Location' }
			].filter(source => !data.ambientSignalsBySource?.find(s => s.sourceName === source.name))
				.map(source => {
					const { signals, range } = convertAmbientSignalsToRaw(source.name);
					return {
						name: source.name,
						displayName: source.displayName,
						company: 'apple' as const,
						type: 'ambient' as const,
						events: [],
						feltEvents: [],
						rawSignals: signals,
						signalRange: range
					};
				})
		];
	}
	*/

    // Scroll to current time on mount
    function scrollToCurrentTime() {
        if (timelineContainer) {
            const now = new Date();
            currentTimePosition = timeToPixel(now);
            timelineContainer.scrollLeft =
                currentTimePosition - timelineContainer.clientWidth / 2;
        }
    }

    // Process real data from server
    function processServerData() {
        // Convert ambient signals to the expected format
        const ambientSourceData = (data.ambientSignalsBySignalName || []).map(
            (signalGroup: any) => {
                // Extract raw signals for visualization based on visualization type
                let rawSignals;
                let signalRange;

                if (signalGroup.visualizationType === "continuous") {
                    // For continuous signals, extract numeric values
                    rawSignals = signalGroup.signals.map((signal: any) => ({
                        timestamp: new Date(signal.timestamp),
                        value: parseFloat(signal.signalValue) || 0,
                        label: signal.signalName,
                    }));

                    // Calculate range for normalization
                    const values = rawSignals.map(
                        (s: any) => s.value as number,
                    );
                    signalRange =
                        values.length > 0
                            ? {
                                  min: Math.min(...values),
                                  max: Math.max(...values),
                                  unit: signalGroup.unit || "",
                              }
                            : undefined;
                } else if (signalGroup.visualizationType === "binary") {
                    // For binary signals (like mac apps), treat as activity presence
                    rawSignals = signalGroup.signals.map((signal: any) => ({
                        timestamp: new Date(signal.timestamp),
                        value: 1, // Always 1 for activity presence
                        label: signal.signalValue || signal.signalName,
                    }));

                    signalRange = { min: 0, max: 1, unit: "activity" };
                } else if (signalGroup.visualizationType === "categorical") {
                    // For categorical signals, use the category as the value
                    rawSignals = signalGroup.signals.map((signal: any) => ({
                        timestamp: new Date(signal.timestamp),
                        value: signal.signalValue,
                        label: signal.signalName,
                        category: signal.signalValue,
                    }));

                    // No numeric range for categorical data
                    signalRange = undefined;
                } else if (signalGroup.visualizationType === "spatial") {
                    // For spatial signals (coordinates), pass through the raw coordinate data
                    rawSignals = signalGroup.signals.map((signal: any) => ({
                        timestamp: new Date(signal.timestamp),
                        value: 0, // Not used for spatial visualization
                        label: "location",
                        coordinates: signal.coordinates, // Keep the actual coordinate data
                    }));

                    signalRange = { min: 0, max: 30, unit: "m/s" }; // Speed range for visualization
                } else {
                    // Default fallback for unknown types
                    rawSignals = signalGroup.signals.map((signal: any) => ({
                        timestamp: new Date(signal.timestamp),
                        value: parseFloat(signal.signalValue) || 0,
                        label: signal.signalName,
                    }));

                    const values = rawSignals.map(
                        (s: any) => s.value as number,
                    );
                    signalRange =
                        values.length > 0
                            ? {
                                  min: Math.min(...values),
                                  max: Math.max(...values),
                                  unit: signalGroup.unit || "",
                              }
                            : undefined;
                }

                // Get proper display name based on signal configuration
                const getSignalDisplayName = (
                    sourceName: string,
                    signalName: string,
                ) => {
                    // Map of known signal names to display names
                    const displayNameMap: Record<string, string> = {
                        ios_speed: "Movement Speed",
                        ios_altitude: "Altitude",
                        ios_coordinates: "GPS Coordinates",
                        ios_activity: "Activity Type",
                        ios_environmental_sound: "Environmental Sound",
                        ios_mic_transcription: "Voice Transcription",
                        mac_apps: "Mac Activity",
                        google_api_calendar: "Calendar Events",
                    };

                    const fullSignalName = `${sourceName}_${signalName}`;
                    return (
                        displayNameMap[fullSignalName] ||
                        displayNameMap[signalName] ||
                        signalGroup.displayName ||
                        signalName
                    );
                };

                return {
                    name: signalGroup.signalName,
                    displayName: getSignalDisplayName(
                        signalGroup.sourceName,
                        signalGroup.signalName,
                    ),
                    company:
                        signalGroup.sourceName.includes("apple") ||
                        signalGroup.sourceName === "ios" ||
                        signalGroup.sourceName === "mac"
                            ? ("apple" as const)
                            : ("google" as const),
                    type: "ambient" as const,
                    visualizationType: signalGroup.visualizationType,
                    events: [], // No processed events yet
                    feltEvents: [], // No FELT events yet
                    rawSignals,
                    signalRange,
                };
            },
        );

        // Convert episodic signals to the expected format
        const episodicSourceData = (data.episodicSignalsBySignalId || []).map(
            (signalGroup: any) => {
                const events = signalGroup.events.map((event: any) => ({
                    id: event.id,
                    startTime: new Date(event.startTimestamp),
                    endTime: new Date(event.endTimestamp),
                    summary: event.summary || "Event",
                    confidence: event.confidence || 0.5,
                    source: signalGroup.sourceName,
                    type: "episodic" as const,
                }));

                // Get proper display name based on signal configuration (reuse the function above)
                const getEpisodicSignalDisplayName = (
                    sourceName: string,
                    signalName: string,
                ) => {
                    // Map of known signal names to display names
                    const displayNameMap: Record<string, string> = {
                        ios_speed: "Movement Speed",
                        ios_altitude: "Altitude",
                        ios_coordinates: "GPS Coordinates",
                        ios_activity: "Activity Type",
                        ios_environmental_sound: "Environmental Sound",
                        ios_mic_transcription: "Voice Transcription",
                        mac_apps: "Mac Activity",
                        google_api_calendar: "Calendar Events",
                    };

                    const fullSignalName = `${sourceName}_${signalName}`;
                    return (
                        displayNameMap[fullSignalName] ||
                        displayNameMap[signalName] ||
                        signalGroup.displayName ||
                        signalName
                    );
                };

                return {
                    name: signalGroup.signalName,
                    displayName: getEpisodicSignalDisplayName(
                        signalGroup.sourceName,
                        signalGroup.signalName,
                    ),
                    company:
                        signalGroup.sourceName.includes("apple") ||
                        signalGroup.sourceName === "ios" ||
                        signalGroup.sourceName === "mac"
                            ? ("apple" as const)
                            : ("google" as const),
                    type: "episodic" as const,
                    visualizationType: signalGroup.visualizationType,
                    events,
                };
            },
        );

        // Set the source timelines with real data
        sourceTimelines = [...episodicSourceData, ...ambientSourceData];

        // Generate master events from the data (simplified for now)
        masterEvents = generateMasterEventsFromSignals();
    }

    // Generate master events based on signal data
    function generateMasterEventsFromSignals() {
        // For now, return empty array - boundary detection will populate this
        return [];
    }

    // Initialize data only once when component mounts
    let initialized = false;
    $effect(() => {
        if (!initialized) {
            processServerData();
            initializeExpandedSources();
            initialized = true;
        }
    });

    // Re-process data when selectedDate changes
    $effect(() => {
        if (selectedDate && initialized) {
            // Data will be reloaded by the server when date changes
            processServerData();
        }
    });

    // Handle container width and resize observer
    $effect(() => {
        if (!timelineContainer) return;

        const updateContainerWidth = () => {
            if (timelineContainer) {
                containerWidth = timelineContainer.clientWidth;
            }
        };

        // Observe container width changes
        const resizeObserver = new ResizeObserver(() => {
            updateContainerWidth();
        });

        // Listen for window resize events
        const handleResize = () => {
            updateContainerWidth();
        };

        resizeObserver.observe(timelineContainer);
        resizeObserver.observe(
            timelineContainer.parentElement || timelineContainer,
        );
        updateContainerWidth();

        // Add window resize listener
        window.addEventListener("resize", handleResize);

        scrollToCurrentTime();

        return () => {
            resizeObserver.disconnect();
            window.removeEventListener("resize", handleResize);
        };
    });

    // Handle current time updates
    $effect(() => {
        const interval = setInterval(() => {
            const now = new Date();
            currentTimePosition = timeToPixel(now);
        }, 60000);

        return () => {
            clearInterval(interval);
        };
    });
</script>

<Page>
    <div class="min-h-screen bg-white">
        <!-- Header -->
        <div class="">
            <h1 class="text-3xl font-mono text-neutral-900 mb-2">Timeline</h1>
            <p class="text-sm text-neutral-600 mb-6 max-w-2xl">
                Your day reconstructed from multiple data sources. Each event
                represents a distinct activity period where signals align with
                sufficient confidence.
            </p>
            <div class="flex items-center justify-between mb-4">
                <div class="flex items-center gap-4">
                    <input
                        type="date"
                        bind:value={selectedDate}
                        onchange={() => {
                            // Update URL with selected date and reload page to fetch new data
                            const url = new URL(window.location.href);
                            url.searchParams.set("date", selectedDate);
                            window.location.href = url.toString();
                        }}
                        class="border border-neutral-300 bg-white rounded-lg px-4 py-2 text-sm font-medium focus:ring-2 focus:ring-neutral-500 focus:border-neutral-500 transition-all"
                    />
                    <p class="text-sm text-neutral-700">
                        {masterEvents.length} events • {episodicSources.length +
                            ambientSources.length} signals
                    </p>
                </div>
                <div class="rounded-lg px-4 py-3 border border-neutral-200">
                    <div class="flex items-start gap-3">
                        <div>
                            {#if selectedMasterEventId}
                                <p class="text-sm font-medium text-neutral-900">
                                    Event Selected
                                </p>
                                <p class="text-xs text-neutral-600 mt-0.5">
                                    Click event again to deselect
                                </p>
                            {:else}
                                <p class="text-sm font-medium text-neutral-900">
                                    Timeline Tips
                                </p>
                                <p class="text-xs text-neutral-600 mt-0.5">
                                    Click events to see sources • Expand ambient
                                    for raw data
                                </p>
                            {/if}
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- Timeline Container -->
        <div class=" space-y-6">
            <!-- Event Inference Engine Card -->
            <div
                class="border border-neutral-200 rounded-lg p-6
  bg-white overflow-visible"
            >
                <!-- Title -->
                <h2
                    class="text-xl font-mono text-neutral-900
  mb-2"
                >
                    Inferred Events
                </h2>

                <!-- Description -->
                <p class="text-sm text-neutral-600 mb-6">
                    Events automatically detected from your activity patterns
                </p>

                <div class="relative overflow-visible">
                    <div
                        bind:this={timelineContainer}
                        class=" overflow-y-visible
  relative"
                    >
                        <div
                            class="relative"
                            style="width:
  {containerWidth - 40}px;"
                        >
                            <!-- Labels at top with 45° angle -->
                            <div class="h-24 relative">
                                <svg
                                    class="absolute inset-0 overflow-visible"
                                    style="width: 100%; height: 100%;"
                                >
                                    {#each masterEvents as event}
                                        {@const x =
                                            timeToPixel(event.startTime) - 4}
                                        <g>
                                            <!-- Label text -->
                                            <text
                                                {x}
                                                y="88"
                                                transform={`rotate(-45, ${x},
  88)`}
                                                fill="#525252"
                                                font-size="11"
                                                font-weight="500"
                                                text-anchor="start"
                                            >
                                                {event.summary}
                                            </text>
                                        </g>
                                    {/each}
                                </svg>
                            </div>

                            <!-- Dotted lines from labels to events -->
                            <svg
                                class="absolute pointer-events-none"
                                style="top: 0; left: 0; width: 100%; height: 156px;"
                            >
                                {#each masterEvents as event}
                                    {@const x =
                                        timeToPixel(event.startTime) - 4}
                                    <line
                                        x1={x}
                                        y1="96"
                                        x2={x}
                                        y2="152"
                                        stroke="#40404040"
                                        stroke-width="1"
                                        stroke-dasharray="2,2"
                                    />
                                {/each}
                            </svg>

                            <!-- Events area -->
                            <div class="relative h-12 mt-4">
                                <!-- Current Time Indicator -->
                                {#if currentTimePosition > 0}
                                    <div
                                        class="absolute w-0.5 bg-red-500
  pointer-events-none z-30"
                                        style="left: {currentTimePosition}px; top:
   -20px; height: calc(100% + 40px);"
                                    >
                                        <div
                                            class="absolute -top-5 -left-8
  bg-red-500 text-white text-[9px] px-1.5 py-0.5 rounded
  font-mono tabular-nums"
                                        >
                                            {new Date().toLocaleTimeString(
                                                "en-US",
                                                {
                                                    hour: "2-digit",
                                                    minute: "2-digit",
                                                    hour12: false,
                                                },
                                            )}
                                        </div>
                                    </div>
                                {/if}

                                <!-- Event items -->
                                {#each masterEvents as event}
                                    {@const isSelected =
                                        selectedMasterEventId === event.id}
                                    {@const isHovered =
                                        hoveredEventId === event.id}
                                    {@const confidenceLevel =
                                        event.confidence < 0.3
                                            ? "low"
                                            : event.confidence < 0.7
                                              ? "medium"
                                              : "high"}
                                    {@const getConfidenceColor = () => {
                                        const colors = {
                                            low: "#ef4444",
                                            medium: "#f59e0b",
                                            high: "#10b981",
                                        };
                                        return colors[confidenceLevel];
                                    }}
                                    {@const confidenceColor =
                                        getConfidenceColor()}
                                    {@const isSleep = event.summary
                                        ?.toLowerCase()
                                        .includes("sleep")}
                                    <button
                                        class="absolute rounded-md px-2 py-1
  cursor-pointer transition-all duration-200 text-left
  border text-neutral-900 h-10 top-1"
                                        class:bg-neutral-50={!isSleep}
                                        class:z-20={isSelected}
                                        class:z-10={isHovered && !isSelected}
                                        class:border-blue-400={isSelected}
                                        class:border-neutral-200={!isSelected}
                                        style="left:
  {timeToPixel(event.startTime)}px; width:
  {Math.max(
                                            getEventWidth(
                                                event.startTime,
                                                event.endTime,
                                            ) - 8,
                                            20,
                                        )}px; border-width: {isSelected
                                            ? '2px'
                                            : '1px'};
   border-opacity: {isSelected ? '1' : '0.5'}; {isSleep
                                            ? `background: repeating-linear-gradient(-45deg, white,
  white 4px, rgb(250 250 250) 4px, rgb(250 250 250) 8px);`
                                            : ''}"
                                        title="{event.summary}
  ({formatTime(event.startTime)} -
  {formatTime(event.endTime)}) -
  {Math.round(event.confidence * 100)}% confidence"
                                        onclick={() =>
                                            handleMasterEventClick(event.id)}
                                        onmouseenter={() =>
                                            (hoveredEventId = event.id)}
                                        onmouseleave={() =>
                                            (hoveredEventId = null)}
                                    >
                                        <div class="flex items-center gap-1">
                                            <div
                                                class="w-1.5 h-1.5 rounded-full
  flex-shrink-0"
                                                style="background-color:
  {confidenceColor};"
                                            ></div>
                                            <div
                                                class="text-[11px] font-medium
  leading-tight truncate"
                                            >
                                                {event.summary}
                                            </div>
                                        </div>
                                    </button>
                                {/each}
                            </div>

                            <!-- Timeline legend at bottom -->
                            <div class="relative h-6 mt-2">
                                {#each Array(timeRange) as _, i}
                                    {@const hour = i}
                                    {@const displayHour = hour % 24}
                                    <span
                                        class="absolute text-[10px]
  text-neutral-500 font-mono tabular-nums top-1"
                                        style="left: {i *
                                            60 *
                                            pixelsPerMinute}px;"
                                    >
                                        {displayHour === 0
                                            ? "00:00"
                                            : displayHour < 10
                                              ? `0${displayHour}:00`
                                              : `${displayHour}:00`}
                                    </span>
                                {/each}
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
</Page>
