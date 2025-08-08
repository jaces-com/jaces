<script lang="ts">
    import { Page, Tabs, Badge } from "$lib/components";
    import type { PageData } from "./$types";
    import "iconify-icon";

    let { data = $bindable() }: { data: PageData } = $props();
    let activeTab = $state('ingestion');

    // Format duration
    function formatDuration(
        start: Date | string | null,
        end: Date | string | null,
    ): string {
        if (!start || !end) return "—";
        const startTime = typeof start === "string" ? new Date(start) : start;
        const endTime = typeof end === "string" ? new Date(end) : end;
        const seconds = (endTime.getTime() - startTime.getTime()) / 1000;

        if (seconds < 60) return `${Math.round(seconds)}s`;
        if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
        return `${Math.round(seconds / 3600)}h`;
    }

    // Format bytes
    function formatBytes(bytes: number): string {
        if (!bytes || bytes === 0) return "0 B";
        const k = 1024;
        const sizes = ["B", "KB", "MB", "GB"];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
    }

    // Format date
    function formatDate(date: string | Date | null): string {
        if (!date) return "—";
        const d = typeof date === "string" ? new Date(date) : date;
        const now = new Date();
        const diff = now.getTime() - d.getTime();
        const minutes = Math.floor(diff / 60000);

        if (minutes < 1) return "Just now";
        if (minutes < 60) return `${minutes}m ago`;
        if (minutes < 1440) return `${Math.floor(minutes / 60)}h ago`;

        return d.toLocaleDateString();
    }

    // Get status color classes
    function getStatusBadgeVariant(status: string): "success" | "error" | "warning" | "default" {
        switch (status?.toUpperCase()) {
            case "RUNNING":
                return "warning";
            case "COMPLETED":
                return "success";
            case "FAILED":
                return "error";
            default:
                return "default";
        }
    }

    // Get source icon
    function getSourceIcon(sourceName: string): string {
        const iconMap: Record<string, string> = {
            ios: "ri:apple-line",
            mac: "ri:mac-line",
            google: "ri:google-line",
            plaid: "ri:bank-line",
            apple_ios_core_location: "ri:map-pin-line",
            apple_ios_mic_transcription: "ri:mic-line",
            apple_ios_healthkit: "ri:heart-pulse-line",
            apple_mac_apps: "ri:window-line",
            google_calendar: "ri:calendar-line",
            plaid_transactions: "ri:bank-line",
        };
        return iconMap[sourceName] || "ri:database-line";
    }

    // Get signal type label
    function getSignalTypeLabel(signalType: string): string {
        return signalType === "ambient" ? "Ambient" : "Episodic";
    }

    // Get signal type badge variant
    function getSignalTypeBadgeVariant(signalType: string): "default" | "success" {
        return signalType === "ambient" ? "default" : "success";
    }

    // Get signal description based on stream name
    function getSignalDescription(streamName: string): string {
        const signalMap: Record<string, string> = {
            apple_ios_core_location: "Coordinates, Altitude, Speed",
            apple_ios_healthkit: "Health Metrics",
            apple_ios_mic_audio: "Audio (Pending Transcription)",
            apple_mac_app_activity: "App Usage",
            google_calendar_events: "Calendar Events",
        };
        return signalMap[streamName] || "Signals";
    }

    const tabs = [
        { id: 'ingestion', label: 'Ingestion' },
        { id: 'signal-creation', label: 'Signal Creation' }
    ];
</script>

<Page>
    <div class="space-y-6">
        <!-- Header -->
        <div>
            <h1 class="text-3xl font-mono text-neutral-900">Data Pipeline</h1>
            <p class="mt-2 text-base text-neutral-600">
                Monitor data flow from ingestion to signal creation
            </p>
        </div>

        <!-- Tabs -->
        <Tabs bind:activeTab {tabs}>
            {#if activeTab === 'ingestion'}
                <!-- Ingestion Tab Content -->
                <div class="space-y-6">
                    <!-- Ingestion Stats -->
                    <div class="grid grid-cols-4 gap-4">
                        <div class="bg-white rounded-lg border border-neutral-200 p-4">
                            <p class="text-sm font-medium text-neutral-600">Active</p>
                            <p class="text-2xl font-semibold text-neutral-900 mt-1">
                                {data.ingestionStats.active || 0}
                            </p>
                        </div>
                        <div class="bg-white rounded-lg border border-neutral-200 p-4">
                            <p class="text-sm font-medium text-neutral-600">Completed Today</p>
                            <p class="text-2xl font-semibold text-neutral-900 mt-1">
                                {data.ingestionStats.completedToday || 0}
                            </p>
                        </div>
                        <div class="bg-white rounded-lg border border-neutral-200 p-4">
                            <p class="text-sm font-medium text-neutral-600">Failed Today</p>
                            <p class="text-2xl font-semibold text-neutral-900 mt-1">
                                {data.ingestionStats.failedToday || 0}
                            </p>
                        </div>
                        <div class="bg-white rounded-lg border border-neutral-200 p-4">
                            <p class="text-sm font-medium text-neutral-600">Data Volume</p>
                            <p class="text-2xl font-semibold text-neutral-900 mt-1">
                                {formatBytes(data.ingestionStats.dataVolumeToday || 0)}
                            </p>
                        </div>
                    </div>

                    <!-- Ingestion Activities Table -->
                    <div class="bg-white rounded-lg border border-neutral-200 overflow-hidden">
                        <div class="px-6 py-4 border-b border-neutral-200">
                            <h3 class="text-lg font-medium text-neutral-900">Recent Ingestion Activities</h3>
                        </div>

                        {#if data.ingestionActivities.length === 0}
                            <div class="p-12 text-center">
                                <iconify-icon
                                    icon="ri:download-cloud-line"
                                    width="48"
                                    height="48"
                                    class="text-neutral-400 mx-auto mb-4"
                                ></iconify-icon>
                                <p class="text-neutral-600">No recent ingestions</p>
                                <p class="text-sm text-neutral-500 mt-1">
                                    Data ingestions will appear here
                                </p>
                            </div>
                        {:else}
                            <table class="min-w-full divide-y divide-neutral-200">
                                <thead class="bg-neutral-100">
                                    <tr>
                                        <th scope="col" class="px-6 py-3 text-left text-xs font-mono font-medium text-neutral-500 uppercase tracking-wider">
                                            Source
                                        </th>
                                        <th scope="col" class="px-6 py-3 text-left text-xs font-mono font-medium text-neutral-500 uppercase tracking-wider">
                                            Stream
                                        </th>
                                        <th scope="col" class="px-6 py-3 text-left text-xs font-mono font-medium text-neutral-500 uppercase tracking-wider">
                                            Status
                                        </th>
                                        <th scope="col" class="px-6 py-3 text-left text-xs font-mono font-medium text-neutral-500 uppercase tracking-wider">
                                            Started
                                        </th>
                                        <th scope="col" class="px-6 py-3 text-left text-xs font-mono font-medium text-neutral-500 uppercase tracking-wider">
                                            Duration
                                        </th>
                                        <th scope="col" class="px-6 py-3 text-left text-xs font-mono font-medium text-neutral-500 uppercase tracking-wider">
                                            Data Size
                                        </th>
                                    </tr>
                                </thead>
                                <tbody class="bg-white divide-y divide-neutral-200">
                                    {#each data.ingestionActivities as activity}
                                        <tr class="hover:bg-neutral-100 transition-colors">
                                            <td class="px-6 py-4 whitespace-nowrap">
                                                <div class="flex items-center">
                                                    <iconify-icon
                                                        icon={getSourceIcon(activity.sourceName)}
                                                        width="20"
                                                        height="20"
                                                        class="text-neutral-600 mr-3"
                                                    ></iconify-icon>
                                                    <span class="text-sm font-medium text-neutral-900">
                                                        {activity.sourceDisplayName || activity.sourceName}
                                                    </span>
                                                </div>
                                            </td>
                                            <td class="px-6 py-4 whitespace-nowrap text-sm text-neutral-900">
                                                {activity.streamDisplayName || activity.streamName || "Unknown stream"}
                                            </td>
                                            <td class="px-6 py-4 whitespace-nowrap">
                                                <Badge variant={getStatusBadgeVariant(activity.status)} size="sm">
                                                    {activity.status}
                                                </Badge>
                                            </td>
                                            <td class="px-6 py-4 whitespace-nowrap text-sm text-neutral-500">
                                                {formatDate(activity.startedAt)}
                                            </td>
                                            <td class="px-6 py-4 whitespace-nowrap text-sm text-neutral-500">
                                                {formatDuration(activity.startedAt, activity.completedAt)}
                                            </td>
                                            <td class="px-6 py-4 whitespace-nowrap text-sm text-neutral-500">
                                                {#if activity.dataSizeBytes}
                                                    {formatBytes(activity.dataSizeBytes)}
                                                {:else}
                                                    —
                                                {/if}
                                            </td>
                                        </tr>
                                        {#if activity.errorMessage}
                                            <tr>
                                                <td colspan="6" class="px-6 py-2 bg-red-50">
                                                    <p class="text-sm text-red-600">
                                                        <iconify-icon icon="ri:error-warning-line" class="inline mr-1"></iconify-icon>
                                                        {activity.errorMessage}
                                                    </p>
                                                </td>
                                            </tr>
                                        {/if}
                                    {/each}
                                </tbody>
                            </table>
                        {/if}
                    </div>
                </div>
            {:else if activeTab === 'signal-creation'}
                <!-- Signal Creation Tab Content -->
                <div class="space-y-6">
                    <!-- Signal Creation Stats -->
                    <div class="grid grid-cols-4 gap-4">
                        <div class="bg-white rounded-lg border border-neutral-200 p-4">
                            <p class="text-sm font-medium text-neutral-600">Processing</p>
                            <p class="text-2xl font-semibold text-neutral-900 mt-1">
                                {data.signalStats.processing || 0}
                            </p>
                        </div>
                        <div class="bg-white rounded-lg border border-neutral-200 p-4">
                            <p class="text-sm font-medium text-neutral-600">Created Today</p>
                            <p class="text-2xl font-semibold text-neutral-900 mt-1">
                                {data.signalStats.createdToday || 0}
                            </p>
                        </div>
                        <div class="bg-white rounded-lg border border-neutral-200 p-4">
                            <p class="text-sm font-medium text-neutral-600">Failed Today</p>
                            <p class="text-2xl font-semibold text-neutral-900 mt-1">
                                {data.signalStats.failedToday || 0}
                            </p>
                        </div>
                        <div class="bg-white rounded-lg border border-neutral-200 p-4">
                            <p class="text-sm font-medium text-neutral-600">Success Rate</p>
                            <p class="text-2xl font-semibold text-neutral-900 mt-1">
                                {data.signalStats.successRate || 0}%
                            </p>
                        </div>
                    </div>

                    <!-- Signal Creation Activities Table -->
                    <div class="bg-white rounded-lg border border-neutral-200 overflow-hidden">
                        <div class="px-6 py-4 border-b border-neutral-200">
                            <h3 class="text-lg font-medium text-neutral-900">Recent Signal Creation Activities</h3>
                        </div>

                        {#if data.signalCreationActivities.length === 0}
                            <div class="p-12 text-center">
                                <iconify-icon
                                    icon="ri:pulse-line"
                                    width="48"
                                    height="48"
                                    class="text-neutral-400 mx-auto mb-4"
                                ></iconify-icon>
                                <p class="text-neutral-600">No recent signal creations</p>
                                <p class="text-sm text-neutral-500 mt-1">
                                    Signal processing will appear here
                                </p>
                            </div>
                        {:else}
                            <table class="min-w-full divide-y divide-neutral-200">
                                <thead class="bg-neutral-100">
                                    <tr>
                                        <th scope="col" class="px-6 py-3 text-left text-xs font-mono font-medium text-neutral-500 uppercase tracking-wider">
                                            Stream
                                        </th>
                                        <th scope="col" class="px-6 py-3 text-left text-xs font-mono font-medium text-neutral-500 uppercase tracking-wider">
                                            Signals Created
                                        </th>
                                        <th scope="col" class="px-6 py-3 text-left text-xs font-mono font-medium text-neutral-500 uppercase tracking-wider">
                                            Type
                                        </th>
                                        <th scope="col" class="px-6 py-3 text-left text-xs font-mono font-medium text-neutral-500 uppercase tracking-wider">
                                            Status
                                        </th>
                                        <th scope="col" class="px-6 py-3 text-left text-xs font-mono font-medium text-neutral-500 uppercase tracking-wider">
                                            Started
                                        </th>
                                        <th scope="col" class="px-6 py-3 text-left text-xs font-mono font-medium text-neutral-500 uppercase tracking-wider">
                                            Duration
                                        </th>
                                        <th scope="col" class="px-6 py-3 text-left text-xs font-mono font-medium text-neutral-500 uppercase tracking-wider">
                                            Records
                                        </th>
                                    </tr>
                                </thead>
                                <tbody class="bg-white divide-y divide-neutral-200">
                                    {#each data.signalCreationActivities as activity}
                                        <tr class="hover:bg-neutral-100 transition-colors">
                                            <td class="px-6 py-4 whitespace-nowrap">
                                                <div class="flex items-center">
                                                    <iconify-icon
                                                        icon={getSourceIcon(activity.sourceName)}
                                                        width="20"
                                                        height="20"
                                                        class="text-neutral-600 mr-3"
                                                    ></iconify-icon>
                                                    <span class="text-sm font-medium text-neutral-900">
                                                        {activity.streamDisplayName || activity.streamName || "Stream"}
                                                    </span>
                                                </div>
                                            </td>
                                            <td class="px-6 py-4 whitespace-nowrap text-sm text-neutral-900">
                                                {getSignalDescription(activity.streamName)}
                                            </td>
                                            <td class="px-6 py-4 whitespace-nowrap">
                                                {#if activity.signalType}
                                                    <Badge variant={getSignalTypeBadgeVariant(activity.signalType)} size="sm">
                                                        {getSignalTypeLabel(activity.signalType)}
                                                    </Badge>
                                                {/if}
                                            </td>
                                            <td class="px-6 py-4 whitespace-nowrap">
                                                <Badge variant={getStatusBadgeVariant(activity.status)} size="sm">
                                                    {activity.status}
                                                </Badge>
                                            </td>
                                            <td class="px-6 py-4 whitespace-nowrap text-sm text-neutral-500">
                                                {formatDate(activity.startedAt)}
                                            </td>
                                            <td class="px-6 py-4 whitespace-nowrap text-sm text-neutral-500">
                                                {formatDuration(activity.startedAt, activity.completedAt)}
                                            </td>
                                            <td class="px-6 py-4 whitespace-nowrap text-sm text-neutral-500">
                                                {#if activity.recordsProcessed}
                                                    {activity.recordsProcessed.toLocaleString()}
                                                {:else}
                                                    —
                                                {/if}
                                            </td>
                                        </tr>
                                        {#if activity.errorMessage}
                                            <tr>
                                                <td colspan="7" class="px-6 py-2 bg-red-50">
                                                    <p class="text-sm text-red-600">
                                                        <iconify-icon icon="ri:error-warning-line" class="inline mr-1"></iconify-icon>
                                                        {activity.errorMessage}
                                                    </p>
                                                </td>
                                            </tr>
                                        {/if}
                                    {/each}
                                </tbody>
                            </table>
                        {/if}
                    </div>
                </div>
            {/if}
        </Tabs>
    </div>
</Page>