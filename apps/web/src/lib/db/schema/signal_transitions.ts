import { pgTable, uuid, timestamp, real, text, varchar, jsonb, index, uniqueIndex } from 'drizzle-orm/pg-core';
import { relations } from 'drizzle-orm';

export const signalTransitions = pgTable('signal_transitions', {
  id: uuid('id').defaultRandom().primaryKey(),
  sourceName: varchar('source_name', { length: 255 }).notNull(),
  signalName: varchar('signal_name', { length: 255 }).notNull(),
  transitionTime: timestamp('transition_time', { withTimezone: true }).notNull(),
  transitionType: varchar('transition_type', { length: 50 }).notNull(), // 'changepoint' or 'data_gap'
  changeMagnitude: real('change_magnitude'), // Size of the change
  changeDirection: varchar('change_direction', { length: 20 }), // 'increase', 'decrease', null for gaps
  beforeMean: real('before_mean'), // Mean value before transition
  beforeStd: real('before_std'), // Std deviation before transition
  afterMean: real('after_mean'), // Mean value after transition
  afterStd: real('after_std'), // Std deviation after transition
  confidence: real('confidence').notNull(),
  detectionMethod: varchar('detection_method', { length: 100 }).notNull(),
  transitionMetadata: jsonb('transition_metadata'),
  createdAt: timestamp('created_at', { withTimezone: true }).defaultNow().notNull(),
}, (table) => {
  return {
    sourceSignalIdx: index('idx_signal_transition_source').on(table.sourceName, table.signalName),
    // Unique constraint to support ON CONFLICT in Python code
    uniqueTransition: uniqueIndex('unique_signal_transition').on(
      table.sourceName, 
      table.signalName, 
      table.transitionTime, 
      table.transitionType, 
      table.changeDirection
    ),
  };
});


export type SignalTransition = typeof signalTransitions.$inferSelect;
export type NewSignalTransition = typeof signalTransitions.$inferInsert;