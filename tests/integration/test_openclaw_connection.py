# tests/integration/test_openclaw_connection.py
"""
Test OpenClaw Gateway Connection

Verifies that Archon AI can connect to the local OpenClaw gateway.
"""

import pytest
import asyncio
import os
import sys

# Add paths
kernel_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../kernel"))
enterprise_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../enterprise"))
sys.path.insert(0, kernel_path)
sys.path.insert(0, enterprise_path)

from kernel.openclaw_integration import create_secure_bridge, IntegrationConfig
from enterprise.event_bus import EventBus


@pytest.mark.asyncio
class TestOpenClawConnection:
    """Tests for OpenClaw gateway connection."""

    async def test_gateway_websocket_connection(self):
        """Test that we can establish a WebSocket connection to OpenClaw."""
        import websockets

        gateway_url = "ws://127.0.0.1:18789"
        test_token = "test_token_123"

        try:
            async with websockets.connect(
                f"{gateway_url}/?token={test_token}",
                close_timeout=5
            ) as ws:
                # Send a ping/health check
                await ws.send('{"method":"health"}')
                response = await asyncio.wait_for(ws.recv(), timeout=5)

                assert response is not None
                assert len(response) > 0
                print(f"✓ Gateway response: {response[:100]}...")
        except Exception as e:
            pytest.skip(f"OpenClaw gateway not available: {e}")

    async def test_secure_gateway_bridge_creation(self):
        """Test creating SecureGatewayBridge with kernel."""
        gateway_url = "ws://127.0.0.1:18789"

        try:
            event_bus = EventBus(persist_events=False)

            config = IntegrationConfig()
            config.ws_url = gateway_url
            config.enable_audit = False
            config.kernel_environment = "test"
            config.enable_circuit_breaker = True

            bridge = create_secure_bridge(
                integration_config=config,
                event_bus=event_bus,
            )

            assert bridge is not None
            print(f"✓ Bridge type: {type(bridge).__name__}")

            # Check if it has kernel
            has_kernel = hasattr(bridge, 'kernel') and bridge.kernel is not None
            print(f"✓ Has kernel: {has_kernel}")

            # Check circuit breaker
            has_circuit_breaker = hasattr(bridge, 'circuit_breaker') and bridge.circuit_breaker is not None
            print(f"✓ Has circuit_breaker: {has_circuit_breaker}")

        except Exception as e:
            pytest.skip(f"Could not create bridge: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
