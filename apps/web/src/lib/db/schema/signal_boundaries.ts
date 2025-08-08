import { pgTable, uuid, timestamp, real, text, varchar, jsonb, index } from 'drizzle-orm/pg-core';
import { relations } from 'drizzle-orm';

export const signalBoundaries = pgTable('signal_boundaries', {
  id: uuid('id').defaultRandom().primaryKey(),
  sourceName: varchar('source_name', { length: 255 }).notNull(),
  signalName: varchar('signal_name', { length: 255 }).notNull(),
  startTime: timestamp('start_time', { withTimezone: true }).notNull(),
  endTime: timestamp('end_time', { withTimezone: true }).notNull(),
  confidence: real('confidence').notNull(),
  detectionMethod: varchar('detection_method', { length: 100 }).notNull(),
  boundaryMetadata: jsonb('boundary_metadata'),
  createdAt: timestamp('created_at', { withTimezone: true }).defaultNow().notNull(),
}, (table) => {
  return {
    sourceSignalIdx: index('idx_signal_boundary_source').on(table.sourceName, table.signalName),
  };
});


export type SignalBoundary = typeof signalBoundaries.$inferSelect;
export type NewSignalBoundary = typeof signalBoundaries.$inferInsert;