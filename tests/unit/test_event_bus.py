"""
Unit tests for EventBus
"""

import pytest
import asyncio
from enterprise.event_bus import EventBus, EventType, Event


@pytest.fixture
def event_bus():
    """Create a fresh EventBus for each test."""
    bus = EventBus()
    return bus


@pytest.fixture
async def started_event_bus(event_bus):
    """Create and start an EventBus."""
    await event_bus.start()
    yield event_bus
    await event_bus.stop()


class TestEvent:
    """Test Event dataclass."""

    def test_create_event(self):
        """Test creating an event."""
        event = Event.create(
            EventType.AGENT_STARTED,
            {"agent_id": "test-agent"}
        )

        assert event.type == EventType.AGENT_STARTED
        assert event.data == {"agent_id": "test-agent"}
        assert event.timestamp is not None

    def test_event_to_dict(self):
        """Test converting event to dictionary."""
        event = Event.create(
            EventType.MESSAGE_RECEIVED,
            {"message": "hello"},
            user_id="user123",
            tenant_id="tenant456"
        )

        data = event.to_dict()

        assert data["type"] == "message_received"
        assert data["data"]["message"] == "hello"
        assert data["user_id"] == "user123"
        assert data["tenant_id"] == "tenant456"


class TestEventBus:
    """Test EventBus functionality."""

    @pytest.mark.asyncio
    async def test_subscribe_and_publish(self, event_bus):
        """Test subscribing to and publishing events."""
        received_events = []

        async def handler(event):
            received_events.append(event)

        event_bus.subscribe(EventType.AGENT_STARTED, handler)

        test_event = Event.create(
            EventType.AGENT_STARTED,
            {"agent_id": "test"}
        )

        await event_bus.publish(test_event)
        await asyncio.sleep(0.1)  # Give time for processing

        assert len(received_events) == 1
        assert received_events[0].data["agent_id"] == "test"

    @pytest.mark.asyncio
    async def test_unsubscribe(self, event_bus):
        """Test unsubscribing from events."""
        received_events = []

        async def handler(event):
            received_events.append(event)

        event_bus.subscribe(EventType.AGENT_STARTED, handler)
        event_bus.unsubscribe(EventType.AGENT_STARTED, handler)

        await event_bus.publish(
            Event.create(EventType.AGENT_STARTED, {"test": True})
        )
        await asyncio.sleep(0.1)

        assert len(received_events) == 0

    @pytest.mark.asyncio
    async def test_event_filtering(self, event_bus):
        """Test event filtering."""
        received_events = []

        async def handler(event):
            received_events.append(event)

        # Filter: only process events with user_id
        def filter_func(event):
            return event.user_id is not None

        event_bus.subscribe(
            EventType.MESSAGE_RECEIVED,
            handler,
            filter_func=filter_func
        )

        # Event without user_id - should be filtered
        await event_bus.publish(
            Event.create(EventType.MESSAGE_RECEIVED, {"message": "test1"})
        )

        # Event with user_id - should pass
        await event_bus.publish(
            Event.create(
                EventType.MESSAGE_RECEIVED,
                {"message": "test2"},
                user_id="user123"
            )
        )

        await asyncio.sleep(0.1)

        assert len(received_events) == 1
        assert received_events[0].user_id == "user123"

    @pytest.mark.asyncio
    async def test_publish_and_wait(self, event_bus):
        """Test publish_and_wait method."""
        results = []

        async def handler1(event):
            results.append("handler1")
            await asyncio.sleep(0.05)
            return "result1"

        async def handler2(event):
            results.append("handler2")
            return "result2"

        event_bus.subscribe(EventType.AGENT_STARTED, handler1)
        event_bus.subscribe(EventType.AGENT_STARTED, handler2)

        event = Event.create(EventType.AGENT_STARTED, {})
        handler_results = await event_bus.publish_and_wait(event)

        assert len(handler_results) == 2
        assert "result1" in handler_results
        assert "result2" in handler_results

    @pytest.mark.asyncio
    async def test_error_isolation(self, event_bus):
        """Test that handler errors don't affect other handlers."""
        results = []

        async def failing_handler(event):
            raise ValueError("Handler failed!")

        async def working_handler(event):
            results.append("success")

        event_bus.subscribe(EventType.AGENT_STARTED, failing_handler)
        event_bus.subscribe(EventType.AGENT_STARTED, working_handler)

        await event_bus.publish(
            Event.create(EventType.AGENT_STARTED, {})
        )
        await asyncio.sleep(0.1)

        # Working handler should still execute
        assert "success" in results

    @pytest.mark.asyncio
    async def test_event_history(self, event_bus):
        """Test event history tracking."""
        event_bus._persist_events = True

        for i in range(5):
            await event_bus.publish(
                Event.create(EventType.AGENT_STARTED, {"index": i})
            )

        history = event_bus.get_history(limit=10)

        assert len(history) == 5
        assert history[0].data["index"] == 0
        assert history[4].data["index"] == 4

    @pytest.mark.asyncio
    async def test_event_history_filtering(self, event_bus):
        """Test filtering event history by type."""
        event_bus._persist_events = True

        await event_bus.publish(Event.create(EventType.AGENT_STARTED, {}))
        await event_bus.publish(Event.create(EventType.MESSAGE_RECEIVED, {}))
        await event_bus.publish(Event.create(EventType.AGENT_STARTED, {}))

        agent_events = event_bus.get_history(
            event_type=EventType.AGENT_STARTED
        )

        assert len(agent_events) == 2

    def test_get_stats(self, event_bus):
        """Test getting event bus statistics."""
        async def dummy_handler(event):
            pass

        event_bus.subscribe(EventType.AGENT_STARTED, dummy_handler)
        event_bus.subscribe(EventType.MESSAGE_RECEIVED, dummy_handler)

        stats = event_bus.get_stats()

        assert stats["running"] is False
        assert stats["subscribers"]["agent_started"] == 1
        assert stats["subscribers"]["message_received"] == 1
