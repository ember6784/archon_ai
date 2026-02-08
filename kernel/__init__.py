# archon/kernel/__init__.py
"""
Execution Kernel - Core validation logic for Archon AI.

This package provides:
- ExecutionKernel: Core validation with fail-fast checks + execute()
- ValidationResult: Type-safe validation results
- DynamicCircuitBreaker: ChaosMonkey-integrated circuit breaker
- Invariants: Security checkers for code injection, protected paths, etc.
- ManifestLoader: Multi-source manifest loading with inheritance
"""

from .execution_kernel import (
    ExecutionKernel,
    ExecutionContext,
    KernelConfig,
    ResourceLimits,
    CircuitState,
    get_kernel,
)

from .validation import (
    ValidationResult,
    DecisionReason,
    Severity,
    PostConditionResult,
    InvariantResult,
    ValidationError,
    ValidationResultBuilder,
)

from .dynamic_circuit_breaker import (
    DynamicCircuitBreaker,
    CircuitBreakerConfig,
    AgentReputation,
    PanicMode,
    MetricsSnapshot,
    get_circuit_breaker,
)

from .invariants import (
    no_code_injection,
    no_shell_injection,
    no_protected_path_access,
    no_hardcoded_secrets,
    max_operation_size,
    combined_safety_invariant,
    INVARIANT_REGISTRY,
    get_invariant,
    list_invariants,
)

from .middleware import (
    ToolCallInterceptor,
    OpenClawMiddleware,
    create_middleware,
    safe_read_file,
    safe_write_file,
    safe_list_directory,
)

from .manifests import ManifestLoader, get_loader, ManifestLoadError

from .openclaw_integration import (
    IntegrationConfig,
    GatewayClientV3,
    GatewayConfig,
    SecureHandler,
    SecureGatewayBridge,
    create_secure_bridge,
    create_middleware_bridge,
)

from .intent_contract import (
    BaseContract,
    IntentContract,
    IntentContractConfig,
    ContractBuilder,
    AlwaysAllow,
    AlwaysDeny,
    RequirePermission,
    RequireDomainEnabled,
    MaxOperationSize,
    ProtectedPathCheck,
    RequireManifestContract,
    CustomInvariant,
    AndContract,
    OrContract,
    NotContract,
    READ_FILE_CONTRACT,
    WRITE_FILE_CONTRACT,
    EXEC_CODE_CONTRACT,
    DELETE_FILE_CONTRACT,
)

from .formal_invariants import (
    Z3InvariantChecker,
    Z3_AVAILABLE,
    sharpe_ratio_invariant,
    position_limit_invariant,
    drawdown_invariant,
    no_market_manipulation_invariant,
    create_safety_invariants,
    create_trading_invariants,
    AndInvariant,
    OrInvariant,
    NotInvariant,
)

__all__ = [
    # Execution Kernel
    "ExecutionKernel",
    "ExecutionContext",
    "KernelConfig",
    "ResourceLimits",
    "CircuitState",
    "get_kernel",
    # Validation
    "ValidationResult",
    "DecisionReason",
    "Severity",
    "PostConditionResult",
    "InvariantResult",
    "ValidationError",
    "ValidationResultBuilder",
    # Circuit Breaker
    "DynamicCircuitBreaker",
    "CircuitBreakerConfig",
    "AgentReputation",
    "PanicMode",
    "MetricsSnapshot",
    "get_circuit_breaker",
    # Invariants
    "no_code_injection",
    "no_shell_injection",
    "no_protected_path_access",
    "no_hardcoded_secrets",
    "max_operation_size",
    "combined_safety_invariant",
    "INVARIANT_REGISTRY",
    "get_invariant",
    "list_invariants",
    # Middleware
    "ToolCallInterceptor",
    "OpenClawMiddleware",
    "create_middleware",
    "safe_read_file",
    "safe_write_file",
    "safe_list_directory",
    # Manifests
    "ManifestLoader",
    "get_loader",
    "ManifestLoadError",
    # OpenClaw Integration
    "IntegrationConfig",
    "GatewayClientV3",
    "GatewayConfig",
    "SecureHandler",
    "SecureGatewayBridge",
    "create_secure_bridge",
    "create_middleware_bridge",
    # Intent Contracts
    "BaseContract",
    "IntentContract",
    "IntentContractConfig",
    "ContractBuilder",
    "AlwaysAllow",
    "AlwaysDeny",
    "RequirePermission",
    "RequireDomainEnabled",
    "MaxOperationSize",
    "ProtectedPathCheck",
    "RequireManifestContract",
    "CustomInvariant",
    "AndContract",
    "OrContract",
    "NotContract",
    "READ_FILE_CONTRACT",
    "WRITE_FILE_CONTRACT",
    "EXEC_CODE_CONTRACT",
    "DELETE_FILE_CONTRACT",
    # Formal Verification
    "Z3InvariantChecker",
    "Z3_AVAILABLE",
    "sharpe_ratio_invariant",
    "position_limit_invariant",
    "drawdown_invariant",
    "no_market_manipulation_invariant",
    "create_safety_invariants",
    "create_trading_invariants",
    "AndInvariant",
    "OrInvariant",
    "NotInvariant",
]
