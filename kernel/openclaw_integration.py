# archon/kernel/openclaw_integration.py
"""
OpenClaw Integration - Gateway Bridge + ExecutionKernel

This module provides the complete security integration between:
- OpenClaw WebSocket Gateway (messaging channels)
- Gateway Bridge (message routing)
- ExecutionKernel (validation and enforcement)
- DynamicCircuitBreaker (autonomy levels)

Architecture:
    Channel → Gateway → Bridge → Kernel.validate() → Kernel.execute() → Handler → Result
                                    ↓
                               REJECT if validation fails

The integration ensures ALL message handling goes through the kernel.
"""

import asyncio
import logging
from typing import Any, Callable, Dict, List, Optional
from dataclasses import dataclass

from .execution_kernel import ExecutionKernel, KernelConfig, ExecutionContext, CircuitState
from .dynamic_circuit_breaker import DynamicCircuitBreaker, get_circuit_breaker
from .validation import ValidationResult, DecisionReason, Severity
from .middleware import OpenClawMiddleware, create_middleware

from enterprise.gateway_bridge import GatewayBridge, ChannelMessage, BridgeResponse
from enterprise.event_bus import EventBus, EventType, Event

# Import new GatewayClientV3
from openclaw import GatewayClientV3, GatewayConfig


logger = logging.getLogger(__name__)


# =============================================================================
# INTEGRATION CONFIGURATION
# =============================================================================

@dataclass
class IntegrationConfig:
    """Configuration for OpenClaw integration."""
    ws_url: str = "ws://localhost:18789"
    auth_token: Optional[str] = None  # Token for gateway authentication
    enable_circuit_breaker: bool = True
    enable_kernel_validation: bool = True
    enable_rbac: bool = True
    enable_audit: bool = True
    kernel_environment: str = "prod"
    skip_manifest_validation: bool = False  # For testing


# =============================================================================
# SECURE HANDLER WRAPPER
# =============================================================================

class SecureHandler:
    """
    Wrapper for message handlers that enforces kernel validation.

    All handlers must be registered through this wrapper to ensure
    they go through the ExecutionKernel.
    """

    def __init__(
        self,
        kernel: ExecutionKernel,
        circuit_breaker: Optional[DynamicCircuitBreaker] = None,
        operation_name: Optional[str] = None
    ):
        self.kernel = kernel
        self.circuit_breaker = circuit_breaker
        self.operation_name = operation_name or "message_handler"

    async def execute(
        self,
        handler_func: Callable,
        message: ChannelMessage,
        autonomy_level: str = "GREEN"
    ) -> BridgeResponse:
        """
        Execute a handler through the kernel.

        Args:
            handler_func: Original handler function
            message: Channel message
            autonomy_level: Current circuit breaker state

        Returns:
            BridgeResponse with result or error
        """
        # Step 1: Create execution context
        context = ExecutionContext(
            agent_id=message.user_id,
            operation=self.operation_name,
            parameters={
                "channel": message.channel.value,
                "message": message.message[:500],  # Truncate for logging
                "channel_id": message.channel_id,
                "autonomy_level": autonomy_level
            },
            domain=message.channel.value,
            request_id=message.message_id
        )

        # Step 2: Validate through kernel
        if not self.kernel.config.skip_manifest_validation:
            validation_result = self.kernel.validate(context)

            if not validation_result.allowed:
                logger.warning(
                    f"[INTEGRATION] Handler BLOCKED: {self.operation_name} "
                    f"reason={validation_result.reason}"
                )
                return BridgeResponse(
                    success=False,
                    response=f"Operation not allowed: {validation_result.reason}",
                    error_code="VALIDATION_FAILED"
                )

        # Step 3: Check autonomy level constraints (always check, even without circuit_breaker)
        if not self._check_autonomy_constraints(message.message, autonomy_level):
            logger.warning(
                f"[INTEGRATION] Operation BLOCKED by autonomy level: "
                f"level={autonomy_level}"
            )
            return BridgeResponse(
                success=False,
                response=f"Operation not allowed in {autonomy_level} mode",
                error_code="NOT_ALLOWED_IN_MODE"
            )

        # Step 4: Execute handler
        try:
            result = await handler_func(message=message, autonomy_level=autonomy_level)

            if isinstance(result, BridgeResponse):
                return result

            return BridgeResponse(
                success=True,
                response=str(result),
                metadata={"autonomy_level": autonomy_level}
            )

        except Exception as e:
            logger.error(f"[INTEGRATION] Handler error: {e}")
            return BridgeResponse(
                success=False,
                response=f"Handler error: {str(e)}",
                error_code="HANDLER_ERROR"
            )

    def _check_autonomy_constraints(self, message: str, autonomy_level: str) -> bool:
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
            for pattern in protected_patterns:
                if pattern in msg_lower:
                    return False
            return True

        elif autonomy_level == "RED":
            read_only = msg_lower.startswith(('show', 'get', 'list', 'status', 'what is'))
            canary = 'canary' in msg_lower
            return read_only or canary

        elif autonomy_level == "BLACK":
            return msg_lower.startswith(('status', 'health', 'metrics'))

        return True


# =============================================================================
# SECURE GATEWAY BRIDGE
# =============================================================================

class SecureGatewayBridge(GatewayBridge):
    """
    Secure Gateway Bridge with kernel integration.

    This extends the standard GatewayBridge to enforce ALL message
    handling through the ExecutionKernel.
    """

    def __init__(
        self,
        integration_config: Optional[IntegrationConfig] = None,
        event_bus: Optional[EventBus] = None,
        rbac_checker: Optional[Callable] = None
    ):
        self.integration_config = integration_config or IntegrationConfig()

        # Initialize circuit breaker
        self.circuit_breaker: Optional[DynamicCircuitBreaker] = None
        if self.integration_config.enable_circuit_breaker:
            self.circuit_breaker = get_circuit_breaker()

        # Initialize kernel
        self.kernel: Optional[ExecutionKernel] = None
        if self.integration_config.enable_kernel_validation:
            kernel_config = KernelConfig(
                environment=self.integration_config.kernel_environment,
                skip_manifest_validation=self.integration_config.skip_manifest_validation,
                enable_rbac=self.integration_config.enable_rbac,
                enable_audit=self.integration_config.enable_audit
            )
            self.kernel = ExecutionKernel(config=kernel_config)

            # Add safety invariants
            from .invariants import combined_safety_invariant
            self.kernel.add_invariant(combined_safety_invariant, "combined_safety")

        # Initialize parent
        super().__init__(
            ws_url=self.integration_config.ws_url,
            event_bus=event_bus,
            rbac_checker=rbac_checker,
            circuit_breaker=self.circuit_breaker
        )

        # Secure handler wrapper
        self.secure_handler = SecureHandler(
            kernel=self.kernel,
            circuit_breaker=self.circuit_breaker
        ) if self.kernel else None

        logger.info(f"[SECURE_BRIDGE] Initialized with kernel={self.kernel is not None}")

    async def handle_message(self, message: ChannelMessage) -> BridgeResponse:
        """
        Process message through kernel-validated handler.

        Overrides parent to enforce kernel validation.
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

            # Step 1: RBAC Check (before kernel)
            if self.rbac_checker:
                if not await self._check_rbac(message):
                    await self._log_denied_access(message, "rbac")
                    return BridgeResponse(
                        success=False,
                        response="Permission denied",
                        error_code="PERMISSION_DENIED"
                    )

            # Step 2: Get autonomy level from circuit breaker state
            autonomy_level = "GREEN"
            if self.circuit_breaker:
                status = self.circuit_breaker.get_status()
                autonomy_level = status.get("circuit_state", "GREEN")

            # Step 3: Get handler
            handler = self._get_handler(message.message)
            if handler:
                # Execute through secure wrapper (kernel validated)
                if self.secure_handler:
                    response = await self.secure_handler.execute(
                        handler,
                        message,
                        autonomy_level
                    )
                else:
                    # Direct execution (no kernel)
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

            # Step 4: Update circuit breaker metrics
            if self.circuit_breaker:
                self.circuit_breaker.record_request(
                    agent_id=message.user_id,
                    operation="message_handler",
                    approved=response.success,
                    forbidden=not response.success and response.error_code in ["VALIDATION_FAILED", "PERMISSION_DENIED"]
                )

            return response

        except Exception as e:
            logger.error(f"[SECURE_BRIDGE] Error handling message: {e}")

            # Record failure in circuit breaker
            if self.circuit_breaker:
                self.circuit_breaker.record_request(
                    agent_id=message.user_id,
                    operation="message_handler",
                    approved=False,
                    forbidden=False
                )

            return BridgeResponse(
                success=False,
                response=f"Internal error: {str(e)}",
                error_code="INTERNAL_ERROR"
            )

    def register_secure_handler(
        self,
        pattern: str,
        handler: Callable,
        operation_name: Optional[str] = None
    ):
        """
        Register a handler that goes through kernel validation.

        Args:
            pattern: Pattern to match in message
            handler: Async handler function
            operation_name: Operation name for kernel logging
        """
        # Register in parent
        self.register_handler(pattern, handler)

        # Also register as kernel operation (if kernel enabled)
        if self.kernel:
            # Wrap handler for kernel execution
            async def kernel_operation(**kwargs):
                return await handler(**kwargs)

            self.kernel.register_operation(
                f"handler:{pattern}",
                kernel_operation,
                f"Handler for pattern: {pattern}"
            )

        logger.info(f"[SECURE_BRIDGE] Registered secure handler: {pattern}")

    async def connect_gateway_v3(self) -> bool:
        """
        Connect to OpenClaw Gateway using Protocol v3.
        
        This replaces the standard start() method and uses GatewayClientV3
        for proper handshake.
        """
        if hasattr(self, '_gateway_client') and self._gateway_client:
            logger.warning("[SECURE_BRIDGE] Gateway already connected")
            return True
        
        # Create GatewayClientV3 config
        gateway_config = GatewayConfig(
            url=self.integration_config.ws_url,
            client_id="archon-ai",
            client_version="0.1.0",
            role="operator",
            scopes=["operator.read", "operator.write"],
            reconnect=True
        )
        
        self._gateway_client = GatewayClientV3(gateway_config)
        
        # Set up message handler
        self._gateway_client.on_event("message", self._on_gateway_message)
        
        # Connect
        connected = await self._gateway_client.connect()
        
        if connected:
            logger.info("[SECURE_BRIDGE] Connected to Gateway v3")
        else:
            logger.error("[SECURE_BRIDGE] Failed to connect to Gateway")
        
        return connected
    
    async def _on_gateway_message(self, message):
        """Handle messages from Gateway."""
        # Convert Gateway message to ChannelMessage
        # This depends on the actual message format from OpenClaw
        payload = message.payload
        
        channel_msg = ChannelMessage(
            channel=payload.get("channel", "webchat"),
            channel_id=payload.get("channel_id", ""),
            user_id=payload.get("user_id", "unknown"),
            user_name=payload.get("user_name", "Unknown"),
            message=payload.get("text", ""),
            timestamp=payload.get("timestamp", 0),
            metadata=payload.get("metadata", {}),
            message_id=payload.get("message_id", "")
        )
        
        # Process through kernel
        response = await self.handle_message(channel_msg)
        
        # Send response back (if needed)
        # This would use Gateway's API to send response
        logger.info(f"[SECURE_BRIDGE] Processed message, response: {response.success}")


# =============================================================================
# INTEGRATION FACTORY
# =============================================================================

def create_secure_bridge(
    integration_config: Optional[IntegrationConfig] = None,
    event_bus: Optional[EventBus] = None,
    rbac_checker: Optional[Callable] = None
) -> SecureGatewayBridge:
    """
    Factory function to create a secure gateway bridge.

    Args:
        integration_config: Integration configuration
        event_bus: Event bus for event emission
        rbac_checker: RBAC checker function

    Returns:
        Configured SecureGatewayBridge

    Usage:
        from kernel.openclaw_integration import create_secure_bridge

        bridge = create_secure_bridge()
        await bridge.start()

        # Register handler
        bridge.register_secure_handler(
            "deploy",
            my_deploy_handler,
            operation_name="deploy_handler"
        )
    """
    bridge = SecureGatewayBridge(
        integration_config=integration_config,
        event_bus=event_bus,
        rbac_checker=rbac_checker
    )

    logger.info("[INTEGRATION] Secure bridge created")

    return bridge


# =============================================================================
# STANDALONE MIDDLEWARE INTEGRATION
# =============================================================================

def create_middleware_bridge(
    kernel_config: Optional[KernelConfig] = None,
    openclaw_gateway_url: str = "ws://localhost:18789"
) -> OpenClawMiddleware:
    """
    Create middleware for direct OpenClaw tool interception.

    Use this when you want to intercept tool calls at the OpenClaw level.

    Args:
        kernel_config: Optional kernel configuration
        openclaw_gateway_url: OpenClaw gateway URL

    Returns:
        Configured OpenClawMiddleware
    """
    middleware = create_middleware(
        kernel_config=kernel_config,
        openclaw_gateway=openclaw_gateway_url
    )

    logger.info("[INTEGRATION] Middleware bridge created")

    return middleware


__all__ = [
    # Configuration
    "IntegrationConfig",
    
    # Gateway Client
    "GatewayClientV3",
    "GatewayConfig",

    # Handler Wrapper
    "SecureHandler",

    # Secure Bridge
    "SecureGatewayBridge",

    # Factory Functions
    "create_secure_bridge",
    "create_middleware_bridge",
]
