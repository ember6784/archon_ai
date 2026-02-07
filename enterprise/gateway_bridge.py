"""
Gateway Bridge

Bridge between OpenClaw WebSocket Gateway and Enterprise security layer.
Handles message routing, RBAC checks, and Circuit Breaker enforcement.
"""

from typing import Optional, Callable, Dict, Any
from dataclasses import dataclass
from enum import Enum
import asyncio
import json
import logging

from enterprise.event_bus import EventBus, EventType, Event

logger = logging.getLogger(__name__)


class ChannelType(Enum):
    """Supported channel types from OpenClaw."""

    WHATSAPP = "whatsapp"
    TELEGRAM = "telegram"
    SLACK = "slack"
    DISCORD = "discord"
    GOOGLE_CHAT = "google_chat"
    SIGNAL = "signal"
    MS_TEAMS = "ms_teams"
    WEBCHAT = "webchat"
    IMESSAGE = "imessage"
    MATRIX = "matrix"
    ZALO = "zalo"


@dataclass
class ChannelMessage:
    """Message from an OpenClaw channel."""

    channel: ChannelType
    channel_id: str  # Specific channel/group ID
    user_id: str
    user_name: str
    message: str
    timestamp: float
    metadata: Dict[str, Any]
    message_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "channel": self.channel.value,
            "channel_id": self.channel_id,
            "user_id": self.user_id,
            "user_name": self.user_name,
            "message": self.message,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
            "message_id": self.message_id
        }


@dataclass
class BridgeResponse:
    """Response to send back through the Gateway."""

    success: bool
    response: str
    requires_approval: bool = False
    metadata: Dict[str, Any] = None
    error_code: Optional[str] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result = {
            "success": self.success,
            "response": self.response,
            "requires_approval": self.requires_approval,
            "metadata": self.metadata
        }
        if self.error_code:
            result["error_code"] = self.error_code
        return result


class GatewayBridge:
    """
    Bridge between OpenClaw Gateway and Enterprise security layer.

    Flow:
    1. Receive message from OpenClaw channel
    2. Check RBAC permissions
    3. Check Circuit Breaker autonomy level
    4. Route to appropriate handler
    5. Return response to channel
    6. Emit events to EventBus
    """

    def __init__(
        self,
        ws_url: str = "ws://localhost:18789",
        event_bus: Optional[EventBus] = None,
        rbac_checker: Optional[Callable] = None,
        circuit_breaker: Optional[Any] = None
    ):
        self.ws_url = ws_url
        self.event_bus = event_bus
        self.rbac_checker = rbac_checker
        self.circuit_breaker = circuit_breaker

        self.handlers: Dict[str, Callable] = {}
        self._running = False
        self._ws_connection = None

        logger.info(f"GatewayBridge initialized with ws_url={ws_url}")

    async def start(self):
        """Connect to OpenClaw Gateway and start listening."""
        if self._running:
            logger.warning("GatewayBridge already running")
            return

        self._running = True

        # Emit connection event
        if self.event_bus:
            await self.event_bus.publish(
                Event.create(
                    EventType.GATEWAY_CONNECTED,
                    {"ws_url": self.ws_url}
                )
            )

        logger.info("GatewayBridge started")

    async def stop(self):
        """Stop the bridge and disconnect."""
        self._running = False

        if self.event_bus:
            await self.event_bus.publish(
                Event.create(
                    EventType.GATEWAY_DISCONNECTED,
                    {"ws_url": self.ws_url}
                )
            )

        logger.info("GatewayBridge stopped")

    async def handle_message(
        self,
        message: ChannelMessage
    ) -> BridgeResponse:
        """
        Process incoming message through security layer.

        Args:
            message: Channel message to process

        Returns:
            BridgeResponse with result
        """
        try:
            # Emit message received event
            if self.event_bus:
                await self.event_bus.publish(
                    Event.create(
                        EventType.MESSAGE_RECEIVED,
                        message.to_dict(),
                        user_id=message.user_id,
                        tenant_id=message.metadata.get("tenant_id")
                    )
                )

            # Step 1: RBAC Check
            if self.rbac_checker:
                if not await self._check_rbac(message):
                    await self._log_denied_access(message, "rbac")
                    return BridgeResponse(
                        success=False,
                        response="Permission denied",
                        error_code="PERMISSION_DENIED"
                    )

            # Step 2: Circuit Breaker Check
            autonomy_level = None
            if self.circuit_breaker:
                autonomy_level = await self._get_autonomy_level()
                if not self._is_operation_allowed(message.message, autonomy_level):
                    return BridgeResponse(
                        success=False,
                        response=f"Operation not allowed in current mode ({autonomy_level})",
                        error_code="NOT_ALLOWED_IN_MODE"
                    )

            # Step 3: Route to handler
            handler = self._get_handler(message.message)
            if handler:
                response = await self._execute_handler(
                    handler,
                    message,
                    autonomy_level
                )
            else:
                response = await self._default_handler(message, autonomy_level)

            # Emit message sent event
            if self.event_bus:
                await self.event_bus.publish(
                    Event.create(
                        EventType.MESSAGE_SENT,
                        {
                            "message_id": message.message_id,
                            "response": response.to_dict()
                        },
                        user_id=message.user_id
                    )
                )

            return response

        except Exception as e:
            logger.error(f"Error handling message: {e}")
            return BridgeResponse(
                success=False,
                response=f"Internal error: {str(e)}",
                error_code="INTERNAL_ERROR"
            )

    async def _check_rbac(self, message: ChannelMessage) -> bool:
        """Check RBAC permissions for the message."""
        if not self.rbac_checker:
            return True

        action = self._infer_action(message.message)
        return await self.rbac_checker(
            user_id=message.user_id,
            channel=message.channel.value,
            action=action,
            message=message.message
        )

    async def _get_autonomy_level(self) -> str:
        """Get current autonomy level from Circuit Breaker."""
        if not self.circuit_breaker:
            return "GREEN"

        try:
            level = await self.circuit_breaker.check_level()
            return level.value if hasattr(level, 'value') else str(level)
        except Exception as e:
            logger.error(f"Error getting autonomy level: {e}")
            return "GREEN"

    def _is_operation_allowed(self, message: str, autonomy_level: str) -> bool:
        """Check if operation is allowed at current autonomy level."""
        if autonomy_level == "GREEN":
            return True

        msg_lower = message.lower()

        # Protected operations
        protected_patterns = [
            'core/', 'production/', 'security/', 'auth/',
            'delete ', 'drop ', 'rm -rf', 'truncate',
            'deploy', 'kubectl', 'terraform apply'
        ]

        if autonomy_level == "AMBER":
            # Block core operations
            for pattern in protected_patterns:
                if pattern in msg_lower:
                    return False
            return True

        elif autonomy_level == "RED":
            # Only allow read-only and canary
            read_only = msg_lower.startswith(('show', 'get', 'list', 'status', 'what is'))
            canary = 'canary' in msg_lower
            return read_only or canary

        elif autonomy_level == "BLACK":
            # Monitor only
            return msg_lower.startswith(('status', 'health', 'metrics'))

        return True

    def _infer_action(self, message: str) -> str:
        """Infer the action type from message content."""
        msg_lower = message.lower().strip()

        if msg_lower.startswith(('run', 'execute', 'exec', 'do')):
            return 'agent.execute'
        elif msg_lower.startswith(('show', 'get', 'list', 'status', 'what')):
            return 'agent.monitor'
        elif msg_lower.startswith(('deploy', 'push', 'ship')):
            return 'code.deploy'
        elif msg_lower.startswith(('delete', 'remove', 'rm')):
            return 'code.delete'
        elif msg_lower.startswith(('create', 'add', 'new')):
            return 'code.create'
        else:
            return 'agent.execute'  # Default to execute

    def _get_handler(self, message: str) -> Optional[Callable]:
        """Get handler for message based on pattern matching."""
        for pattern, handler in self.handlers.items():
            if pattern.lower() in message.lower():
                return handler
        return None

    async def _execute_handler(
        self,
        handler: Callable,
        message: ChannelMessage,
        autonomy_level: str
    ) -> BridgeResponse:
        """Execute the handler with error handling."""
        try:
            result = await handler(
                message=message,
                autonomy_level=autonomy_level
            )

            if isinstance(result, BridgeResponse):
                return result

            return BridgeResponse(
                success=True,
                response=str(result)
            )

        except Exception as e:
            logger.error(f"Handler error: {e}")
            return BridgeResponse(
                success=False,
                response=f"Handler error: {str(e)}",
                error_code="HANDLER_ERROR"
            )

    async def _default_handler(
        self,
        message: ChannelMessage,
        autonomy_level: str
    ) -> BridgeResponse:
        """Default message handler."""
        return BridgeResponse(
            success=True,
            response=f"Received: {message.message[:100]}",
            metadata={
                "autonomy_level": autonomy_level,
                "channel": message.channel.value
            }
        )

    async def _log_denied_access(self, message: ChannelMessage, reason: str):
        """Log denied access attempt."""
        logger.warning(
            f"Access denied for user={message.user_id} "
            f"channel={message.channel.value} reason={reason}"
        )

        if self.event_bus:
            await self.event_bus.publish(
                Event.create(
                    EventType.PERMISSION_DENIED,
                    {
                        "user_id": message.user_id,
                        "channel": message.channel.value,
                        "message": message.message[:200],
                        "reason": reason
                    },
                    user_id=message.user_id
                )
            )

    def register_handler(self, pattern: str, handler: Callable):
        """
        Register a message handler.

        Args:
            pattern: Pattern to match in message
            handler: Async handler function
        """
        self.handlers[pattern] = handler
        logger.debug(f"Registered handler for pattern: {pattern}")

    def unregister_handler(self, pattern: str):
        """Unregister a handler."""
        self.handlers.pop(pattern, None)
        logger.debug(f"Unregistered handler for pattern: {pattern}")

    def get_stats(self) -> Dict[str, Any]:
        """Get bridge statistics."""
        return {
            "running": self._running,
            "ws_url": self.ws_url,
            "handlers": list(self.handlers.keys()),
            "rbac_enabled": self.rbac_checker is not None,
            "circuit_breaker_enabled": self.circuit_breaker is not None
        }
