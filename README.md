# Jaces: An open source ecosystem for owning and exporting your personal data

![GitHub Clones](https://raw.githubusercontent.com/jaces-com/jaces/traffic/traffic-jaces/clones.svg)
[![Release](https://img.shields.io/badge/Release-None-red.svg)](https://github.com/jaces-com/jaces/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![License: ELv2](https://img.shields.io/badge/License-ELv2-orange.svg)](https://www.elastic.co/licensing/elastic-license)

> [!WARNING]
> **Experimental Phase**: Expect rapid iteration and sweeping changes as we refine the core applications and infrastructure.

## What is Jaces

Jaces is your personal AI agent that ingests your digital life—from calendar events and locations to health metrics and screen time—constructing a coherent, queryable timeline. Unlike cloud services that monetize your data, Jaces runs on your infrastructure, ensuring complete privacy and control.

https://github.com/user-attachments/assets/7d3b0c3b-f20b-4b74-b250-c5ff4c3d8d3d

Your data is incredibly valuable—companies build trillion-dollar empires on it. Jaces lets you reclaim that value for yourself:

- **Train personal AI on YOUR data**, not theirs
- **Life logging and memory augmentation** for perfect recall
- **Health and productivity optimization** through pattern recognition  
- **Build a queryable life archive** of your entire digital existence
- **Generate insights for self-improvement** from your actual behavior
- **See what data companies collect** and take back control

## Your Data, Your Database

Unlike cloud services that lock away your data, Jaces gives you **direct PostgreSQL access**. Query your life with SQL, build custom analytics, or export everything—it's your database.

```python
# Connect directly to YOUR data
import psycopg2
import pandas as pd

conn = psycopg2.connect(
    "postgresql://readonly_user:secure_pass@your-server:5432/jaces"
)

# Query your heart rate during meetings
df = pd.read_sql("""
    SELECT s.time, s.value as bpm, c.title as meeting
    FROM signals s
    JOIN signals c ON c.type = 'calendar_event' 
    WHERE s.type = 'heart_rate'
    AND s.time BETWEEN c.start_time AND c.end_time
""", conn)
```

**Manage credentials** at `/settings/database` in your Jaces UI—create read-only users for analysis or full access for integrations. Works with any PostgreSQL client: TablePlus, DBeaver, Jupyter notebooks, or your favorite BI tool.

## ✨ Features

### Data Sources

See the [Implementation Status](#-implementation-status) section below for detailed availability of all sources, streams, and signals.

### Architecture

```txt
Sources → Streams → Signals & Semantics → Event Timeline
```

- **Sources**: Raw data from your devices and services
- **Streams**: Time-series data stored with full fidelity
- **Signals**: State changes detected via PELT algorithms (heart rate spikes, location changes)
- **Semantics**: Knowledge extracted from documents and notes
- **Timeline**: Your queryable life history of 8-24 events in a day through an LLM-friendly Thomistic framework of context

## Status

### Implementation Overview

| Source | Stream | Signal/Semantic | Status | Type | Description |
|--------|--------|-----------------|--------|------|-------------|
| Google | Calendar | Events | ✅ | Signal | Meeting detection |
| Google | Gmail | Emails | 📋 | Semantic | Email content |
| Google | Gmail | Attachments | 📋 | Signal | File attachments |
| Google | Drive | Document Edits | 📋 | Signal | File modifications |
| Google | Drive | Shared Files | 📋 | Signal | Collaboration activity |
| iOS | HealthKit | Heart Rate | ✅ | Signal | BPM tracking |
| iOS | HealthKit | Steps | ✅ | Signal | Daily step count |
| iOS | HealthKit | Active Energy | ✅ | Signal | Calories burned |
| iOS | HealthKit | Sleep | ✅ | Signal | Sleep stages |
| iOS | HealthKit | Workouts | ✅ | Signal | Exercise tracking |
| iOS | HealthKit | HRV | ✅ | Signal | Heart rate variability |
| iOS | Location | Coordinates | ✅ | Signal | GPS tracking |
| iOS | Location | Speed | ✅ | Signal | Movement speed |
| iOS | Location | Altitude | ✅ | Signal | Elevation data |
| iOS | Microphone | Audio Level | ✅ | Signal | Sound levels |
| iOS | Microphone | Transcription | ✅ | Signal | Voice-to-text |
| Mac | Applications | Activity | ✅ | Signal | App focus tracking |
| Mac | iMessage | Messages | 📋 | Semantic | Chat history |
| Mac | iMessage | Attachments | 📋 | Signal | Shared media |
| Mac | Browser | History | 📋 | Signal | Browsing patterns |
| Mac | Browser | Bookmarks | 📋 | Semantic | Saved links |
| Mac | Browser | Downloads | 📋 | Signal | Downloaded files |
| Notion | Pages | Page Content | ✅ | Semantic | Document text |
| Notion | Pages | Database Content | 📋 | Semantic | Structured data |
| Amazon | Orders | Purchase History | 📋 | Semantic | Order details |
| Amazon | Orders | Spending Patterns | 📋 | Signal | Purchase trends |
| Amazon | Orders | Delivery Events | 📋 | Signal | Package tracking |
| WhatsApp | Messages | Conversations | 📋 | Semantic | Chat text |
| WhatsApp | Messages | Voice Notes | 📋 | Signal | Audio messages |
| LinkedIn | Profile | Views | 📋 | Signal | Profile activity |
| LinkedIn | Messages | Conversations | 📋 | Semantic | Professional chats |
| X | Posts | Tweets | 📋 | Semantic | Posted content |
| X | Posts | Engagement | 📋 | Signal | Likes & retweets |
| Spotify | Listening | History | 📋 | Signal | Songs played |
| Spotify | Listening | Playlists | 📋 | Semantic | Playlist data |
| Plaid | Banking | Transactions | 📋 | Signal | Bank activity |
| Plaid | Credit Cards | Purchases | 📋 | Semantic | Transaction details |
| Plaid | Investments | Portfolio | 📋 | Signal | Portfolio value |
| GitHub | Repository | Commits | 📋 | Signal | Code changes |
| GitHub | Repository | Pull Requests | 📋 | Semantic | PR content |
| GitHub | Repository | Issues | 📋 | Semantic | Issue tracking |
| Slack | Workspace | Messages | 📋 | Semantic | Team chats |
| Slack | Workspace | Mentions | 📋 | Signal | Direct mentions |
| Strava | Activities | Workouts | 📋 | Signal | Exercise data |
| Strava | Activities | Performance | 📋 | Signal | Speed & pace |
| Zoom | Meetings | Attendance | 📋 | Signal | Meeting tracking |
| Zoom | Meetings | Recordings | 📋 | Semantic | Transcripts |

### Legend

- ✅ **Stable**: Fully implemented and tested
- 🚧 **In Progress**: Actively being developed
- 📋 **Planned**: On the roadmap

### Notes

- **Authentication Requirements**: Cloud sources require OAuth2 setup. Device sources require the native app installation.
- **Sync Intervals**: Shown in parentheses for active streams. Pull-based sources check for updates, push-based sources upload batched data.
- **PELT Algorithm**: Change Point Detection using Pruned Exact Linear Time with either L1 (sum of absolute differences) or L2 (sum of squared differences) cost functions.
- **iOS Requirements**: Minimum iOS 14.0, requires location/health/microphone permissions
- **Mac Requirements**: Minimum macOS 11.0, requires accessibility and automation permissions

## 🚀 Quick Start

Get Jaces running in under 2 minutes:

```bash
# Clone the repository
git clone https://github.com/jaces-com/jaces
cd jaces

# Start the entire stack (PostgreSQL, Redis, MinIO, Web App, Workers)
# make dev automatically clones .env.example as .env if none available
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

## 🌐 Self-Hosting & Networking

### Recommended: Tailscale Setup (5 Minutes)

Tailscale creates a secure, private network between your devices. Your Jaces instance stays completely private while remaining accessible from all your devices.

#### Quick Start with Tailscale

```bash
# 1. Install Tailscale on your server (where Docker is running)
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up

# 2. Note your Tailscale IP (shown after login, e.g., 100.64.1.5)

# 3. Install Tailscale app on your devices:
# - iOS: App Store → Tailscale
# - macOS: brew install --cask tailscale
# - Windows/Linux: https://tailscale.com/download

# 4. Update your .env file:
PUBLIC_IP=100.64.1.5  # Your Tailscale IP from step 2
FRONTEND_URL=http://100.64.1.5:3000

# 5. Restart Jaces:
make restart

# 6. Access from any device on your Tailscale network:
open http://100.64.1.5:3000
# Or use MagicDNS: http://your-machine.tail-scale.ts.net:3000
```

**Why Tailscale?**

Zero exposed port -- servers aren't on the public internet. E2EE WireGuard protocol. Behind firewalls, NAT, cellular networks. 100 devices, 3 users, perfect for personal use.

### Direct Database Access

Once on Tailscale, you can connect directly to your PostgreSQL database:

```python
# Python
import psycopg2
import pandas as pd

conn = psycopg2.connect(
    "postgresql://jaces_user:jaces_password@100.64.1.5:5432/jaces"
)
df = pd.read_sql("SELECT * FROM signals WHERE type='heart_rate'", conn)
```

```javascript
// JavaScript/TypeScript
import { Client } from 'pg';

const client = new Client({
  connectionString: 'postgresql://jaces_user:jaces_password@100.64.1.5:5432/jaces'
});
await client.connect();
const result = await client.query('SELECT * FROM signals');
```

See the [Database Access](#database-access) section for managing read-only users and connection strings.

### Alternative Networking Options

**Local Only (Simplest):**

```bash
# No changes needed, access at:
http://localhost:3000
```

**Public VPS (Advanced):**

- Use the included `deploy-ec2-setup.sh` script
- Add HTTPS with Caddy or Traefik
- Consider authentication layer (Authelia)

### How External Services Work

Even with Tailscale, these features work perfectly:

- **OAuth (Google/Notion)**: Handled by `auth.jaces.com` proxy
- **API Syncing**: Outbound connections work normally
- **AI Features**: Can call OpenAI/Anthropic APIs
- **Calendar/Email**: Fetches data via polling

Your instance makes outbound connections but accepts no inbound traffic from the internet.

## 📦 Prerequisites

- Docker & Docker Compose (v2.0+)
- 8GB RAM minimum, 16GB recommended
- 20GB free disk space

## 🔐 Database Access

Jaces provides direct PostgreSQL access for power users. Connect with any SQL client, Jupyter notebooks, or your favorite programming language.

### Managing Database Users

Navigate to `/settings/database` in your Jaces web UI to:

- Create read-only users for safe data analysis
- Create read-write users for custom integrations  
- Generate secure connection strings

### Example Queries

```sql
-- Recent heart rate data
SELECT time, value FROM signals 
WHERE type = 'heart_rate' 
AND time > NOW() - INTERVAL '24 hours'
ORDER BY time DESC;

-- Location history with PostGIS
SELECT time, ST_X(location::geometry) as lon, ST_Y(location::geometry) as lat
FROM signals 
WHERE type = 'location'
AND time::date = CURRENT_DATE;

-- Daily activity summary
SELECT 
  DATE(time) as day,
  type,
  COUNT(*) as events,
  AVG(value) as avg_value
FROM signals
GROUP BY DATE(time), type
ORDER BY day DESC, type;
```

## 🏗️ Technical Details

### ELT Data Pipeline

Jaces uses an ELT (Extract, Load, Transform) architecture to preserve raw data while enabling flexible analysis:

1. **Extract**: Pull raw data from APIs and devices
2. **Load**: Store in MinIO and PostgreSQL with full fidelity
3. **Transform**: Apply PELT algorithms and semantic extraction on-demand

This approach ensures you never lose data and can reprocess with improved algorithms later.

### Processing Modes

- **Real-time**: Continuous processing for immediate insights
- **Batch**: Nightly consolidation for pattern discovery
- **On-demand**: Query-time transformations for flexibility

### Tech Stack

**Backend**: Python, Celery, FastAPI, PostgreSQL (PostGIS/pgvector), Redis, MinIO  
**Frontend**: SvelteKit, TypeScript, TailwindCSS  
**Mobile**: Swift/SwiftUI (iOS/macOS)  
**ML/AI**: PELT change detection, HDBSCAN clustering, Vector embeddings

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

## 🤝 Contributing

We believe that only an open-source solution to personal data management can truly respect user privacy while covering the long tail of data sources. We welcome contributions in several areas:

### How to Contribute

1. **Code Contributions**: Implement new data sources, improve existing ones, or enhance the core platform
2. **Architecture Reviews**: Share expertise on iOS/Swift, distributed systems, or data processing
3. **Documentation**: Help others understand and use Jaces effectively
4. **Bug Reports**: Find something broken? Let us know!

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

Headless personal data.
The protocol for personal intelligence.
Your data should work for you, not against you.
