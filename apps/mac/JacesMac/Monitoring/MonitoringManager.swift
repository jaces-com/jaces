import Foundation
import AppKit

class MonitoringManager: ObservableObject {
    static let shared = MonitoringManager()
    
    private let activityMonitor: ActivityMonitor
    private let configWatcher: ConfigWatcher
    private var isRunning = false
    private var syncTimer: Timer?
    private var uiUpdateTimer: Timer?
    
    @Published var isMonitoring = false
    @Published var signalCount = 0
    @Published var lastActivity: String?
    @Published var nextSyncTime: Date?
    @Published var syncScheduleDescription: String = "Not configured"
    
    private init() {
        Logger.shared.info("Initializing MonitoringManager...")
        self.activityMonitor = ActivityMonitor()
        self.configWatcher = ConfigWatcher()
        
        self.activityMonitor.delegate = self
        self.configWatcher.delegate = self
        
        // Set up connection manager callbacks
        ConnectionManager.shared.onConnectionUpdated = { [weak self] connection in
            self?.handleConnectionUpdate(connection)
        }
        
        ConnectionManager.shared.onScheduleChanged = { [weak self] schedule in
            self?.updateSyncSchedule(schedule)
        }
        
        Logger.shared.info("MonitoringManager initialized")
    }
    
    func startMonitoring() {
        guard !isRunning else {
            Logger.shared.warning("Monitoring already running")
            return
        }
        
        Logger.shared.info("=== STARTING MONITORING SERVICES ===")
        
        // Load configuration
        Logger.shared.info("Loading configuration...")
        ConfigManager.shared.loadConfiguration()
        
        if !ConfigManager.shared.isConfigured() {
            Logger.shared.warning("No valid configuration found. Monitoring will start when configured.")
        } else {
            Logger.shared.info("Configuration loaded successfully")
        }
        
        // Start config watching
        Logger.shared.info("Starting config watcher...")
        configWatcher.startWatching()
        
        // Start connection manager
        Logger.shared.info("Starting connection manager...")
        ConnectionManager.shared.startMonitoring()
        
        // Start upload manager (no longer has its own timer)
        Logger.shared.info("Starting upload manager...")
        UploadManager.shared.startUploading()
        
        // Start maintenance manager
        Logger.shared.info("Starting queue maintenance...")
        QueueMaintenanceManager.shared.performMaintenance()
        
        // Update status
        isRunning = true
        DispatchQueue.main.async {
            self.isMonitoring = true
        }
        
        // Don't set up initial sync schedule here - wait for ConnectionManager to fetch it
        // The onScheduleChanged callback will handle it when the connection is fetched
        Logger.shared.info("Waiting for ConnectionManager to fetch connection and determine sync schedule...")
        Logger.shared.info("  onScheduleChanged callback is set: \(ConnectionManager.shared.onScheduleChanged != nil)")
        
        // Log heartbeat every 5 minutes
        Logger.shared.info("Setting up heartbeat timer (5 minute interval)")
        Timer.scheduledTimer(withTimeInterval: 300, repeats: true) { _ in
            let stats = QueueManager.shared.getQueueStats()
            Logger.shared.info(
                "MonitoringManager heartbeat - Queue: \(stats.currentSignals) current, \(stats.pendingSignals) pending"
            )
            self.updateStatusFile()
        }
        
        Logger.shared.info("=== MONITORING STARTED SUCCESSFULLY ===")
        Logger.shared.info("  ActivityMonitor is active")
        Logger.shared.info("  Waiting for connection fetch to set up sync schedule")
    }
    
    func stopMonitoring() {
        guard isRunning else {
            Logger.shared.warning("Monitoring not running")
            return
        }
        
        Logger.shared.info("Stopping monitoring services...")
        
        // Stop services
        configWatcher.stopWatching()
        ConnectionManager.shared.stopMonitoring()
        UploadManager.shared.stopUploading()
        
        // Stop sync timer
        if syncTimer != nil {
            Logger.shared.info("Stopping sync timer")
            syncTimer?.invalidate()
            syncTimer = nil
        }
        
        // Stop UI update timer
        if uiUpdateTimer != nil {
            Logger.shared.info("Stopping UI update timer")
            uiUpdateTimer?.invalidate()
            uiUpdateTimer = nil
        }
        
        isRunning = false
        DispatchQueue.main.async {
            self.isMonitoring = false
        }
        
        Logger.shared.info("Monitoring stopped - All timers cancelled")
    }
    
    private func handleConnectionUpdate(_ connection: Connection) {
        DispatchQueue.main.async {
            self.syncScheduleDescription = CronScheduler.shared.descriptionForCron(connection.syncSchedule)
            if let nextSync = CronScheduler.shared.nextSyncTime(cron: connection.syncSchedule, lastSync: connection.lastSync) {
                self.nextSyncTime = nextSync
            }
        }
    }
    
    private func updateSyncSchedule(_ schedule: String) {
        Logger.shared.info("Updating sync schedule to: \(schedule)")
        
        // Cancel existing timer
        if syncTimer != nil {
            Logger.shared.info("Invalidating existing sync timer")
            syncTimer?.invalidate()
            syncTimer = nil
        }
        
        // Update UI
        DispatchQueue.main.async {
            self.syncScheduleDescription = CronScheduler.shared.descriptionForCron(schedule)
        }
        
        // Set up new timer based on schedule
        let interval = CronScheduler.shared.intervalFromCronExpression(schedule)
        Logger.shared.info("Cron expression '\(schedule)' parsed to interval: \(interval) seconds")
        
        if interval != TimeInterval.infinity {
            // Update upload manager with new interval
            UploadManager.shared.updateSyncInterval(interval)
            
            // Schedule the first sync
            scheduleNextSync(interval: interval)
            
            Logger.shared.info("Sync schedule configured with interval: \(interval) seconds")
        } else {
            Logger.shared.info("Manual sync mode - no automatic timer set")
            
            // Cancel UI update timer for manual mode
            uiUpdateTimer?.invalidate()
            uiUpdateTimer = nil
            
            DispatchQueue.main.async {
                self.nextSyncTime = nil
            }
        }
    }
    
    private func scheduleNextSync(interval: TimeInterval) {
        // Calculate next sync time
        let nextSync = Date().addingTimeInterval(interval)
        
        // Update UI
        DispatchQueue.main.async {
            self.nextSyncTime = nextSync
        }
        
        Logger.shared.info("=== SCHEDULING NEXT SYNC ===")
        Logger.shared.info("  Next sync time: \(nextSync)")
        Logger.shared.info("  Interval: \(interval) seconds (\(interval/60) minutes)")
        Logger.shared.info("  Current time: \(Date())")
        
        // Cancel existing UI update timer
        if uiUpdateTimer != nil {
            Logger.shared.debug("Invalidating existing UI update timer")
            uiUpdateTimer?.invalidate()
            uiUpdateTimer = nil
        }
        
        // Start UI update timer for countdown display (every second)
        Logger.shared.debug("Creating UI update timer (1 second interval)")
        uiUpdateTimer = Timer.scheduledTimer(withTimeInterval: 1.0, repeats: true) { [weak self] _ in
            // This timer is just for UI updates, not for triggering syncs
            // The actual sync is handled by syncTimer
            guard let self = self, let nextSyncTime = self.nextSyncTime else { 
                Logger.shared.warning("UI update timer fired but self or nextSyncTime is nil")
                return 
            }
            
            // Just trigger UI update by accessing published property
            DispatchQueue.main.async {
                // Force UI refresh by updating a timestamp
                self.objectWillChange.send()
            }
        }
        
        // Create a timer that fires exactly at the sync time
        Logger.shared.info("Creating sync timer to fire in \(interval) seconds")
        syncTimer = Timer.scheduledTimer(withTimeInterval: interval, repeats: false) { [weak self] _ in
            guard let self = self else { 
                Logger.shared.error("Sync timer fired but self is nil!")
                return 
            }
            
            Logger.shared.info("=== SYNC TIMER FIRED ===")
            Logger.shared.info("  Scheduled for: \(nextSync)")
            Logger.shared.info("  Actual fire time: \(Date())")
            let delay = Date().timeIntervalSince(nextSync)
            Logger.shared.info("  Timer delay: \(String(format: "%.2f", delay)) seconds")
            
            // Perform the sync
            self.performScheduledSync()
            
            // Schedule the next sync
            Logger.shared.info("Rescheduling timer for next sync cycle")
            self.scheduleNextSync(interval: interval)
        }
        
        // Verify timer was created and retained
        if let timer = syncTimer {
            Logger.shared.info("=== SYNC TIMER CREATED SUCCESSFULLY ===")
            Logger.shared.info("  Timer object: \(Unmanaged.passUnretained(timer).toOpaque())")
            Logger.shared.info("  Is valid: \(timer.isValid)")
            Logger.shared.info("  Fire date: \(timer.fireDate)")
        } else {
            Logger.shared.error("=== SYNC TIMER CREATION FAILED - timer is nil ===")
        }
    }
    
    private func performScheduledSync() {
        let syncStartTime = Date()
        Logger.shared.info("=== SCHEDULED SYNC STARTED at \(syncStartTime) ===")
        
        // Get current queue stats before sync
        let statsBeforeSync = QueueManager.shared.getQueueStats()
        Logger.shared.info("Queue stats before sync - Current signals: \(statsBeforeSync.currentSignals), Pending files: \(statsBeforeSync.pendingFiles)")
        
        // Force queue flush
        QueueManager.shared.forceSyncNow { result in
            switch result {
            case .success(let count):
                Logger.shared.info("Successfully flushed \(count) signals to batches")
                
                // Get stats after flush
                let statsAfterFlush = QueueManager.shared.getQueueStats()
                Logger.shared.info("Queue stats after flush - Current signals: \(statsAfterFlush.currentSignals), Pending files: \(statsAfterFlush.pendingFiles)")
                
            case .failure(let error):
                Logger.shared.error("Failed to flush queue: \(error)")
            }
        }
        
        // Trigger upload
        Logger.shared.info("Triggering upload manager sync")
        UploadManager.shared.triggerSync()
        
        // Update last sync time in connection
        Logger.shared.info("Updating last sync time in connection")
        ConnectionManager.shared.updateLastSyncTime()
        
        let syncDuration = Date().timeIntervalSince(syncStartTime)
        Logger.shared.info("=== SCHEDULED SYNC COMPLETED in \(String(format: "%.2f", syncDuration)) seconds ===")
    }
    
    private func updateStatusFile() {
        let stats = QueueManager.shared.getQueueStats()
        let status = AgentStatus(
            agentRunning: true,
            lastHeartbeat: Date(),
            queueStats: stats
        )
        
        let homeDir = FileManager.default.homeDirectoryForCurrentUser
        let statusFile = homeDir
            .appendingPathComponent(Constants.configDirectory)
            .appendingPathComponent(Constants.statusFileName)
        
        do {
            let encoder = JSONEncoder()
            encoder.outputFormatting = .prettyPrinted
            encoder.dateEncodingStrategy = .iso8601
            let data = try encoder.encode(status)
            try data.write(to: statusFile)
        } catch {
            Logger.shared.error("Failed to update status file: \(error)")
        }
    }
}

// MARK: - ActivityMonitorDelegate
extension MonitoringManager: ActivityMonitorDelegate {
    func activityMonitor(_ monitor: ActivityMonitor, didCollectSignal signal: CanonicalSignal) {
        Logger.shared.info("Signal collected: \(signal.signalType) - \(signal.metadata["app_name"] ?? "unknown")")
        
        // Add signal to queue
        QueueManager.shared.addSignal(signal)
        
        // Update UI
        DispatchQueue.main.async {
            self.signalCount += 1
            self.lastActivity = "\(signal.signalType): \(signal.metadata["app_name"] ?? "unknown")"
        }
    }
}

// MARK: - ConfigWatcherDelegate
extension MonitoringManager: ConfigWatcherDelegate {
    func configurationDidChange() {
        Logger.shared.info("Configuration changed, applying new settings")
        
        // Update queue manager settings
        let newConfig = ConfigManager.shared.configuration
        QueueManager.shared.updateConfiguration(
            batchSize: newConfig.batchSize,
            syncInterval: newConfig.syncInterval
        )
        
        // Update device info in case device name changed
        QueueManager.shared.updateDeviceInfo(deviceID: newConfig.deviceID)
        
        Logger.shared.info("Configuration reloaded - Server: \(newConfig.serverURL), Device: \(newConfig.deviceName)")
    }
}