# JacesMac Run Modes

JacesMac can run in two modes:

## 1. GUI Mode (Default)
Launch the app normally from Applications or Xcode. This provides a full macOS app interface.

```bash
# From Applications
open /Applications/JacesMac.app

# From Xcode
Cmd+R
```

## 2. Headless Mode (CLI)
Run as a background service with no UI. Useful for servers or always-on monitoring.

```bash
# Using the provided script
./run-headless.sh

# Or directly
/Applications/JacesMac.app/Contents/MacOS/JacesMac --headless
```

## Building the App

1. Open `Jaces-mac.xcodeproj` in Xcode
2. Select the "JacesMac" target
3. Build with Cmd+B
4. Run with Cmd+R