import Foundation
import Combine
import AppKit

class ConfigurationViewModel: ObservableObject {
    @Published var serverURL = ""
    @Published var deviceName = ""
    @Published var deviceID = ""
    
    @Published var urlError = ""
    @Published var errorMessage = ""
    @Published var successMessage = ""
    @Published var isTesting = false
    @Published var isSaving = false
    
    private var cancellables = Set<AnyCancellable>()
    
    init() {
        // Validate URL as user types
        $serverURL
            .debounce(for: .milliseconds(300), scheduler: RunLoop.main)
            .sink { [weak self] url in
                self?.validateURL(url)
            }
            .store(in: &cancellables)
    }
    
    var isValid: Bool {
        !serverURL.isEmpty && urlError.isEmpty && !deviceName.isEmpty
    }
    
    func loadConfiguration() {
        let config = ConfigManager.shared.configuration
        
        serverURL = config.serverURL
        deviceName = config.deviceName
        deviceID = config.deviceID.isEmpty ? generateDeviceID() : config.deviceID
    }
    
    func save() {
        guard isValid else { return }
        
        isSaving = true
        errorMessage = ""
        successMessage = ""
        
        let config = Configuration(
            serverURL: serverURL,
            deviceName: deviceName,
            deviceID: deviceID,
            deviceToken: nil, // Will be set during device registration
            syncInterval: Configuration.defaultConfiguration.syncInterval,
            batchSize: Configuration.defaultConfiguration.batchSize,
            maxRetries: Configuration.defaultConfiguration.maxRetries,
            connectionID: nil,
            connectionSchedule: nil,
            lastConnectionSync: nil
        )
        
        do {
            try ConfigManager.shared.saveConfiguration(config)
            successMessage = "Configuration saved successfully"
            
            // Register device after saving configuration
            ConfigManager.shared.registerDevice { result in
                DispatchQueue.main.async {
                    switch result {
                    case .success(let token):
                        self.successMessage = "Configuration saved and device registered successfully"
                        Logger.shared.info("Device registered with token: \(token)")
                    case .failure(let error):
                        // Don't overwrite success message, but log the error
                        Logger.shared.error("Failed to register device: \(error)")
                    }
                    self.isSaving = false
                }
            }
        } catch {
            errorMessage = "Failed to save configuration: \(error.localizedDescription)"
            isSaving = false
        }
    }
    
    func testConnection() {
        guard !serverURL.isEmpty else { return }
        
        isTesting = true
        errorMessage = ""
        successMessage = ""
        
        var urlString = serverURL
        if !urlString.contains("://") {
            urlString = "https://\(urlString)"
        }
        
        guard let url = URL(string: urlString) else {
            errorMessage = "Invalid URL format"
            isTesting = false
            return
        }
        
        // Test connection - try health endpoint first, then try api endpoint
        var request = URLRequest(url: url.appendingPathComponent("health"))
        request.httpMethod = "GET"
        request.timeoutInterval = 10
        
        URLSession.shared.dataTask(with: request) { [weak self] data, response, error in
            if let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 200 {
                DispatchQueue.main.async {
                    self?.isTesting = false
                    self?.successMessage = "Connection successful!"
                }
            } else {
                // Try API endpoint as fallback
                var apiRequest = URLRequest(url: url.appendingPathComponent("api/health"))
                apiRequest.httpMethod = "GET"
                apiRequest.timeoutInterval = 10
                
                URLSession.shared.dataTask(with: apiRequest) { [weak self] data, response, error in
                    DispatchQueue.main.async {
                        self?.isTesting = false
                        
                        if let error = error {
                            self?.errorMessage = "Connection failed: \(error.localizedDescription)"
                        } else if let httpResponse = response as? HTTPURLResponse {
                            if (200...299).contains(httpResponse.statusCode) {
                                self?.successMessage = "Connection successful!"
                            } else {
                                self?.errorMessage = "Server returned status code: \(httpResponse.statusCode)"
                            }
                        }
                    }
                }.resume()
            }
        }.resume()
    }
    
    private func validateURL(_ url: String) {
        if url.isEmpty {
            urlError = ""
            return
        }
        
        var urlString = url
        if !urlString.contains("://") {
            urlString = "https://\(urlString)"
        }
        
        if URL(string: urlString) == nil {
            urlError = "Invalid URL format"
        } else {
            urlError = ""
        }
    }
    
    private func generateDeviceID() -> String {
        // Try to get hardware UUID
        let process = Process()
        process.launchPath = "/usr/sbin/ioreg"
        process.arguments = ["-d2", "-c", "IOPlatformExpertDevice"]
        
        let pipe = Pipe()
        process.standardOutput = pipe
        
        do {
            try process.run()
            process.waitUntilExit()
            
            let data = pipe.fileHandleForReading.readDataToEndOfFile()
            if let output = String(data: data, encoding: .utf8),
               let uuidRange = output.range(of: "IOPlatformUUID\" = \""),
               let endRange = output.range(of: "\"", range: uuidRange.upperBound..<output.endIndex) {
                let uuid = String(output[uuidRange.upperBound..<endRange.lowerBound])
                return uuid
            }
        } catch {
            print("Failed to get hardware UUID: \(error)")
        }
        
        // Fallback to random UUID
        return UUID().uuidString
    }
}