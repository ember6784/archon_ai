# archon/kernel/middleware.py
"""
OpenClaw Integration Middleware.

This middleware intercepts ALL tool calls from OpenClaw agents and
proxies them through the ExecutionKernel for validation.

This is the critical security boundary - agents cannot access tools
directly, ALL calls must go through kernel.execute().

Architecture:
    Agent → Tool Call → Middleware → Kernel.validate() → Kernel.execute() → Result
                                      ↓
                                 REJECT if validation fails
"""

import logging
from typing import Any, Callable, Dict, Optional
from functools import wraps


logger = logging.getLogger(__name__)


class ToolCallInterceptor:
    """
    Intercepts and validates all tool calls before execution.

    Wraps the OpenClaw execution engine to ensure ALL operations
    pass through the ExecutionKernel.
    """

    def __init__(self, kernel, execution_engine=None):
        """
        Initialize the interceptor.

        Args:
            kernel: ExecutionKernel instance for validation
            execution_engine: Original OpenClaw execution engine (for fallback)
        """
        self.kernel = kernel
        self.execution_engine = execution_engine
        self._intercepted_tools: Dict[str, Callable] = {}

    def intercept_tool(
        self,
        tool_name: str,
        original_func: Callable,
        agent_id: str = "default_agent"
    ) -> Callable:
        """
        Wrap a tool function to intercept all calls through the kernel.

        Args:
            tool_name: Name of the tool (operation name)
            original_func: Original tool function from OpenClaw
            agent_id: Agent ID for validation

        Returns:
            Wrapped function that validates before executing
        """
        @wraps(original_func)
        def wrapped(*args, **kwargs):
            # Convert args/kwargs to payload dict
            payload = self._prepare_payload(tool_name, args, kwargs)

            # Add context
            context = {
                "tool_name": tool_name,
                "agent_id": agent_id
            }

            # Execute through kernel (with validation)
            try:
                result = self.kernel.execute(
                    operation=tool_name,
                    payload=payload,
                    agent_id=agent_id,
                    context=context
                )
                return result
            except (PermissionError, ValueError) as e:
                logger.error(
                    f"[MIDDLEWARE] Tool call BLOCKED: {tool_name} by {agent_id} - {e}"
                )
                # Return error result that OpenClaw can handle
                return {
                    "success": False,
                    "error": str(e),
                    "blocked_by": "middleware",
                    "tool": tool_name
                }

        # Store wrapped function
        self._intercepted_tools[tool_name] = wrapped
        return wrapped

    def _prepare_payload(self, tool_name: str, args, kwargs) -> Dict[str, Any]:
        """Convert function args/kwargs to payload dict."""
        # Most tools use kwargs, but handle positional args too
        if kwargs:
            return kwargs
        if args and len(args) == 1 and isinstance(args[0], dict):
            return args[0]
        return {"args": args}

    def register_tool(
        self,
        tool_name: str,
        tool_func: Callable,
        agent_id: Optional[str] = None
    ) -> None:
        """
        Register a tool in both kernel and interceptor.

        This is the main entry point for adding new tools.

        Args:
            tool_name: Name of the tool/operation
            tool_func: The tool function
            agent_id: Agent that owns this tool (optional)
        """
        # Register in kernel whitelist
        self.kernel.register_operation(tool_name, tool_func, f"Tool: {tool_name}")

        # Create intercepted version
        intercepted = self.intercept_tool(tool_name, tool_func, agent_id or "default")

        logger.info(f"[MIDDLEWARE] Tool registered: {tool_name}")


class OpenClawMiddleware:
    """
    Main middleware class for OpenClaw integration.

    Provides a complete wrapper around OpenClaw's execution engine
    to ensure ALL tool calls go through the ExecutionKernel.
    """

    def __init__(self, kernel, openclaw_gateway=None):
        """
        Initialize OpenClaw middleware.

        Args:
            kernel: ExecutionKernel instance
            openclaw_gateway: OpenClaw gateway instance (if available)
        """
        self.kernel = kernel
        self.openclaw_gateway = openclaw_gateway
        self.interceptor = ToolCallInterceptor(kernel, openclaw_gateway)

        # Track which tools have been intercepted
        self._original_tools: Dict[str, Callable] = {}

    def wrap_execution_engine(self, execution_engine: Any) -> Any:
        """
        Wrap an OpenClaw execution engine to intercept all tool calls.

        This replaces the execution_engine's tool registry with
        our intercepted versions.

        Args:
            execution_engine: Original OpenClaw execution engine

        Returns:
            Wrapped execution engine
        """
        # Save original tools
        if hasattr(execution_engine, 'tools'):
            for name, tool_func in execution_engine.tools.items():
                if callable(tool_func):
                    self._original_tools[name] = tool_func
                    # Create intercepted version
                    execution_engine.tools[name] = self.interceptor.intercept_tool(
                        name, tool_func, "openclaw_agent"
                    )

        logger.info(f"[MIDDLEWARE] Wrapped {len(self._original_tools)} tools")

        return execution_engine

    def create_safe_tool(
        self,
        name: str,
        func: Callable,
        description: str = ""
    ) -> Callable:
        """
        Create a new safe tool that's automatically registered in the kernel.

        This is the recommended way to add tools to the system.

        Args:
            name: Tool/operation name
            func: Tool function
            description: Human-readable description

        Returns:
            Intercepted (wrapped) tool function
        """
        # Register in kernel and create intercepted version
        self.interceptor.register_tool(name, func)

        return self.interceptor._intercepted_tools.get(name, func)


# =============================================================================
# Built-in Safe Tools (pre-registered in kernel)
# =============================================================================

def safe_read_file(path: str) -> Dict[str, Any]:
    """Safely read a file (with path validation in kernel)."""
    try:
        with open(path, 'r') as f:
            return {
                "success": True,
                "content": f.read(),
                "path": path
            }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


def safe_write_file(path: str, content: str) -> Dict[str, Any]:
    """Safely write a file (with path validation in kernel)."""
    try:
        with open(path, 'w') as f:
            f.write(content)
        return {
            "success": True,
            "bytes_written": len(content),
            "path": path
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


def safe_list_directory(path: str) -> Dict[str, Any]:
    """Safely list directory contents."""
    import os
    try:
        entries = os.listdir(path)
        return {
            "success": True,
            "entries": entries,
            "path": path,
            "count": len(entries)
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


# =============================================================================
# Middleware Factory
# =============================================================================

def create_middleware(
    kernel_config=None,
    openclaw_gateway=None
) -> OpenClawMiddleware:
    """
    Factory function to create OpenClaw middleware with kernel.

    Args:
        kernel_config: Optional KernelConfig for ExecutionKernel
        openclaw_gateway: Optional OpenClaw gateway instance

    Returns:
        Configured OpenClawMiddleware instance
    """
    from .execution_kernel import ExecutionKernel, KernelConfig

    # Create kernel
    if kernel_config is None:
        kernel_config = KernelConfig(
            environment="prod",
            skip_manifest_validation=False  # Enable manifest validation in production
        )

    kernel = ExecutionKernel(config=kernel_config)

    # Add invariants
    from .invariants import combined_safety_invariant
    kernel.add_invariant(combined_safety_invariant, "combined_safety")

    # Create middleware
    middleware = OpenClawMiddleware(kernel, openclaw_gateway)

    # Register built-in safe tools
    for name, func, desc in [
        ("read_file", safe_read_file, "Read file content"),
        ("write_file", safe_write_file, "Write file content"),
        ("list_directory", safe_list_directory, "List directory contents"),
    ]:
        middleware.create_safe_tool(name, func, desc)

    logger.info("[MIDDLEWARE] Created with kernel and safe tools")

    return middleware


# =============================================================================
# Usage Example
# =============================================================================

"""
# Example usage with OpenClaw:

from kernel import create_middleware

# Create middleware (this creates the kernel)
middleware = create_middleware()

# Wrap OpenClaw execution engine
wrapped_engine = middleware.wrap_execution_engine(openclaw_engine)

# Now all tool calls go through kernel.execute()
# Agent cannot bypass - all calls validated!

# Custom tool registration
@middleware.kernel.register_operation
def my_custom_tool(param1: str) -> str:
    return f"Processed: {param1}"

# This will automatically be intercepted when called through OpenClaw
"""
