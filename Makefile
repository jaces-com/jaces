# Makefile
# Provides simple shortcuts for managing the Jaces project services.

# Default target - show help when just 'make' is run
.DEFAULT_GOAL := help

# === CONFIGURATION ===
# Database Configuration
DB_USER := jaces_user
DB_PASS := jaces_password
DB_NAME := jaces
DB_HOST := localhost
DB_PORT := 5432
DB_URL := postgresql://$(DB_USER):$(DB_PASS)@$(DB_HOST):$(DB_PORT)/$(DB_NAME)
DB_URL_DOCKER := postgresql://$(DB_USER):$(DB_PASS)@host.docker.internal:$(DB_PORT)/$(DB_NAME)

# Service Ports (defaults, can be overridden by .env)
WEB_PORT ?= 3000
STUDIO_PORT ?= 4983
MINIO_PORT ?= 9000
MINIO_CONSOLE_PORT ?= 9001
REDIS_PORT ?= 6379
PROCESSING_PORT ?= 8001

# === PHONY TARGETS ===
.PHONY: help dev stop logs ps rebuild clean reset
.PHONY: db-push db-migrate db-seed db-reset db-python db-studio
.PHONY: env-check env-setup deploy-init deploy-ec2 deploy-update deploy-logs prod
.PHONY: mac-install mac-run minio-download minio-download-date minio-process

# === DEVELOPMENT COMMANDS ===

# Check if .env exists, create from example if not
env-check:
	@if [ ! -f .env ]; then \
		echo "📋 No .env file found. Creating from .env.example..."; \
		cp .env.example .env; \
		echo "✅ Created .env file with default development settings"; \
		echo "   You can customize it later if needed for OAuth integrations"; \
	fi

# Setup environment file (force copy from example)
env-setup:
	@echo "📋 Creating .env from .env.example..."
	@cp .env.example .env
	@echo "✅ Created .env file"

# Start development environment with all services
dev: env-check
	@echo "🚀 Starting Jaces in development mode..."
	docker-compose up --build -d
	@echo "⏳ Waiting for services to initialize..."
	@sleep 5
	@echo "🪣 Initializing MinIO buckets..."
	@docker-compose exec -T minio mc alias set local http://localhost:9000 $${MINIO_ROOT_USER:-minioadmin} $${MINIO_ROOT_PASSWORD:-minioadmin} &>/dev/null || true
	@docker-compose exec -T minio mc mb local/jaces --ignore-existing &>/dev/null || true
	@echo "🎨 Starting Drizzle Studio..."
	@docker-compose exec -d -e DATABASE_URL="$(DB_URL_DOCKER)" web pnpm drizzle-kit studio --host 0.0.0.0 --port $(STUDIO_PORT) &>/dev/null || true
	@echo ""
	@echo "✅ Development environment is ready!"
	@echo "   📱 Web app: http://localhost:$(WEB_PORT)"
	@echo "   🎨 Drizzle Studio: http://localhost:$(STUDIO_PORT)"
	@echo "   📦 MinIO Console: http://localhost:$(MINIO_CONSOLE_PORT)"
	@echo "   🔧 Processing API: http://localhost:$(PROCESSING_PORT)"
	@echo ""
	@echo "   Run 'make logs' to see logs"
	@echo "   Run 'make stop' to shut down"

# Stop all services
stop:
	@echo "🛑 Stopping all Jaces services..."
	docker-compose down

# View logs for all services
logs:
	@echo "📄 Tailing logs for all services..."
	docker-compose logs -f

# Show service status
ps:
	@echo "📋 Current service status:"
	@docker-compose ps

# Force rebuild all containers
rebuild:
	@echo "🔨 Force rebuilding all containers..."
	docker-compose down
	docker-compose build --no-cache
	docker-compose up -d

# === DATABASE COMMANDS ===

# Push schema changes directly to database (dev only)
db-push:
	@echo "⚡ Pushing schema changes to database..."
	docker-compose exec web pnpm db:push

# Run migrations
db-migrate:
	@echo "🚀 Running database migrations..."
	docker-compose exec web pnpm db:migrate

# Seed database with test data
db-seed:
	@echo "🌱 Seeding database with TypeScript seeds..."
	(cd apps/web && DATABASE_URL="$(DB_URL)" MINIO_ENDPOINT="localhost:9000" pnpm db:seed)

# Quick database reset - drop and recreate database
db-reset:
	@echo "🔄 Database reset - drop and recreate..."
	@echo "⚠️  WARNING: This will delete all database data!"
	@read -p "Are you sure? [y/N] " -n 1 -r; \
	echo; \
	if [[ $$REPLY =~ ^[Yy]$$ ]]; then \
		echo "🔌 Terminating database connections..."; \
		docker-compose exec postgres psql -U $(DB_USER) -d postgres -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$(DB_NAME)' AND pid <> pg_backend_pid();"; \
		echo "🗑️  Dropping database..."; \
		docker-compose exec postgres psql -U $(DB_USER) -d postgres -c "DROP DATABASE IF EXISTS $(DB_NAME);"; \
		echo "🏗️  Creating fresh database..."; \
		docker-compose exec postgres psql -U $(DB_USER) -d postgres -c "CREATE DATABASE $(DB_NAME);"; \
		echo "🔧 Installing database extensions..."; \
		docker-compose exec -T postgres psql -U $(DB_USER) -d $(DB_NAME) < scripts/init-db.sql; \
		echo "📝 Pushing schema to fresh database..."; \
		(cd apps/web && DATABASE_URL="$(DB_URL)" npx drizzle-kit push --force); \
		echo "🪣 Clearing MinIO bucket..."; \
		docker-compose exec -T minio mc alias set local http://localhost:9000 $${MINIO_ROOT_USER:-minioadmin} $${MINIO_ROOT_PASSWORD:-minioadmin} &>/dev/null || true; \
		docker-compose exec -T minio mc rm --recursive --force local/jaces &>/dev/null 2>&1 || true; \
		docker-compose exec -T minio mc mb local/jaces --ignore-existing &>/dev/null || true; \
		echo "🌱 Seeding database and MinIO..."; \
		(cd apps/web && DATABASE_URL="$(DB_URL)" MINIO_ENDPOINT="localhost:9000" pnpm db:seed); \
		echo "🐍 Generating Python models..."; \
		(cd apps/web && pnpm run db:python || echo "⚠️  Python model generation skipped (python not found)"); \
		echo "✅ Database reset complete with test data!"; \
	else \
		echo "❌ Reset cancelled."; \
	fi

# Generate Python models from Drizzle schemas
db-python:
	@echo "🐍 Generating Python models from Drizzle schemas..."
	(cd apps/web && pnpm db:python)

# Start Drizzle Studio database UI
db-studio:
	@echo "🎨 Starting Drizzle Studio..."
	@docker-compose exec -d web pnpm drizzle-kit studio --host 0.0.0.0 --port $(STUDIO_PORT)
	@echo "✅ Drizzle Studio started at http://localhost:$(STUDIO_PORT)"

# Generate registry from distributed YAML configs
registry:
	@echo "📊 Generating sources registry from YAML configs..."
	@python scripts/generate_registry.py

# Generate both Python models and registry
db-registry:
	@echo "🔄 Generating Python models and registry..."
	@$(MAKE) db-python

# === DEPLOYMENT COMMANDS ===

# Start production environment (no build)
prod: env-check
	@echo "🚀 Starting Jaces in production mode..."
	@if [ -z "$${PUBLIC_IP}" ]; then \
		export PUBLIC_IP=$$(curl -s ifconfig.me 2>/dev/null || echo "localhost"); \
	fi; \
	PUBLIC_IP=$$PUBLIC_IP docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
	@echo "✅ Production environment started!"
	@echo "   Access at: http://$${PUBLIC_IP:-localhost}:$(WEB_PORT)"

# Package for deployment
deploy-init:
	@echo "📦 Creating deployment package..."
	@tar -czf deploy.tar.gz \
		docker-compose.yml \
		docker-compose.prod.yml \
		.env.example \
		Makefile \
		services/ \
		sources/ \
		apps/ \
		assets/ \
		scripts/ \
		--exclude='**/__pycache__' \
		--exclude='**/node_modules' \
		--exclude='**/.DS_Store' \
		--exclude='**/.git'
	@echo "✅ Created deploy.tar.gz"

# Deploy to EC2
deploy-ec2:
	@read -p "EC2 Host (user@ip): " host; \
	echo "📤 Uploading to $$host..."; \
	scp deploy.tar.gz $$host:~/ && \
	echo "🚀 Deploying on remote host..."; \
	ssh $$host 'tar -xzf deploy.tar.gz && make env-setup && make prod'

# Update deployment (git pull + restart)
deploy-update:
	@read -p "EC2 Host (user@ip): " host; \
	ssh $$host "cd jaces && git pull && make prod"

# View remote logs
deploy-logs:
	@read -p "EC2 Host (user@ip): " host; \
	ssh $$host "cd jaces && docker-compose logs -f"

# === MINIO COMMANDS ===

# Download today's streams from MinIO
minio-download:
	@echo "📥 Downloading today's stream data from MinIO..."
	@docker-compose exec celery-worker uv run python /app/scripts/download-minio-streams.py
	@echo "✅ Stream data saved to assets/test-data/captured-streams/"

# Download streams for a specific date
minio-download-date:
	@read -p "Date (YYYY-MM-DD): " date; \
	echo "📥 Downloading streams for $$date..."; \
	docker-compose exec celery-worker uv run python /app/scripts/download-minio-streams.py $$date

# Process captured streams to filter by date
minio-process:
	@echo "🔄 Processing captured stream data..."
	@docker-compose exec celery-worker uv run python /app/scripts/filter-stream-data.py
	@echo "✅ Processed data saved to assets/test-data/captured-streams/processed/"


# === MAINTENANCE COMMANDS ===

# Clean up all data and volumes
clean:
	@echo "⚠️  WARNING: This will delete all data!"
	@read -p "Are you sure? [y/N] " -n 1 -r; \
	echo; \
	if [[ $$REPLY =~ ^[Yy]$$ ]]; then \
		echo "🧹 Cleaning up all volumes..."; \
		docker-compose down -v; \
	else \
		echo "❌ Cleanup cancelled."; \
	fi

# Full reset - clean, rebuild, push schema, and seed
reset:
	@echo "🔄 Resetting development environment..."
	@echo "⚠️  WARNING: This will delete all data and rebuild everything!"
	@read -p "Are you sure? [y/N] " -n 1 -r; \
	echo; \
	if [[ $$REPLY =~ ^[Yy]$$ ]]; then \
		echo "🧹 Step 1/8: Cleaning up all volumes..."; \
		docker-compose down -v; \
		echo "🔨 Step 2/8: Rebuilding all containers..."; \
		docker-compose build --no-cache; \
		echo "🚀 Step 3/8: Starting services..."; \
		docker-compose up -d; \
		echo "⏳ Step 4/8: Waiting for database to be ready..."; \
		for i in {1..30}; do \
			docker-compose exec -T postgres pg_isready -U $(DB_USER) -d $(DB_NAME) && break || \
			(echo "Waiting for database... ($$i/30)" && sleep 2); \
		done; \
		echo "🗑️  Step 5/8: Resetting drizzle migration state and pushing schema..."; \
		sleep 2; \
		rm -rf apps/web/drizzle/meta/*; \
		echo '{"version":"7","dialect":"postgresql","entries":[]}' > apps/web/drizzle/meta/_journal.json; \
		(cd apps/web && DATABASE_URL="$(DB_URL)" npx drizzle-kit push --force); \
		echo "📊 Step 6/7: Seeding database..."; \
		(cd apps/web && DATABASE_URL="$(DB_URL)" pnpm db:seed); \
		echo "📊 Step 7/7: Generating sources registry..."; \
		$(MAKE) registry; \
		echo "✅ Development environment reset complete!"; \
		echo "📋 Services status:"; \
		docker-compose ps; \
	else \
		echo "❌ Reset cancelled."; \
	fi

# === MAC APP COMMANDS ===

# Build and install JacesMac to /Applications
mac-install:
	@echo "📦 Building and installing JacesMac..."
	@cd apps/mac && echo "y" | ./JacesMac/Scripts/build-app.sh

# Run JacesMac
mac-run:
	@echo "🖥️  Opening JacesMac app..."
	@open /Applications/JacesMac.app || echo "❌ JacesMac.app not found. Run 'make mac-install' first."

# === HELP ===

help:
	@echo "Jaces Commands"
	@echo ""
	@echo "🚀 DEVELOPMENT"
	@echo "  make env-setup        - Create .env file from example"
	@echo "  make dev              - Start development environment"
	@echo "  make stop             - Stop all services"
	@echo "  make logs             - View logs"
	@echo "  make ps               - Show service status"
	@echo "  make rebuild          - Force rebuild containers"
	@echo ""
	@echo "🗄️  DATABASE"
	@echo "  make db-push          - Push schema changes (dev only)"
	@echo "  make db-migrate       - Run migrations"
	@echo "  make db-seed          - Seed with test data"
	@echo "  make db-reset         - Quick DB reset (drop & reseed)"
	@echo "  make db-python        - Generate Python models"
	@echo "  make db-studio        - Start Drizzle Studio UI"
	@echo ""
	@echo "🚢 DEPLOYMENT"
	@echo "  make prod             - Start production mode"
	@echo "  make deploy-init      - Create deployment package"
	@echo "  make deploy-ec2       - Deploy to EC2"
	@echo "  make deploy-update    - Update deployment"
	@echo "  make deploy-logs      - View remote logs"
	@echo ""
	@echo "📦 MINIO"
	@echo "  make minio-download   - Download today's streams"
	@echo "  make minio-download-date - Download streams for specific date"
	@echo "  make minio-process    - Filter captured streams to target dates"
	@echo ""
	@echo "🧹 MAINTENANCE"
	@echo "  make clean            - Delete all data"
	@echo "  make reset            - Full reset"
	@echo ""
	@echo "🖥️  MAC APP"
	@echo "  make mac-install      - Install Mac app"
	@echo "  make mac-run          - Run Mac app"