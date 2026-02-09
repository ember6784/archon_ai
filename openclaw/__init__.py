"""
OpenClaw Integration

This package provides the integration layer with OpenClaw:

- Gateway: WebSocket Gateway client
- Channels: Channel managers for various platforms
- Sandbox: Docker sandbox wrapper
"""

__version__ = "0.1.0"

from openclaw.gateway_v3 import GatewayClientV3, GatewayClient, GatewayConfig, DeviceAuth
from openclaw.channels import ChannelManager

__all__ = [
    "GatewayClientV3",
    "GatewayClient",  # backward compatibility
    "GatewayConfig",
    "DeviceAuth",
    "ChannelManager",
]
