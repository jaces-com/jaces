<script lang="ts">
    import { Page } from "$lib/components";
    import type { PageData } from "./$types";

    let { data }: { data: PageData } = $props();

    // Timeline configuration
    const timeRange = 24; // Always show full day
    const pixelsPerHour = 60; // Fixed height per hour
    const totalHeight = timeRange * pixelsPerHour;

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
    let currentTimePosition = $state(0);
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

    // Convert time to vertical pixel position (considering user timezone)
    function timeToPixel(date: Date): number {
        // For display purposes, use local time of the date object
        // which should already be in the user's timezone from server
        const hours = date.getHours();
        const minutes = date.getMinutes();
        const totalMinutes = hours * 60 + minutes;
        return (totalMinutes / 60) * pixelsPerHour; // Convert to vertical position
    }

    // Get event height in pixels (for vertical layout)
    function getEventHeight(start: Date, end: Date): number {
        return timeToPixel(end) - timeToPixel(start);
    }

    // Format time for display (respecting user timezone)
    function formatTime(date: Date): string {
        return date.toLocaleTimeString("en-US", {
            hour: "numeric",
            minute: "2-digit",
            hour12: true,
            timeZone: data.userTimezone || 'America/Chicago'
        });
    }


    // Update current time position
    function updateCurrentTime() {
        // Only show current time if viewing today
        const now = new Date();
        const today = new Date();
        today.setHours(0, 0, 0, 0);
        
        const viewingDate = new Date(selectedDate);
        viewingDate.setHours(0, 0, 0, 0);
        
        // Check if viewing today
        if (viewingDate.getTime() === today.getTime()) {
            currentTimePosition = timeToPixel(now);
        } else {
            currentTimePosition = -1; // Hide indicator
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

        // Process events from server
        masterEvents = processEventsFromServer();
    }

    // Process events from server data
    function processEventsFromServer() {
        if (!data.timelineEvents) return [];
        
        return data.timelineEvents.map((event: any) => ({
            id: event.id,
            startTime: new Date(event.startTime),
            endTime: new Date(event.endTime),
            summary: event.summary,
            confidence: event.confidence,
            type: 'master' as const,
            eventType: event.eventType,
            signalContributions: event.signalContributions,
            metadata: event.metadata
        }));
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

    // Re-process data when selectedDate changes or new events come in
    $effect(() => {
        if (selectedDate && initialized) {
            // Data will be reloaded by the server when date changes
            processServerData();
        }
    });
    
    // Re-process events when they change
    $effect(() => {
        if (data.timelineEvents) {
            masterEvents = processEventsFromServer();
        }
    });

    // Initialize and update current time
    $effect(() => {
        updateCurrentTime();
    });

    // Handle current time updates
    $effect(() => {
        const interval = setInterval(() => {
            updateCurrentTime();
        }, 60000); // Update every minute

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
            <div class="flex items-center gap-4 mb-4">
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
        </div>

        <!-- Timeline Container -->
        <div class="space-y-6 mt-12">
            <!-- Inferred Events Card -->
            <div class="">
                <!-- Day view timeline -->
                <div class="relative" style="min-height: {totalHeight}px;">
                    <div class="flex">
                        <!-- Time labels column -->
                        <div
                            class="w-18 flex-shrink-0 relative"
                            style="height: {totalHeight}px;"
                        >
                            {#each Array(timeRange) as _, i}
                                {@const hour = i}
                                {@const displayHour = hour % 24}
                                <div
                                    class="absolute left-0 w-full text-right pr-4 text-xs text-neutral-500 font-mono tabular-nums"
                                    style="top: {hour * pixelsPerHour - 6}px;"
                                >
                                    {displayHour === 0
                                        ? "00:00"
                                        : displayHour < 10
                                          ? `0${displayHour}:00`
                                          : `${displayHour}:00`}
                                </div>
                            {/each}
                        </div>

                        <!-- Events area -->
                        <div
                            class="flex-1 relative border-l border-neutral-200"
                            style="height: {totalHeight}px;"
                        >
                            <!-- Hour grid lines -->
                            {#each Array(timeRange + 1) as _, i}
                                <div
                                    class="absolute left-0 right-0 border-t border-neutral-100"
                                    style="top: {i * pixelsPerHour}px;"
                                ></div>
                            {/each}

                            <!-- Current Time Indicator (only show for today) -->
                            {#if currentTimePosition > 0 && currentTimePosition < totalHeight}
                                <div
                                    class="absolute left-0 right-0 h-0.5 bg-red-500 z-30"
                                    style="top: {currentTimePosition}px;"
                                >
                                    <div
                                        class="absolute -left-20 -top-2 bg-red-500 text-white text-[10px] px-1.5 py-0.5 rounded font-mono tabular-nums"
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

                            <!-- Event blocks -->
                            {#each masterEvents as event}
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
                                {@const confidenceColor = getConfidenceColor()}
                                {@const isSleep = event.summary
                                    ?.toLowerCase()
                                    .includes("sleep")}
                                {@const eventTop = timeToPixel(event.startTime)}
                                {@const eventHeight = getEventHeight(
                                    event.startTime,
                                    event.endTime,
                                )}

                                <div
                                    class="absolute left-2 right-2 rounded-md px-3 py-1.5 text-left border border-neutral-200 flex items-center gap-2"
                                    class:bg-neutral-50={!isSleep}
                                    style="top: {eventTop}px; height: {Math.max(
                                        eventHeight - 2,
                                        20,
                                    )}px; {isSleep
                                        ? `background: repeating-linear-gradient(45deg, white, white 4px, rgb(250 250 250) 4px, rgb(250 250 250) 8px);`
                                        : ''}"
                                    title="{event.summary} ({formatTime(
                                        event.startTime,
                                    )} - {formatTime(
                                        event.endTime,
                                    )}) - {Math.round(
                                        event.confidence * 100,
                                    )}% confidence"
                                >
                                    <div
                                        class="w-2 h-2 rounded-full flex-shrink-0"
                                        style="background-color: {confidenceColor};"
                                    ></div>
                                    <div class="text-sm font-medium truncate">
                                        {event.summary}
                                    </div>
                                    <div
                                        class="text-xs text-neutral-500 ml-auto"
                                    >
                                        {formatTime(event.startTime)} - {formatTime(
                                            event.endTime,
                                        )}
                                    </div>
                                </div>
                            {/each}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
</Page>
