#!/bin/bash

# Build the JacesMac Desktop App

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BUILD_DIR="$PROJECT_ROOT/build"
APP_NAME="JacesMac"

echo "Building JacesMac Desktop App..."
echo "===================================="

# Clean
rm -rf "$BUILD_DIR/$APP_NAME.app"

# Create app bundle structure
APP_BUNDLE="$BUILD_DIR/$APP_NAME.app"
mkdir -p "$APP_BUNDLE/Contents/MacOS"
mkdir -p "$APP_BUNDLE/Contents/Resources"

# First build the CLI if needed
if [ ! -f "$BUILD_DIR/Build/Products/Debug/Jaces-mac" ]; then
    echo "Building CLI first..."
    cd "$PROJECT_ROOT"
    xcodebuild -project Jaces-mac.xcodeproj \
               -scheme Jaces-mac \
               -configuration Debug \
               -derivedDataPath build \
               CODE_SIGN_IDENTITY="" \
               CODE_SIGNING_REQUIRED=NO \
               CODE_SIGNING_ALLOWED=NO \
               quiet
fi

# Compile the Desktop app
cd "$PROJECT_ROOT"

echo "Compiling Desktop app..."

# Find all Swift files
SWIFT_FILES=""
SWIFT_FILES="$SWIFT_FILES $(find MemoryAgentUI/App -name "*.swift" 2>/dev/null || true)"
SWIFT_FILES="$SWIFT_FILES $(find MemoryAgentUI/Views -name "*.swift" 2>/dev/null || true)"
SWIFT_FILES="$SWIFT_FILES $(find MemoryAgentUI/ViewModels -name "*.swift" 2>/dev/null || true)"
SWIFT_FILES="$SWIFT_FILES $(find MemoryAgentUI/Models -name "*.swift" 2>/dev/null || true)"
SWIFT_FILES="$SWIFT_FILES $(find MemoryAgentUI/Utilities -name "*.swift" 2>/dev/null || true)"
SWIFT_FILES="$SWIFT_FILES $(find Shared -name "*.swift" 2>/dev/null || true)"
SWIFT_FILES="$SWIFT_FILES Jaces-mac/Sources/Config/ConfigManager.swift"
SWIFT_FILES="$SWIFT_FILES Jaces-mac/Sources/Utils/Logger.swift"

swiftc -O \
    -framework SwiftUI \
    -framework AppKit \
    -framework Combine \
    $SWIFT_FILES \
    -o "$APP_BUNDLE/Contents/MacOS/JacesMac"

# Copy Info.plist
cp "$PROJECT_ROOT/MemoryAgentUI/Resources/Info.plist" "$APP_BUNDLE/Contents/"

# Update the app name in Info.plist
/usr/libexec/PlistBuddy -c "Set :CFBundleName 'JacesMac'" "$APP_BUNDLE/Contents/Info.plist" 2>/dev/null || \
    /usr/libexec/PlistBuddy -c "Add :CFBundleName string 'JacesMac'" "$APP_BUNDLE/Contents/Info.plist"

/usr/libexec/PlistBuddy -c "Set :CFBundleDisplayName 'JacesMac'" "$APP_BUNDLE/Contents/Info.plist" 2>/dev/null || \
    /usr/libexec/PlistBuddy -c "Add :CFBundleDisplayName string 'JacesMac'" "$APP_BUNDLE/Contents/Info.plist"

# Copy the CLI binary and plist to Resources (for embedding)
if [ -f "$BUILD_DIR/Build/Products/Debug/Jaces-mac" ]; then
    cp "$BUILD_DIR/Build/Products/Debug/Jaces-mac" "$APP_BUNDLE/Contents/Resources/jaces-mac"
    chmod +x "$APP_BUNDLE/Contents/Resources/jaces-mac"
else
    echo "Warning: CLI binary not found. Build it first with ./Scripts/build-cli.sh"
fi

cp "$PROJECT_ROOT/Jaces-mac/Scripts/com.jaces.mac.plist" "$APP_BUNDLE/Contents/Resources/"

# TODO: Add app icon
# cp "$PROJECT_ROOT/Resources/AppIcon.icns" "$APP_BUNDLE/Contents/Resources/"

echo ""
echo "✅ Desktop app built successfully!"
echo ""
echo "App location: $APP_BUNDLE"
echo ""
echo "To run:"
echo "  open '$APP_BUNDLE'"
echo ""
echo "To create DMG:"
echo "  ./Scripts/create-dmg.sh"