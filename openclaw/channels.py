"""
OpenClaw Channel Manager

Manages communication channels (WhatsApp, Telegram, Slack, etc.).
This is an interface definition - actual channel implementations
come from the OpenClaw project.
"""

from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class ChannelType(Enum):
    """Supported channel types."""
    WHATSAPP = "whatsapp"
    TELEGRAM = "telegram"
    SLACK = "slack"
    DISCORD = "discord"
    GOOGLE_CHAT = "google_chat"
    SIGNAL = "signal"
    MS_TEAMS = "ms_teams"
    WEBCHAT = "webchat"
    IMESSAGE = "imessage"
    BLUEBUBBLES = "bluebubbles"
    MATRIX = "matrix"
    ZALO = "zalo"


class ChannelStatus(Enum):
    """Channel status."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


@dataclass
class ChannelInfo:
    """Information about a channel."""
    type: ChannelType
    id: str
    name: str
    status: ChannelStatus
    metadata: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "type": self.type.value,
            "id": self.id,
            "name": self.name,
            "status": self.status.value,
            "metadata": self.metadata
        }


@dataclass
class ChannelMessage:
    """Message from a channel."""
    channel_type: ChannelType
    channel_id: str
    user_id: str
    user_name: str
    message: str
    timestamp: float
    metadata: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "channel_type": self.channel_type.value,
            "channel_id": self.channel_id,
            "user_id": self.user_id,
            "user_name": self.user_name,
            "message": self.message,
            "timestamp": self.timestamp,
            "metadata": self.metadata
        }


class ChannelManager:
    """
    Manager for communication channels.

    This class provides an interface to interact with various
    messaging channels supported by OpenClaw.
    """

    def __init__(self, gateway_url: str = "ws://localhost:18789"):
        self.gateway_url = gateway_url
        self._channels: Dict[str, ChannelInfo] = {}
        self._connected = False

    async def connect(self) -> bool:
        """
        Connect to the Gateway and initialize channels.

        Returns:
            True if connection successful
        """
        try:
            # Import here to avoid circular dependency
            from openclaw.gateway import get_gateway_client

            client = get_gateway_client(self.gateway_url)
            self._connected = await client.connect()

            if self._connected:
                await self._load_channels()

            return self._connected

        except Exception as e:
            logger.error(f"Failed to connect channel manager: {e}")
            return False

    async def disconnect(self):
        """Disconnect from the Gateway."""
        self._connected = False
        self._channels.clear()

    async def _load_channels(self):
        """Load available channels from Gateway."""
        # This would query the Gateway for available channels
        # For now, we'll initialize empty
        self._channels = {}

    async def send_message(
        self,
        channel_type: ChannelType,
        channel_id: str,
        message: str
    ) -> bool:
        """
        Send a message to a channel.

        Args:
            channel_type: Type of channel
            channel_id: Channel identifier
            message: Message to send

        Returns:
            True if sent successfully
        """
        if not self._connected:
            logger.warning("Channel manager not connected")
            return False

        try:
            from openclaw.gateway import GatewayMessage, get_gateway_client

            client = get_gateway_client()

            msg = GatewayMessage(
                type="send_message",
                data={
                    "channel_type": channel_type.value,
                    "channel_id": channel_id,
                    "message": message
                }
            )

            return await client.send(msg)

        except Exception as e:
            logger.error(f"Failed to send message: {e}")
            return False

    def get_channels(self) -> List[ChannelInfo]:
        """Get list of available channels."""
        return list(self._channels.values())

    def get_channel(self, channel_id: str) -> Optional[ChannelInfo]:
        """Get a specific channel by ID."""
        return self._channels.get(channel_id)

    def add_channel(self, channel: ChannelInfo):
        """Add a channel to the manager."""
        self._channels[channel.id] = channel

    def remove_channel(self, channel_id: str):
        """Remove a channel from the manager."""
        self._channels.pop(channel_id, None)

    def get_stats(self) -> Dict[str, Any]:
        """Get channel manager statistics."""
        return {
            "connected": self._connected,
            "total_channels": len(self._channels),
            "channels_by_type": self._count_by_type()
        }

    def _count_by_type(self) -> Dict[str, int]:
        """Count channels by type."""
        counts = {}
        for channel in self._channels.values():
            type_name = channel.type.value
            counts[type_name] = counts.get(type_name, 0) + 1
        return counts


# Singleton instance
_channel_manager: Optional[ChannelManager] = None


def get_channel_manager(
    gateway_url: str = "ws://localhost:18789"
) -> ChannelManager:
    """Get or create the global Channel manager."""
    global _channel_manager
    if _channel_manager is None:
        _channel_manager = ChannelManager(gateway_url=gateway_url)
    return _channel_manager
