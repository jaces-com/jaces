import Foundation

class CronScheduler {
    static let shared = CronScheduler()
    
    private init() {}
    
    // Parse common cron expressions and return interval in seconds
    func intervalFromCronExpression(_ cron: String) -> TimeInterval {
        switch cron {
        case "* * * * *":
            return 60 // Every minute
        case "*/1 * * * *":
            return 60 // Every minute
        case "*/4 * * * *":
            return 240 // Every 4 minutes
        case "*/5 * * * *":
            return 300 // Every 5 minutes
        case "*/15 * * * *":
            return 900 // Every 15 minutes
        case "*/30 * * * *":
            return 1800 // Every 30 minutes
        case "0 * * * *":
            return 3600 // Every hour
        case "0 */2 * * *":
            return 7200 // Every 2 hours
        case "0 */6 * * *":
            return 21600 // Every 6 hours
        case "0 */12 * * *":
            return 43200 // Every 12 hours
        case "0 0 * * *":
            return 86400 // Daily at midnight
        case "0 12 * * *":
            return 86400 // Daily at noon
        case "0 0 * * 0":
            return 604800 // Weekly on Sunday
        case "realtime":
            return 60 // Treat realtime as every minute for now
        case "manual":
            return TimeInterval.infinity // Manual sync only
        default:
            // Try to parse basic patterns
            if cron.hasPrefix("*/") {
                // Extract interval from patterns like */X * * * *
                let components = cron.components(separatedBy: " ")
                if let firstComponent = components.first,
                   firstComponent.hasPrefix("*/") {
                    let intervalStr = String(firstComponent.dropFirst(2))
                    if let interval = Int(intervalStr) {
                        Logger.shared.info("Parsed cron \(cron) as \(interval) minute interval")
                        return TimeInterval(interval * 60)
                    }
                }
            }
            // Default to 5 minutes if we can't parse
            Logger.shared.warning("Unknown cron expression: \(cron), defaulting to 5 minutes")
            return 300
        }
    }
    
    // Calculate next sync time based on cron expression and last sync
    func nextSyncTime(cron: String, lastSync: Date?) -> Date? {
        if cron == "manual" {
            return nil
        }
        
        let interval = intervalFromCronExpression(cron)
        if interval == TimeInterval.infinity {
            return nil
        }
        
        // Always calculate from current time, not last sync
        // This ensures we don't miss syncs if the app was offline
        let baseTime = Date()
        return baseTime.addingTimeInterval(interval)
    }
    
    // Human-readable description of cron expression
    func descriptionForCron(_ cron: String) -> String {
        switch cron {
        case "* * * * *":
            return "Every minute"
        case "*/4 * * * *":
            return "Every 4 minutes"
        case "*/5 * * * *":
            return "Every 5 minutes"
        case "*/15 * * * *":
            return "Every 15 minutes"
        case "*/30 * * * *":
            return "Every 30 minutes"
        case "0 * * * *":
            return "Every hour"
        case "0 */2 * * *":
            return "Every 2 hours"
        case "0 */6 * * *":
            return "Every 6 hours"
        case "0 */12 * * *":
            return "Every 12 hours"
        case "0 0 * * *":
            return "Daily at midnight"
        case "0 12 * * *":
            return "Daily at noon"
        case "0 0 * * 0":
            return "Weekly on Sunday"
        case "realtime":
            return "Real-time"
        case "manual":
            return "Manual sync only"
        default:
            return cron
        }
    }
    
    // Format time remaining until next sync
    func timeUntilNextSync(from date: Date, to nextSync: Date) -> String {
        let interval = nextSync.timeIntervalSince(date)
        
        if interval <= 0 {
            return "Syncing now..."
        }
        
        let minutes = Int(interval / 60)
        let hours = minutes / 60
        let days = hours / 24
        
        if days > 0 {
            return "\(days) day\(days == 1 ? "" : "s")"
        } else if hours > 0 {
            let remainingMinutes = minutes % 60
            if remainingMinutes > 0 {
                return "\(hours)h \(remainingMinutes)m"
            }
            return "\(hours) hour\(hours == 1 ? "" : "s")"
        } else if minutes > 0 {
            return "\(minutes) minute\(minutes == 1 ? "" : "s")"
        } else {
            let seconds = Int(interval)
            return "\(seconds) second\(seconds == 1 ? "" : "s")"
        }
    }
}