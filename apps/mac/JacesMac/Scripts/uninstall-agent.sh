#!/bin/bash

# JacesMac LaunchAgent Uninstallation Script
# This script removes the JacesMac background service

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Get current user
CURRENT_USER=$(whoami)
HOME_DIR="/Users/$CURRENT_USER"
PLIST_NAME="com.jaces.mac.plist"
LAUNCH_AGENTS_DIR="$HOME_DIR/Library/LaunchAgents"
JACES_DIR="$HOME_DIR/.jaces-mac"
PLIST_PATH="$LAUNCH_AGENTS_DIR/$PLIST_NAME"

echo -e "${BLUE}JacesMac LaunchAgent Uninstaller${NC}"
echo "=================================="

# Check if running as root
if [ "$EUID" -eq 0 ]; then 
   echo -e "${RED}Error: Please don't run this script as root${NC}"
   exit 1
fi

# Check if agent is loaded
if launchctl list | grep -q "com.jaces.mac"; then
    echo "LaunchAgent is currently loaded"
    
    # Try to unload the agent
    echo "Unloading LaunchAgent..."
    if launchctl bootout gui/$UID/com.jaces.mac 2>/dev/null; then
        echo -e "${GREEN}✓ LaunchAgent unloaded successfully${NC}"
    else
        echo -e "${YELLOW}⚠ Could not unload LaunchAgent (it may have already been stopped)${NC}"
    fi
else
    echo "LaunchAgent is not currently loaded"
fi

# Kill any remaining headless processes
if pgrep -f "JacesMac.*--headless" > /dev/null; then
    echo "Stopping headless processes..."
    pkill -f "JacesMac.*--headless" || true
    sleep 1
    echo -e "${GREEN}✓ Headless processes stopped${NC}"
fi

# Remove plist file
if [ -f "$PLIST_PATH" ]; then
    echo "Removing plist file..."
    rm -f "$PLIST_PATH"
    echo -e "${GREEN}✓ Plist file removed${NC}"
else
    echo "Plist file not found (already removed)"
fi

# Ask about data cleanup
echo ""
echo -e "${YELLOW}Data Cleanup Options:${NC}"
echo "The JacesMac data directory contains:"
echo "  • Configuration files"
echo "  • Queued signals waiting to be uploaded"
echo "  • Log files"
echo ""
read -p "Do you want to remove all JacesMac data? (y/N): " -n 1 -r
echo ""

if [[ $REPLY =~ ^[Yy]$ ]]; then
    if [ -d "$JACES_DIR" ]; then
        # Show what will be deleted
        echo ""
        echo "The following will be deleted:"
        echo "  • Configuration: $JACES_DIR/config.json"
        echo "  • Status files: $JACES_DIR/status.json"
        echo "  • Queue data: $JACES_DIR/queue/"
        echo "  • Log files: $JACES_DIR/*.log"
        echo ""
        read -p "Are you sure? This cannot be undone. (y/N): " -n 1 -r
        echo ""
        
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            echo "Removing JacesMac data directory..."
            rm -rf "$JACES_DIR"
            echo -e "${GREEN}✓ Data directory removed${NC}"
        else
            echo "Data directory preserved"
        fi
    else
        echo "Data directory not found"
    fi
else
    echo "Data directory preserved at: $JACES_DIR"
fi

# Final verification
echo ""
echo "Verifying uninstallation..."

ISSUES=0

# Check if agent is still loaded
if launchctl list | grep -q "com.jaces.mac"; then
    echo -e "${RED}✗ LaunchAgent still appears to be loaded${NC}"
    ((ISSUES++))
else
    echo -e "${GREEN}✓ LaunchAgent not loaded${NC}"
fi

# Check if plist exists
if [ -f "$PLIST_PATH" ]; then
    echo -e "${RED}✗ Plist file still exists${NC}"
    ((ISSUES++))
else
    echo -e "${GREEN}✓ Plist file removed${NC}"
fi

# Check for running processes
if pgrep -f "JacesMac.*--headless" > /dev/null; then
    echo -e "${RED}✗ Headless processes still running${NC}"
    ((ISSUES++))
else
    echo -e "${GREEN}✓ No headless processes found${NC}"
fi

echo ""
if [ $ISSUES -eq 0 ]; then
    echo -e "${GREEN}Uninstallation complete!${NC}"
    echo ""
    echo "The JacesMac background service has been removed."
    echo "You can still use the JacesMac app normally from the dock."
else
    echo -e "${YELLOW}Uninstallation completed with issues${NC}"
    echo "You may need to restart your computer to fully remove the service."
fi

echo ""
echo "To reinstall the background service, run: install-agent.sh"