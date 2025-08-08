import SwiftUI

struct MainView: View {
    @ObservedObject var viewModel: AgentStatusViewModel
    @EnvironmentObject var monitoringManager: MonitoringManager
    @State private var showingConfiguration = false
    @State private var isSyncing = false
    @State private var syncMessage = ""
    @State private var showSyncAlert = false
    @State private var countdownTimer: Timer?
    @State private var timeUntilSync = "Not scheduled"
    @State private var showingClearDataConfirmation = false
    @State private var isClearingData = false
    
    var body: some View {
        VStack(spacing: 0) {
            // Header
            headerView
            
            Divider()
            
            // Main Content
            ScrollView {
                VStack(spacing: 16) {
                    if !ConfigManager.shared.isConfigured() {
                        setupPromptCard
                    } else {
                        statusCard
                        actionsCard
                    }
                }
                .padding(20)
            }
            
            // Footer
            Divider()
            footerView
        }
        .frame(minWidth: 380, idealWidth: 450, minHeight: 380, idealHeight: 500)
        .toolbar {
            ToolbarItem(placement: .automatic) {
                Button {
                    showingConfiguration = true
                } label: {
                    Label("Configure", systemImage: "gear")
                }
            }
        }
        .sheet(isPresented: $showingConfiguration) {
            ConfigurationView {
                showingConfiguration = false
                viewModel.refreshStatus()
                
                // Start monitoring after configuration
                if ConfigManager.shared.isConfigured() {
                    MonitoringManager.shared.startMonitoring()
                }
            }
        }
        .alert("Sync Complete", isPresented: $showSyncAlert) {
            Button("OK") { }
        } message: {
            Text(syncMessage)
        }
        .alert("Clear All Data", isPresented: $showingClearDataConfirmation) {
            Button("Cancel", role: .cancel) { }
            Button("Clear All Data", role: .destructive) {
                clearAllData()
            }
        } message: {
            Text("This will delete all pending data that hasn't been synced. This action cannot be undone.")
        }
        .onAppear {
            viewModel.startMonitoring()
            
            // Start monitoring if configured
            if ConfigManager.shared.isConfigured() {
                MonitoringManager.shared.startMonitoring()
            }
            
            // Start countdown timer
            startCountdownTimer()
        }
        .onDisappear {
            viewModel.stopMonitoring()
            countdownTimer?.invalidate()
        }
    }
    
    private var headerView: some View {
        HStack(spacing: 12) {
            Image(systemName: "sparkles")
                .font(.title2)
                .foregroundColor(.accentColor)
            
            Text("JacesMac")
                .font(.title2)
                .fontWeight(.semibold)
            
            Spacer()
        }
        .padding()
        .background(Color(NSColor.windowBackgroundColor))
    }
    
    private var setupPromptCard: some View {
        VStack(spacing: 16) {
            Image(systemName: "sparkles.rectangle.stack")
                .font(.system(size: 50))
                .foregroundColor(.accentColor)
                .symbolRenderingMode(.hierarchical)
            
            Text("Welcome to JacesMac")
                .font(.title2)
                .fontWeight(.semibold)
            
            Text("JacesMac tracks your application usage and syncs it to your server. Configure the server URL to get started.")
                .multilineTextAlignment(.center)
                .foregroundColor(.secondary)
                .frame(maxWidth: 350)
            
            Button(action: { showingConfiguration = true }) {
                Label("Configure", systemImage: "gear")
                    .frame(maxWidth: 200)
            }
            .controlSize(.large)
            .buttonStyle(.borderedProminent)
        }
        .padding(40)
        .background(Color(NSColor.controlBackgroundColor))
        .cornerRadius(12)
    }
    
    private var statusCard: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                Label("Status", systemImage: "sparkles")
                    .font(.headline)
                Spacer()
                
                // Connection status indicator
                HStack(spacing: 6) {
                    Circle()
                        .fill(viewModel.isAgentRunning ? Color.green : Color.orange)
                        .frame(width: 8, height: 8)
                    Text(viewModel.isAgentRunning ? "Connected" : "Disconnected")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
            }
            
            VStack(spacing: 12) {
                // Queue size
                HStack {
                    Label("\(viewModel.queueStats.currentSignals + viewModel.queueStats.pendingSignals)", systemImage: "tray.2")
                        .font(.title2)
                        .fontWeight(.semibold)
                    Text("signals queued")
                        .foregroundColor(.secondary)
                    Spacer()
                }
                
                Divider()
                
                // Sync info
                HStack(alignment: .top) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Last sync")
                            .font(.caption)
                            .foregroundColor(.secondary)
                        Text(viewModel.lastUploadTime)
                            .font(.body)
                    }
                    
                    Spacer()
                    
                    VStack(alignment: .trailing, spacing: 4) {
                        Text("Next sync")
                            .font(.caption)
                            .foregroundColor(.secondary)
                        Text(timeUntilSync)
                            .font(.body)
                            .monospacedDigit()
                    }
                }
            }
            
            if let error = viewModel.lastError {
                HStack(spacing: 6) {
                    Image(systemName: "exclamationmark.circle.fill")
                        .foregroundColor(.red)
                        .font(.caption)
                    Text(error)
                        .font(.caption)
                        .foregroundColor(.red)
                        .lineLimit(2)
                }
                .padding(.top, 4)
            }
        }
        .padding()
        .background(Color(NSColor.controlBackgroundColor))
        .cornerRadius(10)
    }
    
    
    private var actionsCard: some View {
        VStack(alignment: .leading, spacing: 16) {
            Label("Actions", systemImage: "bolt.circle")
                .font(.headline)
            
            VStack(spacing: 12) {
                // Primary action: Sync Now
                Button(action: syncNow) {
                    HStack {
                        if isSyncing {
                            ProgressView()
                                .scaleEffect(0.7)
                                .frame(width: 16, height: 16)
                        } else {
                            Image(systemName: "arrow.triangle.2.circlepath")
                        }
                        Text(isSyncing ? "Syncing..." : "Sync Now")
                    }
                    .frame(maxWidth: .infinity)
                }
                .disabled(isSyncing || !ConfigManager.shared.isConfigured())
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
                
                HStack(spacing: 12) {
                    // Resync connection
                    Button(action: resyncConnection) {
                        Label("Verify Connection", systemImage: "link.circle")
                    }
                    .disabled(!ConfigManager.shared.isConfigured())
                    
                    Spacer()
                    
                    // Clear data - destructive action
                    Button("Clear Data") {
                        showingClearDataConfirmation = true
                    }
                    .foregroundColor(.red)
                    .disabled(isClearingData)
                }
                .buttonStyle(.borderless)
            }
        }
        .padding()
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(NSColor.controlBackgroundColor))
        .cornerRadius(10)
    }
    
    private var footerView: some View {
        HStack {
            Text("JacesMac v1.0.0")
                .font(.caption2)
                .foregroundColor(.secondary)
            
            Spacer()
            
            Button(action: { showingConfiguration = true }) {
                Label("Settings", systemImage: "gear")
                    .labelStyle(.iconOnly)
                    .font(.caption)
            }
            .buttonStyle(.plain)
            .foregroundColor(.secondary)
        }
        .padding(.horizontal)
        .padding(.vertical, 8)
        .background(Color(NSColor.windowBackgroundColor))
    }
    
    private func syncNow() {
        isSyncing = true
        
        // First flush any pending signals
        QueueManager.shared.forceSyncNow { queueResult in
            switch queueResult {
            case .success(let batchCount):
                // Now upload
                UploadManager.shared.syncNow { uploadResult in
                    DispatchQueue.main.async {
                        isSyncing = false
                        
                        switch uploadResult {
                        case .success(let counts):
                            if counts.uploaded == 0 && batchCount == 0 {
                                syncMessage = "No data to sync."
                            } else {
                                syncMessage = "Successfully synced \(counts.uploaded) batches."
                                if counts.failed > 0 {
                                    syncMessage += " \(counts.failed) batches failed to upload."
                                }
                            }
                            showSyncAlert = true
                            viewModel.refreshStatus()
                            
                        case .failure(let error):
                            syncMessage = "Sync failed: \(error.localizedDescription)"
                            showSyncAlert = true
                        }
                    }
                }
                
            case .failure(let error):
                DispatchQueue.main.async {
                    isSyncing = false
                    syncMessage = "Failed to prepare sync: \(error.localizedDescription)"
                    showSyncAlert = true
                }
            }
        }
    }
    
    private func resyncConnection() {
        ConnectionManager.shared.resyncConnection { result in
            DispatchQueue.main.async {
                switch result {
                case .success(let connection):
                    syncMessage = "Connection resynced successfully. Schedule: \(connection.syncSchedule)"
                    showSyncAlert = true
                case .failure(let error):
                    syncMessage = "Failed to resync connection: \(error.localizedDescription)"
                    showSyncAlert = true
                }
            }
        }
    }
    
    private func clearAllData() {
        isClearingData = true
        
        QueueManager.shared.clearAllData { result in
            DispatchQueue.main.async {
                isClearingData = false
                
                switch result {
                case .success:
                    syncMessage = "All pending data has been cleared."
                    showSyncAlert = true
                    viewModel.refreshStatus()
                    
                case .failure(let error):
                    syncMessage = "Failed to clear data: \(error.localizedDescription)"
                    showSyncAlert = true
                }
            }
        }
    }
    
    private func startCountdownTimer() {
        countdownTimer?.invalidate()
        
        // Update countdown every second
        countdownTimer = Timer.scheduledTimer(withTimeInterval: 1, repeats: true) { _ in
            updateCountdown()
        }
        
        // Initial update
        updateCountdown()
    }
    
    private func updateCountdown() {
        guard let nextSyncTime = monitoringManager.nextSyncTime else {
            timeUntilSync = "Not scheduled"
            return
        }
        
        timeUntilSync = CronScheduler.shared.timeUntilNextSync(from: Date(), to: nextSyncTime)
    }
}