import { pgTable, uuid, varchar, boolean, real, timestamp, json, check, index, unique } from 'drizzle-orm/pg-core';
import { sql } from 'drizzle-orm';
import { sourceConfigs } from './source_configs';

// This table replaces the old "connections" table
// Each record represents an active signal stream from a source
export const signalConfigs = pgTable('signal_configs', {
  // Primary key
  id: uuid('id').primaryKey().defaultRandom(),

  // Signal configuration
  signalName: varchar('signal_name').notNull(), // e.g., 'apple_ios_speed' (triadic: company_source_signal)
  displayName: varchar('display_name').notNull(), // e.g., 'Movement Speed'
  unitUcum: varchar('unit_ucum').notNull(), // e.g., 'm/s' (UCUM format)
  computation: json('computation').$type<{
    algorithm: string;
    cost_function?: string;
    distance_metric?: string;
    value_type: string;
  }>().notNull(),

  // Signal configuration
  fidelityScore: real('fidelity_score').notNull(),
  macroWeight: real('macro_weight').default(0.5),
  minTransitionGap: real('min_transition_gap').default(300),
  sourceName: varchar('source_name')
    .notNull()
    .references(() => sourceConfigs.name, { onDelete: 'restrict' }),
  
  // Stream reference
  streamName: varchar('stream_name').notNull(),

  // User data
  description: varchar('description'),

  // Settings
  settings: json('settings').$type<Record<string, any>>(),

  // Timestamps
  createdAt: timestamp('created_at', { withTimezone: true }).notNull().defaultNow(),
  updatedAt: timestamp('updated_at', { withTimezone: true }).notNull().defaultNow(),
}, (table) => ({
  // Indexes
  sourceNameIdx: index('signals_source_name_idx').on(table.sourceName),
  signalNameIdx: index('signals_signal_name_idx').on(table.signalName),


  // Check constraints
  fidelityScoreCheck: check(
    'signals_fidelity_score_check',
    sql`${table.fidelityScore} >= 0 AND ${table.fidelityScore} <= 1`
  ),
}));

// Type exports
export type SignalConfig = typeof signalConfigs.$inferSelect;
export type NewSignalConfig = typeof signalConfigs.$inferInsert;