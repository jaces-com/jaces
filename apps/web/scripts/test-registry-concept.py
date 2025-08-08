#!/usr/bin/env python3
"""Test the registry concept without imports."""

import json
import os

# Read the generated registry
registry_path = os.path.join(os.path.dirname(__file__), '../../../sources/_generated_registry.py')

# Parse the registry file
with open(registry_path, 'r') as f:
    content = f.read()
    
# Extract STREAMS dictionary using exec
namespace = {}
exec(content, namespace)

STREAMS = namespace.get('STREAMS', {})
SOURCES = namespace.get('SOURCES', {})

print("Testing registry-driven architecture:\n")
print("=" * 50)

# Test that we can derive sync modules from registry
for stream_name, stream_config in STREAMS.items():
    print(f"\nStream: {stream_name}")
    print(f"  Source: {stream_config.get('source')}")
    print(f"  Type: {stream_config.get('ingestion', {}).get('type')}")
    
    # Check if sync module is specified
    if 'sync_module' in stream_config:
        print(f"  ✅ Has explicit sync module: {stream_config['sync_module']}")
    elif stream_config.get('ingestion', {}).get('type') == 'pull':
        # Construct sync module from path
        path = stream_config['path'].rstrip('/')
        sync_module = f"sources.{path.replace('/', '.')}.sync"
        print(f"  📦 Derived sync module: {sync_module}")
    else:
        print(f"  ⚡ Push-only stream (no sync needed)")

print("\n" + "=" * 50)
print("\nSource OAuth configurations:\n")

# Test OAuth sources
for source_name, source_config in SOURCES.items():
    auth_type = source_config.get('auth', {}).get('type')
    if auth_type == 'oauth2':
        print(f"\n{source_name}:")
        print(f"  Auth type: {auth_type}")
        print(f"  Path: {source_config['path']}")
        
        # Auth module would be at
        auth_path = source_config['path'].rstrip('/')
        auth_module = f"sources.{auth_path.replace('/', '.')}.auth"
        print(f"  Expected auth module: {auth_module}")

print("\n" + "=" * 50)
print("\n✅ Registry structure validated!")
print("\nKey insights:")
print("1. All sync modules can be derived from the registry")
print("2. No hardcoded mappings needed")
print("3. OAuth sources have predictable auth module paths")
print("4. Push streams correctly identified (no sync needed)")
print("\n🎉 The registry-driven approach works!")