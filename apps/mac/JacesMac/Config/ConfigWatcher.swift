import Foundation

protocol ConfigWatcherDelegate: AnyObject {
    func configurationDidChange()
}

class ConfigWatcher {
    weak var delegate: ConfigWatcherDelegate?
    
    private var timer: Timer?
    private var lastModificationDate: Date?
    private let checkInterval: TimeInterval = 60.0 // Check every 60 seconds
    
    func startWatching() {
        Logger.shared.info("Starting configuration file watcher")
        
        // Get initial modification date
        lastModificationDate = ConfigManager.shared.getConfigFileModificationDate()
        
        // Start timer
        timer = Timer.scheduledTimer(withTimeInterval: checkInterval, repeats: true) { [weak self] _ in
            self?.checkForChanges()
        }
    }
    
    func stopWatching() {
        Logger.shared.info("Stopping configuration file watcher")
        timer?.invalidate()
        timer = nil
    }
    
    private func checkForChanges() {
        guard let currentModDate = ConfigManager.shared.getConfigFileModificationDate() else {
            // Config file might have been deleted
            if lastModificationDate != nil {
                Logger.shared.warning("Configuration file no longer exists")
                lastModificationDate = nil
                delegate?.configurationDidChange()
            }
            return
        }
        
        if let lastDate = lastModificationDate, currentModDate > lastDate {
            Logger.shared.info("Configuration file changed, reloading")
            lastModificationDate = currentModDate
            
            // Reload configuration
            ConfigManager.shared.loadConfiguration()
            
            // Notify delegate
            delegate?.configurationDidChange()
        } else if lastModificationDate == nil {
            // Config file was created
            Logger.shared.info("Configuration file created")
            lastModificationDate = currentModDate
            ConfigManager.shared.loadConfiguration()
            delegate?.configurationDidChange()
        }
    }
}