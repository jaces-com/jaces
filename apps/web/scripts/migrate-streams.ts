// Script to migrate stream configurations from sources.instance_metadata to streams table
import { db } from '../src/lib/db/client';
import { sources, streamConfigs, streams } from '../src/lib/db/schema';
import { eq } from 'drizzle-orm';

async function migrateStreams() {
	console.log('Starting stream migration...');

	try {
		// Get all sources with stream configurations in metadata
		const allSources = await db.select().from(sources);

		for (const source of allSources) {
			const metadata = source.instanceMetadata as any;
			
			// Check if this source has stream configs in metadata
			if (metadata?.streamConfigs && Array.isArray(metadata.streamConfigs)) {
				console.log(`\nMigrating streams for source: ${source.sourceName} (${source.id})`);
				
				// Get all available stream configs for this source type
				const availableStreamConfigs = await db
					.select()
					.from(streamConfigs)
					.where(eq(streamConfigs.sourceName, source.sourceName));

				// Create a map for easy lookup
				const streamConfigMap = new Map(
					availableStreamConfigs.map(sc => [sc.streamName, sc])
				);

				// First, check if streams already exist for this source
				const existingStreams = await db
					.select()
					.from(streams)
					.where(eq(streams.sourceId, source.id));

				if (existingStreams.length > 0) {
					console.log(`  Skipping - ${existingStreams.length} streams already exist`);
					continue;
				}

				// Migrate each stream configuration
				let migratedCount = 0;
				for (const streamSetting of metadata.streamConfigs) {
					const streamConfig = streamConfigMap.get(streamSetting.streamName);
					
					if (!streamConfig) {
						console.warn(`  Stream config not found for: ${streamSetting.streamName}`);
						continue;
					}

					if (streamSetting.enabled) {
						const [newStream] = await db
							.insert(streams)
							.values({
								sourceId: source.id,
								streamConfigId: streamConfig.id,
								enabled: true,
								syncSchedule: streamSetting.syncSchedule || streamConfig.cronSchedule,
								initialSyncType: streamSetting.initialSyncType || 'limited',
								initialSyncDays: streamSetting.initialSyncDays || 90,
								settings: streamSetting.settings || {},
							})
							.returning();
						
						console.log(`  ✓ Migrated stream: ${streamSetting.streamName} (${newStream.id})`);
						migratedCount++;
					}
				}

				console.log(`  Migrated ${migratedCount} streams for source ${source.id}`);
			}
		}

		console.log('\nMigration complete!');
		
		// Verify migration
		const totalStreams = await db.select().from(streams);
		console.log(`\nTotal streams in database: ${totalStreams.length}`);
		
		for (const stream of totalStreams) {
			const [config] = await db
				.select()
				.from(streamConfigs)
				.where(eq(streamConfigs.id, stream.streamConfigId))
				.limit(1);
			
			console.log(`  - ${config.streamName}: ${stream.enabled ? 'enabled' : 'disabled'}, schedule: ${stream.syncSchedule}`);
		}
		
	} catch (error) {
		console.error('Migration failed:', error);
		process.exit(1);
	}

	process.exit(0);
}

// Run the migration
migrateStreams();