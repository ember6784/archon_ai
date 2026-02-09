"""
OpenClaw Gateway Client - Protocol v3

WebSocket client с поддержкой handshake протокола OpenClaw v3.
"""

from typing import Optional, Callable, Awaitable, Any, Dict
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
import asyncio
import json
import logging
import uuid
from pathlib import Path

try:
    import websockets
    from websockets.client import WebSocketClientProtocol
    WEBSOCKETS_AVAILABLE = True
except ImportError:
    WEBSOCKETS_AVAILABLE = False

try:
    import nacl.signing
    import nacl.encoding
    import base64
    NACL_AVAILABLE = True
except ImportError:
    NACL_AVAILABLE = False

logger = logging.getLogger(__name__)


class DeviceAuth:
    """
    Device Authentication using Ed25519 signatures.

    Generates and manages Ed25519 key pairs for device authentication
    with OpenClaw Gateway.
    """

    def __init__(self, key_path: Optional[str] = None):
        if not NACL_AVAILABLE:
            raise ImportError("PyNaCl is required for device authentication. Install with: pip install pynacl")

        if key_path and Path(key_path).exists():
            self._load_keys(key_path)
        else:
            self._generate_keys()
            if key_path:
                self._save_keys(key_path)

    def _generate_keys(self):
        """Generate new Ed25519 key pair."""
        self.signing_key = nacl.signing.SigningKey.generate()
        self.verify_key = self.signing_key.verify_key
        logger.debug("[DeviceAuth] Generated new Ed25519 key pair")

    def _load_keys(self, key_path: str):
        """Load keys from file."""
        from pathlib import Path
        path = Path(key_path)
        if not path.exists():
            raise FileNotFoundError(f"Key file not found: {key_path}")

        # For simplicity, store as base64 encoded raw bytes
        # In production, use proper key management
        with open(path, 'rb') as f:
            data = f.read().decode().strip()

        # Assume format: private_key\npublic_key
        lines = data.split('\n')
        if len(lines) != 2:
            raise ValueError("Invalid key file format")

        private_raw = base64.urlsafe_b64decode(lines[0])
        public_raw = base64.urlsafe_b64decode(lines[1])

        self.signing_key = nacl.signing.SigningKey(private_raw)
        self.verify_key = nacl.signing.VerifyKey(public_raw)
        logger.debug("[DeviceAuth] Loaded keys from file")

    def _save_keys(self, key_path: str):
        """Save keys to file."""
        from pathlib import Path
        path = Path(key_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        private_b64 = base64.urlsafe_b64encode(self.signing_key.encode()).decode()
        public_b64 = base64.urlsafe_b64encode(self.verify_key.encode()).decode()

        with open(path, 'w') as f:
            f.write(f"{private_b64}\n{public_b64}")
        logger.debug(f"[DeviceAuth] Saved keys to {key_path}")

    def sign_payload(self, payload: str) -> str:
        """
        Sign a payload string and return base64-encoded signature.

        Args:
            payload: String to sign

        Returns:
            Base64-encoded detached signature
        """
        signature = self.signing_key.sign(payload.encode(), encoder=nacl.encoding.RawEncoder)
        return base64.urlsafe_b64encode(signature).decode()

    def get_public_key_raw(self) -> str:
        """
        Get the public key as base64-encoded raw bytes.

        Returns:
            Base64-encoded public key
        """
        raw = self.verify_key.encode(encoder=nacl.encoding.RawEncoder)
        return base64.urlsafe_b64encode(raw).decode()

    def verify_signature(self, payload: str, signature_b64: str) -> bool:
        """
        Verify a signature against a payload.

        Args:
            payload: Original payload
            signature_b64: Base64-encoded signature

        Returns:
            True if signature is valid
        """
        try:
            signature = base64.urlsafe_b64decode(signature_b64)
            self.verify_key.verify(payload.encode(), signature)
            return True
        except Exception:
            return False


class GatewayState(Enum):
    """Gateway connection states."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    HANDSHAKING = "handshaking"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    ERROR = "error"


@dataclass
class GatewayMessage:
    """OpenClaw Protocol v3 message structure."""
    type: str  # req, res, event
    id: Optional[str] = None
    method: Optional[str] = None  # для req
    params: Dict[str, Any] = field(default_factory=dict)
    event: Optional[str] = None  # для event
    payload: Dict[str, Any] = field(default_factory=dict)
    ok: Optional[bool] = None  # для res
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        data = {"type": self.type}
        if self.id:
            data["id"] = self.id
        if self.method:
            data["method"] = self.method
        if self.params:
            data["params"] = self.params
        if self.event:
            data["event"] = self.event
        if self.payload:
            data["payload"] = self.payload
        if self.ok is not None:
            data["ok"] = self.ok
        return json.dumps(data)
    
    @classmethod
    def from_json(cls, json_str: str) -> "GatewayMessage":
        """Create from JSON string."""
        data = json.loads(json_str)
        return cls(
            type=data.get("type", "message"),
            id=data.get("id"),
            method=data.get("method"),
            params=data.get("params", {}),
            event=data.get("event"),
            payload=data.get("payload", {}),
            ok=data.get("ok")
        )


@dataclass
class GatewayConfig:
    """Configuration for Gateway connection."""
    url: str = "ws://localhost:18789"
    client_id: str = "archon-ai"
    client_version: str = "0.1.0"
    platform: str = "python"
    role: str = "operator"
    scopes: list = field(default_factory=lambda: ["operator.read", "operator.write"])
    reconnect: bool = True
    reconnect_delay: float = 5.0
    tick_interval: float = 15.0  # heartbeat interval from gateway
    device_key_path: Optional[str] = None  # Path to store/load device keys


class GatewayClientV3:
    """
    OpenClaw Gateway Client - Protocol v3.
    
    Реализует полный handshake:
    1. Подключение WebSocket
    2. Ожидание connect.challenge
    3. Отправка connect request
    4. Получение hello-ok
    5. Heartbeat (tick)
    """
    
    def __init__(self, config: Optional[GatewayConfig] = None):
        if not WEBSOCKETS_AVAILABLE:
            raise ImportError(
                "websockets package is required. "
                "Install with: pip install websockets"
            )

        self.config = config or GatewayConfig()
        self._state = GatewayState.DISCONNECTED
        self._ws: Optional[WebSocketClientProtocol] = None
        self._message_handlers: Dict[str, Callable] = {}
        self._event_handlers: Dict[str, Callable] = {}
        self._running = False
        self._receive_task: Optional[asyncio.Task] = None
        self._tick_task: Optional[asyncio.Task] = None
        self._device_token: Optional[str] = None
        self._protocol_version: int = 3

        # Initialize device authentication
        self._device_auth = None
        if NACL_AVAILABLE:
            try:
                self._device_auth = DeviceAuth(self.config.device_key_path)
                logger.info("[GatewayV3] Device authentication enabled")
            except Exception as e:
                logger.warning(f"[GatewayV3] Failed to initialize device auth: {e}")
        else:
            logger.warning("[GatewayV3] PyNaCl not available, device auth disabled")

        logger.info(f"[GatewayV3] Initialized for {self.config.url}")
    
    @property
    def state(self) -> GatewayState:
        return self._state
    
    @property
    def is_connected(self) -> bool:
        return self._state == GatewayState.CONNECTED
    
    async def connect(self) -> bool:
        """Connect and perform handshake."""
        if self._state in (GatewayState.CONNECTED, GatewayState.CONNECTING, GatewayState.HANDSHAKING):
            logger.warning(f"[GatewayV3] Already in state: {self._state}")
            return True
        
        self._state = GatewayState.CONNECTING
        
        try:
            logger.info(f"[GatewayV3] Connecting to {self.config.url}...")
            self._ws = await websockets.connect(self.config.url)
            self._running = True
            
            # Start receive loop for handshake
            self._receive_task = asyncio.create_task(self._receive_loop())
            
            # Wait for connection to complete (or fail)
            timeout = 30.0
            start = asyncio.get_event_loop().time()
            while self._state == GatewayState.CONNECTING:
                if asyncio.get_event_loop().time() - start > timeout:
                    raise TimeoutError("Handshake timeout")
                await asyncio.sleep(0.1)
            
            return self._state == GatewayState.CONNECTED
            
        except Exception as e:
            logger.error(f"[GatewayV3] Connection failed: {e}")
            self._state = GatewayState.ERROR
            if self.config.reconnect:
                asyncio.create_task(self._reconnect())
            return False
    
    async def disconnect(self):
        """Disconnect from Gateway."""
        self._running = False
        
        if self._tick_task:
            self._tick_task.cancel()
            try:
                await self._tick_task
            except asyncio.CancelledError:
                pass
        
        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
        
        if self._ws:
            await self._ws.close()
            self._ws = None
        
        self._state = GatewayState.DISCONNECTED
        logger.info("[GatewayV3] Disconnected")
    
    async def send(self, message: GatewayMessage) -> bool:
        """Send a message to Gateway."""
        if self._state != GatewayState.CONNECTED or not self._ws:
            logger.warning(f"[GatewayV3] Cannot send in state: {self._state}")
            return False
        
        try:
            await self._ws.send(message.to_json())
            return True
        except Exception as e:
            logger.error(f"[GatewayV3] Send failed: {e}")
            return False
    
    async def send_request(self, method: str, params: Dict[str, Any]) -> str:
        """Send a request and return request ID."""
        req_id = str(uuid.uuid4())
        message = GatewayMessage(
            type="req",
            id=req_id,
            method=method,
            params=params
        )
        if await self.send(message):
            return req_id
        return ""
    
    def on_event(self, event_type: str, handler: Callable):
        """Register event handler."""
        self._event_handlers[event_type] = handler
        logger.debug(f"[GatewayV3] Registered handler for event: {event_type}")
    
    def on_message(self, msg_type: str, handler: Callable):
        """Register message handler."""
        self._message_handlers[msg_type] = handler
    
    async def _receive_loop(self):
        """Main receive loop."""
        challenge_received = False
        
        while self._running and self._ws:
            try:
                raw = await self._ws.recv()
                message = GatewayMessage.from_json(raw)
                
                # Handle handshake
                if not challenge_received and message.type == "event" and message.event == "connect.challenge":
                    challenge_received = True
                    self._state = GatewayState.HANDSHAKING
                    await self._send_connect(message.payload.get("nonce"), message.payload.get("ts"))
                    continue
                
                # Handle response (hello-ok)
                if message.type == "res":
                    if not message.ok:
                        logger.error(f"[GatewayV3] Connect failed: {message.payload}")
                    if message.ok and message.payload.get("type") == "hello-ok":
                        self._protocol_version = message.payload.get("protocol", 3)
                        policy = message.payload.get("policy", {})
                        tick_interval = policy.get("tickIntervalMs", 15000) / 1000

                        # Extract device token if present
                        auth = message.payload.get("auth", {})
                        self._device_token = auth.get("deviceToken")

                        self._state = GatewayState.CONNECTED
                        logger.info(f"[GatewayV3] Connected! Protocol v{self._protocol_version}")

                        # Start heartbeat
                        self._tick_task = asyncio.create_task(self._tick_loop(tick_interval))
                        continue
                
                # Handle events
                if message.type == "event" and message.event:
                    handler = self._event_handlers.get(message.event)
                    if handler:
                        try:
                            await handler(message)
                        except Exception as e:
                            logger.error(f"[GatewayV3] Event handler error: {e}")
                    continue
                
                # Handle responses
                handler = self._message_handlers.get(message.type)
                if handler:
                    try:
                        await handler(message)
                    except Exception as e:
                        logger.error(f"[GatewayV3] Message handler error: {e}")
                
            except websockets.exceptions.ConnectionClosed:
                logger.warning("[GatewayV3] Connection closed")
                break
            except Exception as e:
                logger.error(f"[GatewayV3] Receive error: {e}")
        
        # Connection lost
        if self._running and self.config.reconnect:
            await self._reconnect()
    
    async def _send_connect(self, nonce: Optional[str], ts: Optional[int]):
        """Send connect request."""
        req_id = str(uuid.uuid4())

        # Get token from environment or device_token
        import os
        env_token = os.getenv("OPENCLAW_GATEWAY_TOKEN")
        auth_token = env_token or self._device_token or ""

        # Build auth object (only include if we have credentials)
        # Note: Gateway requires either auth.token OR device auth (signature)
        # For --allow-unconfigured mode, don't send auth at all if no proper token
        auth = None
        # Only send auth if we have a non-test token
        # Test tokens like "test_token_123" won't be accepted by Gateway
        if auth_token and not auth_token.startswith("test_"):
            auth = {"token": auth_token}

        params = {
            "minProtocol": 3,
            "maxProtocol": 3,
            "client": {
                "id": self.config.client_id,
                "version": self.config.client_version,
                "platform": self.config.platform,
                "mode": "backend"  # Valid modes: webchat, cli, ui, backend, node, probe, test
            },
            "role": self.config.role,
            "scopes": self.config.scopes,
            "caps": [],
            "locale": "en-US",
            "userAgent": f"{self.config.client_id}/{self.config.client_version}",
        }

        # Only add auth if we have a real token (not test token)
        if auth:
            params["auth"] = auth

        # Add device authentication if available
        # Uses Ed25519 signing to prevent replay attacks
        if nonce and self._device_auth:
            payload_to_sign = nonce  # Challenge from gateway
            params["device"] = {
                "id": self.config.client_id,
                "publicKey": self._device_auth.get_public_key_raw(),
                "signature": self._device_auth.sign_payload(payload_to_sign),
                "signedAt": ts,
                "nonce": nonce
            }

        message = GatewayMessage(
            type="req",
            id=req_id,
            method="connect",
            params=params
        )

        await self._ws.send(message.to_json())
        logger.debug(f"[GatewayV3] Sent connect request")
    
    async def _tick_loop(self, interval: float):
        """Send periodic tick (heartbeat)."""
        while self._running and self._state == GatewayState.CONNECTED:
            try:
                await asyncio.sleep(interval)
                if self._state == GatewayState.CONNECTED:
                    await self.send_request("tick", {})
                    logger.debug("[GatewayV3] Tick sent")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[GatewayV3] Tick error: {e}")
    
    async def _reconnect(self):
        """Attempt to reconnect."""
        self._state = GatewayState.RECONNECTING
        
        while self._running and self.config.reconnect:
            logger.info(f"[GatewayV3] Reconnecting in {self.config.reconnect_delay}s...")
            await asyncio.sleep(self.config.reconnect_delay)
            
            if await self.connect():
                break


# Backward compatibility
GatewayClient = GatewayClientV3
