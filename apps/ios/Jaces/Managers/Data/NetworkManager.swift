//
//  NetworkManager.swift
//  Jaces
//
//  Handles all network communication with retry logic
//

import Foundation
import Combine

enum NetworkError: LocalizedError {
    case invalidURL
    case invalidToken
    case serverError(Int)
    case timeout
    case noConnection
    case decodingError
    case unknown(Error)
    
    var errorDescription: String? {
        switch self {
        case .invalidURL:
            return "Invalid API endpoint URL"
        case .invalidToken:
            return "Invalid device token (E002)"
        case .serverError(let code):
            return "Server error: \(code) (E003)"
        case .timeout:
            return "Network timeout (E001)"
        case .noConnection:
            return "No internet connection"
        case .decodingError:
            return "Failed to decode response"
        case .unknown(let error):
            return "Unknown error: \(error.localizedDescription)"
        }
    }
    
    var errorCode: String {
        switch self {
        case .timeout: return "E001"
        case .invalidToken: return "E002"
        case .serverError: return "E003"
        default: return "E000"
        }
    }
}

class NetworkManager: ObservableObject {
    static let shared = NetworkManager()
    
    private let session: URLSession
    private let timeout: TimeInterval = 30.0
    private var cancellables = Set<AnyCancellable>()
    
    @Published var isConnected: Bool = true
    @Published var lastError: NetworkError?
    
    private init() {
        let configuration = URLSessionConfiguration.default
        configuration.timeoutIntervalForRequest = timeout
        configuration.timeoutIntervalForResource = timeout
        configuration.waitsForConnectivity = true
        configuration.allowsCellularAccess = true
        
        self.session = URLSession(configuration: configuration)
    }
    
    // MARK: - Data Upload
    
    func uploadData<T: Encodable>(_ data: T, deviceToken: String, endpoint: URL) async throws -> UploadResponse {
        var request = URLRequest(url: endpoint)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue(deviceToken, forHTTPHeaderField: "X-Device-Token")
        
        // Encode data
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        request.httpBody = try encoder.encode(data)
        
        do {
            let (data, response) = try await session.data(for: request)
            
            guard let httpResponse = response as? HTTPURLResponse else {
                throw NetworkError.unknown(NSError(domain: "Invalid response", code: 0))
            }
            
            switch httpResponse.statusCode {
            case 200...299:
                return try JSONDecoder().decode(UploadResponse.self, from: data)
            case 401:
                throw NetworkError.invalidToken
            case 500...599:
                throw NetworkError.serverError(httpResponse.statusCode)
            default:
                throw NetworkError.unknown(NSError(domain: "HTTP \(httpResponse.statusCode)", code: httpResponse.statusCode))
            }
        } catch {
            if let urlError = error as? URLError {
                switch urlError.code {
                case .timedOut:
                    throw NetworkError.timeout
                case .notConnectedToInternet, .networkConnectionLost:
                    throw NetworkError.noConnection
                default:
                    throw NetworkError.unknown(error)
                }
            }
            
            if error is NetworkError {
                throw error
            }
            
            throw NetworkError.unknown(error)
        }
    }
    
    // MARK: - Device Verification
    
    func verifyDeviceToken(endpoint: URL, deviceToken: String, deviceInfo: [String: Any]) async -> Bool {
        var request = URLRequest(url: endpoint)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue(deviceToken, forHTTPHeaderField: "X-Device-Token")
        request.timeoutInterval = 10.0
        
        do {
            // Encode device info
            request.httpBody = try JSONSerialization.data(withJSONObject: deviceInfo)
            
            let (data, response) = try await session.data(for: request)
            
            guard let httpResponse = response as? HTTPURLResponse else {
                lastError = .unknown(NSError(domain: "Invalid response", code: 0))
                return false
            }
            
            switch httpResponse.statusCode {
            case 200...299:
                // Parse response to confirm success
                if let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                   let success = json["success"] as? Bool {
                    return success
                }
                return true
            case 401:
                lastError = .invalidToken
                return false
            case 404:
                // Token not found in database
                lastError = .unknown(NSError(domain: "Device token not found. Please generate a new token in the web app.", code: 404))
                return false
            default:
                lastError = .serverError(httpResponse.statusCode)
                return false
            }
        } catch {
            if let urlError = error as? URLError {
                switch urlError.code {
                case .timedOut:
                    lastError = .timeout
                case .notConnectedToInternet, .networkConnectionLost:
                    lastError = .noConnection
                default:
                    lastError = .unknown(error)
                }
            } else {
                lastError = .unknown(error)
            }
            return false
        }
    }
    
    // MARK: - Connection Test
    
    func testConnection(endpoint: String) async -> Bool {
        guard let url = URL(string: endpoint) else { return false }
        
        var request = URLRequest(url: url)
        request.httpMethod = "HEAD"
        request.timeoutInterval = 5.0
        
        do {
            let (_, response) = try await session.data(for: request)
            if let httpResponse = response as? HTTPURLResponse {
                return (200...499).contains(httpResponse.statusCode)
            }
        } catch {
            // Log error but don't throw
            print("Connection test failed: \(error)")
        }
        
        return false
    }
}

// MARK: - Request/Response Models

struct UploadResponse: Codable {
    let success: Bool
    let taskId: String
    let pipelineActivityId: String
    let dataSizeBytes: Int
    let dataSize: String
    let source: String
    let message: String
    let streamKey: String
    
    private enum CodingKeys: String, CodingKey {
        case success
        case taskId = "task_id"
        case pipelineActivityId = "pipeline_activity_id"
        case dataSizeBytes = "data_size_bytes"
        case dataSize = "data_size"
        case source
        case message
        case streamKey = "stream_key"
    }
}

struct ErrorResponse: Codable {
    let error: String
    let details: String?
}