import Foundation
#if canImport(Network)
import Network
#endif

class NetworkChecker {
    static let shared = NetworkChecker()
    
    #if canImport(Network)
    private let monitor = NWPathMonitor()
    private let queue = DispatchQueue(label: "com.memory.agent.network")
    #endif
    
    private(set) var isConnected = true // Default to true if Network framework unavailable
    private(set) var isExpensive = false
    private(set) var connectionType: ConnectionType = .unknown
    
    enum ConnectionType {
        case wifi
        case cellular
        case wired
        case unknown
    }
    
    private init() {
        // Don't start with any assumptions
        startMonitoring()
        
        // Give the monitor a moment to get initial status
        // In production, we'd use a completion handler
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) { [weak self] in
            if self?.connectionType == .unknown {
                // If still unknown after initial check, assume connected
                self?.isConnected = true
                Logger.shared.debug("NetworkChecker: No initial status, assuming connected")
            }
        }
    }
    
    private func startMonitoring() {
        #if canImport(Network)
        monitor.pathUpdateHandler = { [weak self] path in
            self?.isConnected = path.status == .satisfied
            self?.isExpensive = path.isExpensive
            
            if path.usesInterfaceType(.wifi) {
                self?.connectionType = .wifi
            } else if path.usesInterfaceType(.cellular) {
                self?.connectionType = .cellular
            } else if path.usesInterfaceType(.wiredEthernet) {
                self?.connectionType = .wired
            } else {
                self?.connectionType = .unknown
            }
            
            Logger.shared.debug("Network status changed - Connected: \(self?.isConnected ?? false), Type: \(self?.connectionType ?? .unknown)")
        }
        
        monitor.start(queue: queue)
        #else
        // Network framework not available, assume always connected
        Logger.shared.debug("Network framework not available, assuming connected")
        #endif
    }
    
    func canUpload() -> Bool {
        // TEMPORARY: Force uploads for testing
        Logger.shared.debug("FORCING UPLOAD FOR TESTING - Connected: \(isConnected), Expensive: \(isExpensive), Type: \(connectionType)")
        return true
        
        // Logger.shared.debug("canUpload() called - Connected: \(isConnected), Expensive: \(isExpensive), Type: \(connectionType)")
        // 
        // // Don't upload on expensive (cellular) connections unless configured
        // if isExpensive {
        //     // In the future, we could add a config option for cellular uploads
        //     // let config = ConfigManager.shared.configuration
        //     Logger.shared.debug("Network is expensive (cellular), skipping upload")
        //     return false
        // }
        // 
        // let result = isConnected
        // Logger.shared.debug("canUpload() returning: \(result)")
        // return result
    }
}