import Foundation

struct QueueStats: Codable {
    var currentSignals: Int = 0
    var pendingFiles: Int = 0
    var pendingSignals: Int = 0
    var failedFiles: Int = 0
    var totalSizeMB: Double = 0.0
    var oldestPending: Date?
    var lastSuccessfulUpload: Date?
    var lastError: String?
    var uploadSuccessRate24h: Double = 0.0
    
    enum CodingKeys: String, CodingKey {
        case currentSignals = "current_signals"
        case pendingFiles = "pending_files"
        case pendingSignals = "pending_signals"
        case failedFiles = "failed_files"
        case totalSizeMB = "total_size_mb"
        case oldestPending = "oldest_pending"
        case lastSuccessfulUpload = "last_successful_upload"
        case lastError = "last_error"
        case uploadSuccessRate24h = "upload_success_rate_24h"
    }
}

struct AgentStatus: Codable {
    let agentRunning: Bool
    let lastHeartbeat: Date
    let queueStats: QueueStats
    
    enum CodingKeys: String, CodingKey {
        case agentRunning = "agent_running"
        case lastHeartbeat = "last_heartbeat"
        case queueStats = "queue_stats"
    }
}