# Jaces iOS App

A native iOS application for continuous data collection including location, health metrics, and audio.

## Setup

### 1. Configuration

Copy the example environment file and configure it:

```bash
cp .env.example .env
```

Edit `.env` and set your Apple Developer Team ID:
```
DEVELOPMENT_TEAM=YOUR_TEAM_ID_HERE
```

You can find your Team ID in:
- Xcode: Project settings → Signing & Capabilities → Team dropdown
- Apple Developer Portal: Account → Membership → Team ID

### 2. Xcode Configuration

The project uses `Config.xcconfig` for build settings. If you prefer to use Xcode's UI:

1. Open `Jaces.xcodeproj`
2. Select the project in the navigator
3. Go to Signing & Capabilities
4. Select your team from the dropdown

### 3. API Endpoint

The default API endpoint is `http://localhost:3000`. To change it:

- **For development**: Edit the `DEFAULT_API_ENDPOINT` in your `.env` file
- **At runtime**: Users can change it in the app's onboarding flow

### 4. Build and Run

```bash
# Open in Xcode
open Jaces.xcodeproj

# Or build from command line
xcodebuild -scheme Jaces -configuration Debug build
```

## Architecture

- **Direct SQLite writes**: No in-memory buffers for reliability
- **Three data streams**: Location, Audio, HealthKit
- **Background support**: Continues collecting data when app is backgrounded
- **Batch uploads**: Groups data by stream type for efficiency

## Required Permissions

The app requires these permissions to function:

- **Location**: Always (for continuous tracking)
- **Microphone**: For audio recording
- **HealthKit**: For fitness and health data
- **Background Modes**: Location, Audio, Fetch, Processing

## Development

See [CONTRIBUTING.md](../../CONTRIBUTING.md) for development guidelines.

## Security

- Device tokens are never hardcoded
- API endpoints are user-configurable
- All sensitive configuration is in `.env` (not committed)
- See [SECURITY.md](../../SECURITY.md) for security policies