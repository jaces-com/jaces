import SwiftUI
import AppKit

class JacesMacAppDelegate: NSObject, NSApplicationDelegate {
    func applicationDidFinishLaunching(_ notification: Notification) {
        // Determine run mode based on launch arguments
        let args = ProcessInfo.processInfo.arguments
        
        if args.contains("--headless") || args.contains("-h") {
            runHeadlessMode()
        } else {
            // Default to GUI mode
            runGUIMode()
        }
    }
    
    private func runHeadlessMode() {
        Logger.shared.info("Starting JacesMac in headless mode")
        
        // Hide dock icon
        NSApp.setActivationPolicy(.accessory)
        
        // Check if device registration is needed
        if ConfigManager.shared.needsDeviceRegistration() {
            Logger.shared.info("Device not registered, attempting registration...")
            ConfigManager.shared.registerDevice { result in
                switch result {
                case .success(let token):
                    Logger.shared.info("Device registered successfully with token: \(token)")
                    // Start monitoring after successful registration
                    MonitoringManager.shared.startMonitoring()
                case .failure(let error):
                    Logger.shared.error("Failed to register device: \(error)")
                    // Still start monitoring, will retry on next launch
                    MonitoringManager.shared.startMonitoring()
                }
            }
        } else {
            // Start monitoring immediately if already registered
            MonitoringManager.shared.startMonitoring()
        }
        
        // Set up signal handlers for graceful shutdown
        setupSignalHandlers()
        
        // Log heartbeat every 5 minutes
        Timer.scheduledTimer(withTimeInterval: 300, repeats: true) { _ in
            let stats = QueueManager.shared.getQueueStats()
            Logger.shared.info(
                "JacesMac heartbeat - Queue: \(stats.currentSignals) current, \(stats.pendingSignals) pending"
            )
        }
    }
    
    private func runGUIMode() {
        Logger.shared.info("Starting JacesMac in GUI mode")
        
        // The main window is created by SwiftUI App
        // Just ensure we're visible in dock
        NSApp.setActivationPolicy(.regular)
        
        // Check if device registration is needed (same as headless mode)
        if ConfigManager.shared.needsDeviceRegistration() {
            Logger.shared.info("Device not registered, attempting registration...")
            ConfigManager.shared.registerDevice { result in
                switch result {
                case .success(let token):
                    Logger.shared.info("Device registered successfully with token: \(token)")
                    // Start monitoring after successful registration
                    MonitoringManager.shared.startMonitoring()
                case .failure(let error):
                    Logger.shared.error("Failed to register device: \(error)")
                    // Still start monitoring, will retry on next launch
                    MonitoringManager.shared.startMonitoring()
                }
            }
        } else {
            // Start monitoring immediately if already registered
            Logger.shared.info("Starting MonitoringManager for GUI mode")
            MonitoringManager.shared.startMonitoring()
        }
    }
    
    private func setupSignalHandlers() {
        signal(SIGTERM) { _ in
            Logger.shared.info("Received SIGTERM, shutting down gracefully")
            QueueManager.shared.addSignal(
                CanonicalSignal(
                    signalType: .appQuit,
                    metadata: ["app_name": "JacesMac", "reason": "SIGTERM"]
                ))
            CrashRecoveryManager.shared.createRecoveryCheckpoint()
            exit(0)
        }
        
        signal(SIGINT) { _ in
            Logger.shared.info("Received SIGINT, shutting down gracefully")
            QueueManager.shared.addSignal(
                CanonicalSignal(
                    signalType: .appQuit,
                    metadata: ["app_name": "JacesMac", "reason": "SIGINT"]
                ))
            CrashRecoveryManager.shared.createRecoveryCheckpoint()
            exit(0)
        }
    }
    
    func applicationWillTerminate(_ notification: Notification) {
        Logger.shared.info("JacesMac terminating")
        QueueManager.shared.addSignal(
            CanonicalSignal(
                signalType: .appQuit,
                metadata: ["app_name": "JacesMac", "reason": "normal_quit"]
            ))
        CrashRecoveryManager.shared.createRecoveryCheckpoint()
    }
}