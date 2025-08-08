import Foundation

class CrashRecoveryManager {
    static let shared = CrashRecoveryManager()
    
    private let fileManager = FileManager.default
    private let recoveryQueue = DispatchQueue(label: "com.memory.agent.recovery", qos: .background)
    
    private init() {}
    
    func performRecovery() {
        recoveryQueue.async { [weak self] in
            self?.recoverIncompleteBatches()
            self?.validatePendingBatches()
            self?.cleanupTempFiles()
        }
    }
    
    private func recoverIncompleteBatches() {
        let homeDir = fileManager.homeDirectoryForCurrentUser
        let queueDir = homeDir
            .appendingPathComponent(Constants.configDirectory)
            .appendingPathComponent(Constants.queueDirectory)
        
        // Check for current.json
        let currentFile = queueDir.appendingPathComponent(Constants.currentQueueFile)
        
        if fileManager.fileExists(atPath: currentFile.path) {
            do {
                let data = try Data(contentsOf: currentFile)
                let decoder = JSONDecoder()
                decoder.dateDecodingStrategy = .iso8601
                let batch = try decoder.decode(SignalBatch.self, from: data)
                
                if batch.signalCount > 0 {
                    Logger.shared.info("Found incomplete batch with \(batch.signalCount) signals, moving to pending")
                    
                    // Generate filename and move to pending
                    let fileName = batch.fileName()
                    let pendingFile = queueDir
                        .appendingPathComponent(Constants.pendingDirectory)
                        .appendingPathComponent(fileName)
                    
                    try fileManager.moveItem(at: currentFile, to: pendingFile)
                    Logger.shared.info("Recovered incomplete batch: \(fileName)")
                    
                    // Notify upload manager
                    NotificationCenter.default.post(name: .newBatchAvailable, object: nil)
                } else {
                    // Empty batch, just remove
                    try fileManager.removeItem(at: currentFile)
                }
            } catch {
                Logger.shared.error("Failed to recover current batch: \(error)")
                
                // Move corrupted file to failed
                let corruptedFile = currentFile.appendingPathExtension("corrupt-\(Int(Date().timeIntervalSince1970))")
                try? fileManager.moveItem(at: currentFile, to: corruptedFile)
                
                let failedDir = queueDir.appendingPathComponent(Constants.failedDirectory)
                let failedFile = failedDir.appendingPathComponent(corruptedFile.lastPathComponent)
                try? fileManager.moveItem(at: corruptedFile, to: failedFile)
            }
        }
    }
    
    private func validatePendingBatches() {
        let pendingBatches = QueueManager.shared.getPendingBatches()
        
        for batchURL in pendingBatches {
            do {
                let data = try Data(contentsOf: batchURL)
                _ = try JSONDecoder().decode(SignalBatch.self, from: data)
                // File is valid
            } catch {
                Logger.shared.error("Found corrupted pending batch: \(batchURL.lastPathComponent)")
                
                // Move to failed with .corrupt extension
                let corruptedFile = batchURL.appendingPathExtension("corrupt")
                try? fileManager.moveItem(at: batchURL, to: corruptedFile)
                try? QueueManager.shared.moveBatchToFailed(corruptedFile)
            }
        }
    }
    
    private func cleanupTempFiles() {
        let homeDir = fileManager.homeDirectoryForCurrentUser
        let queueDir = homeDir
            .appendingPathComponent(Constants.configDirectory)
            .appendingPathComponent(Constants.queueDirectory)
        
        // Clean up any .tmp files
        if let enumerator = fileManager.enumerator(
            at: queueDir,
            includingPropertiesForKeys: nil,
            options: .skipsHiddenFiles
        ) {
            for case let fileURL as URL in enumerator {
                if fileURL.pathExtension == "tmp" {
                    Logger.shared.warning("Removing temp file: \(fileURL.lastPathComponent)")
                    try? fileManager.removeItem(at: fileURL)
                }
            }
        }
    }
    
    func createRecoveryCheckpoint() {
        // Create a checkpoint file that indicates clean shutdown
        let homeDir = fileManager.homeDirectoryForCurrentUser
        let checkpointFile = homeDir
            .appendingPathComponent(Constants.configDirectory)
            .appendingPathComponent("shutdown.checkpoint")
        
        let checkpoint = [
            "timestamp": Date().timeIntervalSince1970,
            "version": "1.0",
            "clean_shutdown": true
        ] as [String : Any]
        
        if let data = try? JSONSerialization.data(withJSONObject: checkpoint) {
            try? data.write(to: checkpointFile)
        }
    }
    
    func wasCleanShutdown() -> Bool {
        let homeDir = fileManager.homeDirectoryForCurrentUser
        let checkpointFile = homeDir
            .appendingPathComponent(Constants.configDirectory)
            .appendingPathComponent("shutdown.checkpoint")
        
        defer {
            // Remove checkpoint after reading
            try? fileManager.removeItem(at: checkpointFile)
        }
        
        guard fileManager.fileExists(atPath: checkpointFile.path),
              let data = try? Data(contentsOf: checkpointFile),
              let checkpoint = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let cleanShutdown = checkpoint["clean_shutdown"] as? Bool else {
            return false
        }
        
        return cleanShutdown
    }
}