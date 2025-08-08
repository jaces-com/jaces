import Foundation

struct SignalBatch: Codable {
    let batchID: String
    var deviceID: String
    let createdAt: Date
    var activityEvents: [ActivityEvent]
    let source: String
    var retryCount: Int
    var lastRetryAt: Date?
    var batchMetadata: [String: String]
    
    init(deviceID: String) {
        self.batchID = UUID().uuidString
        self.deviceID = deviceID
        self.createdAt = Date()
        self.activityEvents = []
        self.source = "apple_mac_apps"
        self.retryCount = 0
        self.lastRetryAt = nil
        self.batchMetadata = [:]
    }
    
    var signalCount: Int {
        return activityEvents.count
    }
    
    // Legacy compatibility for signals property
    var signals: [CanonicalSignal] {
        return activityEvents.map { event in
            CanonicalSignal(
                id: event.id,
                timestamp: event.timestamp,
                signalType: event.signalType,
                metadata: event.metadata
            )
        }
    }
    
    enum CodingKeys: String, CodingKey {
        case batchID = "batch_id"
        case deviceID = "device_id"
        case createdAt = "created_at"
        case activityEvents = "activity_events"
        case source
        case retryCount = "retry_count"
        case lastRetryAt = "last_retry_at"
        case batchMetadata = "batch_metadata"
    }
}

// New ActivityEvent struct that matches the expected format
struct ActivityEvent: Codable {
    let id: String
    let timestamp: Date
    let signalType: CanonicalSignal.SignalType
    let metadata: [String: String]
    
    init(from canonicalSignal: CanonicalSignal) {
        self.id = canonicalSignal.id
        self.timestamp = canonicalSignal.timestamp
        self.signalType = canonicalSignal.signalType
        self.metadata = canonicalSignal.metadata
    }
    
    enum CodingKeys: String, CodingKey {
        case id
        case timestamp
        case signalType
        case metadata
    }
}

extension SignalBatch {
    func fileName() -> String {
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd-HH-mm-ss"
        let dateString = formatter.string(from: createdAt)
        return "\(dateString)-\(batchID).json"
    }
}