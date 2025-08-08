import Foundation

class QueueManager {
    static let shared = QueueManager()
    
    private let queueBaseURL: URL
    private let currentFileURL: URL
    private let pendingDirURL: URL
    private let failedDirURL: URL
    
    private var currentBatch: SignalBatch
    private var maxBatchSize: Int
    private var maxBatchAge: TimeInterval
    private var batchCreatedAt: Date
    
    private let queue = DispatchQueue(label: "com.memory.agent.queue", qos: .background)
    private let fileManager = FileManager.default
    private var flushTimer: Timer?
    
    // Public getter for queue directory
    var queueDirURL: URL {
        return queueBaseURL
    }
    
    private init() {
        let homeDir = fileManager.homeDirectoryForCurrentUser
        let configDir = homeDir.appendingPathComponent(Constants.configDirectory)
        
        self.queueBaseURL = configDir.appendingPathComponent(Constants.queueDirectory)
        self.currentFileURL = queueBaseURL.appendingPathComponent(Constants.currentQueueFile)
        self.pendingDirURL = queueBaseURL.appendingPathComponent(Constants.pendingDirectory)
        self.failedDirURL = queueBaseURL.appendingPathComponent(Constants.failedDirectory)
        
        let config = ConfigManager.shared.configuration
        self.maxBatchSize = config.batchSize
        self.maxBatchAge = config.syncInterval
        self.batchCreatedAt = Date()
        self.currentBatch = SignalBatch(deviceID: config.deviceID)
        self.currentBatch.batchMetadata = createBatchMetadata()
        
        createQueueDirectories()
        loadCurrentBatch()
        startFlushTimer()
    }
    
    func addSignal(_ signal: CanonicalSignal) {
        queue.async { [weak self] in
            guard let self = self else { return }
            
            // Convert CanonicalSignal to ActivityEvent for the new format
            let activityEvent = ActivityEvent(from: signal)
            self.currentBatch.activityEvents.append(activityEvent)
            self.saveCurrentBatch()
            
            Logger.shared.debug("Added signal to batch. Current size: \(self.currentBatch.signalCount)")
            
            if self.shouldFlushBatch() {
                self.flushCurrentBatch()
            }
        }
    }
    
    func forceSyncNow(completion: @escaping (Result<Int, Error>) -> Void) {
        queue.async { [weak self] in
            guard let self = self else {
                completion(.failure(NSError(domain: "QueueManager", code: -1, userInfo: [NSLocalizedDescriptionKey: "Queue manager not available"])))
                return
            }
            
            Logger.shared.info("Force sync requested")
            
            // Flush current batch if it has signals
            if self.currentBatch.signalCount > 0 {
                self.flushCurrentBatch()
            }
            
            // Get count of pending batches
            let pendingBatches = self.getPendingBatches()
            
            // Trigger upload notification
            NotificationCenter.default.post(name: .newBatchAvailable, object: nil)
            
            completion(.success(pendingBatches.count))
        }
    }
    
    func getPendingBatches() -> [URL] {
        do {
            let files = try fileManager.contentsOfDirectory(
                at: pendingDirURL,
                includingPropertiesForKeys: [.creationDateKey],
                options: .skipsHiddenFiles
            )
            
            return files.filter { $0.pathExtension == "json" }
                .sorted { url1, url2 in
                    let date1 = try? url1.resourceValues(forKeys: [.creationDateKey]).creationDate ?? Date.distantPast
                    let date2 = try? url2.resourceValues(forKeys: [.creationDateKey]).creationDate ?? Date.distantPast
                    return date1! < date2!
                }
        } catch {
            Logger.shared.error("Failed to get pending batches: \(error)")
            return []
        }
    }
    
    func moveBatchToPending(_ batch: URL) throws {
        let fileName = batch.lastPathComponent
        let destination = pendingDirURL.appendingPathComponent(fileName)
        try fileManager.moveItem(at: batch, to: destination)
        Logger.shared.info("Moved batch to pending: \(fileName)")
    }
    
    func moveBatchToFailed(_ batch: URL) throws {
        let fileName = batch.lastPathComponent
        let destination = failedDirURL.appendingPathComponent(fileName)
        
        // If file already exists in failed, add timestamp to make unique
        var finalDestination = destination
        if fileManager.fileExists(atPath: destination.path) {
            let timestamp = Int(Date().timeIntervalSince1970)
            let newFileName = fileName.replacingOccurrences(of: ".json", with: "-\(timestamp).json")
            finalDestination = failedDirURL.appendingPathComponent(newFileName)
        }
        
        try fileManager.moveItem(at: batch, to: finalDestination)
        Logger.shared.warning("Moved batch to failed: \(fileName)")
    }
    
    func deleteBatch(_ batch: URL) throws {
        try fileManager.removeItem(at: batch)
        Logger.shared.info("Deleted batch: \(batch.lastPathComponent)")
    }
    
    func clearAllData(completion: @escaping (Result<Void, Error>) -> Void) {
        queue.async { [weak self] in
            guard let self = self else {
                completion(.failure(NSError(domain: "QueueManager", code: -1, userInfo: [NSLocalizedDescriptionKey: "Queue manager not available"])))
                return
            }
            
            do {
                Logger.shared.warning("Starting clearAllData operation")
                
                // 1. Clear current batch
                self.currentBatch = SignalBatch(deviceID: ConfigManager.shared.configuration.deviceID)
                self.currentBatch.batchMetadata = self.createBatchMetadata()
                self.batchCreatedAt = Date()
                self.saveCurrentBatch()
                
                // 2. Delete all pending batches
                let pendingFiles = self.getPendingBatches()
                for file in pendingFiles {
                    try self.fileManager.removeItem(at: file)
                    Logger.shared.info("Deleted pending batch: \(file.lastPathComponent)")
                }
                
                // 3. Delete all failed batches
                if let failedFiles = try? self.fileManager.contentsOfDirectory(
                    at: self.failedDirURL,
                    includingPropertiesForKeys: nil,
                    options: .skipsHiddenFiles
                ) {
                    for file in failedFiles.filter({ $0.pathExtension == "json" }) {
                        try self.fileManager.removeItem(at: file)
                        Logger.shared.info("Deleted failed batch: \(file.lastPathComponent)")
                    }
                }
                
                Logger.shared.warning("Successfully cleared all data")
                DispatchQueue.main.async {
                    completion(.success(()))
                }
                
            } catch {
                Logger.shared.error("Failed to clear all data: \(error)")
                DispatchQueue.main.async {
                    completion(.failure(error))
                }
            }
        }
    }
    
    func getQueueStats() -> QueueStats {
        var stats = QueueStats()
        
        // Current batch stats
        stats.currentSignals = currentBatch.signalCount
        
        // Pending stats
        let pendingFiles = getPendingBatches()
        stats.pendingFiles = pendingFiles.count
        
        // Count signals in pending files
        var pendingSignals = 0
        var oldestPending: Date?
        
        for file in pendingFiles {
            if let data = try? Data(contentsOf: file),
               let batch = try? JSONDecoder().decode(SignalBatch.self, from: data) {
                pendingSignals += batch.signalCount
                
                if oldestPending == nil || batch.createdAt < oldestPending! {
                    oldestPending = batch.createdAt
                }
            }
        }
        
        stats.pendingSignals = pendingSignals
        stats.oldestPending = oldestPending
        
        // Failed stats
        if let failedFiles = try? fileManager.contentsOfDirectory(
            at: failedDirURL,
            includingPropertiesForKeys: nil,
            options: .skipsHiddenFiles
        ) {
            stats.failedFiles = failedFiles.filter { $0.pathExtension == "json" }.count
        }
        
        // Total size
        stats.totalSizeMB = calculateQueueSize() / (1024 * 1024)
        
        return stats
    }
    
    private func createQueueDirectories() {
        let directories = [queueBaseURL, pendingDirURL, failedDirURL]
        
        for dir in directories {
            do {
                try fileManager.createDirectory(
                    at: dir,
                    withIntermediateDirectories: true,
                    attributes: nil
                )
            } catch {
                Logger.shared.error("Failed to create directory \(dir.path): \(error)")
            }
        }
    }
    
    private func loadCurrentBatch() {
        guard fileManager.fileExists(atPath: currentFileURL.path) else {
            Logger.shared.info("No current batch file found, starting fresh")
            return
        }
        
        do {
            let data = try Data(contentsOf: currentFileURL)
            let decoder = JSONDecoder()
            decoder.dateDecodingStrategy = .iso8601
            currentBatch = try decoder.decode(SignalBatch.self, from: data)
            batchCreatedAt = currentBatch.createdAt
            
            // Ensure batch metadata exists (for backwards compatibility)
            if currentBatch.batchMetadata.isEmpty {
                currentBatch.batchMetadata = createBatchMetadata()
                saveCurrentBatch()
            }
            
            Logger.shared.info("Loaded current batch with \(currentBatch.signalCount) signals")
        } catch {
            Logger.shared.error("Failed to load current batch: \(error)")
            // Move corrupted file to failed
            let corruptedFile = currentFileURL.appendingPathExtension("corrupt")
            try? fileManager.moveItem(at: currentFileURL, to: corruptedFile)
            try? moveBatchToFailed(corruptedFile)
        }
    }
    
    private func saveCurrentBatch() {
        do {
            let encoder = JSONEncoder()
            encoder.outputFormatting = .prettyPrinted
            encoder.dateEncodingStrategy = .iso8601
            
            let data = try encoder.encode(currentBatch)
            
            // Atomic write: write to temp file then rename
            let tempURL = currentFileURL.appendingPathExtension("tmp")
            try data.write(to: tempURL)
            
            // Remove existing file if present
            try? fileManager.removeItem(at: currentFileURL)
            
            // Rename temp to current
            try fileManager.moveItem(at: tempURL, to: currentFileURL)
        } catch {
            Logger.shared.error("Failed to save current batch: \(error)")
        }
    }
    
    private func shouldFlushBatch() -> Bool {
        let age = Date().timeIntervalSince(batchCreatedAt)
        return currentBatch.signalCount >= maxBatchSize || age >= maxBatchAge
    }
    
    private func flushCurrentBatch() {
        guard currentBatch.signalCount > 0 else { return }
        
        Logger.shared.info("Flushing batch with \(currentBatch.signalCount) signals")
        
        // Save final state
        saveCurrentBatch()
        
        // Generate filename
        let fileName = currentBatch.fileName()
        let pendingFile = pendingDirURL.appendingPathComponent(fileName)
        
        do {
            // Move current to pending
            try fileManager.moveItem(at: currentFileURL, to: pendingFile)
            
            // Create new batch
            let config = ConfigManager.shared.configuration
            currentBatch = SignalBatch(deviceID: config.deviceID)
            currentBatch.batchMetadata = createBatchMetadata()
            batchCreatedAt = Date()
            
            Logger.shared.info("Batch moved to pending: \(fileName)")
            
            // Notify upload manager
            NotificationCenter.default.post(name: .newBatchAvailable, object: nil)
        } catch {
            Logger.shared.error("Failed to flush batch: \(error)")
        }
    }
    
    private func startFlushTimer() {
        flushTimer = Timer.scheduledTimer(withTimeInterval: 30, repeats: true) { [weak self] _ in
            self?.queue.async {
                if self?.shouldFlushBatch() == true {
                    self?.flushCurrentBatch()
                }
            }
        }
    }
    
    private func calculateQueueSize() -> Double {
        var totalSize: Double = 0
        
        // Add current file size
        if let attrs = try? fileManager.attributesOfItem(atPath: currentFileURL.path),
           let size = attrs[.size] as? NSNumber {
            totalSize += size.doubleValue
        }
        
        // Add pending directory size
        totalSize += directorySize(pendingDirURL)
        
        // Add failed directory size
        totalSize += directorySize(failedDirURL)
        
        return totalSize
    }
    
    private func directorySize(_ url: URL) -> Double {
        var size: Double = 0
        
        if let enumerator = fileManager.enumerator(
            at: url,
            includingPropertiesForKeys: [.fileSizeKey],
            options: .skipsHiddenFiles
        ) {
            for case let fileURL as URL in enumerator {
                if let attrs = try? fileURL.resourceValues(forKeys: [.fileSizeKey]),
                   let fileSize = attrs.fileSize {
                    size += Double(fileSize)
                }
            }
        }
        
        return size
    }
    
    // MARK: - Configuration Updates
    func updateConfiguration(batchSize: Int, syncInterval: TimeInterval) {
        queue.async { [weak self] in
            guard let self = self else { return }
            
            self.maxBatchSize = batchSize
            self.maxBatchAge = syncInterval
            
            Logger.shared.info("Queue configuration updated - Batch size: \(batchSize), Sync interval: \(syncInterval)s")
            
            // Check if we should flush based on new settings
            if self.shouldFlushBatch() {
                self.flushCurrentBatch()
            }
        }
    }
    
    func updateDeviceInfo(deviceID: String) {
        queue.async { [weak self] in
            guard let self = self else { return }
            
            // Update current batch device ID
            self.currentBatch.deviceID = deviceID
            self.saveCurrentBatch()
            
            Logger.shared.info("Device ID updated in current batch")
        }
    }
    
    private func createBatchMetadata() -> [String: String] {
        var metadata: [String: String] = [:]
        
        // Add system information
        let processInfo = ProcessInfo.processInfo
        metadata["os_version"] = processInfo.operatingSystemVersionString
        metadata["host_name"] = processInfo.hostName
        metadata["process_name"] = processInfo.processName
        metadata["app_version"] = Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "unknown"
        metadata["build_number"] = Bundle.main.infoDictionary?["CFBundleVersion"] as? String ?? "unknown"
        
        // Add timestamp info
        metadata["batch_created_at"] = ISO8601DateFormatter().string(from: Date())
        metadata["timezone"] = TimeZone.current.identifier
        
        return metadata
    }
}

// MARK: - Notifications
extension Notification.Name {
    static let newBatchAvailable = Notification.Name("com.memory.agent.newBatchAvailable")
}