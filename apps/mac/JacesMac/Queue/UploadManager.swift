import Foundation

class UploadManager {
    static let shared = UploadManager()
    
    private let uploadQueue = DispatchQueue(label: "com.memory.agent.upload", qos: .background)
    private let session: URLSession
    private var isUploading = false
    private var syncInterval: TimeInterval = 60 // Default 1 minute for testing
    private var pendingSyncRequest = false
    
    private let maxRetries = 5
    private let baseRetryDelay: TimeInterval = 1.0
    private let maxRetryDelay: TimeInterval = 300.0 // 5 minutes
    
    private var uploadStats = UploadStats()
    
    private init() {
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 30
        config.timeoutIntervalForResource = 60
        self.session = URLSession(configuration: config)
        
        // Listen for new batches
        NotificationCenter.default.addObserver(
            self,
            selector: #selector(newBatchAvailable),
            name: .newBatchAvailable,
            object: nil
        )
        
        // Don't start timer here - let MonitoringManager control sync scheduling
        Logger.shared.info("UploadManager initialized - waiting for sync schedule configuration")
    }
    
    func startUploading() {
        uploadQueue.async { [weak self] in
            Logger.shared.info("UploadManager starting - initial processUploadQueue call")
            self?.processUploadQueue()
        }
    }
    
    func stopUploading() {
        uploadQueue.async { [weak self] in
            self?.isUploading = false
            Logger.shared.info("UploadManager stopped")
        }
    }
    
    func updateSyncInterval(_ interval: TimeInterval) {
        uploadQueue.async { [weak self] in
            self?.syncInterval = interval
            Logger.shared.info("Updated upload sync interval to \(interval) seconds")
        }
    }
    
    func triggerSync() {
        let triggerTime = Date()
        Logger.shared.info("UploadManager.triggerSync() called at \(triggerTime)")
        uploadQueue.async { [weak self] in
            Logger.shared.info("Starting upload queue processing from triggerSync (queued at \(triggerTime))")
            self?.processUploadQueue()
        }
    }
    
    func syncNow(completion: @escaping (Result<(uploaded: Int, failed: Int), Error>) -> Void) {
        uploadQueue.async { [weak self] in
            guard let self = self else {
                completion(.failure(NSError(domain: "UploadManager", code: -1, userInfo: [NSLocalizedDescriptionKey: "Upload manager not available"])))
                return
            }
            
            Logger.shared.info("Sync now requested - forcing immediate upload")
            
            // Force process upload queue
            var uploadedCount = 0
            var failedCount = 0
            
            guard ConfigManager.shared.isConfigured() else {
                completion(.failure(NSError(domain: "UploadManager", code: -2, userInfo: [NSLocalizedDescriptionKey: "No configuration found"])))
                return
            }
            
            guard NetworkChecker.shared.canUpload() else {
                completion(.failure(NSError(domain: "UploadManager", code: -3, userInfo: [NSLocalizedDescriptionKey: "Network not available"])))
                return
            }
            
            let pendingBatches = QueueManager.shared.getPendingBatches()
            Logger.shared.info("Force syncing \(pendingBatches.count) pending batches")
            
            for batchURL in pendingBatches {
                let result = self.uploadBatch(batchURL)
                
                switch result {
                case .success:
                    self.handleSuccessfulUpload(batchURL)
                    uploadedCount += 1
                case .failure(let error):
                    self.handleFailedUpload(batchURL, error: error)
                    failedCount += 1
                case .offline:
                    Logger.shared.info("Offline during sync, stopping")
                    completion(.failure(NSError(domain: "UploadManager", code: -4, userInfo: [NSLocalizedDescriptionKey: "Lost network connection during sync"])))
                    return
                }
            }
            
            // Update status file
            self.updateStatusFile()
            
            completion(.success((uploaded: uploadedCount, failed: failedCount)))
        }
    }
    
    @objc private func newBatchAvailable() {
        Logger.shared.debug("New batch available notification received")
        // Don't automatically trigger upload - wait for scheduled sync
    }
    
    private func processUploadQueue() {
        Logger.shared.info("=== processUploadQueue() started ===")
        
        guard !isUploading else {
            Logger.shared.warning("Upload already in progress, marking sync as pending")
            pendingSyncRequest = true
            return
        }
        
        guard ConfigManager.shared.isConfigured() else {
            Logger.shared.debug("No configuration found, skipping upload")
            return
        }
        
        guard NetworkChecker.shared.canUpload() else {
            Logger.shared.debug("Network not available for upload, skipping")
            return
        }
        
        isUploading = true
        defer { 
            isUploading = false
            Logger.shared.info("=== processUploadQueue() completed ===")
            
            // Check if there's a pending sync request
            if pendingSyncRequest {
                pendingSyncRequest = false
                Logger.shared.info("Processing pending sync request")
                // Process again after a short delay to allow system to settle
                uploadQueue.asyncAfter(deadline: .now() + 1.0) { [weak self] in
                    self?.processUploadQueue()
                }
            }
        }
        
        let pendingBatches = QueueManager.shared.getPendingBatches()
        Logger.shared.info("Processing \(pendingBatches.count) pending batches")
        
        if pendingBatches.isEmpty {
            Logger.shared.info("No pending batches to upload")
        }
        
        for batchURL in pendingBatches {
            Logger.shared.info("Uploading batch: \(batchURL.lastPathComponent)")
            let result = uploadBatch(batchURL)
            
            switch result {
            case .success:
                handleSuccessfulUpload(batchURL)
            case .failure(let error):
                handleFailedUpload(batchURL, error: error)
            case .offline:
                Logger.shared.info("Offline, stopping upload queue processing")
                return
            }
        }
        
        // Update status file
        updateStatusFile()
    }
    
    private func transformBatchForUpload(_ batch: SignalBatch) -> UploadPayload {
        return UploadPayload(
            stream_name: "apple_mac_app_activity",
            device_id: batch.deviceID,
            activity_events: batch.activityEvents,
            batch_metadata: batch.batchMetadata
        )
    }
    
    private func uploadBatch(_ batchURL: URL) -> UploadResult {
        do {
            // Load batch
            let data = try Data(contentsOf: batchURL)
            let decoder = JSONDecoder()
            decoder.dateDecodingStrategy = .iso8601
            var batch = try decoder.decode(SignalBatch.self, from: data)
            
            Logger.shared.debug("Loading batch: \(batchURL.lastPathComponent), retryCount: \(batch.retryCount), lastRetryAt: \(batch.lastRetryAt?.description ?? "nil")")
            
            // Check if we should retry
            if !shouldRetryBatch(batch) {
                Logger.shared.warning("Batch exceeded max retries, moving to failed: \(batchURL.lastPathComponent)")
                return .failure(UploadError.maxRetriesExceeded)
            }
            
            // Transform batch data for the new API format
            let uploadPayload = transformBatchForUpload(batch)
            let uploadData = try JSONEncoder().encode(uploadPayload)
            
            // Build request
            let config = ConfigManager.shared.configuration
            guard let url = URL(string: config.normalizedServerURL)?.appendingPathComponent("api/ingest") else {
                Logger.shared.error("Invalid URL: \(config.serverURL)")
                return .failure(UploadError.invalidURL)
            }
            
            Logger.shared.info("Attempting upload to: \(url.absoluteString)")
            
            var request = URLRequest(url: url)
            request.httpMethod = "POST"
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            // Use device token if available, otherwise fall back to device ID
            if let deviceToken = config.deviceToken {
                request.setValue(deviceToken, forHTTPHeaderField: "X-Device-Token")
            } else {
                request.setValue("Bearer \(config.deviceID)", forHTTPHeaderField: "Authorization")
            }
            request.httpBody = uploadData
            
            // Upload synchronously
            let semaphore = DispatchSemaphore(value: 0)
            var uploadResult: UploadResult = .failure(UploadError.unknown)
            
            let task = session.dataTask(with: request) { data, response, error in
                defer { semaphore.signal() }
                
                if let error = error {
                    let nsError = error as NSError
                    Logger.shared.error("Upload network error: \(error.localizedDescription) (code: \(nsError.code))")
                    
                    // Check if offline or server unreachable
                    if nsError.code == NSURLErrorNotConnectedToInternet ||
                       nsError.code == NSURLErrorNetworkConnectionLost {
                        uploadResult = .offline
                    } else if nsError.code == NSURLErrorCannotConnectToHost ||
                              nsError.code == NSURLErrorCannotFindHost ||
                              nsError.code == NSURLErrorTimedOut {
                        // Server is down/unreachable - should retry
                        Logger.shared.warning("Server unreachable, will retry later")
                        uploadResult = .failure(UploadError.serverError(nsError.code))
                    } else {
                        uploadResult = .failure(UploadError.network(error))
                    }
                    return
                }
                
                guard let httpResponse = response as? HTTPURLResponse else {
                    uploadResult = .failure(UploadError.invalidResponse)
                    return
                }
                
                switch httpResponse.statusCode {
                case 200...299:
                    uploadResult = .success
                case 400...499:
                    // Client error, don't retry
                    uploadResult = .failure(UploadError.clientError(httpResponse.statusCode))
                case 500...599:
                    // Server error, retry
                    uploadResult = .failure(UploadError.serverError(httpResponse.statusCode))
                default:
                    uploadResult = .failure(UploadError.unexpectedStatus(httpResponse.statusCode))
                }
            }
            
            task.resume()
            _ = semaphore.wait(timeout: .now() + 60)
            
            // Update retry info if failed
            if case .failure = uploadResult {
                batch.retryCount += 1
                batch.lastRetryAt = Date()
                
                // Save updated batch
                let encoder = JSONEncoder()
                encoder.dateEncodingStrategy = .iso8601
                let updatedData = try encoder.encode(batch)
                try updatedData.write(to: batchURL)
            }
            
            return uploadResult
            
        } catch {
            Logger.shared.error("Failed to decode batch \(batchURL.lastPathComponent): \(error)")
            return .failure(UploadError.decodingError(error))
        }
    }
    
    private func shouldRetryBatch(_ batch: SignalBatch) -> Bool {
        if batch.retryCount >= maxRetries {
            Logger.shared.debug("Batch retry count \(batch.retryCount) >= maxRetries \(maxRetries)")
            return false
        }
        
        // Check if enough time has passed for retry
        if let lastRetry = batch.lastRetryAt {
            let delay = retryDelay(for: batch.retryCount)
            let nextRetryTime = lastRetry.addingTimeInterval(delay)
            let canRetry = Date() >= nextRetryTime
            Logger.shared.debug("Batch retry check: lastRetry=\(lastRetry), delay=\(delay)s, nextRetryTime=\(nextRetryTime), canRetry=\(canRetry)")
            return canRetry
        }
        
        Logger.shared.debug("Batch has no lastRetryAt, allowing retry")
        return true
    }
    
    private func retryDelay(for attemptNumber: Int) -> TimeInterval {
        // Exponential backoff: 1s, 2s, 4s, 8s, 16s... up to max
        let delay = baseRetryDelay * pow(2.0, Double(attemptNumber - 1))
        return min(delay, maxRetryDelay)
    }
    
    private func handleSuccessfulUpload(_ batchURL: URL) {
        do {
            try QueueManager.shared.deleteBatch(batchURL)
            uploadStats.successCount += 1
            uploadStats.lastSuccessfulUpload = Date()
            Logger.shared.info("Successfully uploaded and deleted batch: \(batchURL.lastPathComponent)")
        } catch {
            Logger.shared.error("Failed to delete uploaded batch: \(error)")
        }
    }
    
    private func handleFailedUpload(_ batchURL: URL, error: UploadError) {
        uploadStats.failureCount += 1
        uploadStats.lastError = error.localizedDescription
        
        switch error {
        case .clientError, .maxRetriesExceeded:
            // Don't retry client errors or max retries
            do {
                try QueueManager.shared.moveBatchToFailed(batchURL)
            } catch {
                Logger.shared.error("Failed to move batch to failed: \(error)")
            }
        default:
            // Will retry on next run
            Logger.shared.warning("Upload failed, will retry: \(error)")
        }
    }
    
    private func updateStatusFile() {
        let stats = QueueManager.shared.getQueueStats()
        let status = AgentStatus(
            agentRunning: true,
            lastHeartbeat: Date(),
            queueStats: QueueStats(
                currentSignals: stats.currentSignals,
                pendingFiles: stats.pendingFiles,
                pendingSignals: stats.pendingSignals,
                failedFiles: stats.failedFiles,
                totalSizeMB: stats.totalSizeMB,
                oldestPending: stats.oldestPending,
                lastSuccessfulUpload: uploadStats.lastSuccessfulUpload,
                lastError: uploadStats.lastError,
                uploadSuccessRate24h: uploadStats.calculateSuccessRate()
            )
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

// MARK: - Upload Types
private struct UploadPayload: Codable {
    let stream_name: String
    let device_id: String
    let activity_events: [ActivityEvent]
    let batch_metadata: [String: String]
}
private enum UploadResult {
    case success
    case failure(UploadError)
    case offline
}

private enum UploadError: LocalizedError {
    case invalidURL
    case invalidResponse
    case network(Error)
    case clientError(Int)
    case serverError(Int)
    case unexpectedStatus(Int)
    case decodingError(Error)
    case maxRetriesExceeded
    case unknown
    
    var errorDescription: String? {
        switch self {
        case .invalidURL:
            return "Invalid server URL"
        case .invalidResponse:
            return "Invalid server response"
        case .network(let error):
            return "Network error: \(error.localizedDescription)"
        case .clientError(let code):
            return "Client error: HTTP \(code)"
        case .serverError(let code):
            return "Server error: HTTP \(code)"
        case .unexpectedStatus(let code):
            return "Unexpected status: HTTP \(code)"
        case .decodingError(let error):
            return "Decoding error: \(error.localizedDescription)"
        case .maxRetriesExceeded:
            return "Maximum retries exceeded"
        case .unknown:
            return "Unknown error"
        }
    }
}

private struct UploadStats {
    var successCount = 0
    var failureCount = 0
    var lastSuccessfulUpload: Date?
    var lastError: String?
    private var recentUploads: [(date: Date, success: Bool)] = []
    
    mutating func calculateSuccessRate() -> Double {
        // Remove uploads older than 24 hours
        let cutoff = Date().addingTimeInterval(-24 * 60 * 60)
        recentUploads.removeAll { $0.date < cutoff }
        
        guard !recentUploads.isEmpty else { return 0.0 }
        
        let successCount = recentUploads.filter { $0.success }.count
        return Double(successCount) / Double(recentUploads.count)
    }
}