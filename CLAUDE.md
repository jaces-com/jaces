# Claude's Readme

Important instruction reminders:

- Do what has been asked; nothing more, nothing less.
- NEVER create files unless they're absolutely necessary for achieving your goal.
- ALWAYS prefer editing an existing file to creating a new one.
- NEVER proactively create documentation files (*.md) or README files. Only create documentation files if explicitly requested by the User.
- Run commands within the Docker container with docker compose exec.

## Monorepo Structure

``` txt
jaces/
├── apps/                      # 📱 User-facing applications and gateways
│   ├── google-auth-proxy/     # 🔐 OAuth proxy for all Google services (deployed separately)
│   ├── ios/                   # 🍎 Native iOS application for data collection
│   ├── mac/                   # 🖥️ Native macOS agent application
│   └── web/                   # 🌐 SvelteKit frontend web application
│
├── sources/                   # 📦 Single source of truth for all data pipeline logic
│   ├── base/                  # 🏗️ Shared utilities and infrastructure (formerly services/)
│   │   ├── auth/              # 🔐 Authentication handlers (OAuth, device tokens)
│   │   ├── config.py          # ⚙️ Configuration loader (YAML/JSON support)
│   │   ├── interfaces/        # 📝 Abstract base classes for sources
│   │   ├── models/            # 📊 Database models (auto-generated from Drizzle)
│   │   ├── processing/        # 🏃‍♀️ Data processing and signal analysis
│   │   ├── scheduler/         # ⏰ Celery app and background tasks
│   │   ├── storage/           # 💾 MinIO, database, and cache clients
│   │   └── transitions/       # 📈 PELT-based transition detectors
│   ├── ios/                   # 🍎 iOS data sources
│   │   ├── location/          # 📍 GPS and location tracking
│   │   ├── healthkit/         # 🏃 Health and fitness data
│   │   └── mic/               # 🎤 Audio transcription
│   ├── mac/                   # 🖥️ macOS data sources
│   │   └── apps/              # 💻 Application usage tracking
│   ├── google/                # 🔍 Google service integrations
│   │   └── api/               # 📅 Calendar and other APIs
│   └── _registry.yaml         # 📚 Master registry of all sources/streams/signals
│
├── assets/                    # 🎨 Static configuration and resources
│   ├── config/                # 🔩 Configuration files (YAML primary, JSON fallback)
│   │   ├── source_configs.yaml   # Source metadata and UI configuration
│   │   ├── stream_configs.yaml   # Stream definitions and processing rules
│   │   ├── signal_configs.yaml   # Signal types and processing logic
│   │   └── defaults.yaml         # System-wide default settings
│   └── prompts/               # 🗣️ AI prompt templates
│
├── scripts/                   # 📜 Utility scripts for development and operations
│   ├── init-db.sql            # Database initialization
│   ├── minio-entrypoint.sh    # MinIO container setup
│   └── deploy-ec2-setup.sh    # Production deployment
│
├── tests/                     # 🧪 E2E tests, integration tests, and test data
│
├── Makefile                   # 🛠️ Simple aliases for common developer commands
├── biome.json                 # 💅 Linting and formatting configuration
├── docker-compose.yml         # 🚀 Local development stack definition
└── README.md                  # 📖 Project documentation
```

## Source Architecture Pattern

The Jaces platform follows a three-tier data architecture: **sources → streams → signals & semantics**. This configuration-driven approach handles 20+ integrations without code sprawl:

### Benefits

- Adding a new source requires minimal code (just sync logic)
- UI automatically adapts to new sources without frontend changes
- Configuration can be validated and tested separately
- Easy to enable/disable sources without code changes
- Clear separation between business logic and presentation
- YAML format allows inline documentation and better readability
- Centralized infrastructure in `sources/base/` reduces duplication
- Auto-generated models keep database schema in sync

## Technical Opinions

### Backend Stack

- **Python** for all backend services and data processing
- **FastAPI/SvelteKit** for API endpoints (transitioned from separate FastAPI to SvelteKit's native API)
- **Celery + Redis** for task scheduling and background processing
- **MinIO** for object storage (raw data and processed streams)
- **PostgreSQL** for metadata storage (with Drizzle ORM)
- **Docker Compose** for local development environment

### Frontend Stack

- **SvelteKit** for the web application
- **Swift/SwiftUI** for native iOS and macOS applications
- **TypeScript** throughout the web stack

### Data Processing

- **Stream-based architecture** for real-time data processing
- **Transition detection algorithms** (PELT, custom detectors) for signal analysis
- **Configuration-driven** source and signal definitions
- **Batch processing** with configurable upload intervals

### Development Practices

- **Monorepo structure** with clear separation of concerns
- **Type safety** with TypeScript and Python type hints
- **Automated schema generation** from Drizzle to Python models (run `pnpm db:python` in apps/web/)
- **Comprehensive error handling** and retry mechanisms
