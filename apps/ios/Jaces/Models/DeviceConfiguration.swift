//
//  DeviceConfiguration.swift
//  Jaces
//
//  Configuration model for device token and API settings
//

import Foundation
import UIKit

struct DeviceConfiguration: Codable {
    let deviceId: String
    var deviceToken: String // Device token provided by user from web app
    var apiEndpoint: String
    let deviceName: String
    var configuredDate: Date?
    
    private enum CodingKeys: String, CodingKey {
        case deviceId = "device_id"
        case deviceToken = "device_token"
        case apiEndpoint = "api_endpoint"
        case deviceName = "device_name"
        case configuredDate = "configured_date"
    }
    
    init(deviceId: String = UUID().uuidString,
         deviceToken: String = "",
         apiEndpoint: String = "http://localhost:3000",
         deviceName: String = UIDevice.current.name,
         configuredDate: Date? = nil) {
        self.deviceId = deviceId
        self.deviceToken = deviceToken
        self.apiEndpoint = apiEndpoint
        self.deviceName = deviceName
        self.configuredDate = configuredDate
    }
    
    // Helper to check if device is configured
    var isConfigured: Bool {
        return !deviceToken.isEmpty && !apiEndpoint.isEmpty
    }
    
    // Helper to get the full ingest URL
    var ingestURL: URL? {
        guard !apiEndpoint.isEmpty else { return nil }
        let cleanEndpoint = apiEndpoint.trimmingCharacters(in: .whitespacesAndNewlines)
        
        // Handle cases where user might have included /api/ingest already
        if cleanEndpoint.hasSuffix("/api/ingest") {
            return URL(string: cleanEndpoint)
        } else if cleanEndpoint.hasSuffix("/") {
            return URL(string: "\(cleanEndpoint)api/ingest")
        } else {
            return URL(string: "\(cleanEndpoint)/api/ingest")
        }
    }
}