<script lang="ts">
    import { Page } from "$lib/components";
    import type { PageData } from "./$types";
    import { tick, untrack, onMount } from "svelte";
    import { browser } from "$app/environment";
    import {
        TimelineContext,
        TimelineGrid,
        TimelineLegend,
        TimelineCursor,
    } from "$lib/components/signal-analysis";
    import TimelineHoverWatcher from "$lib/components/signal-analysis/timeline/TimelineHoverWatcher.svelte";
    import LocationDataIndicator from "$lib/components/signal-analysis/timeline/LocationDataIndicator.svelte";

    let { data }: { data: PageData } = $props();

    let mapContainer = $state<HTMLDivElement>();
    let map = $state<any>();
    let loading = $state(false);
    let error = $state<string | null>(null);
    let timelineContainerWidth = $state(0);
    let timelineContainer = $state<HTMLDivElement>();
    let hoverMarker = $state<any>(null);
    
    // State for date selection
    let selectedDate = $state(
        data.selectedDate
            ? new Date(data.selectedDate).toISOString().split("T")[0]
            : new Date().toISOString().split("T")[0],
    );

    // Create a reactive async function for map initialization
    async function initializeMap() {
        if (
            !browser ||
            !mapContainer ||
            !data.coordinateSignals ||
            data.coordinateSignals.length <= 1
        ) {
            return;
        }

        try {
            loading = true;

            // Dynamically import Leaflet only on the client side
            const L = (await import("leaflet")).default;
            await import("leaflet/dist/leaflet.css");

            // Ensure container is visible and has dimensions
            if (mapContainer.offsetHeight === 0) {
                throw new Error("Map container not ready");
            }

            // Initialize the map
            const leafletMap = L.map(mapContainer).setView([0, 0], 13);
            map = leafletMap;

            // Force a resize after a short delay to ensure proper rendering
            setTimeout(() => {
                leafletMap.invalidateSize();
            }, 100);

            // Add a light-styled tile layer
            L.tileLayer(
                "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
                {
                    attribution: "© OpenStreetMap contributors © CARTO",
                    subdomains: "abcd",
                    maxZoom: 20,
                },
            ).addTo(leafletMap);

            // Convert coordinates to Leaflet format (lat, lng)
            const latLngs = data.coordinateSignals.map((signal) =>
                L.latLng(signal.coordinates[1], signal.coordinates[0]),
            );

            // Add the path as a polyline with blue coloring
            const polyline = L.polyline(latLngs, {
                color: "#2563eb", // blue-600
                weight: 4,
                opacity: 0.7, // 70% opacity
                smoothFactor: 1,
                lineJoin: "round",
                lineCap: "round",
            }).addTo(leafletMap);

            // Fit the map to the path bounds
            leafletMap.fitBounds(polyline.getBounds(), {
                padding: [50, 50],
            });

            console.log("Map initialized successfully");
            loading = false;
        } catch (err) {
            console.error("Failed to initialize map:", err);
            error = err instanceof Error ? err.message : "Failed to load map";
            loading = false;
        }
    }

    // Use $effect to manage the map lifecycle
    $effect(() => {
        // Track dependencies
        const container = mapContainer;
        const signals = data.coordinateSignals;

        if (container && signals && signals.length > 1) {
            // Initialize map without tracking to avoid re-runs
            untrack(() => {
                initializeMap();
            });
        }

        // Cleanup function
        return () => {
            if (map && map.remove) {
                map.remove();
                map = null;
            }
        };
    });

    // Binary search to find the nearest location point by timestamp
    function findNearestLocation(targetTime: Date) {
        if (!data.coordinateSignals || data.coordinateSignals.length === 0) {
            return null;
        }

        const targetMs = targetTime.getTime();
        let left = 0;
        let right = data.coordinateSignals.length - 1;
        let nearest = 0;
        let minDiff = Infinity;

        while (left <= right) {
            const mid = Math.floor((left + right) / 2);
            const midTime = new Date(
                data.coordinateSignals[mid].timestamp,
            ).getTime();
            const diff = Math.abs(midTime - targetMs);

            if (diff < minDiff) {
                minDiff = diff;
                nearest = mid;
            }

            if (midTime < targetMs) {
                left = mid + 1;
            } else {
                right = mid - 1;
            }
        }

        return data.coordinateSignals[nearest];
    }

    // Update hover marker position
    async function updateHoverMarker(hoveredTime: Date | null) {
        if (!map || !hoveredTime || !browser) return;

        const nearestLocation = findNearestLocation(hoveredTime);
        if (!nearestLocation) {
            if (hoverMarker) {
                map.removeLayer(hoverMarker);
                hoverMarker = null;
            }
            return;
        }

        const L = (await import("leaflet")).default;
        const latLng = L.latLng(
            nearestLocation.coordinates[1],
            nearestLocation.coordinates[0],
        );

        if (!hoverMarker) {
            // Create a new marker
            hoverMarker = L.circleMarker(latLng, {
                radius: 8,
                fillColor: "#2563eb",
                color: "#1e40af",
                weight: 2,
                opacity: 1,
                fillOpacity: 0.8,
            }).addTo(map);
        } else {
            // Update existing marker position
            hoverMarker.setLatLng(latLng);
        }
    }

    // Observe timeline container width
    $effect(() => {
        const container = timelineContainer;
        if (!container) return;

        const resizeObserver = new ResizeObserver((entries) => {
            for (const entry of entries) {
                timelineContainerWidth = entry.contentRect.width;
            }
        });

        resizeObserver.observe(container);

        return () => {
            resizeObserver.disconnect();
        };
    });
</script>

<Page>
    <div class="min-h-screen bg-white">
        <h1 class="text-3xl font-mono text-neutral-900 mb-2">Location</h1>
        <p class=" text-neutral-600 mb-6 max-w-2xl">
            A location-based view throughout your day.
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
            <p class="text-neutral-700">
                Showing location data for {selectedDate} ({data.userTimezone})
            </p>
        </div>

        <div class="mt-6">
            {#if error}
                <div class="p-4 bg-red-50 text-red-800 rounded-lg">
                    <p class="font-bold">Error loading map</p>
                    <p class="text-sm">{error}</p>
                </div>
            {:else if !data.coordinateSignals || data.coordinateSignals.length === 0}
                <div
                    class="flex items-center justify-center h-64 bg-gray-50 rounded-lg"
                >
                    <p class="text-gray-500">
                        No location data found for {selectedDate}.
                    </p>
                </div>
            {:else if data.coordinateSignals.length === 1}
                <div
                    class="flex items-center justify-center h-64 bg-gray-50 rounded-lg"
                >
                    <p class="text-gray-500">
                        Only one location point found. Need at least 2 points to
                        draw a path.
                    </p>
                </div>
            {:else}
                <!-- Timeline card -->
                <div
                    bind:this={timelineContainer}
                    class="rounded-lg border border-neutral-200 bg-white mb-4"
                    style="height: 60px; position: relative; overflow: visible;"
                >
                    {#if timelineContainerWidth > 0}
                        <TimelineContext
                            selectedDate={data.selectedDate}
                            containerWidth={timelineContainerWidth}
                            padding={0}
                            userTimezone={data.userTimezone}
                        >
                            <div class="relative w-full" style="height: 60px;">
                                <TimelineGrid
                                    selectedDate={data.selectedDate}
                                    userTimezone={data.userTimezone}
                                />

                                <!-- Location data availability indicator -->
                                <LocationDataIndicator
                                    coordinateSignals={data.coordinateSignals}
                                    selectedDate={data.selectedDate}
                                    userTimezone={data.userTimezone}
                                />

                                <div
                                    class="absolute inset-0 pointer-events-none"
                                >
                                    <TimelineLegend
                                        selectedDate={data.selectedDate}
                                        userTimezone={data.userTimezone}
                                    />
                                </div>
                                <TimelineCursor />
                            </div>
                            <TimelineHoverWatcher
                                onHoverChange={updateHoverMarker}
                            />
                        </TimelineContext>
                    {/if}
                </div>

                <!-- Map container -->
                <div class="relative">
                    {#if loading}
                        <div
                            class="absolute inset-0 flex items-center justify-center bg-white bg-opacity-75 z-10"
                        >
                            <p class="text-gray-500 animate-pulse">
                                Loading map...
                            </p>
                        </div>
                    {/if}
                    <div
                        bind:this={mapContainer}
                        class="rounded-lg border border-neutral-200"
                        style="height: 32rem;"
                    ></div>
                </div>
                <p class="text-xs text-gray-500 mt-2">
                    Found {data.coordinateSignals.length} location points
                </p>
            {/if}
        </div>
    </div>
</Page>

<style>
    @reference "../../../app.css";

    /* Fix for Leaflet CSS in SvelteKit */
    :global(.leaflet-container) {
        height: 100%;
        width: 100%;
        z-index: 1;
        background-color: #f5f5f5; /* neutral-100 */
        font-family: ui-monospace, SFMono-Regular, "SF Mono", Consolas,
            "Liberation Mono", Menlo, monospace;
    }

    /* Style the map controls to match the app */
    :global(.leaflet-control-container) {
        position: absolute;
        pointer-events: none;
    }

    :global(.leaflet-control) {
        pointer-events: auto;
    }

    /* Style zoom controls */
    :global(.leaflet-control-zoom) {
        border: 1px solid #e5e5e5 !important; /* neutral-200 */
        box-shadow: none !important;
        border-radius: 0.5rem !important;
        overflow: hidden;
    }

    :global(.leaflet-control-zoom a) {
        background-color: white !important;
        color: #525252 !important; /* neutral-600 */
        width: 32px !important;
        height: 32px !important;
        line-height: 32px !important;
        font-size: 18px !important;
        font-weight: 300 !important;
        border: none !important;
    }

    :global(.leaflet-control-zoom a:hover) {
        background-color: #f5f5f5 !important; /* neutral-100 */
    }

    /* Style attribution */
    :global(.leaflet-control-attribution) {
        background-color: rgba(255, 255, 255, 0.8) !important;
        color: #737373 !important; /* neutral-500 */
        font-size: 11px !important;
        padding: 2px 6px !important;
        border-radius: 0.25rem !important;
        margin: 0.5rem !important;
    }

    :global(.leaflet-control-attribution a) {
        color: #525252 !important; /* neutral-600 */
    }

    /* Remove default gray tile background while loading */
    :global(.leaflet-tile-container) {
        background-color: #f5f5f5; /* neutral-100 */
    }

    /* Style the popup if needed */
    :global(.leaflet-popup-content-wrapper) {
        background-color: white;
        border-radius: 0.5rem;
        box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1);
        border: 1px solid #e5e5e5; /* neutral-200 */
    }

    :global(.leaflet-popup-content) {
        color: #262626; /* neutral-800 */
        font-size: 14px;
    }

    /* Fix for missing marker images */
    :global(.leaflet-default-icon-path) {
        background-image: url(https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png);
    }

    /* Apply CSS filter to make tiles completely grayscale */
    :global(.leaflet-tile) {
        filter: grayscale(1) brightness(1.15) contrast(0.9) opacity(0.9);
    }

    /* Ensure the border is visible */
    :global(.leaflet-container) {
        border-color: #e5e5e5 !important; /* neutral-200 */
    }

    /* Timeline card specific styles */
    :global(.timeline-context) {
        font-size: 11px;
    }

    /* Adjust timeline cursor for the card view */
    :global(.timeline-cursor .time-badge) {
        top: -32px !important; /* Position above the timeline card */
        font-size: 11px;
        padding: 0.25rem 0.5rem;
    }

    :global(.timeline-cursor .cursor-line) {
        height: 60px !important; /* Match timeline card height */
    }

    :global(.timeline-cursor .click-hint) {
        display: none; /* Hide in compact view */
    }

    /* Ensure timeline legend text is visible */
    :global(.timeline-legend .hour-label) {
        font-size: 10px;
        line-height: 10px;
        top: 30px !important; /* Center in 60px height */
        transform: translateY(-50%) !important;
    }

    /* Adjust grid column colors for better visibility */
    :global(.hour-column.odd) {
        @apply bg-neutral-50;
    }

    /* Make grid visible in compact timeline */
    :global(.timeline-grid) {
        height: 60px !important;
    }
</style>
