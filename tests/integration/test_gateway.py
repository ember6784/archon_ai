"""
OpenClaw Gateway Connection Test

Tests WebSocket connection to OpenClaw Gateway.
"""

import asyncio
import websockets
import json
from datetime import datetime

GATEWAY_URL = "ws://localhost:18789"
GATEWAY_TOKEN = "test_token_123"


async def test_gateway_connection():
    """Test basic WebSocket connection to Gateway."""
    
    print("=" * 60)
    print("OpenClaw Gateway Integration Test")
    print("=" * 60)
    print(f"Connecting to Gateway at {GATEWAY_URL}...")
    
    try:
        # Connect with token
        uri = f"{GATEWAY_URL}/?token={GATEWAY_TOKEN}"
        
        async with websockets.connect(
            uri,
            close_timeout=5,
            ping_timeout=None
        ) as ws:
            print("[+] Connected!")

            # Wait for hello message
            try:
                hello = await asyncio.wait_for(ws.recv(), timeout=3)
                hello_data = json.loads(hello)
                print(f"   Protocol version: {hello_data.get('protocol', 'unknown')}")
                print(f"   Device token: {hello_data.get('deviceToken', 'N/A')[:30]}...")
            except asyncio.TimeoutError:
                print("   No hello message received (might be normal)")
            
            # Listen for messages
            print("\nListening for messages (5 seconds)...")
            messages_count = 0
            start_time = datetime.now()
            
            while (datetime.now() - start_time).seconds < 5:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=1)
                    data = json.loads(msg)
                    messages_count += 1
                    print(f"   [MSG] {data.get('type', 'unknown')}: {str(data)[:80]}...")
                except asyncio.TimeoutError:
                    continue
            
            print(f"Messages received: {messages_count}")
            print("\nDisconnected.")
            
    except websockets.exceptions.WebSocketException as e:
        print(f"[-] WebSocket error: {e}")
        return False
    except Exception as e:
        print(f"[-] Error: {e}")
        return False
    
    return True


if __name__ == "__main__":
    asyncio.run(test_gateway_connection())
