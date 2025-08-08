import Foundation

// Signal data model (renamed from Connection)
struct Connection: Codable {
    let id: String
    let signalName: String
    let unit: String?
    let computation: Computation?
    let sourceName: String
    let displayName: String
    let status: String
    let displayStatus: String?
    let syncSchedule: String
    let fidelityScore: Double?
    let insiderTip: String?
    let lastSync: Date?
    let nextSync: Date?
    let createdAt: Date
    let updatedAt: Date?
    let isSyncing: Bool?
    let errorMessage: String?
    
    enum CodingKeys: String, CodingKey {
        case id
        case signalName = "signal_name"
        case unit
        case computation
        case sourceName = "source_name"
        case displayName = "display_name"
        case status
        case displayStatus = "display_status"
        case syncSchedule = "sync_schedule"
        case fidelityScore = "fidelity_score"
        case insiderTip = "insider_tip"
        case lastSync = "last_sync"
        case nextSync = "next_sync"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
        case isSyncing = "is_syncing"
        case errorMessage = "error_message"
    }
}

// Computation configuration
struct Computation: Codable {
    let algorithm: String
    let costFunction: String?
    let distanceMetric: String?
    let valueType: String
    
    enum CodingKeys: String, CodingKey {
        case algorithm
        case costFunction = "cost_function"
        case distanceMetric = "distance_metric"
        case valueType = "value_type"
    }
}

class ConnectionManager {
    static let shared = ConnectionManager()
    
    private let session: URLSession
    private var currentConnection: Connection?
    private var connectionTimer: Timer?
    
    // Callbacks for connection updates
    var onConnectionUpdated: ((Connection) -> Void)?
    var onScheduleChanged: ((String) -> Void)?
    
    private init() {
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 30
        self.session = URLSession(configuration: config)
    }
    
    func startMonitoring() {
        Logger.shared.info("ConnectionManager: Starting monitoring")
        
        // Fetch connection immediately
        Logger.shared.info("ConnectionManager: Fetching connection immediately on start")
        fetchConnection()
        
        // Set up timer to check every 5 minutes
        Logger.shared.info("ConnectionManager: Setting up 5-minute refresh timer")
        connectionTimer = Timer.scheduledTimer(withTimeInterval: 300, repeats: true) { [weak self] _ in
            Logger.shared.info("ConnectionManager: Timer fired, refreshing connection")
            self?.fetchConnection()
        }
    }
    
    func stopMonitoring() {
        connectionTimer?.invalidate()
        connectionTimer = nil
    }
    
    func fetchConnection(completion: ((Result<Connection, Error>) -> Void)? = nil) {
        Logger.shared.info("ConnectionManager: fetchConnection() called")
        
        guard let config = ConfigManager.shared.currentConfig,
              let deviceToken = config.deviceToken else {
            let error = NSError(domain: "ConnectionManager", code: -2, 
                              userInfo: [NSLocalizedDescriptionKey: "No device token available"])
            Logger.shared.warning("ConnectionManager: No device token available for fetching connection")
            completion?(.failure(error))
            return
        }
        
        Logger.shared.info("ConnectionManager: Device token available, device ID: \(config.deviceID)")
        
        // Build URL with device ID query parameter
        guard var urlComponents = URLComponents(string: config.normalizedServerURL) else {
            let error = NSError(domain: "ConnectionManager", code: -3, 
                              userInfo: [NSLocalizedDescriptionKey: "Invalid server URL"])
            Logger.shared.error("ConnectionManager: Invalid server URL for connection fetch")
            completion?(.failure(error))
            return
        }
        
        urlComponents.path = "/api/signals"
        // No need for device_id query param - the device token in header handles authentication
        
        guard let url = urlComponents.url else {
            let error = NSError(domain: "ConnectionManager", code: -4, 
                              userInfo: [NSLocalizedDescriptionKey: "Failed to build connection URL"])
            Logger.shared.error("ConnectionManager: Failed to build connection URL")
            completion?(.failure(error))
            return
        }
        
        Logger.shared.info("ConnectionManager: Fetching signals from: \(url.absoluteString)")
        
        var request = URLRequest(url: url)
        request.setValue(deviceToken, forHTTPHeaderField: "X-Device-Token")
        
        let task = session.dataTask(with: request) { [weak self] data, response, error in
            if let error = error {
                Logger.shared.error("Failed to fetch signals: \(error)")
                completion?(.failure(error))
                return
            }
            
            guard let httpResponse = response as? HTTPURLResponse else {
                let error = NSError(domain: "ConnectionManager", code: -5, 
                                  userInfo: [NSLocalizedDescriptionKey: "Invalid response"])
                completion?(.failure(error))
                return
            }
            
            Logger.shared.info("Connection fetch response status: \(httpResponse.statusCode)")
            
            guard httpResponse.statusCode == 200 else {
                let error = NSError(domain: "ConnectionManager", code: httpResponse.statusCode, 
                                  userInfo: [NSLocalizedDescriptionKey: "Server returned status \(httpResponse.statusCode)"])
                completion?(.failure(error))
                return
            }
            
            guard let data = data else {
                let error = NSError(domain: "ConnectionManager", code: -6, 
                                  userInfo: [NSLocalizedDescriptionKey: "No data received"])
                Logger.shared.error("No data received from signals endpoint")
                completion?(.failure(error))
                return
            }
            
            do {
                let decoder = JSONDecoder()
                decoder.dateDecodingStrategy = .iso8601
                let connections = try decoder.decode([Connection].self, from: data)
                
                Logger.shared.info("Received \(connections.count) signals")
                
                // Find the first active signal for mac apps
                Logger.shared.info("ConnectionManager: Looking for apple_mac_apps signal...")
                if let macConnection = connections.first(where: { 
                    $0.signalName == "apple_mac_apps" && $0.sourceName == "mac" && $0.status == "active" 
                }) {
                    Logger.shared.info("ConnectionManager: Found active apple_mac_apps signal")
                    Logger.shared.info("  Connection ID: \(macConnection.id)")
                    Logger.shared.info("  Sync schedule: \(macConnection.syncSchedule)")
                    Logger.shared.info("  Last sync: \(macConnection.lastSync?.description ?? "never")")
                    self?.handleConnectionUpdate(macConnection)
                    completion?(.success(macConnection))
                } else {
                    Logger.shared.warning("ConnectionManager: No active apple_mac_apps signal found")
                    Logger.shared.warning("  Total signals: \(connections.count)")
                    for conn in connections {
                        Logger.shared.warning("  - \(conn.signalName) (\(conn.sourceName)): \(conn.status)")
                    }
                    let error = NSError(domain: "ConnectionManager", code: -7, 
                                      userInfo: [NSLocalizedDescriptionKey: "No active apple_mac_apps signal found"])
                    completion?(.failure(error))
                }
            } catch {
                Logger.shared.error("Failed to decode signals: \(error)")
                completion?(.failure(error))
            }
        }
        
        task.resume()
    }
    
    func resyncConnection(completion: @escaping (Result<Connection, Error>) -> Void) {
        // Use the completion-based fetchConnection
        fetchConnection(completion: completion)
    }
    
    func updateLastSyncTime() {
        guard let connection = currentConnection,
              let config = ConfigManager.shared.currentConfig,
              let deviceToken = config.deviceToken else {
            return
        }
        
        guard let url = URL(string: config.normalizedServerURL)?
            .appendingPathComponent("api/signals")
            .appendingPathComponent(connection.id) else {
            return
        }
        
        var request = URLRequest(url: url)
        request.httpMethod = "PATCH"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue(deviceToken, forHTTPHeaderField: "X-Device-Token")
        
        let body = ["last_successful_ingestion_at": ISO8601DateFormatter().string(from: Date())]
        
        do {
            request.httpBody = try JSONSerialization.data(withJSONObject: body)
        } catch {
            Logger.shared.error("Failed to encode last sync update: \(error)")
            return
        }
        
        let task = session.dataTask(with: request) { _, response, error in
            if let error = error {
                Logger.shared.error("Failed to update last sync time: \(error)")
            } else if let httpResponse = response as? HTTPURLResponse,
                      httpResponse.statusCode == 200 {
                Logger.shared.info("Successfully updated last sync time")
            }
        }
        
        task.resume()
    }
    
    private func handleConnectionUpdate(_ connection: Connection) {
        Logger.shared.info("=== ConnectionManager: handleConnectionUpdate ===")
        
        let previousSchedule = currentConnection?.syncSchedule
        let isFirstConnection = currentConnection == nil
        currentConnection = connection
        
        Logger.shared.info("ConnectionManager: Connection update details:")
        Logger.shared.info("  Display name: \(connection.displayName)")
        Logger.shared.info("  Current schedule: \(connection.syncSchedule)")
        Logger.shared.info("  Previous schedule: \(previousSchedule ?? "none")")
        Logger.shared.info("  Is first connection: \(isFirstConnection)")
        
        // Notify about connection update
        Logger.shared.info("ConnectionManager: Triggering onConnectionUpdated callback")
        Logger.shared.info("  Callback is set: \(onConnectionUpdated != nil)")
        DispatchQueue.main.async {
            self.onConnectionUpdated?(connection)
        }
        
        // Check if schedule changed OR if this is the first connection
        if isFirstConnection || previousSchedule != connection.syncSchedule {
            Logger.shared.info("ConnectionManager: Sync schedule \(isFirstConnection ? "initialized" : "changed")")
            Logger.shared.info("  From: \(previousSchedule ?? "none")")
            Logger.shared.info("  To: \(connection.syncSchedule)")
            Logger.shared.info("  Triggering onScheduleChanged callback")
            Logger.shared.info("  Callback is set: \(self.onScheduleChanged != nil)")
            
            DispatchQueue.main.async {
                Logger.shared.info("ConnectionManager: Executing onScheduleChanged callback on main thread")
                self.onScheduleChanged?(connection.syncSchedule)
            }
        } else {
            Logger.shared.info("ConnectionManager: Schedule unchanged, not triggering callback")
        }
        
        Logger.shared.info("=== ConnectionManager: handleConnectionUpdate complete ===")
    }
    
    var syncSchedule: String? {
        return currentConnection?.syncSchedule
    }
    
    var connection: Connection? {
        return currentConnection
    }
}