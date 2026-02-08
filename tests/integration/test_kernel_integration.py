# tests/integration/test_kernel_integration.py
"""
Integration Tests for ExecutionKernel + OpenClaw Integration

Tests the complete security flow:
- SecureGatewayBridge with kernel validation
- CircuitBreaker integration
- Invariant enforcement
- Handler registration and execution
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from kernel.openclaw_integration import (
    IntegrationConfig,
    SecureHandler,
    SecureGatewayBridge,
    create_secure_bridge,
)
from kernel.execution_kernel import ExecutionKernel, KernelConfig
from kernel.dynamic_circuit_breaker import get_circuit_breaker

from enterprise.gateway_bridge import ChannelMessage, BridgeResponse, ChannelType
from enterprise.event_bus import EventBus, EventType


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def event_bus():
    """Create event bus for testing."""
    bus = EventBus()
    return bus


@pytest.fixture
def sample_message():
    """Create sample channel message."""
    return ChannelMessage(
        channel=ChannelType.WEBCHAT,
        channel_id="test_channel",
        user_id="test_user",
        user_name="Test User",
        message="list all files",
        timestamp=1234567890.0,
        metadata={"tenant_id": "test_tenant"},
        message_id="msg_123"
    )


@pytest.fixture
async def integration_bridge(event_bus):
    """Create secure gateway bridge for testing."""
    config = IntegrationConfig(
        ws_url="ws://test:1234",
        enable_circuit_breaker=True,
        enable_kernel_validation=True,
        skip_manifest_validation=True,  # For testing
        kernel_environment="test"
    )

    bridge = SecureGatewayBridge(
        integration_config=config,
        event_bus=event_bus,
        rbac_checker=None  # No RBAC for tests
    )

    yield bridge

    # Cleanup
    await bridge.stop()


# =============================================================================
# SECURE HANDLER TESTS
# =============================================================================

class TestSecureHandler:
    """Tests for SecureHandler wrapper."""

    @pytest.mark.asyncio
    async def test_secure_handler_allows_safe_operation(self, sample_message):
        """Test that safe operations are allowed."""
        kernel = ExecutionKernel(
            config=KernelConfig(skip_manifest_validation=True)
        )

        handler = SecureHandler(kernel)

        async def dummy_handler(message, autonomy_level):
            return BridgeResponse(success=True, response="OK")

        result = await handler.execute(
            dummy_handler,
            sample_message,
            autonomy_level="GREEN"
        )

        assert result.success
        assert result.response == "OK"

    @pytest.mark.asyncio
    async def test_secure_handler_blocks_protected_in_red_mode(self, sample_message):
        """Test that protected operations are blocked in RED mode."""
        kernel = ExecutionKernel(
            config=KernelConfig(skip_manifest_validation=True)
        )

        handler = SecureHandler(kernel)

        # Protected message
        sample_message.message = "delete production database"

        async def dummy_handler(message, autonomy_level):
            return BridgeResponse(success=True, response="OK")

        result = await handler.execute(
            dummy_handler,
            sample_message,
            autonomy_level="RED"
        )

        assert not result.success
        assert result.error_code == "NOT_ALLOWED_IN_MODE"

    @pytest.mark.asyncio
    async def test_secure_handler_allows_readonly_in_red_mode(self, sample_message):
        """Test that read-only operations are allowed in RED mode."""
        kernel = ExecutionKernel(
            config=KernelConfig(skip_manifest_validation=True)
        )

        handler = SecureHandler(kernel)

        # Read-only message
        sample_message.message = "show system status"

        async def dummy_handler(message, autonomy_level):
            return BridgeResponse(success=True, response="OK")

        result = await handler.execute(
            dummy_handler,
            sample_message,
            autonomy_level="RED"
        )

        assert result.success

    @pytest.mark.asyncio
    async def test_secure_handler_blocks_core_in_amber_mode(self, sample_message):
        """Test that core operations are blocked in AMBER mode."""
        kernel = ExecutionKernel(
            config=KernelConfig(skip_manifest_validation=True)
        )

        handler = SecureHandler(kernel)

        # Core operation
        sample_message.message = "deploy to production"

        async def dummy_handler(message, autonomy_level):
            return BridgeResponse(success=True, response="OK")

        result = await handler.execute(
            dummy_handler,
            sample_message,
            autonomy_level="AMBER"
        )

        assert not result.success
        assert result.error_code == "NOT_ALLOWED_IN_MODE"


# =============================================================================
# SECURE BRIDGE TESTS
# =============================================================================

class TestSecureGatewayBridge:
    """Tests for SecureGatewayBridge."""

    @pytest.mark.asyncio
    async def test_bridge_initialization(self, event_bus):
        """Test bridge initialization."""
        config = IntegrationConfig(
            enable_circuit_breaker=True,
            enable_kernel_validation=True,
            skip_manifest_validation=True
        )

        bridge = SecureGatewayBridge(
            integration_config=config,
            event_bus=event_bus
        )

        assert bridge.kernel is not None
        assert bridge.circuit_breaker is not None
        assert bridge.secure_handler is not None

        await bridge.stop()

    @pytest.mark.asyncio
    async def test_bridge_handles_message(self, integration_bridge, sample_message):
        """Test message handling through bridge."""
        await integration_bridge.start()

        # Register a handler
        async def test_handler(message, autonomy_level):
            return BridgeResponse(
                success=True,
                response=f"Processed: {message.message}"
            )

        integration_bridge.register_handler("list", test_handler)

        result = await integration_bridge.handle_message(sample_message)

        assert result.success
        assert "Processed:" in result.response

    @pytest.mark.asyncio
    async def test_bridge_records_circuit_breaker_metrics(
        self, integration_bridge, sample_message
    ):
        """Test that circuit breaker metrics are recorded."""
        await integration_bridge.start()

        # Register handler that succeeds
        async def success_handler(message, autonomy_level):
            return BridgeResponse(success=True, response="OK")

        integration_bridge.register_handler("success", success_handler)

        initial_status = integration_bridge.circuit_breaker.get_status()
        initial_requests = initial_status["current_window"]["total_requests"]

        await integration_bridge.handle_message(sample_message)

        final_status = integration_bridge.circuit_breaker.get_status()
        final_requests = final_status["current_window"]["total_requests"]

        assert final_requests == initial_requests + 1

    @pytest.mark.asyncio
    async def test_bridge_records_failure_metrics(
        self, integration_bridge, sample_message
    ):
        """Test that failures are recorded in circuit breaker."""
        await integration_bridge.start()

        # Register handler that fails
        async def fail_handler(message, autonomy_level):
            return BridgeResponse(
                success=False,
                response="Error occurred",
                error_code="TEST_ERROR"
            )

        integration_bridge.register_handler("fail", fail_handler)

        initial_status = integration_bridge.circuit_breaker.get_status()
        initial_requests = initial_status["current_window"]["total_requests"]

        sample_message.message = "fail this"
        await integration_bridge.handle_message(sample_message)

        final_status = integration_bridge.circuit_breaker.get_status()
        final_requests = final_status["current_window"]["total_requests"]

        assert final_requests == initial_requests + 1


# =============================================================================
# FACTORY FUNCTION TESTS
# =============================================================================

class TestFactoryFunctions:
    """Tests for factory functions."""

    @pytest.mark.asyncio
    async def test_create_secure_bridge(self):
        """Test secure bridge factory."""
        bridge = create_secure_bridge(
            integration_config=IntegrationConfig(
                skip_manifest_validation=True
            )
        )

        assert bridge is not None
        assert bridge.kernel is not None

        await bridge.stop()

    @pytest.mark.asyncio
    async def test_create_secure_bridge_with_event_bus(self, event_bus):
        """Test secure bridge factory with event bus."""
        bridge = create_secure_bridge(
            integration_config=IntegrationConfig(
                skip_manifest_validation=True
            ),
            event_bus=event_bus
        )

        assert bridge.event_bus == event_bus

        await bridge.stop()


# =============================================================================
# AUTONOMY LEVEL TESTS
# =============================================================================

class TestAutonomyLevels:
    """Tests for autonomy level constraints."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("level,message,should_succeed", [
        ("GREEN", "delete everything", True),  # GREEN allows all
        ("GREEN", "deploy to production", True),
        ("AMBER", "list files", True),
        ("AMBER", "delete everything", False),  # AMBER blocks delete
        ("AMBER", "deploy to production", False),  # AMBER blocks deploy
        ("RED", "list files", True),  # RED allows read-only
        ("RED", "delete everything", False),
        ("RED", "write file", False),  # RED blocks writes
        ("BLACK", "status", True),  # BLACK allows status only
        ("BLACK", "list files", False),  # BLACK blocks list
    ])
    async def test_autonomy_level_constraints(
        self, level, message, should_succeed
    ):
        """Test autonomy level constraints."""
        kernel = ExecutionKernel(
            config=KernelConfig(skip_manifest_validation=True)
        )
        handler = SecureHandler(kernel)

        test_message = ChannelMessage(
            channel=ChannelType.WEBCHAT,
            channel_id="test",
            user_id="user",
            user_name="User",
            message=message,
            timestamp=1234567890.0,
            metadata={}
        )

        async def dummy_handler(message, autonomy_level):
            return BridgeResponse(success=True, response="OK")

        result = await handler.execute(
            dummy_handler,
            test_message,
            autonomy_level=level
        )

        if should_succeed:
            assert result.success, f"Expected success for {level}: {message}"
        else:
            assert not result.success, f"Expected failure for {level}: {message}"
            assert result.error_code == "NOT_ALLOWED_IN_MODE"


# =============================================================================
# RUN TESTS
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
