import Foundation

enum ConfigError: LocalizedError {
    case notConfigured
    case invalidURL
    case registrationFailed
    
    var errorDescription: String? {
        switch self {
        case .notConfigured:
            return "Configuration not set up"
        case .invalidURL:
            return "Invalid server URL"
        case .registrationFailed:
            return "Failed to register device with server"
        }
    }
}

class ConfigManager {
    static let shared = ConfigManager()
    
    private let configDirURL: URL
    private let configFileURL: URL
    internal var currentConfig: Configuration?
    
    private init() {
        let homeDir = FileManager.default.homeDirectoryForCurrentUser
        self.configDirURL = homeDir.appendingPathComponent(Constants.configDirectory)
        self.configFileURL = configDirURL.appendingPathComponent("config.json")
        
        createConfigDirectoryIfNeeded()
    }
    
    var configuration: Configuration {
        if let config = currentConfig {
            return config
        }
        
        loadConfiguration()
        return currentConfig ?? Configuration.defaultConfiguration
    }
    
    func loadConfiguration() {
        Logger.shared.info("Loading configuration from \(configFileURL.path)")
        
        guard FileManager.default.fileExists(atPath: configFileURL.path) else {
            Logger.shared.warning("Configuration file not found at \(configFileURL.path)")
            currentConfig = nil
            return
        }
        
        do {
            let data = try Data(contentsOf: configFileURL)
            let config = try JSONDecoder().decode(Configuration.self, from: data)
            currentConfig = config
            Logger.shared.info("Configuration loaded successfully")
        } catch {
            Logger.shared.error("Failed to load configuration: \(error)")
            currentConfig = nil
        }
    }
    
    func saveConfiguration(_ config: Configuration) throws {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        let data = try encoder.encode(config)
        
        try data.write(to: configFileURL)
        currentConfig = config
        Logger.shared.info("Configuration saved successfully")
    }
    
    func isConfigured() -> Bool {
        return currentConfig != nil && !configuration.serverURL.isEmpty
    }
    
    func needsDeviceRegistration() -> Bool {
        return isConfigured() && configuration.deviceToken == nil
    }
    
    func registerDevice(completion: @escaping (Result<String, Error>) -> Void) {
        guard isConfigured() else {
            completion(.failure(ConfigError.notConfigured))
            return
        }
        
        let config = configuration
        guard let url = URL(string: config.normalizedServerURL)?.appendingPathComponent("api/sources/activate") else {
            completion(.failure(ConfigError.invalidURL))
            return
        }
        
        // Generate a new device token
        let deviceToken = UUID().uuidString
        
        // Prepare request body
        let requestBody: [String: Any] = [
            "device_id": config.deviceID,
            "device_token": deviceToken,
            "device_name": config.deviceName,
            "device_type": "mac",
            "user_id": "00000000-0000-0000-0000-000000000001", // Default user for now
            "source_names": ["mac"]
        ]
        
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        
        do {
            request.httpBody = try JSONSerialization.data(withJSONObject: requestBody)
        } catch {
            completion(.failure(error))
            return
        }
        
        let task = URLSession.shared.dataTask(with: request) { [weak self] data, response, error in
            if let error = error {
                Logger.shared.error("Device registration failed: \(error)")
                completion(.failure(error))
                return
            }
            
            guard let httpResponse = response as? HTTPURLResponse,
                  (200...299).contains(httpResponse.statusCode) else {
                Logger.shared.error("Device registration failed with status: \((response as? HTTPURLResponse)?.statusCode ?? -1)")
                completion(.failure(ConfigError.registrationFailed))
                return
            }
            
            // Save the device token to configuration
            do {
                let updatedConfig = config
                let newConfig = Configuration(
                    serverURL: updatedConfig.serverURL,
                    deviceName: updatedConfig.deviceName,
                    deviceID: updatedConfig.deviceID,
                    deviceToken: deviceToken,
                    syncInterval: updatedConfig.syncInterval,
                    batchSize: updatedConfig.batchSize,
                    maxRetries: updatedConfig.maxRetries,
                    connectionID: updatedConfig.connectionID,
                    connectionSchedule: updatedConfig.connectionSchedule,
                    lastConnectionSync: updatedConfig.lastConnectionSync
                )
                try self?.saveConfiguration(newConfig)
                Logger.shared.info("Device registered successfully with token: \(deviceToken)")
                completion(.success(deviceToken))
            } catch {
                completion(.failure(error))
            }
        }
        
        task.resume()
    }
    
    func getConfigFileModificationDate() -> Date? {
        do {
            let attributes = try FileManager.default.attributesOfItem(atPath: configFileURL.path)
            return attributes[.modificationDate] as? Date
        } catch {
            return nil
        }
    }
    
    private func createConfigDirectoryIfNeeded() {
        let fileManager = FileManager.default
        
        if !fileManager.fileExists(atPath: configDirURL.path) {
            do {
                try fileManager.createDirectory(at: configDirURL, withIntermediateDirectories: true, attributes: nil)
                Logger.shared.info("Created configuration directory at \(configDirURL.path)")
            } catch {
                Logger.shared.error("Failed to create configuration directory: \(error)")
            }
        }
    }
}