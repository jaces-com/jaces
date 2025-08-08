#!/usr/bin/env tsx
import * as dotenv from 'dotenv';
dotenv.config({ path: '../../.env' });

import postgres from 'postgres';

// Handle both Docker and local development environments
const rawUrl = process.env.DATABASE_URL || '';
let databaseUrl = rawUrl.replace('postgresql+asyncpg://', 'postgresql://');

// Simple environment detection
const isDocker = process.env.NODE_ENV === 'production' || process.env.HOSTNAME || process.env.DOCKER_ENV;

if (!isDocker) {
  // Local development: replace postgres hostname with localhost
  databaseUrl = databaseUrl.replace('@postgres:', '@localhost:');
}

console.log('Applying schema changes...');
console.log('Database URL:', databaseUrl);

async function applyChanges() {
  const sql = postgres(databaseUrl, { max: 1 });
  
  try {
    // Create streams table
    await sql`
      CREATE TABLE IF NOT EXISTS "streams" (
        "id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
        "source_id" uuid NOT NULL,
        "stream_config_id" uuid NOT NULL,
        "enabled" boolean DEFAULT true NOT NULL,
        "sync_schedule" varchar,
        "initial_sync_type" varchar DEFAULT 'limited',
        "initial_sync_days" integer DEFAULT 90,
        "settings" json DEFAULT '{}'::json,
        "last_sync_at" timestamp with time zone,
        "last_sync_status" varchar,
        "last_sync_error" varchar,
        "created_at" timestamp with time zone DEFAULT now() NOT NULL,
        "updated_at" timestamp with time zone DEFAULT now() NOT NULL,
        CONSTRAINT "streams_unique_source_stream" UNIQUE("source_id","stream_config_id")
      )
    `;
    console.log('✅ Created streams table');

    // Add new columns to source_configs
    await sql`ALTER TABLE "source_configs" ADD COLUMN IF NOT EXISTS "video" varchar`;
    console.log('✅ Added video column to source_configs');
    
    await sql`ALTER TABLE "source_configs" ADD COLUMN IF NOT EXISTS "default_sync_schedule" varchar`;
    console.log('✅ Added default_sync_schedule column to source_configs');
    
    await sql`ALTER TABLE "source_configs" ADD COLUMN IF NOT EXISTS "min_sync_frequency" integer`;
    console.log('✅ Added min_sync_frequency column to source_configs');
    
    await sql`ALTER TABLE "source_configs" ADD COLUMN IF NOT EXISTS "max_sync_frequency" integer`;
    console.log('✅ Added max_sync_frequency column to source_configs');

    // Add foreign keys for streams table
    await sql`
      DO $$
      BEGIN
        IF NOT EXISTS (
          SELECT 1 FROM pg_constraint 
          WHERE conname = 'streams_source_id_sources_id_fk'
        ) THEN
          ALTER TABLE "streams" 
          ADD CONSTRAINT "streams_source_id_sources_id_fk" 
          FOREIGN KEY ("source_id") 
          REFERENCES "public"."sources"("id") 
          ON DELETE cascade ON UPDATE no action;
        END IF;
      END $$;
    `;
    console.log('✅ Added foreign key for source_id');

    await sql`
      DO $$
      BEGIN
        IF NOT EXISTS (
          SELECT 1 FROM pg_constraint 
          WHERE conname = 'streams_stream_config_id_stream_configs_id_fk'
        ) THEN
          ALTER TABLE "streams" 
          ADD CONSTRAINT "streams_stream_config_id_stream_configs_id_fk" 
          FOREIGN KEY ("stream_config_id") 
          REFERENCES "public"."stream_configs"("id") 
          ON DELETE restrict ON UPDATE no action;
        END IF;
      END $$;
    `;
    console.log('✅ Added foreign key for stream_config_id');

    // Create indexes
    await sql`CREATE INDEX IF NOT EXISTS "streams_source_id_idx" ON "streams" USING btree ("source_id")`;
    console.log('✅ Created index on streams.source_id');
    
    await sql`CREATE INDEX IF NOT EXISTS "streams_stream_config_id_idx" ON "streams" USING btree ("stream_config_id")`;
    console.log('✅ Created index on streams.stream_config_id');

    console.log('\n✅ All schema changes applied successfully!');
  } catch (error) {
    console.error('❌ Error applying schema changes:', error);
    process.exit(1);
  } finally {
    await sql.end();
  }
}

applyChanges();