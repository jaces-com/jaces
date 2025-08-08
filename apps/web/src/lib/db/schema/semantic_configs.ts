import { pgTable, uuid, varchar, timestamp, json, index, check } from 'drizzle-orm/pg-core';
import { sql } from 'drizzle-orm';
import { sourceConfigs } from './source_configs';

// Configuration for semantic data types (documents, pages, emails, etc.)
export const semanticConfigs = pgTable('semantic_configs', {
  // Primary key
  id: uuid('id').primaryKey().defaultRandom(),

  // Semantic configuration
  semanticName: varchar('semantic_name').notNull().unique(), // e.g., 'notion_pages', 'google_docs'
  displayName: varchar('display_name').notNull(), // e.g., 'Notion Pages'
  
  // References
  sourceName: varchar('source_name')
    .notNull()
    .references(() => sourceConfigs.name, { onDelete: 'restrict' }),
  streamName: varchar('stream_name').notNull(), // e.g., 'notion_pages'
  
  // Semantic type
  semanticType: varchar('semantic_type').notNull(), // 'page', 'document', 'email', 'message', etc.
  
  // Status
  status: varchar('status').notNull().default('active'),
  
  // Configuration
  description: varchar('description'),
  settings: json('settings').$type<{
    syncMode?: 'incremental' | 'full_refresh' | 'initial';
    lookbackDays?: number;
    includeArchived?: boolean;
    filters?: Record<string, any>;
  }>(),
  
  // Timestamps
  createdAt: timestamp('created_at', { withTimezone: true }).notNull().defaultNow(),
  updatedAt: timestamp('updated_at', { withTimezone: true }).notNull().defaultNow(),
}, (table) => ({
  // Indexes
  sourceNameIdx: index('semantic_configs_source_name_idx').on(table.sourceName),
  streamNameIdx: index('semantic_configs_stream_name_idx').on(table.streamName),
  semanticTypeIdx: index('semantic_configs_semantic_type_idx').on(table.semanticType),
  
  // Check constraints
  statusCheck: check(
    'semantic_configs_status_check',
    sql`${table.status} IN ('active', 'paused', 'inactive')`
  ),
  semanticTypeCheck: check(
    'semantic_configs_type_check', 
    sql`${table.semanticType} IN ('page', 'database', 'document', 'email', 'message', 'post', 'file', 'other')`
  ),
}));

export type SemanticConfig = typeof semanticConfigs.$inferSelect;
export type NewSemanticConfig = typeof semanticConfigs.$inferInsert;