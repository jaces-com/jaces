#!/bin/bash

# JacesMac LaunchAgent Installation Script
# This script installs the JacesMac background service

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Get current user
CURRENT_USER=$(whoami)
HOME_DIR="/Users/$CURRENT_USER"
PLIST_NAME="com.jaces.mac.plist"
LAUNCH_AGENTS_DIR="$HOME_DIR/Library/LaunchAgents"
JACES_DIR="$HOME_DIR/.jaces-mac"

echo -e "${BLUE}JacesMac LaunchAgent Installer${NC}"
echo "================================"

# Check if running as root
if [ "$EUID" -eq 0 ]; then 
   echo -e "${RED}Error: Please don't run this script as root${NC}"
   exit 1
fi

# Check if JacesMac.app exists
if [ ! -d "/Applications/JacesMac.app" ]; then
    echo -e "${RED}Error: JacesMac.app not found in /Applications${NC}"
    echo "Please install JacesMac.app first"
    exit 1
fi

# Create LaunchAgents directory if it doesn't exist
if [ ! -d "$LAUNCH_AGENTS_DIR" ]; then
    echo "Creating LaunchAgents directory..."
    mkdir -p "$LAUNCH_AGENTS_DIR"
fi

# Create jaces-mac directory if it doesn't exist
if [ ! -d "$JACES_DIR" ]; then
    echo "Creating .jaces-mac directory..."
    mkdir -p "$JACES_DIR"
fi

# Check if agent is already installed
if launchctl list | grep -q "com.jaces.mac"; then
    echo -e "${BLUE}LaunchAgent is already loaded. Unloading first...${NC}"
    launchctl bootout gui/$UID/com.jaces.mac 2>/dev/null || true
    sleep 1
fi

# Copy plist file from app bundle
PLIST_SOURCE="/Applications/JacesMac.app/Contents/Resources/$PLIST_NAME"
PLIST_DEST="$LAUNCH_AGENTS_DIR/$PLIST_NAME"

if [ ! -f "$PLIST_SOURCE" ]; then
    echo -e "${RED}Error: Plist file not found in app bundle${NC}"
    echo "Looking for: $PLIST_SOURCE"
    exit 1
fi

echo "Copying plist file..."
cp "$PLIST_SOURCE" "$PLIST_DEST"

# Replace USER_NAME placeholder with actual username
sed -i '' "s/USER_NAME/$CURRENT_USER/g" "$PLIST_DEST"

# Set correct permissions
chmod 644 "$PLIST_DEST"

# Load the agent
echo "Loading LaunchAgent..."
if launchctl bootstrap gui/$UID "$PLIST_DEST"; then
    echo -e "${GREEN}✓ LaunchAgent loaded successfully${NC}"
else
    echo -e "${RED}✗ Failed to load LaunchAgent${NC}"
    exit 1
fi

# Wait a moment for the agent to start
sleep 2

# Check if agent is running
if launchctl list | grep -q "com.jaces.mac"; then
    echo -e "${GREEN}✓ LaunchAgent is running${NC}"
    
    # Check if the process is actually running
    if pgrep -f "JacesMac.*--headless" > /dev/null; then
        echo -e "${GREEN}✓ JacesMac headless process is active${NC}"
    else
        echo -e "${RED}✗ LaunchAgent loaded but process not found${NC}"
        echo "Check logs at: $JACES_DIR/launchagent.stderr.log"
    fi
else
    echo -e "${RED}✗ LaunchAgent not found in launchctl list${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}Installation complete!${NC}"
echo ""
echo "The JacesMac background service will now:"
echo "  • Start automatically when you log in"
echo "  • Restart if it crashes"
echo "  • Run in the background without a dock icon"
echo ""
echo "Logs can be found at:"
echo "  • $JACES_DIR/launchagent.stdout.log"
echo "  • $JACES_DIR/launchagent.stderr.log"
echo "  • $JACES_DIR/jaces-mac.log"
echo ""
echo "To check status: launchctl list | grep com.jaces.mac"
echo "To uninstall: run uninstall-agent.sh"