import Foundation

struct CanonicalSignal: Codable {
    let id: String
    let timestamp: Date
    let signalType: SignalType
    let metadata: [String: String]

    init(signalType: SignalType, metadata: [String: String]) {
        self.id = UUID().uuidString
        self.timestamp = Date()
        self.signalType = signalType
        self.metadata = metadata
    }
    
    init(id: String, timestamp: Date, signalType: SignalType, metadata: [String: String]) {
        self.id = id
        self.timestamp = timestamp
        self.signalType = signalType
        self.metadata = metadata
    }

    enum SignalType: String, Codable {
        case appLaunch = "app_launch"
        case appQuit = "app_quit"
        case appFocus = "app_focus"
        case appUnfocus = "app_unfocus"
    }
}
