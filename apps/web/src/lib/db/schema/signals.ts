import { sql } from "drizzle-orm"
import {
  check,
  geometry,
  index,
  json,
  pgTable,
  real,
  timestamp,
  unique,
  uuid,
  varchar,
} from "drizzle-orm/pg-core"
import { signalConfigs } from "./signal_configs"
import { sourceConfigs } from "./source_configs"

export const signals = pgTable(
  "signals",
  {
    // Primary key
    id: uuid("id").primaryKey().defaultRandom(),


    signalId: uuid("signal_id")
      .notNull()
      .references(() => signalConfigs.id, { onDelete: "cascade" }),
    sourceName: varchar("source_name")
      .notNull()
      .references(() => sourceConfigs.name, { onDelete: "restrict" }),

    // Signal metadata
    timestamp: timestamp("timestamp", { withTimezone: true }).notNull(),
    confidence: real("confidence").notNull(),

    // Unstructured signal data
    signalName: varchar("signal_name").notNull(),
    signalValue: varchar("signal_value").notNull(),

    // Special type for geometry (when signalName = 'location')
    coordinates: geometry("coordinates", { type: "point", mode: "tuple", srid: 4326 }),

    // Group related signals from same source event
    sourceEventId: varchar("source_event_id").notNull(),

    // Additional metadata from source
    sourceMetadata: json("source_metadata"),

    // Timestamps
    createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
    updatedAt: timestamp("updated_at", { withTimezone: true }).notNull().defaultNow(),
  },
  (table) => ({
    // Composite indexes for queries
    sourceEventIdx: index("idx_ambient_signals_source_event").on(table.sourceEventId),
    signalNameIdx: index("idx_ambient_signals_signal_name").on(table.signalName),

    // Spatial index for location queries
    coordinatesIdx: index("idx_ambient_signals_coordinates")
      .using("gist", table.coordinates)
      .where(sql`${table.coordinates} IS NOT NULL`),

    // Unique constraint to prevent duplicates
    uniqueSourceSignal: unique("unique_source_signal").on(
      table.sourceName,
      table.sourceEventId,
      table.signalName,
    ),

    // Check constraints
    confidenceCheck: check(
      "ambient_signals_confidence_check",
      sql`${table.confidence} >= 0 AND ${table.confidence} <= 1`,
    ),
  }),
)

// Type exports
export type Signal = typeof signals.$inferSelect
export type NewSignal = typeof signals.$inferInsert
