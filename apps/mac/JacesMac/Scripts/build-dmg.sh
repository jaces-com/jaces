#!/bin/bash

# Memory Agent DMG Builder Script
# This script builds both the CLI and Menu Bar app, embeds the CLI in the app bundle,
# and creates a DMG for distribution

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BUILD_DIR="$PROJECT_ROOT/build"
DMG_DIR="$PROJECT_ROOT/dmg"
APP_NAME="JacesMac"
DMG_NAME="JacesMac.dmg"
VOLUME_NAME="Memory Agent"

echo "Memory Agent DMG Builder"
echo "========================"
echo ""

# Clean previous builds
echo "Cleaning previous builds..."
rm -rf "$BUILD_DIR"
rm -rf "$DMG_DIR"
rm -f "$PROJECT_ROOT/$DMG_NAME"

# Build CLI agent
echo "Building CLI agent..."
cd "$PROJECT_ROOT/Jaces-mac"
xcodebuild -project ../Jaces-mac.xcodeproj \
           -scheme Jaces-mac \
           -configuration Release \
           -derivedDataPath "$BUILD_DIR/cli" \
           PRODUCT_NAME="memory-agent" \
           > /dev/null

# Find built CLI binary
CLI_BINARY=$(find "$BUILD_DIR/cli" -name "memory-agent" -type f -perm +111 | head -1)
if [ -z "$CLI_BINARY" ]; then
    echo "Error: Could not find built CLI binary"
    exit 1
fi

# Build Menu Bar app
echo "Building Menu Bar app..."
cd "$PROJECT_ROOT/MemoryAgentUI"

# Create a temporary Xcode project for the Menu Bar app
# In a real scenario, this would be part of the main Xcode project
cat > "$PROJECT_ROOT/Package.swift" << EOF
// swift-tools-version:5.5
import PackageDescription

let package = Package(
    name: "JacesMac",
    platforms: [
        .macOS(.v12)
    ],
    products: [
        .executable(name: "JacesMac", targets: ["JacesMac"])
    ],
    targets: [
        .executableTarget(
            name: "JacesMac",
            path: "MemoryAgentUI",
            resources: [.copy("Resources")]
        )
    ]
)
EOF

# Build the Menu Bar app
swift build -c release --product JacesMac

# Create app bundle structure
echo "Creating app bundle..."
mkdir -p "$DMG_DIR"
APP_BUNDLE="$DMG_DIR/$APP_NAME.app"
mkdir -p "$APP_BUNDLE/Contents/MacOS"
mkdir -p "$APP_BUNDLE/Contents/Resources"

# Copy Menu Bar app executable
cp "$PROJECT_ROOT/.build/release/JacesMac" "$APP_BUNDLE/Contents/MacOS/MemoryAgent"

# Copy Info.plist
cp "$PROJECT_ROOT/MemoryAgentUI/Resources/Info.plist" "$APP_BUNDLE/Contents/Info.plist"

# Embed CLI binary and plist in Resources
echo "Embedding CLI agent in app bundle..."
cp "$CLI_BINARY" "$APP_BUNDLE/Contents/Resources/memory-agent"
cp "$PROJECT_ROOT/Jaces-mac/Scripts/com.memory.agent.plist" "$APP_BUNDLE/Contents/Resources/"

# Set executable permissions
chmod +x "$APP_BUNDLE/Contents/MacOS/MemoryAgent"
chmod +x "$APP_BUNDLE/Contents/Resources/memory-agent"

# Create an icon (placeholder - in production, use a proper .icns file)
echo "Adding app icon..."
# This would copy your .icns file:
# cp "$PROJECT_ROOT/Resources/AppIcon.icns" "$APP_BUNDLE/Contents/Resources/"

# Sign the app (requires developer certificate)
if security find-identity -v -p codesigning | grep -q "Developer ID Application"; then
    echo "Signing app..."
    codesign --deep --force --verify --verbose --sign "Developer ID Application" "$APP_BUNDLE"
else
    echo "Warning: No Developer ID found, app will not be signed"
fi

# Create DMG
echo "Creating DMG..."
mkdir -p "$DMG_DIR/.background"

# Create a simple background image (in production, use a designed image)
# cp "$PROJECT_ROOT/Resources/dmg-background.png" "$DMG_DIR/.background/"

# Create Applications symlink
ln -s /Applications "$DMG_DIR/Applications"

# Create DMG
hdiutil create -volname "$VOLUME_NAME" \
               -srcfolder "$DMG_DIR" \
               -ov \
               -format UDZO \
               "$PROJECT_ROOT/$DMG_NAME"

# Clean up
echo "Cleaning up..."
rm -rf "$BUILD_DIR"
rm -rf "$DMG_DIR"
rm -f "$PROJECT_ROOT/Package.swift"

echo ""
echo "✅ DMG created successfully: $PROJECT_ROOT/$DMG_NAME"
echo ""
echo "The DMG contains:"
echo "- $APP_NAME.app (Menu Bar UI)"
echo "  └── Embedded memory-agent CLI binary"
echo "  └── Launch agent plist"
echo ""
echo "Users can:"
echo "1. Drag $APP_NAME.app to Applications"
echo "2. Run the app to install and configure the agent"
echo "3. The agent will be automatically installed on first run"