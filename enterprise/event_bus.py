"""
Enterprise Event Bus

Async pub/sub event system for component communication.
Supports filtering, async handlers, and event persistence.
"""

from typing import Any, Callable, Awaitable, Optional, Dict
from dataclasses import dataclass
from enum import Enum
from datetime import datetime
import asyncio
import logging

logger = logging.getLogger(__name__)


class EventType(Enum):
    """Event types in the system."""

    # Security events
    AUTONOMY_LEVEL_CHANGED = "autonomy_level_changed"
    PERMISSION_DENIED = "permission_denied"
    SAFETY_VIOLATION = "safety_violation"
    CIRCUIT_BREAKER_TRIPPpped = "circuit_breaker_tripped"

    # Agent events
    AGENT_STARTED = "agent_started"
    AGENT_COMPLETED = "agent_completed"
    AGENT_FAILED = "agent_failed"
    DEBATE_STARTED = "debate_started"
    DEBATE_COMPLETED = "debate_completed"

    # System events
    SIEGE_MODE_ACTIVATED = "siege_mode_activated"
    SIEGE_MODE_DEACTIVATED = "siege_mode_deactivated"
    TENANT_CREATED = "tenant_created"
    TENANT_DELETED = "tenant_deleted"
    TENANT_LIMIT_REACHED = "tenant_limit_reached"

    # Gateway events
    GATEWAY_CONNECTED = "gateway_connected"
    GATEWAY_DISCONNECTED = "gateway_disconnected"
    MESSAGE_RECEIVED = "message_received"
    MESSAGE_SENT = "message_sent"

    # Audit events
    AUDIT_EVENT_CREATED = "audit_event_created"
    COMPLIANCE_REPORT_GENERATED = "compliance_report_generated"

    # Execution events
    TASK_STARTED = "task_started"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    SANDBOX_CREATED = "sandbox_created"
    SANDBOX_DESTROYED = "sandbox_destroyed"


@dataclass
class Event:
    """Event data structure."""

    type: EventType
    data: Dict[str, Any]
    timestamp: float
    tenant_id: Optional[str] = None
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    correlation_id: Optional[str] = None
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}

    @classmethod
    def create(
        cls,
        event_type: EventType,
        data: Dict[str, Any],
        **kwargs
    ) -> "Event":
        """Create a new event with auto-generated timestamp."""
        return cls(
            type=event_type,
            data=data,
            timestamp=datetime.now().timestamp(),
            **kwargs
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert event to dictionary."""
        return {
            "type": self.type.value,
            "data": self.data,
            "timestamp": self.timestamp,
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "correlation_id": self.correlation_id,
            "metadata": self.metadata
        }


class EventBus:
    """
    Async event bus for component communication.

    Features:
    - Pub/sub with filtering
    - Async handler execution
    - Error isolation (one handler failure doesn't affect others)
    - Optional event persistence
    """

    def __init__(self, persist_events: bool = False):
        self._subscribers: Dict[EventType, list[Callable]] = {}
        self._filters: Dict[EventType, Callable[[Event], bool]] = {}
        self._queue: asyncio.Queue[Event] = asyncio.Queue()
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._persist_events = persist_events
        self._event_history: list[Event] = []
        self._max_history = 10000

    def subscribe(
        self,
        event_type: EventType,
        handler: Callable[[Event], Awaitable[None]],
        filter_func: Optional[Callable[[Event], bool]] = None
    ):
        """
        Subscribe to an event type.

        Args:
            event_type: Type of event to subscribe to
            handler: Async callback function
            filter_func: Optional filter function (return False to skip handler)
        """
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(handler)

        if filter_func:
            self._filters[event_type] = filter_func

        logger.debug(f"Subscribed to {event_type.value}: {handler.__name__}")

    def unsubscribe(self, event_type: EventType, handler: Callable):
        """
        Unsubscribe handler from event type.

        Args:
            event_type: Type of event
            handler: Handler function to remove
        """
        if event_type in self._subscribers:
            self._subscribers[event_type] = [
                h for h in self._subscribers[event_type] if h != handler
            ]
            logger.debug(f"Unsubscribed from {event_type.value}: {handler.__name__}")

    async def publish(self, event: Event):
        """
        Publish event to the queue.

        Args:
            event: Event to publish
        """
        await self._queue.put(event)

        if self._persist_events:
            self._add_to_history(event)

    async def publish_and_wait(
        self,
        event: Event,
        timeout: float = 5.0
    ) -> list[Any]:
        """
        Publish event and wait for all handlers to complete.

        Args:
            event: Event to publish
            timeout: Maximum time to wait for handlers

        Returns:
            List of results from handlers
        """
        subscribers = self._subscribers.get(event.type, [])

        filter_func = self._filters.get(event.type)
        if filter_func and not filter_func(event):
            return []

        tasks = [handler(event) for handler in subscribers]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        return [r for r in results if not isinstance(r, Exception)]

    async def start(self):
        """Start event processing loop."""
        if self._running:
            logger.warning("Event bus already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._process_loop())
        logger.info("Event bus started")

    async def stop(self):
        """Stop event processing."""
        if not self._running:
            return

        self._running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        logger.info("Event bus stopped")

    async def _process_loop(self):
        """Process events from queue."""
        while self._running:
            try:
                event = await asyncio.wait_for(
                    self._queue.get(),
                    timeout=1.0
                )
                await self._dispatch(event)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Event bus error: {e}")

    async def _dispatch(self, event: Event):
        """
        Dispatch event to all subscribers.

        Errors in handlers are isolated and logged.
        """
        subscribers = self._subscribers.get(event.type, [])

        # Apply filter if exists
        filter_func = self._filters.get(event.type)
        if filter_func:
            try:
                if not filter_func(event):
                    logger.debug(f"Event {event.type.value} filtered out")
                    return
            except Exception as e:
                logger.error(f"Filter error for {event.type.value}: {e}")
                return

        # Dispatch to all subscribers concurrently
        if subscribers:
            tasks = [self._safe_call(handler, event) for handler in subscribers]
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _safe_call(self, handler: Callable, event: Event):
        """Call handler with error isolation."""
        try:
            await handler(event)
        except Exception as e:
            logger.error(
                f"Handler {handler.__name__} failed for {event.type.value}: {e}"
            )

    def _add_to_history(self, event: Event):
        """Add event to history (circular buffer)."""
        self._event_history.append(event)
        if len(self._event_history) > self._max_history:
            self._event_history.pop(0)

    def get_history(
        self,
        event_type: Optional[EventType] = None,
        limit: int = 100
    ) -> list[Event]:
        """
        Get events from history.

        Args:
            event_type: Filter by event type (optional)
            limit: Maximum number of events to return

        Returns:
            List of events
        """
        events = self._event_history

        if event_type:
            events = [e for e in events if e.type == event_type]

        return events[-limit:]

    def get_stats(self) -> Dict[str, Any]:
        """Get event bus statistics."""
        return {
            "running": self._running,
            "subscribers": {
                event_type.value: len(handlers)
                for event_type, handlers in self._subscribers.items()
            },
            "queue_size": self._queue.qsize(),
            "history_size": len(self._event_history),
            "persist_events": self._persist_events
        }


# Global event bus instance (will be initialized in main())
_global_event_bus: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    """Get the global event bus instance."""
    global _global_event_bus
    if _global_event_bus is None:
        _global_event_bus = EventBus()
    return _global_event_bus


def set_event_bus(event_bus: EventBus):
    """Set the global event bus instance."""
    global _global_event_bus
    _global_event_bus = event_bus
