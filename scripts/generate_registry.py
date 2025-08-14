#!/usr/bin/env python3
"""
Generate a consolidated registry from distributed YAML configurations.
Walks through all source/stream/signal folders and creates a single registry.
"""

import os
import sys
import yaml
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime


def load_yaml(filepath: Path) -> Dict[str, Any]:
    """Load a YAML file safely."""
    if not filepath.exists():
        return {}

    with open(filepath, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f) or {}


def walk_sources_directory() -> Dict[str, Any]:
    """Walk through sources directory and collect all configurations."""
    sources_dir = Path(__file__).parent.parent / 'sources'

    registry = {
        'version': '2.0.0',
        'generated_at': datetime.now().isoformat(),
        'sources': {},
        'streams': {},
        'signals': {},
        'semantics': {},  # Add semantics section
        'transition_detectors': {}
    }

    # Walk through each source directory
    for source_dir in sources_dir.iterdir():
        if not source_dir.is_dir() or source_dir.name.startswith(('_', '.', 'base')):
            continue

        # Load source config
        source_config = load_yaml(source_dir / '_source.yaml')
        if source_config:
            source_name = source_config.get('name', source_dir.name)
            registry['sources'][source_name] = {
                'path': f"{source_dir.name}/",
                'display_name': source_config.get('display_name', source_name),
                'description': source_config.get('description', ''),
                'company': source_config.get('company', ''),
                'platform': source_config.get('platform', 'cloud'),
                'icon': source_config.get('icon', ''),
                'video': source_config.get('video', ''),  # Include video field
                'auth': source_config.get('auth', {}),  # All auth config including OAuth settings
                'sync': source_config.get('sync', {}),  # Preserve sync config
                'requirements': source_config.get('requirements', {}),  # Preserve requirements
                'streams': [],
                'streams_config': source_config.get('streams', [])  # Preserve stream configs with scopes
            }

            # Walk through stream directories
            for stream_dir in source_dir.iterdir():
                if not stream_dir.is_dir() or stream_dir.name.startswith(('_', '.')):
                    continue

                # Load stream config
                stream_config = load_yaml(stream_dir / '_stream.yaml')
                if stream_config:
                    stream_name = stream_config.get(
                        'name', f"{source_name}_{stream_dir.name}")

                    # Add to source's stream list
                    registry['sources'][source_name]['streams'].append(
                        stream_name)
                    
                    # Determine output type (signals or semantics)
                    output_type = stream_config.get('output', 'signals')
                    
                    # Add stream details with more configuration
                    registry['streams'][stream_name] = {
                        'source': source_name,
                        'path': f"{source_dir.name}/{stream_dir.name}/",
                        'display_name': stream_config.get('display_name', stream_name),
                        'description': stream_config.get('description', ''),
                        'processor': f"sources.{source_dir.name}.{stream_dir.name}.stream_processor",
                        'processor_config': stream_config.get('processor', {}),  # Include processor configuration
                        'output_type': output_type,
                        'ingestion': stream_config.get('ingestion', {}),
                        'sync': stream_config.get('sync', {}),
                        'processing': stream_config.get('processing', {}),
                        'storage': stream_config.get('storage', {}),
                        'signals': [],
                        'semantics': stream_config.get('semantics', [])
                    }

                    # Check for sync.py and extract sync_class from YAML or derive it
                    if (stream_dir / 'sync.py').exists():
                        sync_module = f"sources.{source_dir.name}.{stream_dir.name}.sync"
                        registry['streams'][stream_name]['sync_module'] = sync_module
                        
                        # Get sync_class from YAML or derive from stream name
                        sync_class = stream_config.get('sync', {}).get('class')
                        if not sync_class:
                            # Derive sync class name from stream name
                            # e.g., google_calendar -> GoogleCalendarSync
                            # Use the full stream_name to preserve source prefix
                            stream_parts = stream_name.split('_')
                            sync_class = ''.join(p.capitalize() for p in stream_parts) + 'Sync'
                        
                        registry['streams'][stream_name]['sync_class'] = sync_class

                    # Handle based on output type
                    if output_type == 'semantics':
                        # For semantic streams, add to semantics registry
                        semantic_types = stream_config.get('semantics', [])
                        for semantic_type in semantic_types:
                            semantic_name = f"{stream_name}_{semantic_type}"
                            registry['semantics'][semantic_name] = {
                                'source': source_name,
                                'stream': stream_name,
                                'semantic_type': semantic_type,
                                'display_name': f"{stream_config.get('display_name', stream_name)} - {semantic_type.title()}",
                                'description': stream_config.get('description', ''),
                                'sync_config': stream_config.get('sync', {}),
                                'processing_config': stream_config.get('processing', {}),
                                'storage_config': stream_config.get('storage', {})
                            }
                    else:
                        # Walk through signal directories for signal-based streams
                        for signal_dir in stream_dir.iterdir():
                            if not signal_dir.is_dir() or signal_dir.name.startswith(('_', '.')):
                                continue

                            # Load signal config
                            signal_config = load_yaml(signal_dir / '_signal.yaml')
                            if signal_config:
                                signal_name = signal_config.get(
                                    'name', f"{source_name}_{stream_dir.name}_{signal_dir.name}")

                                # Add to stream's signal list
                                registry['streams'][stream_name]['signals'].append(
                                    signal_name)

                                # Get computation details
                                computation = signal_config.get('computation', {})
                                
                                # Check for detector configuration
                                detector_class = None
                                detector_module = None
                                
                                # First check if YAML specifies detector class name
                                if signal_config.get('detector'):
                                    detector_class = signal_config['detector']
                                    # If detector.py exists, build the module path
                                    if (signal_dir / 'detector.py').exists():
                                        detector_module = f"sources.{source_dir.name}.{stream_dir.name}.{signal_dir.name}.detector"
                                # Otherwise check if detector.py exists and generate class name
                                elif (signal_dir / 'detector.py').exists():
                                    # Generate class name from signal directory name
                                    detector_class = ''.join(
                                        word.capitalize() for word in signal_dir.name.split('_'))
                                    detector_class = f"{detector_class}TransitionDetector"
                                    detector_module = f"sources.{source_dir.name}.{stream_dir.name}.{signal_dir.name}.detector"
                                
                                # Add detector info to computation if found
                                if detector_class and detector_module:
                                    computation['detector_class'] = detector_class
                                    computation['detector_module'] = detector_module
                                
                                # Add signal details with full configuration
                                registry['signals'][signal_name] = {
                                    'source': source_name,
                                    'stream': stream_name,
                                    'path': f"{source_dir.name}/{stream_dir.name}/{signal_dir.name}/",
                                    'display_name': signal_config.get('display_name', signal_name),
                                    'description': signal_config.get('description', ''),
                                    'unit': signal_config.get('unit', {}),
                                    'value_type': computation.get('value_type', 'continuous'),
                                    'algorithm': computation.get('algorithm', 'pelt'),
                                    'cost_function': computation.get('cost_function', 'l2'),
                                    'computation': computation,  # Include full computation config with detector info
                                    'weight': signal_config.get('weight', {}),
                                    'transitions': signal_config.get('transitions', {}),
                                    'zones': signal_config.get('zones', {}),  # Include zones if present
                                    'metadata': signal_config.get('metadata', {}),
                                    'schedule': signal_config.get('schedule', {})
                                }
                                
                                # Add to transition_detectors for backward compatibility
                                if detector_class and detector_module:
                                    registry['transition_detectors'][signal_name] = {
                                        'module': detector_module.replace('.detector', ''),  # Remove .detector suffix for backward compat
                                        'class': detector_class
                                    }

    return registry


def validate_registry(registry: Dict[str, Any]) -> List[str]:
    """Validate the registry for completeness and consistency."""
    issues = []
    
    # Check all streams have either signals or semantics
    for stream_name, stream_info in registry['streams'].items():
        if stream_info['output_type'] == 'signals':
            if not stream_info['signals']:
                issues.append(f"Stream {stream_name} outputs signals but has no signals defined")
        elif stream_info['output_type'] == 'semantics':
            if not stream_info['semantics']:
                issues.append(f"Stream {stream_name} outputs semantics but has no semantic types defined")
    
    # Check all signals have required fields
    for signal_name, signal_info in registry['signals'].items():
        if not signal_info.get('unit'):
            issues.append(f"Signal {signal_name} missing unit definition")
        if not signal_info.get('computation'):
            issues.append(f"Signal {signal_name} missing computation configuration")
    
    # Check all referenced sources exist
    for stream_name, stream_info in registry['streams'].items():
        if stream_info['source'] not in registry['sources']:
            issues.append(f"Stream {stream_name} references non-existent source {stream_info['source']}")
    
    # Check signal naming consistency
    for signal_name, signal_info in registry['signals'].items():
        expected_prefix = f"{signal_info['source']}_"
        if not signal_name.startswith(expected_prefix):
            issues.append(f"Signal {signal_name} doesn't follow naming convention (should start with {expected_prefix})")
    
    return issues


def generate_python_registry_DEPRECATED(registry: Dict[str, Any]) -> str:
    """Generate Python code for the registry."""
    code = f'''"""
Auto-generated registry from distributed YAML configurations.
Generated at: {registry['generated_at']}
DO NOT EDIT THIS FILE MANUALLY - Run generate_registry.py to regenerate
"""

from typing import Dict, Any

# Registry version
VERSION = "{registry['version']}"
GENERATED_AT = "{registry['generated_at']}"

# Sources registry
SOURCES = {repr(registry['sources'])}

# Streams registry
STREAMS = {repr(registry['streams'])}

# Signals registry  
SIGNALS = {repr(registry['signals'])}

# Semantics registry
SEMANTICS = {repr(registry['semantics'])}

# Transition detectors for signal_analysis.py
TRANSITION_DETECTORS = {{'''

    # Format transition detectors specially for import
    for signal_name, detector_info in registry['transition_detectors'].items():
        code += f"\n    '{signal_name}': '{detector_info['module']}.{detector_info['class']}',"

    code += '''
}

# Stream registry for process_streams.py
STREAM_REGISTRY = {'''

    # Format stream registry for process_streams
    for stream_name, stream_info in registry['streams'].items():
        if stream_info['output_type'] == 'signals':
            signals_list = ', '.join(f"'{s}'" for s in stream_info['signals'])
            code += f"""
    '{stream_name}': {{
        'source': '{stream_info['source']}',
        'path': '{stream_info['path']}',
        'processor': '{stream_info['processor']}',
        'output_type': 'signals',
        'produces_signals': [{signals_list}]
    }},"""
        else:
            semantics_list = ', '.join(f"'{s}'" for s in stream_info['semantics'])
            code += f"""
    '{stream_name}': {{
        'source': '{stream_info['source']}',
        'path': '{stream_info['path']}',
        'processor': '{stream_info['processor']}',
        'output_type': 'semantics',
        'produces_semantics': [{semantics_list}]
    }},"""

    code += '\n}\n'

    return code


def generate_yaml_registry(registry: Dict[str, Any]) -> str:
    """Generate YAML format of the registry."""
    return yaml.dump(registry, default_flow_style=False, sort_keys=False, width=120, allow_unicode=True)


def main():
    """Main function to generate the registry."""
    print("🔍 Scanning sources directory...")
    registry = walk_sources_directory()
    
    # Validate registry
    issues = validate_registry(registry)
    if issues:
        print("⚠️  Registry validation issues found:")
        for issue in issues:
            print(f"   - {issue}")
        print()

    # Statistics
    num_sources = len(registry['sources'])
    num_streams = len(registry['streams'])
    num_signals = len(registry['signals'])
    num_semantics = len(registry['semantics'])
    num_detectors = len(registry['transition_detectors'])

    print(
        f"✅ Found {num_sources} sources, {num_streams} streams, {num_signals} signals, {num_semantics} semantics, {num_detectors} detectors")

    # Generate YAML registry to root directory for documentation
    yaml_content = """# AUTO-GENERATED DOCUMENTATION - DO NOT EDIT MANUALLY
# Generated from distributed YAML configurations in sources/
# For reference only - runtime code uses database as source of truth
# Run 'make registry' or 'python scripts/generate_registry.py' to regenerate

"""
    yaml_content += generate_yaml_registry(registry)
    yaml_file = Path(__file__).parent.parent / 'sources' / '_generated_registry.yaml'
    with open(yaml_file, 'w', encoding='utf-8') as f:
        f.write(yaml_content)
    print(f"📝 Generated documentation registry: {yaml_file}")
    
    # Note: Python registry generation removed - use database instead

    print("✨ Registry generation complete!")

    # Print summary
    print("\n📊 Registry Summary:")
    print("=" * 50)
    for source_name, source_info in registry['sources'].items():
        print(f"\n📦 {source_name}:")
        for stream_name in source_info['streams']:
            stream_info = registry['streams'][stream_name]
            if stream_info['output_type'] == 'signals':
                print(f"  📡 {stream_name} (signals):")
                for signal_name in stream_info['signals']:
                    has_detector = '✓' if signal_name in registry['transition_detectors'] else '✗'
                    print(f"    📈 {signal_name} [detector: {has_detector}]")
            else:
                print(f"  📡 {stream_name} (semantics):")
                for semantic_type in stream_info['semantics']:
                    print(f"    📄 {semantic_type}")


if __name__ == '__main__':
    main()