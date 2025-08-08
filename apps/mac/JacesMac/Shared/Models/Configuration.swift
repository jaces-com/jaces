import Foundation

struct Configuration: Codable {
    let serverURL: String
    let deviceName: String
    let deviceID: String
    let deviceToken: String?
    let syncInterval: TimeInterval
    let batchSize: Int
    let maxRetries: Int
    
    // Connection-specific fields
    let connectionID: String?
    let connectionSchedule: String?
    let lastConnectionSync: Date?
    
    // Computed property that returns normalized URL with http:// prefix if needed
    var normalizedServerURL: String {
        if serverURL.isEmpty {
            return serverURL
        }
        
        // Check if URL already has a scheme
        if serverURL.hasPrefix("http://") || serverURL.hasPrefix("https://") {
            return serverURL
        }
        
        // Add http:// prefix
        return "http://\(serverURL)"
    }
    
    // Get effective sync interval - use connection schedule if available, otherwise default
    var effectiveSyncInterval: TimeInterval {
        // If we have a connection schedule, parse it
        if let schedule = connectionSchedule {
            return CronScheduler.shared.intervalFromCronExpression(schedule)
        }
        // Otherwise use the configured interval
        return syncInterval
    }
    
    static let defaultConfiguration = Configuration(
        serverURL: "",
        deviceName: "Macbook",
        deviceID: UUID().uuidString,
        deviceToken: nil,
        syncInterval: 60, // Default to 1 minute for testing
        batchSize: 100,
        maxRetries: 5,
        connectionID: nil,
        connectionSchedule: nil,
        lastConnectionSync: nil
    )
    
    enum CodingKeys: String, CodingKey {
        case serverURL = "server_url"
        case deviceName = "device_name"
        case deviceID = "device_id"
        case deviceToken = "device_token"
        case syncInterval = "sync_interval"
        case batchSize = "batch_size"
        case maxRetries = "max_retries"
        case connectionID = "connection_id"
        case connectionSchedule = "connection_schedule"
        case lastConnectionSync = "last_connection_sync"
    }
}