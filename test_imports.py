#!/usr/bin/env python3
"""Test all module imports to verify the modularized codebase."""

import sys
import importlib

modules_to_test = [
    'enums_and_dataclasses',
    'config',
    'Utils',
    'skill_registry',
    'skills_tools_framework',
    'server_management',
    'memory_system',
    'attention_mechanism',
    'heartbeat_protocol',
    'builtin_skills',
    'local_model_wrapper',
    'nexuss_agent',
    'Nexuss'
]

print("\n" + "="*60)
print("  IMPORT TEST - Modularized Nexuss Codebase")
print("="*60)

success = []
failed = []

for module_name in modules_to_test:
    try:
        mod = importlib.import_module(module_name)
        success.append(module_name)
        print(f"✓ {module_name:30} OK")
    except Exception as e:
        failed.append((module_name, str(e)[:80]))
        print(f"✗ {module_name:30} FAILED: {str(e)[:50]}")

print("="*60)
print(f"Result: {len(success)}/{len(modules_to_test)} modules loaded")

if failed:
    print(f"\n⚠ {len(failed)} module(s) failed to import:")
    for m, err in failed:
        print(f"  - {m}: {err}")
    sys.exit(1)
else:
    print("\n★ SUCCESS! All imports working - codebase ready to run!")
    sys.exit(0)
