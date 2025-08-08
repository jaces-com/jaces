//
//  DeviceManager.swift
//  Jaces
//
//  Manages device configuration and pairing state
//

import Foundation
import Combine

class DeviceManager: ObservableObject {
    static let shared = DeviceManager()
    
    @Published var configuration: DeviceConfiguration
    @Published var isConfigured: Bool = false
    @Published var isVerifying: Bool = false
    @Published var lastError: String?
    
    private let userDefaults = UserDefaults.standard
    private let configKey = "com.jaces.deviceConfiguration"
    
    private var cancellables = Set<AnyCancellable>()
    
    private init() {
        // Load saved configuration or create new one
        if let savedData = userDefaults.data(forKey: configKey),
           let savedConfig = try? JSONDecoder().decode(DeviceConfiguration.self, from: savedData) {
            self.configuration = savedConfig
            self.isConfigured = savedConfig.isConfigured
        } else {
            self.configuration = DeviceConfiguration()
            self.isConfigured = false
        }
        
        // Observe configuration changes to save automatically
        $configuration
            .debounce(for: .milliseconds(500), scheduler: RunLoop.main)
            .sink { [weak self] config in
                self?.saveConfiguration(config)
                self?.isConfigured = config.isConfigured
            }
            .store(in: &cancellables)
    }
    
    // MARK: - Configuration Management
    
    func updateConfiguration(apiEndpoint: String, deviceToken: String) {
        configuration.apiEndpoint = apiEndpoint.trimmingCharacters(in: .whitespacesAndNewlines)
        configuration.deviceToken = deviceToken.trimmingCharacters(in: .whitespacesAndNewlines)
        configuration.configuredDate = Date()
    }
    
    func updateEndpoint(_ newEndpoint: String) async -> Bool {
        let trimmedEndpoint = newEndpoint.trimmingCharacters(in: .whitespacesAndNewlines)
        
        // Validate the endpoint format
        guard validateEndpoint(trimmedEndpoint) else {
            await MainActor.run {
                self.lastError = "Invalid endpoint URL format"
            }
            return false
        }
        
        // Test the connection to the new endpoint
        let isReachable = await NetworkManager.shared.testConnection(endpoint: trimmedEndpoint)
        if !isReachable {
            await MainActor.run {
                self.lastError = "Cannot reach the new endpoint"
            }
            return false
        }
        
        // Update the configuration
        await MainActor.run {
            self.configuration.apiEndpoint = trimmedEndpoint
            self.lastError = nil
            
            // Force save the configuration
            self.saveConfiguration(self.configuration)
        }
        
        print("✅ Endpoint updated successfully to: \(trimmedEndpoint)")
        return true
    }
    
    private func saveConfiguration(_ config: DeviceConfiguration) {
        if let encoded = try? JSONEncoder().encode(config) {
            userDefaults.set(encoded, forKey: configKey)
        }
    }
    
    func clearConfiguration() {
        configuration = DeviceConfiguration()
        userDefaults.removeObject(forKey: configKey)
        isConfigured = false
        lastError = nil
    }
    
    // MARK: - Connection Verification
    
    func verifyConfiguration() async -> Bool {
        await MainActor.run {
            isVerifying = true
            lastError = nil
        }
        
        defer { 
            Task { @MainActor in
                self.isVerifying = false
            }
        }
        
        // Validate configuration
        guard !configuration.apiEndpoint.isEmpty else {
            await MainActor.run {
                self.lastError = "Please enter an API endpoint URL"
            }
            return false
        }
        
        guard !configuration.deviceToken.isEmpty else {
            await MainActor.run {
                self.lastError = "Please enter a device token"
            }
            return false
        }
        
        guard let baseURL = URL(string: configuration.apiEndpoint) else {
            await MainActor.run {
                self.lastError = "Invalid API endpoint URL format"
            }
            return false
        }
        
        // Validate token format (should start with dev_tk_)
        guard configuration.deviceToken.hasPrefix("dev_tk_") else {
            await MainActor.run {
                self.lastError = "Invalid device token format. Token should start with 'dev_tk_'"
            }
            return false
        }
        
        // Verify token with server
        let verifyURL = baseURL.appendingPathComponent("/api/device/verify")
        let success = await NetworkManager.shared.verifyDeviceToken(
            endpoint: verifyURL,
            deviceToken: configuration.deviceToken,
            deviceInfo: [
                "deviceName": configuration.deviceName,
                "deviceId": configuration.deviceId,
                "platform": "iOS",
                "osVersion": UIDevice.current.systemVersion,
                "model": UIDevice.current.model
            ]
        )
        
        if !success {
            await MainActor.run {
                self.lastError = NetworkManager.shared.lastError?.errorDescription ?? "Failed to verify device token. Please check the token and try again."
            }
            return false
        }
        
        // Mark as configured
        await MainActor.run {
            self.configuration.configuredDate = Date()
            self.isConfigured = true
            self.lastError = nil
            
            // Force save the configuration
            self.saveConfiguration(self.configuration)
        }
        
        print("✅ Device configuration verified successfully")
        print("   Endpoint: \(configuration.apiEndpoint)")
        print("   Token: \(configuration.deviceToken.prefix(15))...")
        print("   Is configured: \(self.isConfigured)")
        
        return true
    }
    
    // MARK: - Validation
    
    func validateEndpoint(_ endpoint: String) -> Bool {
        let trimmed = endpoint.trimmingCharacters(in: .whitespacesAndNewlines)
        
        // Basic URL validation
        if trimmed.isEmpty { return false }
        
        // Check if it's a valid URL
        if let url = URL(string: trimmed) {
            // Allow http for local development
            return url.scheme == "http" || url.scheme == "https"
        }
        
        return false
    }
    
    func validateToken(_ token: String) -> Bool {
        let trimmed = token.trimmingCharacters(in: .whitespacesAndNewlines)
        return !trimmed.isEmpty && trimmed.count >= 8 // Minimum token length
    }
    
    // MARK: - Status Helpers
    
    var hasValidConfiguration: Bool {
        return validateEndpoint(configuration.apiEndpoint) && 
               validateToken(configuration.deviceToken)
    }
    
    var statusMessage: String {
        if isConfigured {
            if let configuredDate = configuration.configuredDate {
                let formatter = RelativeDateTimeFormatter()
                formatter.unitsStyle = .abbreviated
                return "Configured \(formatter.localizedString(for: configuredDate, relativeTo: Date()))"
            }
            return "Device configured"
        } else if !configuration.apiEndpoint.isEmpty || !configuration.deviceToken.isEmpty {
            return "Not configured - complete setup"
        } else {
            return "Not configured"
        }
    }
    
    // MARK: - Debug Helpers
    
    func getDebugInfo() -> String {
        var info = "Device Configuration:\n"
        info += "- Device ID: \(configuration.deviceId)\n"
        info += "- Configured: \(isConfigured)\n"
        info += "- Endpoint: \(configuration.apiEndpoint.isEmpty ? "Not set" : configuration.apiEndpoint)\n"
        info += "- Token: \(configuration.deviceToken.isEmpty ? "Not set" : "***\(String(configuration.deviceToken.suffix(4)))")\n"
        
        return info
    }
}