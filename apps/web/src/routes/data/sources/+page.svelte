<script lang="ts">
	import { Page, Badge, Button } from "$lib/components";
	import "iconify-icon";
	import type { PageData } from "./$types";

	// Import videos directly
	import googleVideo from "$lib/assets/videos/google2.webm";
	import iosVideo from "$lib/assets/videos/ios.webm";
	import macVideo from "$lib/assets/videos/mac2.webm";
	import notionVideo from "$lib/assets/videos/notion.webm";

	// Create a map of source names to video URLs
	const videoMap: Record<string, string> = {
		google: googleVideo,
		ios: iosVideo,
		mac: macVideo,
		notion: notionVideo,
	};

	function getVideoSrc(sourceName: string): string | null {
		return videoMap[sourceName] || null;
	}

	let { data }: { data: PageData } = $props();

	// Track which card is being hovered
	let hoveredSource = $state<string | null>(null);

	// Store video element references
	let videoElements: Record<string, HTMLVideoElement> = {};

	// Video action to handle play/pause
	function handleVideo(node: HTMLVideoElement) {
		const sourceName = node.dataset.sourceName;

		// Preload the video to avoid flash
		node.load();

		$effect(() => {
			if (hoveredSource === sourceName) {
				node.play().catch(() => {
					// Ignore autoplay errors
				});
			} else {
				node.pause();
				// Don't reset currentTime to avoid flash
			}
		});

		return {
			destroy() {
				// Cleanup if needed
			},
		};
	}

	// Timer for real-time "last seen" updates
	let currentTime = $state(new Date());

	$effect(() => {
		const timer = setInterval(() => {
			currentTime = new Date();
		}, 1000);

		return () => clearInterval(timer);
	});

	// Get status badge variant for a source
	function getStatusBadgeVariant(source: any): "success" | "error" | "warning" | "default" | "info" {
		if (!source.is_connected) {
			return source.enabled ? "info" : "default";
		}
		
		switch (source.status) {
			case 'active':
				return 'success';
			case 'authenticated':
				return 'warning';
			case 'paused':
				return 'default';
			case 'needs_reauth':
			case 'error':
				return 'error';
			default:
				return 'default';
		}
	}

	// Get status display text for a source
	function getStatusText(source: any): string {
		if (!source.is_connected) {
			return source.enabled ? 'Available' : 'Disabled';
		}
		
		switch (source.status) {
			case 'authenticated':
				return 'Setup Required';
			case 'active':
				return 'Active';
			case 'paused':
				return 'Paused';
			case 'needs_reauth':
				return 'Reconnect';
			case 'error':
				return 'Error';
			default:
				return 'Unknown';
		}
	}

	// Get button text based on source status
	function getButtonText(source: any): string {
		if (!source.is_connected) {
			return 'Connect';
		}
		
		switch (source.status) {
			case 'authenticated':
				return 'Configure';
			case 'active':
				return 'View';
			case 'paused':
				return 'Resume';
			case 'needs_reauth':
				return 'Reconnect';
			case 'error':
				return 'Fix';
			default:
				return 'View';
		}
	}

	// Get button href based on source status
	function getButtonHref(source: any): string {
		if (!source.is_connected) {
			return `/data/sources/new?source=${source.name}`;
		}
		
		if (source.status === 'authenticated') {
			return `/data/sources/new?source=${source.name}&configure=true`;
		}
		
		if (source.status === 'needs_reauth') {
			return `/data/sources/new?source=${source.name}&reauth=true`;
		}
		
		return `/data/sources/${source.id}`;
	}
</script>

<Page>
	<div class="">
		<div class="flex justify-between items-center mb-8">
			<div>
				<h1 class="text-3xl text-neutral-900 mb-2 font-mono">
					Data Sources
				</h1>
				<p class="text-neutral-600">
					Connect your devices and cloud services to start syncing
					data
				</p>
			</div>
		</div>

		{#if data.error}
			<div class="bg-red-50 border border-red-200 rounded-lg p-4 mb-6">
				<p class="text-red-700">{data.error}</p>
			</div>
		{/if}

		<!-- All Sources -->
		{#if data.sources && data.sources.length > 0}
			<div class="mb-12">
				<div class="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
					{#each data.sources as source}
						{@const videoSrc = getVideoSrc(source.name)}
						<div
							class="group bg-white border border-neutral-200 rounded-lg overflow-hidden hover:border-neutral-300 transition-colors duraiton-300 cursor-pointer"
							role="button"
							tabindex="0"
							onmouseenter={() => (hoveredSource = source.name)}
							onmouseleave={() => (hoveredSource = null)}
							onclick={() => {
								window.location.href = getButtonHref(source);
							}}
							onkeydown={(e) => {
								if (e.key === "Enter" || e.key === " ") {
									e.preventDefault();
									window.location.href = getButtonHref(source);
								}
							}}
						>
							{#if videoSrc}
								<div
									class="relative w-full aspect-video bg-neutral-900 overflow-hidden"
								>
									<video
										class="absolute inset-0 w-full h-full object-cover"
										muted
										loop
										playsinline
										bind:this={videoElements[source.name]}
										use:handleVideo
										data-source-name={source.name}
									>
										<source
											src={videoSrc}
											type="video/webm"
										/>
									</video>
								</div>
							{/if}
							<div class="p-6">
								<div
									class="flex items-center justify-between mb-2"
								>
									<div class="flex items-center gap-3">
										{#if source.icon}
											<iconify-icon
												icon={source.icon}
												class="text-2xl text-neutral-700"
											></iconify-icon>
										{/if}
										<h3
											class="text-xl font-semibold text-neutral-900 font-mono"
										>
											{source.display_name}
										</h3>
									</div>
									<Badge
										variant={getStatusBadgeVariant(source)}
										size="sm"
									>
										{getStatusText(source)}
									</Badge>
								</div>
								<p class="text-sm text-neutral-600 my-4">
									{source.description}
								</p>
								<div class="flex flex-col gap-2 text-sm">
									<div class="flex justify-between">
										<span class="text-neutral-500"
											>Platform:</span
										>
										<span class="text-neutral-700"
											>{source.platform}</span
										>
									</div>
									<div class="flex justify-between">
										<span class="text-neutral-500"
											>Auth:</span
										>
										<span class="text-neutral-700"
											>{source.auth_type}</span
										>
									</div>
								</div>
								<div class="mt-4">
									<Button
										href={getButtonHref(source)}
										text={getButtonText(source)}
										type="link"
										variant={source.is_connected
											? "filled"
											: "outline"}
										className={source.is_connected
											? "group-hover:bg-gradient-to-br group-hover:from-blue-700 group-hover:via-blue-600 group-hover:to-indigo-400"
											: "group-hover:bg-neutral-800 group-hover:text-white"}
									/>
								</div>
							</div>
						</div>
					{/each}
				</div>
			</div>
		{/if}
	</div>
</Page>
