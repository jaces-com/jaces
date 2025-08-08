import Foundation

struct Constants {
    static let agentName = "jaces-mac"
    static let launchAgentIdentifier = "com.jaces.mac"
    static let configDirectory = ".jaces-mac"
    static let configFileName = "config.json"
    static let statusFileName = "status.json"
    
    static let queueDirectory = "queue"
    static let currentQueueFile = "current.json"
    static let pendingDirectory = "pending"
    static let failedDirectory = "failed"
    
    static let logFileName = "jaces-mac.log"
    static let maxLogSize = 10 * 1024 * 1024 // 10MB
    static let maxLogFiles = 5
    
    static let defaultSyncInterval: TimeInterval = 60
    static let defaultBatchSize = 100
    static let defaultMaxRetries = 5
    
    static let heartbeatInterval: TimeInterval = 300 // 5 minutes
    static let configCheckInterval: TimeInterval = 60 // 1 minute
    
    static let maxQueueSizeWarning = 100 * 1024 * 1024 // 100MB
    static let maxQueueSizeCritical = 500 * 1024 * 1024 // 500MB
    static let maxQueueSizeLimit = 1024 * 1024 * 1024 // 1GB
}