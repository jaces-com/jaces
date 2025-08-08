#!/bin/bash

# Create a professional DMG with drag-to-Applications window

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BUILD_DIR="$PROJECT_ROOT/build"
APP_NAME="Memory Agent"
DMG_NAME="MemoryAgent"
VOLUME_NAME="Memory Agent Installer"

echo "Creating Memory Agent DMG..."
echo "==========================="

# Check if app exists
if [ ! -d "$BUILD_DIR/$APP_NAME.app" ]; then
    echo "Error: App not found. Run ./Scripts/build-desktop.sh first"
    exit 1
fi

# Clean up any existing DMG or temp files
rm -f "$PROJECT_ROOT/$DMG_NAME.dmg"
rm -rf "$BUILD_DIR/dmg-temp"

# Create temporary directory for DMG contents
DMG_TEMP="$BUILD_DIR/dmg-temp"
mkdir -p "$DMG_TEMP"

# Copy app to temp directory
cp -R "$BUILD_DIR/$APP_NAME.app" "$DMG_TEMP/"

# Create Applications symlink
ln -s /Applications "$DMG_TEMP/Applications"

# Create background image directory
mkdir -p "$DMG_TEMP/.background"

# Create a simple background image using ImageMagick if available, otherwise use osascript
if command -v convert >/dev/null 2>&1; then
    # Create background with ImageMagick
    convert -size 540x380 xc:'#f0f0f5' \
        -fill '#333333' -pointsize 24 -font Arial-Bold \
        -draw "text 270,100 'Memory Agent'" \
        -fill '#666666' -pointsize 18 -font Arial \
        -draw "text 270,140 'Drag to Applications folder to install'" \
        -fill '#333333' -pointsize 72 \
        -draw "text 240,240 '→'" \
        "$DMG_TEMP/.background/background.png"
else
    # Create a simple background using system tools
    echo "Note: Install ImageMagick for a better background image"
    # We'll set a solid color background via AppleScript below
fi

# Create temporary DMG
echo "Creating temporary DMG..."
hdiutil create -volname "$VOLUME_NAME" \
    -srcfolder "$DMG_TEMP" \
    -ov -quiet \
    -format UDRW \
    -size 100m \
    "$BUILD_DIR/temp.dmg"

# Mount the temporary DMG
echo "Mounting temporary DMG..."
DEVICE=$(hdiutil attach -readwrite -noverify -quiet "$BUILD_DIR/temp.dmg" | egrep '^/dev/' | sed 1q | awk '{print $1}')
MOUNT_POINT="/Volumes/$VOLUME_NAME"

# Wait for mount
sleep 2

# Use AppleScript to set DMG window properties
echo "Setting DMG window properties..."
osascript <<EOF
tell application "Finder"
    tell disk "$VOLUME_NAME"
        open
        
        -- Wait for window to open
        delay 1
        
        set current view of container window to icon view
        set toolbar visible of container window to false
        set statusbar visible of container window to false
        set bounds of container window to {200, 120, 740, 500}
        
        set viewOptions to icon view options of container window
        set arrangement of viewOptions to not arranged
        set icon size of viewOptions to 80
        
        -- Set background (only if we have an image)
        try
            set background picture of viewOptions to file ".background:background.png"
        on error
            -- Fall back to color if no image
            set background color of viewOptions to {61680, 61680, 62480}
        end try
        
        -- Position the app icon
        set position of item "$APP_NAME.app" of container window to {135, 190}
        
        -- Position the Applications symlink
        set position of item "Applications" of container window to {405, 190}
        
        -- Hide extension for app
        set extension hidden of item "$APP_NAME.app" of container window to true
        
        -- Update and close
        update without registering applications
        delay 2
        close
    end tell
end tell
EOF

# Give Finder time to write changes
sync
sleep 3

# Unmount the temporary DMG
echo "Unmounting temporary DMG..."
hdiutil detach "$DEVICE" -quiet

# Convert to compressed DMG
echo "Creating final DMG..."
hdiutil convert "$BUILD_DIR/temp.dmg" \
    -format UDZO \
    -imagekey zlib-level=9 \
    -quiet \
    -o "$PROJECT_ROOT/$DMG_NAME.dmg"

# Clean up
rm -f "$BUILD_DIR/temp.dmg"
rm -rf "$DMG_TEMP"

# Sign the DMG if certificate is available
if security find-identity -v -p codesigning | grep -q "Developer ID"; then
    echo "Signing DMG..."
    codesign --force --sign "Developer ID Application" "$PROJECT_ROOT/$DMG_NAME.dmg"
else
    echo "Note: No Developer ID found, DMG will not be signed"
fi

echo ""
echo "✅ DMG created successfully!"
echo ""
echo "DMG location: $PROJECT_ROOT/$DMG_NAME.dmg"
echo "Size: $(du -h "$PROJECT_ROOT/$DMG_NAME.dmg" | cut -f1)"
echo ""
echo "The DMG contains:"
echo "  - $APP_NAME.app"
echo "  - Drag-to-Applications interface"
echo ""
echo "To test: open '$PROJECT_ROOT/$DMG_NAME.dmg'"