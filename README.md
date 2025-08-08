# Jaces

[![GitHub Stars](https://img.shields.io/github/stars/jaces-com/jaces?style=social)](https://github.com/jaces-com/jaces/stargazers)
[![Release](https://img.shields.io/badge/Release-None-red.svg)](https://github.com/jaces-com/jaces/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![License: ELv2](https://img.shields.io/badge/License-ELv2-orange.svg)](https://www.elastic.co/licensing/elastic-license)

> Open-source personal memory and data platform. Your data, your infrastructure, your control.

> [!WARNING]
> **Experimental Phase**: We're still figuring out the core architecture and user experience. Jump in if you want to help shape the future of personal data sovereignty, but expect rapid iteration and breaking changes.

## What is Jaces?

In a world where tech giants monetize every click, scroll, and heartbeat, Jaces offers a radical alternative: **complete data sovereignty**. This isn't another cloud service where your data mingles with millions of others. Jaces is your personal AI agent that ingests the digital exhaust of your existence—from calendar events and locations to health metrics and screen time—constructing a coherent, queryable timeline of your life.

**The AI that helps you know yourself better.** From being the product to becoming the protagonist.

## How It Works

```
📱 Your Sources & Streams    🔄 Continuous Processing        🎯 Intelligent Timeline
┌─────────────────┐          ┌──────────────────────┐        ┌─────────────────────┐
│ • iOS Health    │          │  📊 Signals          │        │  🕐 Timeline        │
│ • Location      │  ──►     │  (Change Detection)  │  ──►   │  "Heart rate spiked"│
│ • Calendar      │          │  Heart rate: 72→120  │        │  "Entered office"   │
│ • Notion docs   │          │                      │        │  "Meeting started"  │
│ • Mac apps      │          │  📝 Semantics        │        │  "Doc: Project Plan"│
└─────────────────┘          │  (Knowledge Base)    │        │  "Note: Summary"    │
                             │  Docs, notes, pages  │        └─────────────────────┘
                             └──────────────────────┘              ↓
                                      ↓                     🔍 Query Your Life
                             🎯 PELT Algorithm              "When did I last..."
                             Detects transitions &          "Show me patterns in..."
                             meaningful changes              "What happened before..."
```

**Signals** are for change detection—PELT algorithms and boundary detection find meaningful transitions in heart rate, location, app focus, calendar events. **Semantics** are for content knowledge bases & retrieval—GPU-accelerated vector search across documents, notes, and pages. Together they create a searchable timeline of your life, turning noise into insight.

Think of it as your:

- **Second brain** that actually remembers everything
- **Personal historian** documenting your life
- **Computational phronesis engine** for practical wisdom from your own data
- **Private memory palace** that you own completely

## ✨ Features

### Data Sources

#### ✅ Live & Working

- **iOS**: HealthKit (heart rate, steps, workouts, sleep), Location tracking, Audio transcription
- **macOS**: Application usage and focus events
- **Google**: Calendar events and meeting patterns
- **Notion**: Pages and databases from your workspace

#### 📋 Planned

- **Google**: Gmail, Drive, Photos
- **Fitness**: Strava, Garmin, Fitbit
- **Communication**: Slack, Discord, Telegram
- **Financial**: Transaction processing
- **Media**: Spotify, YouTube

### Architecture Highlights

- **Hot Day, Cold Night**: Real-time processing for "what's happening now?" transitions to nightly consolidation for "what did today mean?"
- **Data Pipeline**: Sources → Streams → Signals & Semantics
  - **Signals**: Time-series data (heart rate changes, app switches, location moves)
  - **Semantics**: Content data (documents, notes, calendar events)
- **Configuration-Driven**: Sources defined in YAML, UI auto-generates from config
- **Privacy-First**: All auth is proxied, we never see your credentials

### Platform Components

- **Web Dashboard**: Beautiful, maintenance-free interface for exploring your life timeline
- **Native iOS App**: Seamless background data collection with minimal battery impact
- **macOS Agent**: Lightweight system monitoring that captures your digital context
- **AI Analysis**: Your shield against predatory AI—local LLM integration that works for you

## 🚀 Quick Start

Get Jaces running in under 5 minutes:

```bash
# Clone the repository
git clone https://github.com/jaces-com/jaces
cd jaces

# Copy environment template
cp .env.example .env

# Start the entire stack (PostgreSQL, Redis, MinIO, Web App, Workers)
make dev

# Open the dashboard
open http://localhost:3000
```

That's it! The system will:

- Initialize PostgreSQL with PostGIS and pgvector extensions
- Set up MinIO for object storage
- Start Redis for task queuing
- Launch the SvelteKit web application
- Spin up Celery workers for background processing

## 📦 Installation

### Prerequisites

- Docker & Docker Compose (v2.0+)
- Node.js 18+ and pnpm (for local development)
- Python 3.11+ (for backend development)
- 8GB RAM minimum, 16GB recommended
- 20GB free disk space for data storage

### Production Deployment

For production deployment on AWS EC2 or similar:

```bash
# Use the production compose file
docker-compose -f docker-compose.prod.yml up -d

# Run database migrations
make db-migrate

# Check system health
make health-check
```

## 🏗️ Architecture

Jaces follows a three-tier data architecture that processes your digital exhaust into actionable insights:

```
┌─────────────┐     ┌─────────────┐     ┌──────────────────────┐
│   Sources   │ ──> │   Streams   │ ──> │ Signals & Semantics  │
└─────────────┘     └─────────────┘     └──────────────────────┘
     Raw Data         Time-Series         Signals: State changes
   (APIs, Files)    (Processed Data)      Semantics: Content/docs
```

### Hot Day, Cold Night Architecture

**☀️ Hot Day (Real-time)**

- Processes incoming data streams throughout the day
- Maintains GPU-accelerated vector indices for instant retrieval
- Answers: "What is happening right now?"
- Sub-second query responses across your entire digital life

**🌙 Cold Night (Synthesis)**

- Runs nightly consolidation and boundary detection while you sleep
- Transforms raw signals into coherent life events and permanent memories
- Answers: "What did today mean?"
- Builds long-term patterns, discovers recurring habits

### Tech Stack

- **Frontend**: SvelteKit, TypeScript, TailwindCSS, D3.js
- **Backend**: Python, SvelteKit API routes, Celery, SQLAlchemy
- **Databases**: PostgreSQL (with PostGIS & pgvector), Redis
- **Storage**: MinIO (S3-compatible object storage)
- **Mobile**: Swift/SwiftUI (iOS & macOS)
- **ML/AI**: NumPy, Ruptures (change detection), HDBSCAN (clustering)
- **Infrastructure**: Docker, Docker Compose

## 🔧 Development

### Available Commands

```bash
make dev              # Start development environment
make stop             # Stop all services
make clean            # Clean up containers and volumes
make logs             # View application logs
make db-studio        # Open Drizzle Studio for database inspection
make test             # Run test suite
make format           # Format code with Biome
make lint             # Lint codebase
```

### Project Structure

```
jaces/
├── apps/                      # User-facing applications
│   ├── web/                   # SvelteKit dashboard
│   ├── ios/                   # Native iOS app
│   ├── mac/                   # Native macOS agent
│   └── google-auth-proxy/     # OAuth proxy for Google services
├── sources/                   # Data pipeline logic
│   ├── base/                  # Shared infrastructure
│   ├── google/                # Google service integrations
│   ├── ios/                   # iOS data sources
│   ├── mac/                   # macOS data sources
│   ├── notion/                # Notion integration
│   └── _registry.yaml         # Master source/stream/signal registry
└── scripts/                   # Utility scripts
```

For detailed architecture documentation, see [CLAUDE.md](./CLAUDE.md).

## 🤝 Contributing

We believe that only an open-source solution to personal data management can truly respect user privacy while covering the long tail of data sources. We welcome contributions in several areas:

### How to Contribute

1. **Code Contributions**: Implement new data sources, improve existing ones, or enhance the core platform
2. **Architecture Reviews**: Share expertise on iOS/Swift, distributed systems, or data processing
3. **Documentation**: Help others understand and use Jaces effectively
4. **Bug Reports**: Find something broken? Let us know!

<!-- ### Compensation for Contributors

We're committed to paying for quality contributions. Whether it's code, documentation, or architectural insights, we believe good work deserves compensation. Join our [Discord](https://discord.gg/jaces) to discuss contribution opportunities. -->

```bash
# Fork and clone the repository
git clone https://github.com/jaces-com/jaces
cd jaces

# Create a feature branch
git checkout -b feature/your-feature-name

# Make your changes and test
make test

# Submit a pull request
```

## 📄 License

Jaces uses a dual-license model:

- **MIT License**: Core functionality and most components
- **Elastic License 2.0 (ELv2)**: Certain enterprise components

**You can**: Self-host, modify, extend, and use Jaces for personal or commercial purposes.

**You cannot**: Offer Jaces as a hosted service or remove license functionality.

See [LICENSE](./LICENSE) for complete details.

## 📞 Contact & Support

- **Community**: Slack coming soon
- **GitHub Issues**: [Report bugs or request features](https://github.com/jaces-com/jaces/issues)

---

## Axioms

- If the product is free, you are the product.
- An AI with a conscience—yours.
- We built Jaces with the intent to use AI to increase human agency, not detract from it.
- Your data should work for you, not against you.
- The protocol for personal intelligence.
