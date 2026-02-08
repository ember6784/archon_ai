"""
OpenClaw End-to-End Test

Interactive test for the full integration pipeline.
"""

import asyncio
import websockets
import json
from datetime import datetime
from typing import Optional

GATEWAY_URL = "ws://localhost:18789"
GATEWAY_TOKEN = "test_token_123"


class E2ETester:
    """End-to-end tester for OpenClaw integration."""
    
    def __init__(self):
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.messages_received = []
        
    async def connect(self):
        """Connect to Gateway."""
        uri = f"{GATEWAY_URL}/?token={GATEWAY_TOKEN}"
        self.ws = await websockets.connect(uri)
        print("[+] Connected to Gateway")
        
    async def disconnect(self):
        """Disconnect from Gateway."""
        if self.ws:
            await self.ws.close()
            print("[-] Disconnected")
    
    async def listen(self, duration: int = 10):
        """Listen for messages."""
        print(f"\n🔈 Listening for {duration} seconds...")
        start_time = datetime.now()
        
        while (datetime.now() - start_time).seconds < duration:
            try:
                msg = await asyncio.wait_for(self.ws.recv(), timeout=1)
                data = json.loads(msg)
                self.messages_received.append(data)
                
                msg_type = data.get('type', 'unknown')
                print(f"   [MSG] [{msg_type}] {json.dumps(data, ensure_ascii=False)[:100]}...")
                
            except asyncio.TimeoutError:
                continue
    
    async def send_test_message(self):
        """Send a test message through the gateway."""
        test_msg = {
            "type": "test",
            "timestamp": datetime.now().isoformat(),
            "data": {"message": "Hello from E2E test!"}
        }
        await self.ws.send(json.dumps(test_msg))
        print(f"[SENT] {test_msg}")
    
    def print_summary(self):
        """Print test summary."""
        print("\n" + "=" * 60)
        print("Test Summary")
        print("=" * 60)
        print(f"Messages received: {len(self.messages_received)}")
        
        if self.messages_received:
            print("\nMessage types:")
            types = {}
            for msg in self.messages_received:
                msg_type = msg.get('type', 'unknown')
                types[msg_type] = types.get(msg_type, 0) + 1
            for msg_type, count in types.items():
                print(f"  - {msg_type}: {count}")


async def interactive_mode():
    """Interactive test mode."""
    tester = E2ETester()
    
    try:
        await tester.connect()
        
        print("\n" + "=" * 60)
        print("Interactive Menu")
        print("=" * 60)
        print("1. Listen for messages (10s)")
        print("2. Send test message")
        print("3. Listen for messages (30s)")
        print("4. Exit")
        
        while True:
            choice = input("\nSelect option (1-4): ").strip()
            
            if choice == "1":
                await tester.listen(10)
            elif choice == "2":
                await tester.send_test_message()
            elif choice == "3":
                await tester.listen(30)
            elif choice == "4":
                break
            else:
                print("Invalid option")
        
        tester.print_summary()
        
    finally:
        await tester.disconnect()


async def quick_test():
    """Quick non-interactive test."""
    tester = E2ETester()
    
    try:
        await tester.connect()
        await tester.listen(5)
        tester.print_summary()
    finally:
        await tester.disconnect()


if __name__ == "__main__":
    import sys
    
    if "--interactive" in sys.argv:
        asyncio.run(interactive_mode())
    else:
        asyncio.run(quick_test())
