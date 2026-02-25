#!/usr/bin/env python3
"""
Quick import check for all new components.
Run this to verify everything is importable.
"""

import sys

def check_import(module_name, items=None):
    """Check if module imports correctly."""
    try:
        module = __import__(module_name, fromlist=[''])
        if items:
            for item in items:
                if not hasattr(module, item):
                    print(f"  ❌ {module_name}.{item} not found")
                    return False
        print(f"  ✅ {module_name}")
        return True
    except Exception as e:
        print(f"  ❌ {module_name}: {e}")
        return False

print("Checking Archon AI + OpenClaw Integration Imports")
print("=" * 60)
print()

all_ok = True

print("1. OpenClaw Gateway Client:")
all_ok &= check_import("openclaw", ["GatewayClientV3", "GatewayConfig", "GatewayClient"])

print("\n2. Kernel Components:")
all_ok &= check_import("kernel", [
    "ExecutionKernel",
    "DynamicCircuitBreaker",
    "CircuitState"
])

print("\n3. Enterprise Components:")
all_ok &= check_import("enterprise.gateway_bridge", ["GatewayBridge", "ChannelMessage", "BridgeResponse"])
all_ok &= check_import("enterprise.event_bus", ["EventBus", "EventType"])
all_ok &= check_import("enterprise.openclaw_integration", [
    "create_secure_bridge",
    "SecureGatewayBridge",
    "IntegrationConfig"
])

print("\n4. MAT Components:")
all_ok &= check_import("mat", ["DebatePipeline", "CircuitBreaker", "LLMRouter"])

print()
print("=" * 60)
if all_ok:
    print("✅ All imports successful!")
    sys.exit(0)
else:
    print("❌ Some imports failed")
    sys.exit(1)
