import Foundation

class QueueMaintenanceManager {
    static let shared = QueueMaintenanceManager()
    
    private let maintenanceQueue = DispatchQueue(label: "com.memory.agent.maintenance", qos: .background)
    private var maintenanceTimer: Timer?
    private let fileManager = FileManager.default
    
    private let warningThreshold = Constants.maxQueueSizeWarning
    private let criticalThreshold = Constants.maxQueueSizeCritical
    private let maxSize = Constants.maxQueueSizeLimit
    
    private init() {
        startMaintenanceTimer()
    }
    
    func performMaintenance() {
        maintenanceQueue.async { [weak self] in
            self?.checkQueueSize()
            self?.cleanupOldFailedFiles()
            self?.validateQueueIntegrity()
        }
    }
    
    private func startMaintenanceTimer() {
        // Run maintenance every hour
        maintenanceTimer = Timer.scheduledTimer(withTimeInterval: 3600, repeats: true) { [weak self] _ in
            self?.performMaintenance()
        }
        
        // Also run on startup after a delay
        DispatchQueue.main.asyncAfter(deadline: .now() + 30) { [weak self] in
            self?.performMaintenance()
        }
    }
    
    private func checkQueueSize() {
        let stats = QueueManager.shared.getQueueStats()
        let totalSizeBytes = stats.totalSizeMB * 1024 * 1024
        
        Logger.shared.info("Queue size check: \(stats.totalSizeMB)MB")
        
        if totalSizeBytes > Double(maxSize) {
            Logger.shared.error("Queue size exceeded limit (\(stats.totalSizeMB)MB), starting cleanup")
            performEmergencyCleanup()
        } else if totalSizeBytes > Double(criticalThreshold) {
            Logger.shared.warning("Queue size critical (\(stats.totalSizeMB)MB)")
            cleanupOldFailedFiles(aggressive: true)
        } else if totalSizeBytes > Double(warningThreshold) {
            Logger.shared.warning("Queue size warning (\(stats.totalSizeMB)MB)")
        }
    }
    
    private func cleanupOldFailedFiles(aggressive: Bool = false) {
        let homeDir = fileManager.homeDirectoryForCurrentUser
        let failedDir = homeDir
            .appendingPathComponent(Constants.configDirectory)
            .appendingPathComponent(Constants.queueDirectory)
            .appendingPathComponent(Constants.failedDirectory)
        
        do {
            let files = try fileManager.contentsOfDirectory(
                at: failedDir,
                includingPropertiesForKeys: [.creationDateKey, .fileSizeKey],
                options: .skipsHiddenFiles
            )
            
            // Sort by creation date (oldest first)
            let sortedFiles = files.sorted { url1, url2 in
                let date1 = (try? url1.resourceValues(forKeys: [.creationDateKey]).creationDate) ?? Date.distantPast
                let date2 = (try? url2.resourceValues(forKeys: [.creationDateKey]).creationDate) ?? Date.distantPast
                return date1 < date2
            }
            
            // Determine how many files to keep
            let cutoffDate = aggressive ? 
                Date().addingTimeInterval(-24 * 60 * 60) : // 1 day if aggressive
                Date().addingTimeInterval(-7 * 24 * 60 * 60) // 7 days normally
            
            var deletedCount = 0
            var deletedSize: Int64 = 0
            
            for file in sortedFiles {
                let values = try file.resourceValues(forKeys: [.creationDateKey, .fileSizeKey])
                
                if let creationDate = values.creationDate, creationDate < cutoffDate {
                    let size = Int64(values.fileSize ?? 0)
                    try fileManager.removeItem(at: file)
                    deletedCount += 1
                    deletedSize += size
                    
                    Logger.shared.info("Deleted old failed file: \(file.lastPathComponent)")
                }
            }
            
            if deletedCount > 0 {
                let deletedMB = Double(deletedSize) / (1024 * 1024)
                Logger.shared.info("Cleaned up \(deletedCount) failed files, freed \(String(format: "%.2f", deletedMB))MB")
            }
            
        } catch {
            Logger.shared.error("Failed to cleanup old files: \(error)")
        }
    }
    
    private func performEmergencyCleanup() {
        Logger.shared.warning("Performing emergency cleanup to free space")
        
        let homeDir = fileManager.homeDirectoryForCurrentUser
        let queueDir = homeDir
            .appendingPathComponent(Constants.configDirectory)
            .appendingPathComponent(Constants.queueDirectory)
        
        // First, delete all failed files
        let failedDir = queueDir.appendingPathComponent(Constants.failedDirectory)
        if let files = try? fileManager.contentsOfDirectory(at: failedDir, includingPropertiesForKeys: nil) {
            for file in files {
                try? fileManager.removeItem(at: file)
            }
            Logger.shared.warning("Deleted all failed files during emergency cleanup")
        }
        
        // If still over limit, start deleting oldest pending files
        let stats = QueueManager.shared.getQueueStats()
        if stats.totalSizeMB * 1024 * 1024 > Double(maxSize) {
            Logger.shared.error("Still over limit after deleting failed files, this should not happen with pending files")
            // In production, we might want to alert the user or take other action
        }
    }
    
    private func validateQueueIntegrity() {
        // Check for corrupted files
        let homeDir = fileManager.homeDirectoryForCurrentUser
        let queueDir = homeDir
            .appendingPathComponent(Constants.configDirectory)
            .appendingPathComponent(Constants.queueDirectory)
        
        let directories = [
            queueDir.appendingPathComponent(Constants.pendingDirectory),
            queueDir.appendingPathComponent(Constants.failedDirectory)
        ]
        
        for dir in directories {
            validateFilesInDirectory(dir)
        }
    }
    
    private func validateFilesInDirectory(_ directory: URL) {
        guard let files = try? fileManager.contentsOfDirectory(
            at: directory,
            includingPropertiesForKeys: nil,
            options: .skipsHiddenFiles
        ) else { return }
        
        for file in files where file.pathExtension == "json" {
            do {
                let data = try Data(contentsOf: file)
                _ = try JSONDecoder().decode(SignalBatch.self, from: data)
            } catch {
                Logger.shared.error("Found corrupted file: \(file.lastPathComponent)")
                
                // Move corrupted file
                let corruptedFile = file.appendingPathExtension("corrupt")
                try? fileManager.moveItem(at: file, to: corruptedFile)
                
                // If in pending, move to failed
                if directory.lastPathComponent == Constants.pendingDirectory {
                    try? QueueManager.shared.moveBatchToFailed(corruptedFile)
                }
            }
        }
    }
    
    func getMaintenanceReport() -> MaintenanceReport {
        let stats = QueueManager.shared.getQueueStats()
        let totalSizeBytes = stats.totalSizeMB * 1024 * 1024
        
        return MaintenanceReport(
            queueSizeMB: stats.totalSizeMB,
            sizeStatus: sizeStatus(for: totalSizeBytes),
            pendingFiles: stats.pendingFiles,
            failedFiles: stats.failedFiles,
            recommendation: recommendation(for: totalSizeBytes, stats: stats)
        )
    }
    
    private func sizeStatus(for sizeBytes: Double) -> MaintenanceReport.SizeStatus {
        if sizeBytes > Double(criticalThreshold) {
            return .critical
        } else if sizeBytes > Double(warningThreshold) {
            return .warning
        } else {
            return .normal
        }
    }
    
    private func recommendation(for sizeBytes: Double, stats: QueueStats) -> String? {
        if sizeBytes > Double(criticalThreshold) {
            return "Queue size is critical. Check network connectivity and server status."
        } else if stats.failedFiles > 100 {
            return "Many failed uploads. Check server configuration and logs."
        } else if let oldest = stats.oldestPending, 
                  oldest < Date().addingTimeInterval(-24 * 60 * 60) {
            return "Pending uploads are over 24 hours old. Check network and server."
        }
        return nil
    }
}

struct MaintenanceReport {
    let queueSizeMB: Double
    let sizeStatus: SizeStatus
    let pendingFiles: Int
    let failedFiles: Int
    let recommendation: String?
    
    enum SizeStatus {
        case normal
        case warning
        case critical
    }
}