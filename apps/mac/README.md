# How to Use

  1. Build the app:
  ./JacesMac/Scripts/build-app.sh

  2. Run in GUI mode (default):

* open /Applications/JacesMac.app *

  3. Run in headless mode (CLI):
  ./JacesMac/Scripts/run-headless.sh

* or directly: *
  
  /Applications/JacesMac.app/Contents/MacOS/JacesMac --headless

  Debug Logging Added

  1. MonitoringManager.swift:
  * Startup process logging with clear section markers
  * Detailed sync timer creation and lifecycle tracking
  * Timer firing events with timing precision
  * Timer cancellation logging
  * Connection callback status verification
  2. ConnectionManager.swift:
  * Connection fetch initiation and completion
  * Detailed connection validation logging
  * Schedule change detection and callback triggering
  * Main thread callback execution tracking

  Key Logging Points

  The logging now tracks:
  * When monitoring starts and waits for connection
  * When connections are fetched from the API
  * When sync schedules are detected (first time or changes)
  * When sync timers are created/invalidated
  * Exact timing of when sync timers fire
  * Full sync execution flow

  This comprehensive logging will help diagnose:
  * Whether the connection is being fetched successfully
  * If the schedule callback is being triggered
  * When timers are created and with what intervals
  * If timers are firing on schedule
  * Any timing delays or issues

  The logging uses clear section markers (===) for major events and indented details for
  better readability in the logs.
