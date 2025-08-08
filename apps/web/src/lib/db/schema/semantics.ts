import { pgTable, timestamp, uuid, varchar, text, integer, boolean, jsonb, unique, index } from "drizzle-orm/pg-core"
import { sourceConfigs } from "./source_configs"

// Semantics table for content-based data (documents, pages, emails, etc.)
// Stores lightweight index with full content in MinIO
export const semantics = pgTable("semantics", {
  // Primary key
  id: uuid("id").primaryKey().defaultRandom(),
  
  // Source tracking
  sourceName: varchar("source_name").notNull()
    .references(() => sourceConfigs.name, { onDelete: "restrict" }),
  streamName: varchar("stream_name").notNull(),
  
  // Semantic identity
  semanticId: varchar("semantic_id").notNull(), // Source's unique ID (e.g., Notion page ID)
  semanticType: varchar("semantic_type").notNull(), // page, database, block, email, etc.
  
  // Searchable fields (lightweight index)
  title: text("title"),
  summary: text("summary"), // First 500 chars of content for preview
  
  // Storage reference
  minioPath: varchar("minio_path").notNull(), // Path to full content in MinIO
  
  // Versioning & deduplication
  contentHash: varchar("content_hash"), // SHA256 of content
  version: integer("version").default(1),
  isLatest: boolean("is_latest").default(true),
  
  // Metadata
  authorId: varchar("author_id"),
  authorName: varchar("author_name"),
  parentId: varchar("parent_id"), // For hierarchical content
  
  // Timestamps from source
  sourceCreatedAt: timestamp("source_created_at", { withTimezone: true }),
  sourceUpdatedAt: timestamp("source_updated_at", { withTimezone: true }),
  
  // System timestamps
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
  updatedAt: timestamp("updated_at", { withTimezone: true }).notNull().defaultNow(),
  
  // Source-specific metadata
  extraMetadata: jsonb("extra_metadata"),
}, (table) => ({
  // Unique constraint for versioning
  uniqueSemanticVersion: unique("unique_semantic_version").on(
    table.sourceName,
    table.semanticId,
    table.version
  ),
  
  // Indexes for search and queries
  sourceNameIdx: index("idx_semantics_source_name").on(table.sourceName),
  semanticIdIdx: index("idx_semantics_semantic_id").on(table.semanticId),
  semanticTypeIdx: index("idx_semantics_semantic_type").on(table.semanticType),
  titleIdx: index("idx_semantics_title").on(table.title),
  isLatestIdx: index("idx_semantics_is_latest").on(table.isLatest),
}))

// Type exports
export type Semantic = typeof semantics.$inferSelect
export type NewSemantic = typeof semantics.$inferInsert
