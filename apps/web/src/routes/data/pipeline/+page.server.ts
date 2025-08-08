import type { PageServerLoad } from './$types';
import { db } from '$lib/db/client';
import { pipelineActivities, signalConfigs, sourceConfigs, streamConfigs } from '$lib/db/schema';
import { desc, eq, sql } from 'drizzle-orm';

export const load: PageServerLoad = async ({ url }) => {
	try {
		const limit = 10; // Show 10 of each type

		// Get recent ingestion activities - simplify the query
		const ingestionActivities = await db
			.select()
			.from(pipelineActivities)
			.leftJoin(streamConfigs, eq(pipelineActivities.streamId, streamConfigs.id))
			.leftJoin(sourceConfigs, eq(pipelineActivities.sourceName, sourceConfigs.name))
			.where(eq(pipelineActivities.activityType, 'ingestion'))
			.orderBy(desc(pipelineActivities.createdAt))
			.limit(limit);

		// Get recent signal creation activities
		const signalCreationActivities = await db
			.select()
			.from(pipelineActivities)
			.leftJoin(signalConfigs, eq(pipelineActivities.signalId, signalConfigs.id))
			.leftJoin(sourceConfigs, eq(pipelineActivities.sourceName, sourceConfigs.name))
			.leftJoin(streamConfigs, eq(pipelineActivities.streamId, streamConfigs.id))
			.where(eq(pipelineActivities.activityType, 'signal_creation'))
			.orderBy(desc(pipelineActivities.createdAt))
			.limit(limit);

		// Get ingestion statistics for today
		const [ingestionStats] = await db
			.select({
				active: sql<number>`SUM(CASE WHEN ${pipelineActivities.status} = 'running' THEN 1 ELSE 0 END)::int`,
				completedToday: sql<number>`SUM(CASE WHEN ${pipelineActivities.status} = 'completed' AND DATE(${pipelineActivities.completedAt}) = CURRENT_DATE THEN 1 ELSE 0 END)::int`,
				failedToday: sql<number>`SUM(CASE WHEN ${pipelineActivities.status} = 'failed' AND DATE(${pipelineActivities.completedAt}) = CURRENT_DATE THEN 1 ELSE 0 END)::int`,
				dataVolumeToday: sql<number>`SUM(CASE WHEN ${pipelineActivities.status} = 'completed' AND DATE(${pipelineActivities.completedAt}) = CURRENT_DATE THEN ${pipelineActivities.dataSizeBytes} ELSE 0 END)::bigint`
			})
			.from(pipelineActivities)
			.where(eq(pipelineActivities.activityType, 'ingestion'));

		// Get signal creation statistics for today
		const [signalStats] = await db
			.select({
				processing: sql<number>`SUM(CASE WHEN ${pipelineActivities.status} = 'running' THEN 1 ELSE 0 END)::int`,
				createdToday: sql<number>`SUM(CASE WHEN ${pipelineActivities.status} = 'completed' AND DATE(${pipelineActivities.completedAt}) = CURRENT_DATE THEN 1 ELSE 0 END)::int`,
				failedToday: sql<number>`SUM(CASE WHEN ${pipelineActivities.status} = 'failed' AND DATE(${pipelineActivities.completedAt}) = CURRENT_DATE THEN 1 ELSE 0 END)::int`,
				successRate: sql<number>`
					ROUND(
						100.0 * SUM(CASE WHEN ${pipelineActivities.status} = 'completed' AND DATE(${pipelineActivities.completedAt}) = CURRENT_DATE THEN 1 ELSE 0 END) / 
						NULLIF(SUM(CASE WHEN ${pipelineActivities.status} IN ('completed', 'failed') AND DATE(${pipelineActivities.completedAt}) = CURRENT_DATE THEN 1 ELSE 0 END), 0),
						1
					)
				`
			})
			.from(pipelineActivities)
			.where(eq(pipelineActivities.activityType, 'signal_creation'));

		const mappedIngestion = ingestionActivities.map(row => ({
			...row.pipeline_activities,
			streamName: row.stream_configs?.streamName,
			streamDisplayName: row.stream_configs?.displayName,
			sourceDisplayName: row.source_configs?.displayName
		}));
		return {
			ingestionActivities: mappedIngestion,
			signalCreationActivities: signalCreationActivities.map(row => ({
				...row.pipeline_activities,
				signalName: row.signal_configs?.signalName,
				signalDisplayName: row.signal_configs?.displayName,
				signalType: row.signal_configs?.computation?.value_type || 'continuous',
				sourceDisplayName: row.source_configs?.displayName,
				streamName: row.stream_configs?.streamName,
				streamDisplayName: row.stream_configs?.displayName
			})),
			ingestionStats: ingestionStats || {
				active: 0,
				completedToday: 0,
				failedToday: 0,
				dataVolumeToday: 0
			},
			signalStats: signalStats || {
				processing: 0,
				createdToday: 0,
				failedToday: 0,
				successRate: 0
			}
		};
	} catch (error) {
		console.error('Error loading pipeline data:', error);
		return {
			ingestionActivities: [],
			signalCreationActivities: [],
			ingestionStats: {
				active: 0,
				completedToday: 0,
				failedToday: 0,
				dataVolumeToday: 0
			},
			signalStats: {
				processing: 0,
				createdToday: 0,
				failedToday: 0,
				successRate: 0
			}
		};
	}
};