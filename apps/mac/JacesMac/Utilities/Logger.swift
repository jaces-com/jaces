import Foundation

class Logger {
    static let shared = Logger()
    
    private let logFileURL: URL
    private let maxLogSize: Int = 10 * 1024 * 1024 // 10MB
    private let maxLogFiles: Int = 5
    private let dateFormatter: DateFormatter
    private let queue = DispatchQueue(label: "com.jaces.mac.logger", qos: .background)
    
    // Public getter for log directory
    var logDirURL: URL {
        return logFileURL.deletingLastPathComponent()
    }
    
    private init() {
        let logDir = URL(fileURLWithPath: "/tmp")
        self.logFileURL = logDir.appendingPathComponent("jaces-mac.log")
        
        self.dateFormatter = DateFormatter()
        self.dateFormatter.dateFormat = "yyyy-MM-dd HH:mm:ss.SSS"
        
        createLogFileIfNeeded()
    }
    
    enum LogLevel: String {
        case debug = "DEBUG"
        case info = "INFO"
        case warning = "WARN"
        case error = "ERROR"
    }
    
    func log(_ message: String, level: LogLevel = .info, file: String = #file, function: String = #function, line: Int = #line) {
        queue.async { [weak self] in
            guard let self = self else { return }
            
            let timestamp = self.dateFormatter.string(from: Date())
            let fileName = URL(fileURLWithPath: file).lastPathComponent
            let logEntry = "[\(timestamp)] [\(level.rawValue)] [\(fileName):\(line)] \(function) - \(message)\n"
            
            self.rotateLogsIfNeeded()
            self.writeToLog(logEntry)
            
            #if DEBUG
            print(logEntry.trimmingCharacters(in: .newlines))
            #endif
        }
    }
    
    func debug(_ message: String, file: String = #file, function: String = #function, line: Int = #line) {
        log(message, level: .debug, file: file, function: function, line: line)
    }
    
    func info(_ message: String, file: String = #file, function: String = #function, line: Int = #line) {
        log(message, level: .info, file: file, function: function, line: line)
    }
    
    func warning(_ message: String, file: String = #file, function: String = #function, line: Int = #line) {
        log(message, level: .warning, file: file, function: function, line: line)
    }
    
    func error(_ message: String, file: String = #file, function: String = #function, line: Int = #line) {
        log(message, level: .error, file: file, function: function, line: line)
    }
    
    private func createLogFileIfNeeded() {
        let fileManager = FileManager.default
        if !fileManager.fileExists(atPath: logFileURL.path) {
            fileManager.createFile(atPath: logFileURL.path, contents: nil, attributes: nil)
        }
    }
    
    private func writeToLog(_ entry: String) {
        guard let data = entry.data(using: .utf8) else { return }
        
        if let fileHandle = FileHandle(forWritingAtPath: logFileURL.path) {
            defer { fileHandle.closeFile() }
            fileHandle.seekToEndOfFile()
            fileHandle.write(data)
        }
    }
    
    private func rotateLogsIfNeeded() {
        let fileManager = FileManager.default
        
        do {
            let attributes = try fileManager.attributesOfItem(atPath: logFileURL.path)
            if let fileSize = attributes[.size] as? Int, fileSize > maxLogSize {
                rotateLogs()
            }
        } catch {
            print("Error checking log file size: \(error)")
        }
    }
    
    private func rotateLogs() {
        let fileManager = FileManager.default
        
        // Remove oldest log if at max
        let oldestLog = logFileURL.appendingPathExtension("\(maxLogFiles)")
        try? fileManager.removeItem(at: oldestLog)
        
        // Shift existing logs
        for i in (1..<maxLogFiles).reversed() {
            let oldURL = logFileURL.appendingPathExtension("\(i)")
            let newURL = logFileURL.appendingPathExtension("\(i + 1)")
            try? fileManager.moveItem(at: oldURL, to: newURL)
        }
        
        // Move current log to .1
        let rotatedURL = logFileURL.appendingPathExtension("1")
        try? fileManager.moveItem(at: logFileURL, to: rotatedURL)
        
        // Create new log file
        createLogFileIfNeeded()
    }
}