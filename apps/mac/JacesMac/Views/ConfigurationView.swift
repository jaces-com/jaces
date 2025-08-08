import SwiftUI

struct ConfigurationView: View {
    @StateObject private var viewModel = ConfigurationViewModel()
    let onSave: () -> Void
    
    var body: some View {
        VStack(spacing: 20) {
            // Header
            HStack {
                Image(systemName: "gear.badge.checkmark")
                    .font(.largeTitle)
                    .foregroundColor(.accentColor)
                    .symbolRenderingMode(.hierarchical)
                
                VStack(alignment: .leading) {
                    Text("Settings")
                        .font(.title2)
                        .fontWeight(.semibold)
                    Text("Configure your connection")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
                
                Spacer()
            }
            .padding()
            
            // Form
            Form {
                Section("Server Settings") {
                    TextField("Server URL", text: $viewModel.serverURL)
                        .textFieldStyle(RoundedBorderTextFieldStyle())
                    
                    if !viewModel.urlError.isEmpty {
                        HStack {
                            Image(systemName: "exclamationmark.triangle.fill")
                                .foregroundColor(.red)
                            Text(viewModel.urlError)
                                .font(.caption)
                                .foregroundColor(.red)
                        }
                    }
                }
                
                Section("Device Information") {
                    TextField("Device Name", text: $viewModel.deviceName)
                        .textFieldStyle(RoundedBorderTextFieldStyle())
                    
                    HStack {
                        Text("Device ID:")
                            .foregroundColor(.secondary)
                        Text(viewModel.deviceID)
                            .font(.system(.body, design: .monospaced))
                            .textSelection(.enabled)
                    }
                }
                
            }
            .padding()
            
            // Status Message
            if !viewModel.errorMessage.isEmpty || !viewModel.successMessage.isEmpty {
                HStack(spacing: 8) {
                    Image(systemName: viewModel.errorMessage.isEmpty ? "checkmark.circle.fill" : "exclamationmark.circle.fill")
                        .foregroundColor(viewModel.errorMessage.isEmpty ? .green : .red)
                        .font(.body)
                    
                    Text(viewModel.errorMessage.isEmpty ? viewModel.successMessage : viewModel.errorMessage)
                        .font(.body)
                        .foregroundColor(viewModel.errorMessage.isEmpty ? .green : .red)
                    
                    Spacer()
                }
                .padding()
                .background(viewModel.errorMessage.isEmpty ? Color.green.opacity(0.1) : Color.red.opacity(0.1))
                .cornerRadius(8)
                .padding(.horizontal)
                .transition(.move(edge: .top).combined(with: .opacity))
            }
            
            // Buttons
            HStack {
                Button(action: { viewModel.testConnection() }) {
                    HStack {
                        if viewModel.isTesting {
                            ProgressView()
                                .scaleEffect(0.7)
                                .frame(width: 14, height: 14)
                        } else {
                            Image(systemName: "link.badge.plus")
                        }
                        Text(viewModel.isTesting ? "Verifying..." : "Verify Connection")
                    }
                }
                .disabled(viewModel.isTesting || !viewModel.isValid)
                
                Spacer()
                
                Button("Cancel") {
                    onSave()
                }
                .keyboardShortcut(.escape)
                
                Button("Save") {
                    viewModel.save()
                    onSave()
                }
                .buttonStyle(.borderedProminent)
                .keyboardShortcut(.return)
                .disabled(!viewModel.isValid || viewModel.isSaving)
            }
            .padding()
        }
        .frame(width: 480, height: 380)
        .onAppear {
            viewModel.loadConfiguration()
        }
    }
}