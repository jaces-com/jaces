#!/bin/bash

# Simple build script for development
# This creates the app bundle structure manually without needing a full Xcode project

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BUILD_DIR="$PROJECT_ROOT/build"
APP_NAME="JacesMac"

echo "Memory Agent Simple Build"
echo "========================"
echo ""

# Clean
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"

# Build CLI
echo "Building CLI agent..."
cd "$PROJECT_ROOT/Jaces-mac"
swiftc -O \
    main.swift \
    Sources/**/*.swift \
    ../Shared/**/*.swift \
    -o "$BUILD_DIR/memory-agent"

# Build Menu Bar App
echo "Building Menu Bar app..."
cd "$PROJECT_ROOT/MemoryAgentUI"
swiftc -O \
    -framework SwiftUI \
    -framework AppKit \
    App/*.swift \
    Views/*.swift \
    ViewModels/*.swift \
    Models/*.swift \
    ../Shared/**/*.swift \
    ../Jaces-mac/Sources/Config/*.swift \
    ../Jaces-mac/Sources/Utils/Logger.swift \
    -o "$BUILD_DIR/MemoryAgent"

# Create app bundle
echo "Creating app bundle..."
APP_BUNDLE="$BUILD_DIR/$APP_NAME.app"
mkdir -p "$APP_BUNDLE/Contents/MacOS"
mkdir -p "$APP_BUNDLE/Contents/Resources"

# Copy files
cp "$BUILD_DIR/MemoryAgent" "$APP_BUNDLE/Contents/MacOS/"
cp "$BUILD_DIR/memory-agent" "$APP_BUNDLE/Contents/Resources/"
cp "$PROJECT_ROOT/Jaces-mac/Scripts/com.memory.agent.plist" "$APP_BUNDLE/Contents/Resources/"
cp "$PROJECT_ROOT/MemoryAgentUI/Resources/Info.plist" "$APP_BUNDLE/Contents/"

# Set permissions
chmod +x "$APP_BUNDLE/Contents/MacOS/MemoryAgent"
chmod +x "$APP_BUNDLE/Contents/Resources/memory-agent"

echo ""
echo "✅ Build complete: $APP_BUNDLE"
echo ""
echo "To run:"
echo "  open '$APP_BUNDLE'"