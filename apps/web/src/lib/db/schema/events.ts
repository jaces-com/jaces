import { pgTable, timestamp, uuid, date, integer, real, jsonb, text } from "drizzle-orm/pg-core";

export const events = pgTable("events", {
	id: uuid("id").primaryKey().defaultRandom(),
	date: date("date").notNull(),
	clusterId: integer("cluster_id").notNull(),
	startTime: timestamp("start_time", { withTimezone: true }).notNull(),
	endTime: timestamp("end_time", { withTimezone: true }).notNull(),
	coreDensity: real("core_density").notNull(),
	clusterSize: integer("cluster_size").notNull(),
	persistence: real("persistence"),
	transitionIds: uuid("transition_ids").array(),
	signalContributions: jsonb("signal_contributions"),
	eventMetadata: jsonb("event_metadata"),
	eventType: text("event_type").default('activity'),
	createdAt: timestamp("created_at", { withTimezone: true }).defaultNow().notNull(),
});