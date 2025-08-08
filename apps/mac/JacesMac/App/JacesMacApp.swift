import SwiftUI

@main
struct JacesMacApp: App {
    @NSApplicationDelegateAdaptor(JacesMacAppDelegate.self) var appDelegate
    @StateObject private var agentStatusViewModel = AgentStatusViewModel()
    @StateObject private var monitoringManager = MonitoringManager.shared
    
    init() {
        // Check for crash recovery
        if !CrashRecoveryManager.shared.wasCleanShutdown() {
            Logger.shared.warning("Detected unclean shutdown, performing recovery")
            CrashRecoveryManager.shared.performRecovery()
        }
        
        // Load configuration
        ConfigManager.shared.loadConfiguration()
        
        if !ConfigManager.shared.isConfigured() {
            Logger.shared.warning(
                "No valid configuration found. Agent will wait for configuration.")
        }
        
        // Let AppDelegate handle starting monitoring for both GUI and headless modes
        // This ensures consistent initialization and prevents dual starts
    }
    
    var body: some Scene {
        WindowGroup {
            MainView(viewModel: agentStatusViewModel)
                .navigationTitle("JacesMac")
                .environmentObject(monitoringManager)
        }
        .commands {
            // Keep the standard commands
        }
    }
}