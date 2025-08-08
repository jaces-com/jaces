import Foundation
import AppKit

protocol ActivityMonitorDelegate: AnyObject {
    func activityMonitor(_ monitor: ActivityMonitor, didCollectSignal signal: CanonicalSignal)
}

class ActivityMonitor {
    weak var delegate: ActivityMonitorDelegate?
    
    private var frontmostApp: NSRunningApplication?
    private var activeAppTimer: Timer?
    
    init() {
        Logger.shared.info("Initializing ActivityMonitor...")
        
        // Log current frontmost app on init
        if let frontmost = NSWorkspace.shared.frontmostApplication {
            Logger.shared.info("Current frontmost app: \(frontmost.localizedName ?? "Unknown") (PID: \(frontmost.processIdentifier))")
            frontmostApp = frontmost
        }
        
        setupNotifications()
        startActiveAppMonitoring()
        Logger.shared.info("ActivityMonitor initialized successfully")
    }
    
    deinit {
        activeAppTimer?.invalidate()
    }
    
    private func setupNotifications() {
        let workspace = NSWorkspace.shared
        let center = workspace.notificationCenter
        
        // App launch
        center.addObserver(
            self,
            selector: #selector(appLaunched(_:)),
            name: NSWorkspace.didLaunchApplicationNotification,
            object: nil
        )
        
        // App quit
        center.addObserver(
            self,
            selector: #selector(appTerminated(_:)),
            name: NSWorkspace.didTerminateApplicationNotification,
            object: nil
        )
        
        // App activate (focus)
        center.addObserver(
            self,
            selector: #selector(appActivated(_:)),
            name: NSWorkspace.didActivateApplicationNotification,
            object: nil
        )
        
        // App deactivate
        center.addObserver(
            self,
            selector: #selector(appDeactivated(_:)),
            name: NSWorkspace.didDeactivateApplicationNotification,
            object: nil
        )
        
        Logger.shared.info("Activity monitoring notifications set up")
    }
    
    private func startActiveAppMonitoring() {
        Logger.shared.info("Starting active app monitoring timer")
        
        // Add a heartbeat counter for debugging
        var heartbeatCount = 0
        
        // Check for frontmost app changes every second
        activeAppTimer = Timer.scheduledTimer(withTimeInterval: 1.0, repeats: true) { [weak self] _ in
            heartbeatCount += 1
            if heartbeatCount % 10 == 0 {
                Logger.shared.debug("ActivityMonitor heartbeat: \(heartbeatCount) checks performed")
            }
            self?.checkFrontmostApp()
        }
        
        // Do an initial check
        checkFrontmostApp()
    }
    
    private func checkFrontmostApp() {
        let currentFrontmost = NSWorkspace.shared.frontmostApplication
        
        if currentFrontmost != frontmostApp {
            // Log the change at INFO level for better visibility
            Logger.shared.info("Frontmost app changed!")
            
            if let previous = frontmostApp {
                // Previous app lost focus
                Logger.shared.info("App losing focus: \(previous.localizedName ?? "Unknown") (PID: \(previous.processIdentifier))")
                let signal = createSignal(for: previous, type: .appUnfocus)
                delegate?.activityMonitor(self, didCollectSignal: signal)
            }
            
            if let current = currentFrontmost {
                // New app gained focus
                Logger.shared.info("App gaining focus: \(current.localizedName ?? "Unknown") (PID: \(current.processIdentifier))")
                let signal = createSignal(for: current, type: .appFocus)
                delegate?.activityMonitor(self, didCollectSignal: signal)
            }
            
            frontmostApp = currentFrontmost
        }
    }
    
    @objc private func appLaunched(_ notification: Notification) {
        guard let app = notification.userInfo?[NSWorkspace.applicationUserInfoKey] as? NSRunningApplication else { return }
        
        let signal = createSignal(for: app, type: .appLaunch)
        delegate?.activityMonitor(self, didCollectSignal: signal)
        
        Logger.shared.info("App launched: \(app.localizedName ?? "Unknown")")
    }
    
    @objc private func appTerminated(_ notification: Notification) {
        guard let app = notification.userInfo?[NSWorkspace.applicationUserInfoKey] as? NSRunningApplication else { return }
        
        let signal = createSignal(for: app, type: .appQuit)
        delegate?.activityMonitor(self, didCollectSignal: signal)
        
        Logger.shared.info("App terminated: \(app.localizedName ?? "Unknown")")
    }
    
    @objc private func appActivated(_ notification: Notification) {
        guard let app = notification.userInfo?[NSWorkspace.applicationUserInfoKey] as? NSRunningApplication else { return }
        
        // Create signal for app activation
        let signal = createSignal(for: app, type: .appFocus)
        delegate?.activityMonitor(self, didCollectSignal: signal)
        
        // Update frontmost app
        frontmostApp = app
        
        Logger.shared.debug("App activated: \(app.localizedName ?? "Unknown")")
    }
    
    @objc private func appDeactivated(_ notification: Notification) {
        guard let app = notification.userInfo?[NSWorkspace.applicationUserInfoKey] as? NSRunningApplication else { return }
        
        // Create signal for app deactivation
        let signal = createSignal(for: app, type: .appUnfocus)
        delegate?.activityMonitor(self, didCollectSignal: signal)
        
        Logger.shared.debug("App deactivated: \(app.localizedName ?? "Unknown")")
    }
    
    private func createSignal(for app: NSRunningApplication, type: CanonicalSignal.SignalType) -> CanonicalSignal {
        var metadata: [String: String] = [:]
        
        // Try to get app info, but handle permission errors gracefully
        if let bundleID = app.bundleIdentifier {
            metadata["bundle_id"] = bundleID
        } else {
            metadata["bundle_id"] = "unknown"
        }
        
        if let name = app.localizedName {
            metadata["app_name"] = name
        } else {
            // Try to get name from bundle URL as fallback
            if let bundleURL = app.bundleURL {
                metadata["app_name"] = bundleURL.lastPathComponent.replacingOccurrences(of: ".app", with: "")
            } else {
                metadata["app_name"] = "Process \(app.processIdentifier)"
            }
        }
        
        if let bundleURL = app.bundleURL {
            metadata["bundle_path"] = bundleURL.path
        }
        
        metadata["process_id"] = String(app.processIdentifier)
        
        Logger.shared.debug("Created signal for app: \(metadata["app_name"] ?? "unknown") (type: \(type))")
        
        return CanonicalSignal(signalType: type, metadata: metadata)
    }
}