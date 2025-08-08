import Foundation
import Combine
import AppKit

class AgentStatusViewModel: ObservableObject {
    @Published var isAgentRunning = false
    @Published var queueStats = QueueStats()
    @Published var lastSuccessfulUpload: Date?
    @Published var lastError: String?
    
    private var statusTimer: Timer?
    private let statusUpdateInterval: TimeInterval = 5.0  // Update more frequently for real-time feel
    
    var lastUploadTime: String {
        if let date = lastSuccessfulUpload {
            let formatter = RelativeDateTimeFormatter()
            return formatter.localizedString(for: date, relativeTo: Date())
        }
        return "Never"
    }
    
    func startMonitoring() {
        refreshStatus()
        
        statusTimer = Timer.scheduledTimer(withTimeInterval: statusUpdateInterval, repeats: true) { _ in
            self.refreshStatus()
        }
    }
    
    func stopMonitoring() {
        statusTimer?.invalidate()
        statusTimer = nil
    }
    
    func refreshStatus() {
        checkAgentStatus()
        loadQueueStats()
    }
    
    private func checkAgentStatus() {
        // Check if monitoring is active
        DispatchQueue.main.async {
            self.isAgentRunning = MonitoringManager.shared.isMonitoring
        }
    }
    
    private func loadQueueStats() {
        // Always fetch real-time stats directly from QueueManager
        DispatchQueue.global(qos: .userInitiated).async {
            let stats = QueueManager.shared.getQueueStats()
            
            DispatchQueue.main.async {
                self.queueStats = stats
                self.lastSuccessfulUpload = stats.lastSuccessfulUpload
                self.lastError = stats.lastError
            }
        }
    }
}

