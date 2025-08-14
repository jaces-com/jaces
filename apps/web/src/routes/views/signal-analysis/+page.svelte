<script lang="ts">
	import { Page, Button } from "$lib/components";
	import {
		SignalTimeline,
		TimelineContext,
		TimelineGrid,
		TimelineLegend,
		TimelineCursor,
	} from "$lib/components/signal-analysis";
	import { EventVisualization } from "$lib/components/signal-analysis/visualizations";
	import { invalidate } from "$app/navigation";
	import type { PageData } from "./$types";

	let { data }: { data: PageData } = $props();

	// Timeline configuration
	let detectionContainerWidth = $state(0); // Will be updated dynamically
	let signalsContainerWidth = $state(0); // Will be updated dynamically
	let detectionTimelineContainer: HTMLDivElement;
	let signalsTimelineContainer: HTMLDivElement;

	// State
	let selectedDate = $state(
		data.selectedDate
			? new Date(data.selectedDate).toISOString().split("T")[0]
			: new Date().toISOString().split("T")[0],
	);
	// let isRunningAnalysis = $state(false);
	// let analysisError = $state<string | null>(null);
	// Removed boundary detection - focusing on transitions only
	// Removed manual event generation - events are now auto-generated

	// Source timelines from server data - derived from data prop
	let sourceTimelines = $derived(processServerData());

	// Transform HDBSCAN events to EventVisualization format
	function transformHDBSCANEventsToSignals(events: any[]) {
		if (!events || events.length === 0) return [];
		
		return events.map((event, index) => {
			const startTime = new Date(event.startTime);
			const endTime = new Date(event.endTime);
			const duration = endTime.getTime() - startTime.getTime();
			
			// Generate event summary
			let summary = `Event ${index + 1}`;
			if (event.signalContributions && Object.keys(event.signalContributions).length > 0) {
				// Find dominant signal
				const [dominantSignal] = Object.entries(event.signalContributions)
					.sort(([,a], [,b]) => (b as number) - (a as number))[0];
				if (dominantSignal) {
					summary = dominantSignal[0].replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
				}
			}
			
			return {
				timestamp: startTime,
				value: summary,
				label: summary,
				duration: duration,
				metadata: {
					event: {
						id: event.id,
						clusterId: event.clusterId,
						confidence: event.metadata?.avg_confidence || event.coreDensity || 0.5,
						clusterSize: event.clusterSize,
						eventType: event.eventType,
						signalContributions: event.signalContributions
					},
					timing: {
						start: startTime,
						end: endTime,
						duration_minutes: duration / (60 * 1000)
					}
				}
			};
		});
	}
	
	// Transform HDBSCAN events for visualization
	let hdbscanEventSignals = $derived(transformHDBSCANEventsToSignals(data.hdbscanEvents));

	// Process real data from server
	function processServerData() {
		// Convert ambient signals to the expected format
		const ambientSourceData = (data.ambientSignalsBySignalName || []).map(
			(signalGroup: any) => {
				// Extract raw signals for visualization
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
				} else if (signalGroup.visualizationType === "count") {
					// For count signals (steps, calories), these are cumulative values
					rawSignals = signalGroup.signals.map((signal: any) => ({
						timestamp: new Date(signal.timestamp),
						value: parseFloat(signal.signalValue) || 0,
						label: signal.signalName,
					}));

					// Calculate range based on the max value
					const values = rawSignals.map(
						(s: any) => s.value as number,
					);
					signalRange =
						values.length > 0
							? {
									min: 0,
									max: Math.max(...values),
									unit: signalGroup.unit || "count",
								}
							: {
									min: 0,
									max: 100,
									unit: signalGroup.unit || "count",
								};
				} else if (signalGroup.visualizationType === "event") {
					// For discrete events (like calendar events), show as blocks
					rawSignals = signalGroup.signals.map((signal: any) => {
						// Parse metadata if it's a string
						let metadata = signal.sourceMetadata;
						if (typeof metadata === 'string') {
							try {
								metadata = JSON.parse(metadata);
							} catch (e) {
								metadata = {};
							}
						}
						
						return {
							timestamp: new Date(signal.timestamp),
							value: 1, // Always 1 for event presence
							label: signal.signalValue || signal.signalName,
							duration: 60 * 60 * 1000, // Default 1 hour duration for events
							metadata: metadata
						};
					});

					signalRange = { min: 0, max: 1, unit: "event" };
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

				// Use the display name from the server
				const getSignalDisplayName = (
					sourceName: string,
					signalName: string,
				) => {
					return signalGroup.displayName || signalName;
				};
				
				// Parse just the signal part (after source_stream)
				const getSignalPart = (fullSignalName: string, sourceName: string, streamName: string) => {
					// Remove source_stream prefix to get just the signal
					const prefix = `${sourceName}_${streamName}_`;
					if (fullSignalName.startsWith(prefix)) {
						return fullSignalName.substring(prefix.length);
					}
					// Fallback: try just source_ prefix
					const sourcePrefix = `${sourceName}_`;
					if (fullSignalName.startsWith(sourcePrefix)) {
						const remainder = fullSignalName.substring(sourcePrefix.length);
						// If we have a stream, remove it too
						if (streamName && remainder.startsWith(`${streamName}_`)) {
							return remainder.substring(`${streamName}_`.length);
						}
						return remainder;
					}
					return fullSignalName;
				};
				
				const signalPart = getSignalPart(signalGroup.signalName, signalGroup.sourceName, signalGroup.streamName);

				return {
					name: signalGroup.signalName,
					signalId: signalGroup.signalId, // Add signalId for boundary matching
					displayName: getSignalDisplayName(
						signalGroup.sourceName,
						signalGroup.signalName,
					),
					sourceName: signalGroup.sourceName,
					streamName: signalGroup.streamName,
					signalName: signalPart,
					company:
						signalGroup.sourceName.includes("apple") ||
						signalGroup.sourceName === "ios" ||
						signalGroup.sourceName === "mac"
							? ("apple" as const)
							: ("google" as const),
					type: signalGroup.visualizationType === "event" ? ("event" as const) : ("continuous" as const),
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

				// Use the display name from the server
				const getEpisodicSignalDisplayName = (
					sourceName: string,
					signalName: string,
				) => {
					return signalGroup.displayName || signalName;
				};

				return {
					name: signalGroup.signalName,
					signalId: signalGroup.signalId, // Add signalId for boundary matching
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

		// Combine and sort source timelines alphabetically by display name
		let timelines = [...episodicSourceData, ...ambientSourceData].sort(
			(a, b) => a.displayName.localeCompare(b.displayName),
		);

		// Add computed events from signal boundaries
		if (data.signalBoundariesBySource) {
			timelines = timelines.map((source) => {
				// For ambient signals, use signalId as the key
				const boundaryKey = source.signalId || source.name;
				const boundaries =
					data.signalBoundariesBySource?.[boundaryKey] || [];

				if (boundaries && boundaries.length > 0) {
					// Convert boundaries to felt events format
					const feltEvents = boundaries.map((boundary: any) => ({
						id: boundary.id,
						startTime: new Date(boundary.startTime),
						endTime: new Date(boundary.endTime),
						summary:
							boundary.summary ||
							boundary.metadata?.description ||
							"Unknown",
						confidence: boundary.confidence || 0.5,
						source: source.name,
						type: "felt" as const,
						metadata: boundary.metadata,
					}));

					return {
						...source,
						feltEvents,
					};
				}

				return source;
			});
		}

		// Add transitions data to all signal types
		if (data.signalTransitionsBySource) {
			timelines = timelines.map((source) => {
				// Check for transitions for all signal types (continuous, ambient, event)
				// Note: transitions are keyed by signal_name (e.g., "ios_speed", "google_calendar_events")
				if (source.type === "continuous" || source.type === "ambient" || source.type === "event") {
					const transitions =
						data.signalTransitionsBySource?.[source.name] || [];

					if (transitions && transitions.length > 0) {
						// Convert transitions to the expected format
						const formattedTransitions = transitions.map(
							(transition: any) => ({
								id: transition.id,
								transitionTime: new Date(
									transition.transitionTime,
								),
								transitionType: transition.transitionType || 'changepoint',
								changeMagnitude: transition.changeMagnitude,
								changeDirection: transition.changeDirection,
								beforeMean: transition.beforeMean,
								afterMean: transition.afterMean,
								fromState: transition.fromState,
								toState: transition.toState,
								confidence: transition.confidence || 0.8,
								metadata: transition.metadata,
							}),
						);

						return {
							...source,
							transitions: formattedTransitions,
							hasTransitions: true,
						};
					}
				}

				return source;
			});
		}

		return timelines;
	}

	// Removed: handleSignalAnalysisComplete - transitions now happen automatically in the pipeline

	// Format time for display
	function formatTime(date: Date): string {
		// Use the user's timezone for formatting
		return date.toLocaleTimeString("en-US", {
			hour: "numeric",
			minute: "2-digit",
			hour12: true,
			timeZone: data.userTimezone,
		});
	}

	// Removed manual event generation - events are now auto-generated

	// Run signal analysis
	async function runSignalAnalysis() {
		isRunningAnalysis = true;
		analysisError = null;

		try {
			// Get start and end of selected date in LOCAL time
			const [year, month, day] = selectedDate.split("-").map(Number);
			// Create date at midnight local time
			const startTime = new Date(year, month - 1, day, 0, 0, 0);
			const endTime = new Date(year, month - 1, day, 23, 59, 59, 999);

			// Get browser's timezone
			const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;

			// TODO: Replace with actual user ID from auth context
			const userId = "00000000-0000-0000-0000-000000000001"; // Mock user ID

			const response = await fetch("/api/signal-analysis/run", {
				method: "POST",
				headers: {
					"Content-Type": "application/json",
				},
				body: JSON.stringify({
					userId,
					startTime: startTime.toISOString(),
					endTime: endTime.toISOString(),
					timezone: timezone,
				}),
			});

			if (!response.ok) {
				throw new Error(
					`Failed to run signal analysis: ${response.statusText}`,
				);
			}

			const result = await response.json();

			if (result.success && result.status === "pending") {
				// Task was queued, poll for results

				// Poll every 2 seconds for up to 30 seconds
				let attempts = 0;
				const maxAttempts = 15;
				const pollInterval = 2000;

				const pollForResults = async () => {
					if (attempts >= maxAttempts) {
						isRunningAnalysis = false;
						throw new Error("Signal analysis timed out");
					}

					attempts++;

					// Check run status
					const statusResponse = await fetch(
						`/api/signal-analysis/run?runId=${result.run.id}`,
					);

					if (!statusResponse.ok) {
						isRunningAnalysis = false;
						throw new Error(
							"Failed to check signal analysis status",
						);
					}

					const statusResult = await statusResponse.json();

					if (statusResult.run.status === "completed") {
						// Success! Update UI with boundaries
						analysisResults = statusResult.boundaries || [];
						isRunningAnalysis = false;
					} else if (statusResult.run.status === "failed") {
						isRunningAnalysis = false;
						throw new Error("Signal analysis failed");
					} else {
						// Still pending, poll again
						setTimeout(pollForResults, pollInterval);
					}
				};

				// Start polling
				setTimeout(pollForResults, pollInterval);
			} else if (result.success) {
				// Immediate result (shouldn't happen with Celery, but handle it)
				analysisResults = result.boundaries || [];
			} else {
				throw new Error(result.error || "Unknown error occurred");
			}
		} catch (error) {
			analysisError =
				error instanceof Error
					? error.message
					: "Failed to run signal analysis";
			isRunningAnalysis = false;
		} finally {
			// Ensure button state is reset
			if (isRunningAnalysis) {
				isRunningAnalysis = false;
			}
		}
	}

	// Handle container width and resize observer for both sections
	$effect(() => {
		const containers = [
			{
				element: detectionTimelineContainer,
				setter: (w: number) => (detectionContainerWidth = w),
			},
			{
				element: signalsTimelineContainer,
				setter: (w: number) => (signalsContainerWidth = w),
			},
		];

		const resizeObserver = new ResizeObserver((entries) => {
			for (const entry of entries) {
				const container = containers.find(
					(c) => c.element === entry.target,
				);
				if (container) {
					const newWidth = entry.contentRect.width;
					container.setter(newWidth);
				}
			}
		});

		// Observe both containers
		containers.forEach(({ element }) => {
			if (element) {
				resizeObserver.observe(element);
			}
		});

		return () => {
			resizeObserver.disconnect();
		};
	});
</script>

<Page>
	<div class="min-h-screen bg-white">
		<!-- Header -->
		<div class="">
			<h1 class="text-3xl font-mono text-neutral-900 mb-2">
				Signal Analysis
			</h1>
			<p class="text-sm text-neutral-600 mb-6 max-w-2xl">
				Computational confidence analysis of signal boundaries from
				episodic and ambient data sources. Non-semantic detection of
				activity transitions based on data patterns.
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
					<!-- Boundary detection removed -->
					<!-- Event generation is now automatic -->
				</div>
			</div>

			<!-- Error message display removed (boundary detection) -->
			<!-- Event generation messages removed (now automatic) -->
		</div>

		<!-- Signal Analysis Card -->
		<div
			class="border border-neutral-200 rounded-lg bg-white overflow-hidden"
		>
			<!-- Header and content with padding -->
			<div class="p-6 pb-0">
				<h2 class="text-xl font-mono text-neutral-900 mb-4">
					Detection Results
				</h2>
				<p class="text-sm text-neutral-600 mb-4">
					Daily events detected using HDBSCAN clustering on
					transitions. Events represent periods of coherent activity
					based on signal density.
				</p>
			</div>

			<!-- Full-width timeline section -->
			<div bind:this={detectionTimelineContainer} class="relative w-full overflow-hidden">
				{#if detectionContainerWidth > 0}
					<TimelineContext
						{selectedDate}
						containerWidth={detectionContainerWidth}
						padding={0}
						userTimezone={data.userTimezone}
					>
						<div class="relative">
							<!-- Single Timeline Grid overlay for entire area -->
							<div class="absolute inset-0 pointer-events-none z-0">
								<TimelineGrid
									{selectedDate}
									userTimezone={data.userTimezone}
								/>
							</div>

							<!-- Content wrapper with proper z-index -->
							<div class="relative z-10">
								<!-- Timeline Legend at the top -->
								<div class="h-8 pointer-events-none relative w-full mb-2">
									<TimelineLegend
										{selectedDate}
										userTimezone={data.userTimezone}
									/>
								</div>

								<!-- HDBSCAN Events Section -->
								<div class="bg-transparent">
									<div class="flex items-center gap-2 px-4 h-8 border-b border-neutral-200">
										<span class="text-[10px] font-semibold text-neutral-700 font-mono">Detected Events</span>
										<span class="text-[10px] text-neutral-500">
											({hdbscanEventSignals.length})
										</span>
									</div>

									{#if hdbscanEventSignals.length > 0}
										<div class="relative my-4" style="min-height: 60px;">
											<EventVisualization
												signals={hdbscanEventSignals}
												height={60}
											/>
										</div>
									{:else}
										<div class="flex flex-col items-center justify-center p-6 text-neutral-400 text-[13px] gap-2">
											<p class="text-neutral-500">No events detected yet</p>
											<p class="text-xs text-neutral-400">
												Events are automatically generated from signal transitions
											</p>
										</div>
									{/if}
								</div>

								<!-- Timeline Cursor -->
								<TimelineCursor />
							</div>
						</div>
					</TimelineContext>
				{:else}
					<div style="min-height: 120px;"></div>
				{/if}
			</div>
		</div>

		<!-- Signals Card -->
		<div class="border border-neutral-200 rounded-lg bg-white mt-6">
			<!-- Header with padding -->
			<div class="p-6 pb-0">
				<h2 class="text-xl font-mono text-neutral-900 mb-4">Signals</h2>
				<p class="text-sm text-neutral-600 mb-6">
					All data sources that contribute to signal analysis,
					including discrete events and continuous ambient streams.
				</p>
			</div>

			<!-- Full-width timeline section -->
			<div bind:this={signalsTimelineContainer} class="relative w-full">
				{#if signalsContainerWidth > 0}
					<TimelineContext
						{selectedDate}
						containerWidth={signalsContainerWidth}
						padding={0}
						userTimezone={data.userTimezone}
					>
						<!-- Signal Timelines Container -->
						<div class="relative">
							<!-- Signal Timelines -->
							{#each sourceTimelines as source}
								<!-- Removed: onSignalAnalysisComplete - transitions now happen automatically -->
								<SignalTimeline
									name={source.name}
									displayName={source.displayName}
									sourceName={source.sourceName}
									streamName={source.streamName}
									signalName={source.signalName}
									company={source.company}
									type={source.type}
									visualizationType={source.visualizationType}
									computedEvents={source.feltEvents ||
										source.events ||
										[]}
									rawSignals={source.rawSignals || []}
									signalRange={source.signalRange}
									transitions={source.transitions || []}
									hasTransitions={source.hasTransitions ||
										false}
									showCursorOnExpandedHover={true}
									{selectedDate}
									userTimezone={data.userTimezone}
								/>
							{/each}

							<!-- Timeline Cursor -->
							<TimelineCursor />
						</div>
					</TimelineContext>
				{/if}
			</div>
		</div>
	</div>
</Page>
