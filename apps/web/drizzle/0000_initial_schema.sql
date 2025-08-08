CREATE TYPE "public"."activity_status" AS ENUM('pending', 'running', 'completed', 'failed', 'cancelled');--> statement-breakpoint
CREATE TYPE "public"."activity_type" AS ENUM('ingestion', 'signal_creation', 'transition_detection');--> statement-breakpoint
CREATE TABLE "events" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"date" date NOT NULL,
	"cluster_id" integer NOT NULL,
	"start_time" timestamp NOT NULL,
	"end_time" timestamp NOT NULL,
	"core_density" real NOT NULL,
	"cluster_size" integer NOT NULL,
	"persistence" real,
	"transition_ids" uuid[],
	"signal_contributions" jsonb,
	"event_metadata" jsonb,
	"event_type" text DEFAULT 'activity',
	"created_at" timestamp DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "users" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"first_name" varchar NOT NULL,
	"last_name" varchar NOT NULL,
	"email" varchar NOT NULL,
	"timezone" varchar(50) DEFAULT 'America/Chicago' NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "users_email_unique" UNIQUE("email")
);
--> statement-breakpoint
CREATE TABLE "source_configs" (
	"name" varchar PRIMARY KEY NOT NULL,
	"company" varchar NOT NULL,
	"platform" varchar DEFAULT 'cloud' NOT NULL,
	"device_type" varchar,
	"default_fidelity_score" real DEFAULT 1 NOT NULL,
	"auth_type" varchar DEFAULT 'oauth2',
	"display_name" varchar,
	"description" text,
	"icon" varchar,
	"video" varchar,
	"oauth_config" json,
	"sync_config" json,
	"default_sync_schedule" varchar,
	"min_sync_frequency" integer,
	"max_sync_frequency" integer,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "fidelity_score_check" CHECK ("source_configs"."default_fidelity_score" >= 0 AND "source_configs"."default_fidelity_score" <= 1)
);
--> statement-breakpoint
CREATE TABLE "sources" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"source_name" varchar NOT NULL,
	"instance_name" varchar NOT NULL,
	"is_active" boolean DEFAULT true NOT NULL,
	"device_id" varchar,
	"device_token" text,
	"device_type" varchar,
	"paired_device_name" varchar,
	"pairing_code" varchar(6),
	"pairing_expires_at" timestamp with time zone,
	"device_last_seen" timestamp with time zone,
	"oauth_access_token" text,
	"oauth_refresh_token" text,
	"oauth_expires_at" timestamp with time zone,
	"scopes" json,
	"instance_metadata" json DEFAULT '{}'::json,
	"last_sync_at" timestamp with time zone,
	"last_sync_status" varchar,
	"last_sync_error" text,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "stream_configs" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"stream_name" varchar NOT NULL,
	"source_name" varchar NOT NULL,
	"display_name" varchar NOT NULL,
	"description" text,
	"ingestion_type" varchar NOT NULL,
	"status" varchar DEFAULT 'active' NOT NULL,
	"cron_schedule" varchar,
	"settings" json,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "streams_ingestion_type_check" CHECK ("stream_configs"."ingestion_type" IN ('push', 'pull')),
	CONSTRAINT "streams_status_check" CHECK ("stream_configs"."status" IN ('active', 'paused', 'inactive'))
);
--> statement-breakpoint
CREATE TABLE "streams" (
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
);
--> statement-breakpoint
CREATE TABLE "signal_configs" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"signal_name" varchar NOT NULL,
	"display_name" varchar NOT NULL,
	"unit_ucum" varchar NOT NULL,
	"computation" json NOT NULL,
	"fidelity_score" real NOT NULL,
	"macro_weight" real DEFAULT 0.5,
	"min_transition_gap" real DEFAULT 300,
	"source_name" varchar NOT NULL,
	"stream_name" varchar NOT NULL,
	"description" varchar,
	"settings" json,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "signals_fidelity_score_check" CHECK ("signal_configs"."fidelity_score" >= 0 AND "signal_configs"."fidelity_score" <= 1)
);
--> statement-breakpoint
CREATE TABLE "semantic_configs" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"semantic_name" varchar NOT NULL,
	"display_name" varchar NOT NULL,
	"source_name" varchar NOT NULL,
	"stream_name" varchar NOT NULL,
	"semantic_type" varchar NOT NULL,
	"status" varchar DEFAULT 'active' NOT NULL,
	"description" varchar,
	"settings" json,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "semantic_configs_semantic_name_unique" UNIQUE("semantic_name"),
	CONSTRAINT "semantic_configs_status_check" CHECK ("semantic_configs"."status" IN ('active', 'paused', 'inactive')),
	CONSTRAINT "semantic_configs_type_check" CHECK ("semantic_configs"."semantic_type" IN ('page', 'database', 'document', 'email', 'message', 'post', 'file', 'other'))
);
--> statement-breakpoint
CREATE TABLE "pipeline_activities" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"activity_type" "activity_type" NOT NULL,
	"activity_name" varchar NOT NULL,
	"stream_id" uuid,
	"signal_id" uuid,
	"source_name" varchar NOT NULL,
	"status" "activity_status" DEFAULT 'pending' NOT NULL,
	"started_at" timestamp with time zone,
	"completed_at" timestamp with time zone,
	"records_processed" integer,
	"data_size_bytes" integer,
	"output_path" varchar,
	"activity_metadata" jsonb,
	"error_message" text,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "signals" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"signal_id" uuid NOT NULL,
	"source_name" varchar NOT NULL,
	"timestamp" timestamp with time zone NOT NULL,
	"confidence" real NOT NULL,
	"signal_name" varchar NOT NULL,
	"signal_value" varchar NOT NULL,
	"coordinates" geometry(point),
	"source_event_id" varchar NOT NULL,
	"source_metadata" json,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "unique_source_signal" UNIQUE("source_name","source_event_id","signal_name"),
	CONSTRAINT "ambient_signals_confidence_check" CHECK ("signals"."confidence" >= 0 AND "signals"."confidence" <= 1)
);
--> statement-breakpoint
CREATE TABLE "semantics" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"source_name" varchar NOT NULL,
	"stream_name" varchar NOT NULL,
	"semantic_id" varchar NOT NULL,
	"semantic_type" varchar NOT NULL,
	"title" text,
	"summary" text,
	"minio_path" varchar NOT NULL,
	"content_hash" varchar,
	"version" integer DEFAULT 1,
	"is_latest" boolean DEFAULT true,
	"author_id" varchar,
	"author_name" varchar,
	"parent_id" varchar,
	"source_created_at" timestamp with time zone,
	"source_updated_at" timestamp with time zone,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL,
	"extra_metadata" jsonb,
	CONSTRAINT "unique_semantic_version" UNIQUE("source_name","semantic_id","version")
);
--> statement-breakpoint
CREATE TABLE "signal_boundaries" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"source_name" varchar(255) NOT NULL,
	"signal_name" varchar(255) NOT NULL,
	"start_time" timestamp with time zone NOT NULL,
	"end_time" timestamp with time zone NOT NULL,
	"confidence" real NOT NULL,
	"detection_method" varchar(100) NOT NULL,
	"boundary_metadata" jsonb,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "signal_transitions" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"source_name" varchar(255) NOT NULL,
	"signal_name" varchar(255) NOT NULL,
	"transition_time" timestamp with time zone NOT NULL,
	"transition_type" varchar(50) NOT NULL,
	"change_magnitude" real,
	"change_direction" varchar(20),
	"before_mean" real,
	"before_std" real,
	"after_mean" real,
	"after_std" real,
	"confidence" real NOT NULL,
	"detection_method" varchar(100) NOT NULL,
	"transition_metadata" jsonb,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
ALTER TABLE "sources" ADD CONSTRAINT "sources_source_name_source_configs_name_fk" FOREIGN KEY ("source_name") REFERENCES "public"."source_configs"("name") ON DELETE restrict ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "stream_configs" ADD CONSTRAINT "stream_configs_source_name_source_configs_name_fk" FOREIGN KEY ("source_name") REFERENCES "public"."source_configs"("name") ON DELETE restrict ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "streams" ADD CONSTRAINT "streams_source_id_sources_id_fk" FOREIGN KEY ("source_id") REFERENCES "public"."sources"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "streams" ADD CONSTRAINT "streams_stream_config_id_stream_configs_id_fk" FOREIGN KEY ("stream_config_id") REFERENCES "public"."stream_configs"("id") ON DELETE restrict ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "signal_configs" ADD CONSTRAINT "signal_configs_source_name_source_configs_name_fk" FOREIGN KEY ("source_name") REFERENCES "public"."source_configs"("name") ON DELETE restrict ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "semantic_configs" ADD CONSTRAINT "semantic_configs_source_name_source_configs_name_fk" FOREIGN KEY ("source_name") REFERENCES "public"."source_configs"("name") ON DELETE restrict ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "pipeline_activities" ADD CONSTRAINT "pipeline_activities_stream_id_stream_configs_id_fk" FOREIGN KEY ("stream_id") REFERENCES "public"."stream_configs"("id") ON DELETE set null ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "pipeline_activities" ADD CONSTRAINT "pipeline_activities_signal_id_signal_configs_id_fk" FOREIGN KEY ("signal_id") REFERENCES "public"."signal_configs"("id") ON DELETE set null ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "signals" ADD CONSTRAINT "signals_signal_id_signal_configs_id_fk" FOREIGN KEY ("signal_id") REFERENCES "public"."signal_configs"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "signals" ADD CONSTRAINT "signals_source_name_source_configs_name_fk" FOREIGN KEY ("source_name") REFERENCES "public"."source_configs"("name") ON DELETE restrict ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "semantics" ADD CONSTRAINT "semantics_source_name_source_configs_name_fk" FOREIGN KEY ("source_name") REFERENCES "public"."source_configs"("name") ON DELETE restrict ON UPDATE no action;--> statement-breakpoint
CREATE INDEX "users_email_idx" ON "users" USING btree ("email");--> statement-breakpoint
CREATE INDEX "sources_platform_idx" ON "source_configs" USING btree ("platform");--> statement-breakpoint
CREATE INDEX "sources_instances_source_name_idx" ON "sources" USING btree ("source_name");--> statement-breakpoint
CREATE INDEX "sources_instances_device_id_idx" ON "sources" USING btree ("device_id");--> statement-breakpoint
CREATE UNIQUE INDEX "sources_instances_unique_device_id" ON "sources" USING btree ("device_id");--> statement-breakpoint
CREATE UNIQUE INDEX "sources_instances_unique_user_source_instance" ON "sources" USING btree ("source_name","instance_name");--> statement-breakpoint
CREATE INDEX "streams_source_name_idx" ON "stream_configs" USING btree ("source_name");--> statement-breakpoint
CREATE INDEX "streams_stream_name_idx" ON "stream_configs" USING btree ("stream_name");--> statement-breakpoint
CREATE INDEX "streams_source_id_idx" ON "streams" USING btree ("source_id");--> statement-breakpoint
CREATE INDEX "streams_stream_config_id_idx" ON "streams" USING btree ("stream_config_id");--> statement-breakpoint
CREATE INDEX "signals_source_name_idx" ON "signal_configs" USING btree ("source_name");--> statement-breakpoint
CREATE INDEX "signals_signal_name_idx" ON "signal_configs" USING btree ("signal_name");--> statement-breakpoint
CREATE INDEX "semantic_configs_source_name_idx" ON "semantic_configs" USING btree ("source_name");--> statement-breakpoint
CREATE INDEX "semantic_configs_stream_name_idx" ON "semantic_configs" USING btree ("stream_name");--> statement-breakpoint
CREATE INDEX "semantic_configs_semantic_type_idx" ON "semantic_configs" USING btree ("semantic_type");--> statement-breakpoint
CREATE INDEX "pipeline_activities_activity_type_idx" ON "pipeline_activities" USING btree ("activity_type");--> statement-breakpoint
CREATE INDEX "pipeline_activities_status_idx" ON "pipeline_activities" USING btree ("status");--> statement-breakpoint
CREATE INDEX "pipeline_activities_stream_id_idx" ON "pipeline_activities" USING btree ("stream_id");--> statement-breakpoint
CREATE INDEX "pipeline_activities_signal_id_idx" ON "pipeline_activities" USING btree ("signal_id");--> statement-breakpoint
CREATE INDEX "pipeline_activities_created_at_idx" ON "pipeline_activities" USING btree ("created_at");--> statement-breakpoint
CREATE INDEX "idx_ambient_signals_source_event" ON "signals" USING btree ("source_event_id");--> statement-breakpoint
CREATE INDEX "idx_ambient_signals_signal_name" ON "signals" USING btree ("signal_name");--> statement-breakpoint
CREATE INDEX "idx_ambient_signals_coordinates" ON "signals" USING gist ("coordinates") WHERE "signals"."coordinates" IS NOT NULL;--> statement-breakpoint
CREATE INDEX "idx_semantics_source_name" ON "semantics" USING btree ("source_name");--> statement-breakpoint
CREATE INDEX "idx_semantics_semantic_id" ON "semantics" USING btree ("semantic_id");--> statement-breakpoint
CREATE INDEX "idx_semantics_semantic_type" ON "semantics" USING btree ("semantic_type");--> statement-breakpoint
CREATE INDEX "idx_semantics_title" ON "semantics" USING btree ("title");--> statement-breakpoint
CREATE INDEX "idx_semantics_is_latest" ON "semantics" USING btree ("is_latest");--> statement-breakpoint
CREATE INDEX "idx_signal_boundary_source" ON "signal_boundaries" USING btree ("source_name","signal_name");--> statement-breakpoint
CREATE INDEX "idx_signal_transition_source" ON "signal_transitions" USING btree ("source_name","signal_name");