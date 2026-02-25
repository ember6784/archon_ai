"""
Real Messages Test

Waits for and displays real messages from Telegram/WhatsApp/etc.
"""

import asyncio
import sys
import os
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List

# Add archon_ai to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from openclaw import GatewayClientV3, GatewayConfig
from openclaw.gateway_v3 import GatewayMessage

# Enable debug logging
logging.basicConfig(level=logging.DEBUG, format='%(name)s - %(levelname)s - %(message)s')

GATEWAY_URL = "ws://127.0.0.1:18789"
# Don't set test token - Gateway with --allow-unconfigured should accept connections without auth
# GATEWAY_TOKEN = "test_token_123"


class MessageListener:
    """Listens for real messages from channels."""

    def __init__(self):
        self.messages: List[Dict[str, Any]] = []
        self.running = True
        self.gateway: GatewayClientV3 = None

    async def connect_and_listen(self):
        """Connect to Gateway and listen for messages."""

        print("=" * 60)
        print("Real Messages Listener")
        print("=" * 60)
        print(f"Connecting to {GATEWAY_URL}...")

        try:
            # Create gateway client
            config = GatewayConfig(
                url=GATEWAY_URL,
                client_id="test_listener",
                client_version="0.1.0",
                role="operator"
            )
            self.gateway = GatewayClientV3(config)

            # Register event handler for messages
            self.gateway.on_event("message", self._handle_gateway_message)
            self.gateway.on_event("health", self._handle_health_event)

            # Connect
            print("Starting connection...")
            connected = await self.gateway.connect()

            if not connected:
                print(f"[-] Failed to connect to Gateway. State: {self.gateway.state}")
                return

            print("[+] Connected! Waiting for messages...")
            print(f"   Device token: {self.gateway._device_token}")
            print("   (Send a message to @quant_dev_ai_bot in Telegram)")
            print("   (Press Ctrl+C to stop)\n")

            # Keep running
            while self.running:
                await asyncio.sleep(1)

        except KeyboardInterrupt:
            print("\n\nStopping...")
        except Exception as e:
            print(f"[-] Error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            if self.gateway:
                await self.gateway.disconnect()
    
    async def _handle_gateway_message(self, message: GatewayMessage):
        """Handle incoming message from Gateway."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        payload = message.payload

        self.messages.append(payload)

        # Format and display
        print(f"[{timestamp}] [MSG] message event")
        print(f"   [CHAN] Channel: {payload.get('channel', 'unknown')}")
        print(f"   [USER] User: {payload.get('user_name', 'Unknown')} (ID: {payload.get('user_id', 'unknown')})")
        print(f"   [TEXT] {payload.get('text', '')[:100]}")

        # Send to Archon AI for processing
        await self._process_with_archon(payload)

    async def _handle_health_event(self, message: GatewayMessage):
        """Handle health check event."""
        print(f"[{datetime.now().strftime('%H:%M:%S')}] [HEALTH] Gateway is healthy")

    async def _process_with_archon(self, msg: Dict[str, Any]):
        """Simulate processing message through Archon AI."""
        print("   [PROCESS] Processing through Archon AI...")

        # Simulate SecureGatewayBridge processing
        text = msg.get('text', '')

        # Check through kernel
        try:
            from kernel.execution_kernel import ExecutionKernel, ExecutionContext

            kernel = ExecutionKernel()
            context = ExecutionContext(
                agent_id=msg.get('user_id', ''),
                operation="telegram_message",
                parameters={"message": text}
            )

            result = await kernel.validate_pre(context)

            if result.approved:
                print(f"   [+] Kernel: {result.reason}")

                # Generate simple response
                response = f"Echo: {text}"
                print(f"   [RESP] {response}")
            else:
                print(f"   [-] Kernel blocked: {result.reason}")
        except Exception as e:
            print(f"   [ERROR] Kernel processing failed: {e}")

    def print_summary(self):
        """Print summary of received messages."""
        print("\n" + "=" * 60)
        print("Session Summary")
        print("=" * 60)
        print(f"Total messages: {len(self.messages)}")


async def main():
    """Main entry point."""
    listener = MessageListener()
    await listener.connect_and_listen()
    listener.print_summary()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nExiting...")
