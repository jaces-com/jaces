#!/bin/bash
# Build the unified JacesMac app

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "Building JacesMac..."
echo "===================="

cd "$PROJECT_ROOT"

# Build using Xcode
xcodebuild -project Jaces-mac.xcodeproj \
           -scheme JacesMac \
           -configuration Debug \
           -derivedDataPath build \
           CODE_SIGN_IDENTITY="" \
           CODE_SIGNING_REQUIRED=NO \
           CODE_SIGNING_ALLOWED=NO

echo "Build completed!"
echo "App location: $PROJECT_ROOT/build/Build/Products/Debug/JacesMac.app"

# Optional: Copy to Applications
read -p "Copy to /Applications? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    sudo rm -rf /Applications/JacesMac.app
    sudo cp -R "$PROJECT_ROOT/build/Build/Products/Debug/JacesMac.app" /Applications/
    echo "Installed to /Applications/JacesMac.app"
fi