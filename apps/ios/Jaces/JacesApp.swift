//
//  JacesApp.swift
//  Jaces
//
//  Created by Adam Jace on 7/30/25.
//

import SwiftUI
import BackgroundTasks

@main
struct JacesApp: App {
    @StateObject private var deviceManager = DeviceManager.shared
    @StateObject private var uploadCoordinator = BatchUploadCoordinator.shared
    @StateObject private var healthKitManager = HealthKitManager.shared
    @StateObject private var locationManager = LocationManager.shared
    @StateObject private var audioManager = AudioManager.shared
    @AppStorage("isOnboardingComplete") private var isOnboardingComplete = false
    
    init() {
        // Register background tasks on app launch
        registerBackgroundTasks()
    }
    
    var body: some Scene {
        WindowGroup {
            Group {
                if isOnboardingComplete {
                    MainView()
                        .onAppear {
                            // Start all background services
                            startAllServices()
                        }
                } else {
                    OnboardingView(isOnboardingComplete: $isOnboardingComplete)
                }
            }
            .onReceive(NotificationCenter.default.publisher(for: UIApplication.willEnterForegroundNotification)) { _ in
                // Update stats when app comes to foreground
                uploadCoordinator.updateUploadStats()
                
                // Check and recover audio recording state if needed
                if isOnboardingComplete && audioManager.hasPermission && !audioManager.isRecording {
                    print("⚠️ Audio recording was stopped, restarting...")
                    audioManager.startRecording()
                }
            }
        }
    }
    
    private func registerBackgroundTasks() {
        // Register background refresh task
        BGTaskScheduler.shared.register(
            forTaskWithIdentifier: "com.jaces.ios.refresh",
            using: nil
        ) { task in
            handleBackgroundRefresh(task: task as! BGAppRefreshTask)
        }
        
        // Register background processing task
        BGTaskScheduler.shared.register(
            forTaskWithIdentifier: "com.jaces.ios.processing",
            using: nil
        ) { task in
            handleBackgroundProcessing(task: task as! BGProcessingTask)
        }
    }
    
    private func handleBackgroundRefresh(task: BGAppRefreshTask) {
        // Schedule next refresh
        scheduleBackgroundRefresh()
        
        // Perform quick sync
        let syncTask = Task {
            await uploadCoordinator.performUpload()
        }
        
        task.expirationHandler = {
            syncTask.cancel()
        }
        
        Task {
            _ = await syncTask.result
            task.setTaskCompleted(success: true)
        }
    }
    
    private func handleBackgroundProcessing(task: BGProcessingTask) {
        // Perform longer running tasks
        let processingTask = Task {
            await uploadCoordinator.performUpload()
        }
        
        task.expirationHandler = {
            processingTask.cancel()
        }
        
        Task {
            _ = await processingTask.result
            task.setTaskCompleted(success: true)
        }
    }
    
    private func scheduleBackgroundRefresh() {
        let request = BGAppRefreshTaskRequest(identifier: "com.jaces.ios.refresh")
        request.earliestBeginDate = Date(timeIntervalSinceNow: 15 * 60) // 15 minutes
        
        do {
            try BGTaskScheduler.shared.submit(request)
        } catch {
            print("Failed to schedule background refresh: \(error)")
        }
    }
    
    private func startAllServices() {
        // Start periodic uploads (this now handles all data collection)
        uploadCoordinator.startPeriodicUploads()
        
        // Start location tracking if authorized
        if locationManager.hasPermission {
            locationManager.startTracking()
            print("✅ Started location tracking")
        }
        
        // Start audio recording if authorized
        if audioManager.hasPermission {
            audioManager.startRecording()
            print("✅ Started audio recording")
        }
        
        // Start HealthKit monitoring if authorized
        if healthKitManager.isAuthorized {
            healthKitManager.startMonitoring()
            print("✅ Started HealthKit monitoring")
        } else {
            // Try again after a delay in case authorization is still being checked
            Task {
                try? await Task.sleep(nanoseconds: 2_000_000_000) // 2 seconds
                if healthKitManager.isAuthorized {
                    healthKitManager.startMonitoring()
                    print("✅ Started HealthKit monitoring (delayed)")
                } else {
                    print("⚠️ HealthKit still not authorized after delay")
                }
            }
        }
        
        print("✅ All services started")
    }
}
