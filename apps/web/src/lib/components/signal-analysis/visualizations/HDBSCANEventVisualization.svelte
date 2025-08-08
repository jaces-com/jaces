<script lang="ts">
	import { getTimelineContext } from '../timeline';

	interface Event {
		id: string;
		clusterId: number;
		startTime: Date;
		endTime: Date;
		coreDensity: number;
		clusterSize: number;
		signalContributions: Record<string, number>;
		eventType?: string;
		metadata: {
			duration_minutes: number;
			avg_confidence: number;
			type?: string;
			reason?: string;
		};
	}

	interface Props {
		events: Event[];
		transitions: Array<{
			id: string;
			transitionTime: Date;
			confidence: number;
			signalName: string;
		}>;
		selectedDate: string;
		userTimezone: string;
	}

	let { events = [], transitions = [], selectedDate, userTimezone }: Props = $props();

	// Use timeToPixel directly from context, accessing it lazily
	const getPositionForTime = (date: Date) => {
		const context = getTimelineContext();
		if (!context || !context.timeToPixel) return 0;
		return context.timeToPixel(date);
	};


	// Neutral gray palette
	function getClusterColor(clusterId: number): string {
		// Use a single neutral gray color for all events
		return '#6B7280'; // gray-500
	}

	// Format time for tooltip
	function formatTime(date: Date): string {
		return date.toLocaleTimeString('en-US', {
			hour: 'numeric',
			minute: '2-digit',
			hour12: true,
			timeZone: userTimezone,
		});
	}

	// Get dominant signal for an event
	function getDominantSignal(contributions: Record<string, number>): string {
		const entries = Object.entries(contributions);
		if (entries.length === 0) return 'Unknown';
		
		entries.sort((a, b) => b[1] - a[1]);
		return entries[0][0].replace(/_/g, ' ');
	}

	let hoveredEvent: Event | null = $state(null);
</script>

<div class="relative w-full">
	<!-- Horizontal connecting line -->
	<div class="absolute w-full h-0.5 bg-gray-300" style="top: 40px;"></div>

	<!-- Event Clusters -->
	<div class="relative h-20">
		{#each events as event, i}
			{@const startX = getPositionForTime(event.startTime)}
			{@const endX = getPositionForTime(event.endTime)}
			{@const width = Math.max(endX - startX, 2)}
			{@const color = getClusterColor(event.clusterId)}
			
			<!-- Connection line from previous event to this one -->
			{#if i > 0}
				{@const prevEvent = events[i - 1]}
				{@const prevEndX = getPositionForTime(prevEvent.endTime)}
				{@const lineStartX = prevEndX}
				{@const lineWidth = startX - prevEndX}
				{#if lineWidth > 0}
					<div 
						class="absolute h-0.5 bg-gray-300"
						style="
							left: {lineStartX}px;
							width: {lineWidth}px;
							top: 40px;
						"
					></div>
				{/if}
			{/if}
			
			<button
				class="absolute top-4 h-12 rounded-lg transition-all duration-200 hover:scale-y-110 hover:shadow-lg {event.eventType === 'unknown' ? 'border-2 border-dashed border-gray-400' : ''}"
				style="
					left: {startX}px;
					width: {width}px;
					background-color: {event.eventType === 'unknown' ? '#F3F4F6' : color};
					opacity: {event.eventType === 'unknown' ? 0.8 : (0.8 + event.coreDensity * 0.2)};
				"
				onmouseenter={() => hoveredEvent = event}
				onmouseleave={() => hoveredEvent = null}
			>
				<div class="flex items-center justify-center h-full">
					<span class="{event.eventType === 'unknown' ? 'text-gray-600' : 'text-white'} text-xs font-medium">
						{event.eventType === 'unknown' ? '?' : event.clusterSize}
					</span>
				</div>
			</button>
		{/each}
	</div>


	<!-- Hover Tooltip -->
	{#if hoveredEvent}
		<div
			class="absolute z-20 bg-gray-900 text-white p-3 rounded-lg shadow-xl pointer-events-none"
			style="
				left: {getPositionForTime(hoveredEvent.startTime)}px;
				top: -120px;
				min-width: 200px;
			"
		>
			<div class="text-sm font-medium mb-1">
				{hoveredEvent.eventType === 'unknown' ? 'Unknown Period' : `Event #${hoveredEvent.clusterId}`}
			</div>
			<div class="text-xs space-y-1">
				<div>{formatTime(hoveredEvent.startTime)} - {formatTime(hoveredEvent.endTime)}</div>
				<div>Duration: {hoveredEvent.metadata.duration_minutes.toFixed(0)} min</div>
				{#if hoveredEvent.eventType === 'unknown'}
					<div>Reason: {hoveredEvent.metadata.reason === 'no_data' ? 'No data available' : 'Gap in data'}</div>
				{:else}
					<div>Transitions: {hoveredEvent.clusterSize}</div>
					<div>Confidence: {(hoveredEvent.metadata.avg_confidence * 100).toFixed(0)}%</div>
					<div>Density: {(hoveredEvent.coreDensity * 100).toFixed(0)}%</div>
					<div class="pt-1 border-t border-gray-700">
						Primary: {getDominantSignal(hoveredEvent.signalContributions)}
					</div>
				{/if}
			</div>
		</div>
	{/if}

</div>

<style>
	/* Additional styles if needed */
</style>