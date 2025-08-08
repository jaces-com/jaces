<script lang="ts">
	import { Badge } from "$lib/components";
	import { toast } from "svelte-sonner";
	import { slide } from "svelte/transition";
	import {
		getTimelineContext,
		TimelineGrid,
		TimelineCursor,
		TimelineLegend,
	} from "./timeline";
	import {
		ContinuousVisualization,
		BinaryVisualization,
		CategoricalVisualization,
		SpatialVisualization,
		TransitionVisualization,
		CountVisualization,
	} from "./visualizations";
	import { parseDate, toZoned } from "@internationalized/date";

	interface TimelineEvent {
		id: string;
		startTime: Date;
		endTime: Date;
		summary?: string;
		confidence: number;
		source?: string;
		type?: "master" | "event" | "continuous" | "felt";
		metadata?: any;
	}

	interface RawSignal {
		timestamp: Date;
		value: number | string;
		label?: string;
		category?: string;
		coordinates?: any;
	}

	export let name: string;
	export let displayName: string;
	export let company: "apple" | "google";
	export let type: "event" | "continuous";
	export let visualizationType:
		| "continuous"
		| "binary"
		| "categorical"
		| "spatial"
		| "event"
		| undefined;
	export let computedEvents: TimelineEvent[] = [];
	export let rawSignals: RawSignal[] = [];
	export let signalRange:
		| { min: number; max: number; unit: string }
		| undefined;
	export let showCursorOnExpandedHover: boolean = false;
	export let selectedDate: string | undefined = undefined;
	export let onSignalAnalysisComplete: (() => void) | undefined = undefined;
	export let transitions: any[] = [];
	export let hasTransitions: boolean = false;
	export let userTimezone: string = "America/Chicago";

	const { timeToPixel, state } = getTimelineContext();

	// Local hover state for this card
	let isHoveringContent = false;

	// View state
	let isExpanded = true; // Default to expanded
	let isComputingBoundaries = false;

	// Get event width in pixels
	function getEventWidth(start: Date, end: Date): number {
		return Math.max(timeToPixel(end) - timeToPixel(start), 2);
	}

	// Format time for display
	function formatTime(date: Date): string {
		return date.toLocaleTimeString("en-US", {
			hour: "numeric",
			minute: "2-digit",
			hour12: true,
		});
	}

	// Run single signal transition detection
	async function runSingleSignalTransitionDetection() {
		isComputingBoundaries = true;

		try {
			// Use the selectedDate prop or fall back to today
			const dateToUse =
				selectedDate || new Date().toISOString().split("T")[0];
			const [year, month, day] = dateToUse.split("-").map(Number);

			// Create start and end of day in user's timezone
			const calendarDate = parseDate(
				`${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`,
			);
			const zonedStart = toZoned(calendarDate, userTimezone);
			const zonedEnd = zonedStart.add({
				hours: 23,
				minutes: 59,
				seconds: 59,
				milliseconds: 999,
			});

			// Convert to Date objects for the API
			const startOfDay = zonedStart.toDate();
			const endOfDay = zonedEnd.toDate();

			const requestBody = {
				userId: "00000000-0000-0000-0000-000000000001", // Default user ID
				signalName: name,
				startTime: startOfDay.toISOString(),
				endTime: endOfDay.toISOString(),
				timezone: userTimezone,
			};

			const response = await fetch("/api/signal-analysis/detect", {
				method: "POST",
				headers: {
					"Content-Type": "application/json",
				},
				body: JSON.stringify(requestBody),
			});

			if (!response.ok) {
				throw new Error(
					`HTTP ${response.status}: ${response.statusText}`,
				);
			}

			const result = await response.json();

			if (result.success) {
				// Show success feedback
				const detectionType = "transition";
				toast.success(
					`${detectionType.charAt(0).toUpperCase() + detectionType.slice(1)} detection started for ${displayName}`,
					{
						description: `Processing ${detectionType}s...`,
						duration: 3000,
					},
				);

				// Poll for completion
				const taskId = result.taskId;
				let pollAttempts = 0;
				const maxPollAttempts = 30; // 30 seconds max
				const pollInterval = 1000; // 1 second

				const pollForCompletion = async () => {
					if (pollAttempts >= maxPollAttempts) {
						toast.error("Detection timed out", {
							description:
								"Please refresh the page to see results",
						});
						isComputingBoundaries = false;
						return;
					}

					pollAttempts++;

					try {
						// For now, just wait and refresh since we don't have a task status endpoint
						// In the future, we could check task status here

						// After a few seconds, refresh the parent component
						if (pollAttempts === 3) {
							// After 3 seconds
							toast.success(
								`Detection completed for ${displayName}`,
								{
									description: `Found transitions`,
									duration: 3000,
								},
							);

							// Notify parent component to refresh data
							if (onSignalAnalysisComplete) {
								onSignalAnalysisComplete();
							}
							isComputingBoundaries = false;
						} else {
							// Continue polling
							setTimeout(pollForCompletion, pollInterval);
						}
					} catch (error) {
						console.error("Error polling for completion:", error);
						isComputingBoundaries = false;
					}
				};

				// Start polling after a short delay
				setTimeout(pollForCompletion, pollInterval);
			} else {
				toast.error("Failed to start detection", {
					description: result.error || "Unknown error",
				});
				isComputingBoundaries = false;
			}
		} catch (error) {
			toast.error("Error starting detection", {
				description:
					error instanceof Error ? error.message : "Unknown error",
			});
			isComputingBoundaries = false;
		}
	}
</script>

<div
	class="bg-white border-y border-neutral-200 overflow-hidden transition-all duration-200"
>
	<!-- Signal Header -->
	<div
		class="flex items-center justify-between px-4 py-3 bg-neutral-100 border-neutral-200 min-h-[56px]"
	>
		<div class="flex items-center gap-3 flex-1">
			<button
				class="bg-transparent border-none p-2 rounded cursor-pointer text-neutral-500 transition-colors duration-200 hover:bg-neutral-200 hover:text-neutral-700"
				on:click={() => (isExpanded = !isExpanded)}
				aria-label={isExpanded ? "Collapse" : "Expand"}
			>
				<svg width="12" height="12" viewBox="0 0 12 12" fill="none">
					<path
						d={isExpanded ? "M2 4L6 8L10 4" : "M4 2L8 6L4 10"}
						stroke="currentColor"
						stroke-width="2"
						stroke-linecap="round"
						stroke-linejoin="round"
					/>
				</svg>
			</button>

			<div class="flex items-center gap-3">
				<h3 class="text-sm font-normal font-mono text-neutral-900 m-0">
					{displayName}
				</h3>
				<Badge variant="default" size="sm">{name}</Badge>
			</div>
		</div>

		<div class="flex gap-2 items-center">
			<Badge variant="default" size="sm">{company}</Badge>
			<Badge variant="secondary" size="sm">{type}</Badge>
			{#if visualizationType}
				<Badge variant="secondary" size="sm">{visualizationType}</Badge>
			{/if}
		</div>
	</div>

	<!-- Signal Content -->
	{#if isExpanded}
		<div
			class="relative"
			on:mouseenter={() => (isHoveringContent = true)}
			on:mouseleave={() => (isHoveringContent = false)}
			role="region"
			aria-label="Timeline content"
			transition:slide={{ duration: 200 }}
		>
			<!-- Single Timeline Grid overlay for entire expanded area -->
			<div class="absolute inset-0 pointer-events-none z-0">
				<TimelineGrid {selectedDate} userTimezone={userTimezone} />
			</div>

			<!-- Content wrapper with proper z-index -->
			<div class="relative z-10">
				<!-- Timeline Legend at the top -->
				<div class="h-8 pointer-events-none relative w-full mb-2">
					<TimelineLegend {selectedDate} {userTimezone} />
				</div>

				<!-- Transition Markers Section -->
				<div class="bg-transparent border-b border-neutral-200">
					<div
						class="flex items-center gap-2 px-4 h-8 border-b border-neutral-200"
					>
						<span
							class="text-[10px] font-semibold text-neutral-700 font-mono"
							>Transition Markers</span
						>
						<span class="text-[10px] text-neutral-500"
							>({transitions.length})</span
						>
					</div>

					{#if transitions.length > 0}
						<!-- Show transitions -->
						<div class="relative my-4">
							<TransitionVisualization
								{transitions}
								height={30}
							/>
						</div>
					{:else if computedEvents.length > 0}
						<!-- Show event data as markers -->
						<div class="relative h-12 my-4">
							{#each computedEvents as event}
								<div
									class="computed-event"
									style="
										left: {timeToPixel(event.startTime)}px;
										width: {getEventWidth(event.startTime, event.endTime)}px;
										background: {event.type === 'felt'
										? `rgba(34,197,94,${event.confidence * 0.2})`
										: 'linear-gradient(135deg, #F5F5F7 0%, #E8E8ED 100%)'};
										border-color: {event.type === 'felt'
										? `rgba(34,197,94,${event.confidence * 0.6})`
										: '#86868B'};
									"
									title="{event.summary} ({formatTime(
										event.startTime,
									)} - {formatTime(
										event.endTime,
									)}) - {Math.round(
										event.confidence * 100,
									)}% confidence"
								>
									{#if getEventWidth(event.startTime, event.endTime) > 60}
										<span
											class="text-[10px] font-mono text-neutral-700 whitespace-nowrap text-ellipsis overflow-hidden"
										>
											{event.summary}
										</span>
									{/if}
								</div>
							{/each}
						</div>
					{:else}
						<div
							class="flex flex-col items-center justify-center p-6 text-neutral-400 text-[13px] gap-2"
						>
							{#if isComputingBoundaries}
								<div class="flex items-center gap-2">
									<svg
										class="animate-spin h-4 w-4 text-blue-500"
										xmlns="http://www.w3.org/2000/svg"
										fill="none"
										viewBox="0 0 24 24"
									>
										<circle
											class="opacity-25"
											cx="12"
											cy="12"
											r="10"
											stroke="currentColor"
											stroke-width="4"
										></circle>
										<path
											class="opacity-75"
											fill="currentColor"
											d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
										></path>
									</svg>
									<span class="text-blue-500"
										>Detecting transitions...</span
									>
								</div>
							{:else}
								<p>No transition markers detected</p>
								{#if type !== "event"}
									<button
										type="button"
										class="px-2 py-1 text-[10px] bg-blue-500 text-white border-none rounded cursor-pointer font-medium transition-colors duration-200 hover:bg-blue-600 disabled:bg-gray-400 disabled:cursor-not-allowed"
										on:click|stopPropagation|preventDefault={runSingleSignalTransitionDetection}
										disabled={isComputingBoundaries}
									>
										Detect Transitions
									</button>
								{/if}
							{/if}
						</div>
					{/if}
				</div>

				<!-- Raw Data Section -->
				<div class="bg-transparent">
					<div
						class="flex items-center gap-2 px-4 h-8 border-b border-neutral-200"
					>
						<span
							class="text-[10px] font-semibold text-neutral-700 font-mono"
							>Raw Data</span
						>
						<span class="text-[10px] text-neutral-500"
							>({rawSignals.length})</span
						>
					</div>

					{#if rawSignals.length > 0}
						<div class="relative py-4 min-h-[60px]">
							{#if visualizationType === "continuous" && signalRange}
								<ContinuousVisualization
									signals={rawSignals}
									{signalRange}
								/>
							{:else if visualizationType === "binary"}
								<BinaryVisualization signals={rawSignals} />
							{:else if visualizationType === "categorical"}
								<CategoricalVisualization
									signals={rawSignals}
								/>
							{:else if visualizationType === "spatial"}
								<SpatialVisualization signals={rawSignals} />
							{:else if visualizationType === "count"}
								<CountVisualization signals={rawSignals} {signalRange} />
							{:else}
								<!-- Fallback for unknown visualization types -->
								<div
									class="p-4 bg-neutral-100 rounded text-center text-neutral-500 text-xs"
								>
									<p>{rawSignals.length} data points</p>
								</div>
							{/if}
						</div>
					{:else}
						<div
							class="flex flex-col items-center justify-center p-6 text-neutral-400 text-[13px] gap-2"
						>
							<p>No raw data available</p>
						</div>
					{/if}
				</div>
			</div>

			<!-- Show timeline cursor only when hovering over expanded content -->
			{#if showCursorOnExpandedHover && (isHoveringContent || $state.isCursorLocked)}
				<TimelineCursor />
			{/if}
		</div>
	{/if}
</div>

<style>
	@reference "../../../app.css";

	.computed-event {
		@apply absolute top-2 h-8 border-1 rounded-sm px-1 flex items-center cursor-pointer transition-all duration-200 overflow-hidden;
	}
</style>
