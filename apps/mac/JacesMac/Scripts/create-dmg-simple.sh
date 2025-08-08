#!/bin/bash

# Create a simple DMG for JacesMac

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BUILD_DIR="$PROJECT_ROOT/build"
APP_NAME="JacesMac"
DMG_NAME="JacesMac"

echo "Creating JacesMac DMG (Simple)..."
echo "===================================="

# Check if app exists
if [ ! -d "$BUILD_DIR/$APP_NAME.app" ]; then
    echo "Error: App not found. Run ./Scripts/build-desktop.sh first"
    exit 1
fi

# Clean up
rm -f "$PROJECT_ROOT/$DMG_NAME.dmg"
rm -rf "$BUILD_DIR/dmg"

# Create DMG source folder
mkdir -p "$BUILD_DIR/dmg"
cp -R "$BUILD_DIR/$APP_NAME.app" "$BUILD_DIR/dmg/"
ln -s /Applications "$BUILD_DIR/dmg/Applications"

# Create DMG
hdiutil create -volname "JacesMac" \
    -srcfolder "$BUILD_DIR/dmg" \
    -ov \
    -format UDZO \
    "$PROJECT_ROOT/$DMG_NAME.dmg"

# Clean up
rm -rf "$BUILD_DIR/dmg"

echo ""
echo "✅ DMG created successfully!"
echo ""
echo "Location: $PROJECT_ROOT/$DMG_NAME.dmg"
echo "Size: $(du -h "$PROJECT_ROOT/$DMG_NAME.dmg" | cut -f1)"
echo ""
echo "To install:"
echo "1. Open $DMG_NAME.dmg"
echo "2. Drag JacesMac to Applications"
echo "3. Eject the DMG"
echo "4. Launch JacesMac from Applications"