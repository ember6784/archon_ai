"""
OpenClaw Gateway Client

WebSocket client for connecting to OpenClaw Gateway.
This is a lightweight wrapper around the OpenClaw Gateway protocol.
"""

from typing import Optional, Callable, Awaitable, Any, Dict
from dataclasses import dataclass
from enum import Enum
import asyncio
import json
import logging

try:
    import websockets
    WEBSOCKETS_AVAILABLE = True
except ImportError:
    WEBSOCKETS_AVAILABLE = False

logger = logging.getLogger(__name__)


class GatewayState(Enum):
    """Gateway connection states."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    ERROR = "error"


@dataclass
class GatewayMessage:
    """Message structure for Gateway communication."""
    type: str  # message, event, response, error
    data: Dict[str, Any]
    id: Optional[str] = None
    timestamp: Optional[float] = None

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps({
            "type": self.type,
            "data": self.data,
            "id": self.id,
            "timestamp": self.timestamp
        })

    @classmethod
    def from_json(cls, json_str: str) -> "GatewayMessage":
        """Create from JSON string."""
        data = json.loads(json_str)
        return cls(
            type=data.get("type", "message"),
            data=data.get("data", {}),
            id=data.get("id"),
            timestamp=data.get("timestamp")
        )


class GatewayClient:
    """
    WebSocket client for OpenClaw Gateway.

    Handles connection, reconnection, and message routing.
    """

    def __init__(
        self,
        url: str = "ws://localhost:18789",
        reconnect: bool = True,
        reconnect_delay: float = 5.0,
        ping_interval: float = 30.0
    ):
        if not WEBSOCKETS_AVAILABLE:
            raise ImportError(
                "websockets package is required. "
                "Install with: pip install websockets"
            )

        self.url = url
        self.reconnect = reconnect
        self.reconnect_delay = reconnect_delay
        self.ping_interval = ping_interval

        self._state = GatewayState.DISCONNECTED
        self._ws: Optional[Any] = None
        self._message_handlers: Dict[str, Callable] = {}
        self._event_handlers: Dict[str, Callable] = {}
        self._running = False
        self._task: Optional[asyncio.Task] = None

        logger.info(f"GatewayClient initialized for {url}")

    async def connect(self) -> bool:
        """
        Connect to the Gateway.

        Returns:
            True if connection successful
        """
        if self._state in (GatewayState.CONNECTED, GatewayState.CONNECTING):
            logger.warning(f"Already connected or connecting: {self._state}")
            return True

        self._state = GatewayState.CONNECTING

        try:
            logger.info(f"Connecting to Gateway at {self.url}...")
            self._ws = await websockets.connect(
                self.url,
                ping_interval=self.ping_interval
            )
            self._state = GatewayState.CONNECTED
            logger.info("Connected to Gateway")

            # Start receive loop
            self._running = True
            self._task = asyncio.create_task(self._receive_loop())

            return True

        except Exception as e:
            logger.error(f"Failed to connect to Gateway: {e}")
            self._state = GatewayState.ERROR

            if self.reconnect:
                asyncio.create_task(self._reconnect())

            return False

    async def disconnect(self):
        """Disconnect from the Gateway."""
        self._running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        if self._ws:
            await self._ws.close()
            self._ws = None

        self._state = GatewayState.DISCONNECTED
        logger.info("Disconnected from Gateway")

    async def send(self, message: GatewayMessage) -> bool:
        """
        Send a message to the Gateway.

        Args:
            message: Message to send

        Returns:
            True if sent successfully
        """
        if self._state != GatewayState.CONNECTED:
            logger.warning(f"Cannot send in state: {self._state}")
            return False

        try:
            await self._ws.send(message.to_json())
            return True
        except Exception as e:
            logger.error(f"Failed to send message: {e}")
            return False

    async def send_command(
        self,
        command: str,
        data: Dict[str, Any]
    ) -> bool:
        """
        Send a command to the Gateway.

        Args:
            command: Command name
            data: Command data

        Returns:
            True if sent successfully
        """
        message = GatewayMessage(
            type="command",
            data={"command": command, **data}
        )
        return await self.send(message)

    def on_message(self, message_type: str, handler: Callable):
        """
        Register a message handler.

        Args:
            message_type: Type of message to handle
            handler: Async callback function
        """
        self._message_handlers[message_type] = handler
        logger.debug(f"Registered handler for message type: {message_type}")

    def on_event(self, event_type: str, handler: Callable):
        """
        Register an event handler.

        Args:
            event_type: Type of event to handle
            handler: Async callback function
        """
        self._event_handlers[event_type] = handler
        logger.debug(f"Registered handler for event type: {event_type}")

    async def _receive_loop(self):
        """Receive and process messages from Gateway."""
        while self._running and self._state == GatewayState.CONNECTED:
            try:
                raw = await asyncio.wait_for(
                    self._ws.recv(),
                    timeout=1.0
                )

                message = GatewayMessage.from_json(raw)
                await self._handle_message(message)

            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Error in receive loop: {e}")
                break

        # Connection lost
        if self._running and self.reconnect:
            await self._reconnect()

    async def _handle_message(self, message: GatewayMessage):
        """Route message to appropriate handler."""
        if message.type == "event":
            event_type = message.data.get("event")
            handler = self._event_handlers.get(event_type)
            if handler:
                try:
                    await handler(message)
                except Exception as e:
                    logger.error(f"Event handler error: {e}")
        else:
            handler = self._message_handlers.get(message.type)
            if handler:
                try:
                    await handler(message)
                except Exception as e:
                    logger.error(f"Message handler error: {e}")

    async def _reconnect(self):
        """Attempt to reconnect to Gateway."""
        self._state = GatewayState.RECONNECTING

        while self._running and self.reconnect:
            logger.info(f"Reconnecting in {self.reconnect_delay}s...")
            await asyncio.sleep(self.reconnect_delay)

            if await self.connect():
                break

    def get_state(self) -> GatewayState:
        """Get current connection state."""
        return self._state

    def get_stats(self) -> Dict[str, Any]:
        """Get client statistics."""
        return {
            "state": self._state.value,
            "url": self.url,
            "reconnect": self.reconnect,
            "message_handlers": list(self._message_handlers.keys()),
            "event_handlers": list(self._event_handlers.keys())
        }


# Singleton instance
_gateway_client: Optional[GatewayClient] = None


def get_gateway_client(
    url: str = "ws://localhost:18789"
) -> GatewayClient:
    """Get or create the global Gateway client."""
    global _gateway_client
    if _gateway_client is None:
        _gateway_client = GatewayClient(url=url)
    return _gateway_client
