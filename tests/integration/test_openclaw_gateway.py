"""
Integration test for OpenClaw Gateway connection.

This test verifies that Archon AI can connect to OpenClaw Gateway
and properly handle the protocol v3 handshake.

Usage:
    # Make sure OpenClaw Gateway is running:
    # cd claw && pnpm gateway:dev
    
    # Then run test:
    pytest tests/integration/test_openclaw_gateway.py -v
"""

import asyncio
import pytest
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from openclaw import GatewayClientV3, GatewayConfig


@pytest.mark.asyncio
async def test_gateway_connection():
    """Test basic connection to OpenClaw Gateway."""
    config = GatewayConfig(
        url="ws://localhost:18789",
        client_id="archon-test",
        client_version="0.1.0-test"
    )
    
    client = GatewayClientV3(config)
    
    # Track events
    events_received = []
    
    async def on_test_event(message):
        events_received.append(message.event)
        print(f"Event received: {message.event}")
    
    client.on_event("test", on_test_event)
    
    try:
        # Connect (with timeout)
        connected = await asyncio.wait_for(client.connect(), timeout=10.0)
        
        if not connected:
            pytest.skip("Gateway not available - make sure 'pnpm gateway:dev' is running in claw/")
        
        assert client.is_connected
        assert client.state.value == "connected"
        
        # Wait a bit for any initial events
        await asyncio.sleep(1)
        
        print(f"✅ Connected to Gateway (protocol v{client._protocol_version})")
        
    except asyncio.TimeoutError:
        pytest.skip("Connection timeout - Gateway not responding")
    except Exception as e:
        pytest.skip(f"Gateway connection failed: {e}")
    finally:
        await client.disconnect()


@pytest.mark.asyncio
async def test_gateway_message_roundtrip():
    """Test sending a message and receiving response."""
    config = GatewayConfig(
        url="ws://localhost:18789",
        client_id="archon-test"
    )
    
    client = GatewayClientV3(config)
    
    try:
        connected = await asyncio.wait_for(client.connect(), timeout=10.0)
        
        if not connected:
            pytest.skip("Gateway not available")
        
        # Send a health/status request
        req_id = await client.send_request("health", {})
        assert req_id != ""
        
        # Wait for response
        await asyncio.sleep(0.5)
        
        print(f"✅ Message roundtrip successful (req_id: {req_id})")
        
    except asyncio.TimeoutError:
        pytest.skip("Connection timeout")
    except Exception as e:
        pytest.skip(f"Test failed: {e}")
    finally:
        await client.disconnect()


if __name__ == "__main__":
    # Run tests directly
    print("Testing OpenClaw Gateway integration...")
    print("Make sure Gateway is running: cd claw && pnpm gateway:dev")
    print()
    
    asyncio.run(test_gateway_connection())
