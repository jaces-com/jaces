#!/bin/bash
# Run JacesMac in headless mode (no UI, runs in background)

APP_PATH="/Applications/JacesMac.app"

if [ ! -d "$APP_PATH" ]; then
    echo "JacesMac.app not found at $APP_PATH"
    echo "Please build and install the app first"
    exit 1
fi

echo "Starting JacesMac in headless mode..."
"$APP_PATH/Contents/MacOS/JacesMac" --headless