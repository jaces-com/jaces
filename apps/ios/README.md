# Jaces iOS App

A native iOS application for continuous data collection including location, health metrics, and audio.

## Setup

### 1. Open in Xcode

```bash
cd apps/ios
open Jaces.xcodeproj
```

### 2. Configure Signing

1. Select the **Jaces** project in the navigator
2. Go to **Signing & Capabilities** tab
3. Select your **Team** from the dropdown menu
4. Xcode will automatically manage the provisioning profile

You can find your Team ID in:
- Xcode: The Team dropdown will show your available teams
- Apple Developer Portal: Account → Membership → Team ID

### 3. Configure API Endpoint (Optional)

The app defaults to `http://localhost:3000` for the API endpoint. Users can change this during the onboarding flow in the app.

If you want to change the default, edit line 28 in `Models/DeviceConfiguration.swift`:
```swift
apiEndpoint: String = "http://localhost:3000"
```

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