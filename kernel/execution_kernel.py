# archon/kernel/execution_kernel.py
"""
Execution Kernel - Core validation logic for Archon AI.

This is the TRUSTED BOUNDARY component. All agent operations must pass
through this kernel before reaching the execution environment.

Key principles:
- Fail-fast validation: cheap checks first, expensive checks last
- Fail-closed policy: any uncertainty = DENY
- NO LLM inside kernel: deterministic logic only
- Minimal code surface: keep it simple and auditable

Validation order (all must pass):
1. Domain enabled check
2. RBAC permission check
3. Risk level threshold check
4. Intent Contract pre-conditions
5. Circuit Breaker state check
6. Resource limits check
7. Audit log (fail-closed: if logging fails, operation blocked)
"""

import logging
import hashlib
import time
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Callable
from dataclasses import dataclass, field

from .manifests import ManifestLoader, get_loader
from .validation import ValidationResult, DecisionReason, Severity, PostConditionResult


logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit breaker states for autonomous operation."""
    GREEN = "green"      # Full operations - human online
    AMBER = "amber"      # Reduced operations - human offline 2h+
    RED = "red"          # Read-only - human offline 6h+
    BLACK = "black"      # Monitoring only - critical failures


@dataclass
class ExecutionContext:
    """Context for an execution request."""
    agent_id: str
    operation: str
    parameters: Dict[str, Any]
    domain: Optional[str] = None
    intent_contract: Optional[Dict[str, Any]] = None
    request_id: Optional[str] = None
    timestamp: float = field(default_factory=time.time)

    def __post_init__(self):
        if self.request_id is None:
            # Generate deterministic request ID
            content = f"{self.agent_id}:{self.operation}:{self.timestamp}:{str(sorted(self.parameters.items()))}"
            self.request_id = hashlib.sha256(content.encode()).hexdigest()[:16]


@dataclass
class ResourceLimits:
    """Resource limits for an operation."""
    max_tokens: int = 100000
    max_execution_time: float = 300.0  # seconds
    max_memory_mb: int = 1024
    max_file_size_mb: int = 100


@dataclass
class KernelConfig:
    """Configuration for ExecutionKernel."""
    environment: str = "prod"
    default_risk_threshold: float = 0.5
    enable_circuit_breaker: bool = True
    enable_rbac: bool = True
    enable_audit: bool = True
    audit_fail_closed: bool = True  # If true, audit failure blocks operation
    skip_manifest_validation: bool = False  # If true, skip manifest checks (for testing)
    resource_limits: ResourceLimits = field(default_factory=ResourceLimits)


class ExecutionKernel:
    """
    Core validation kernel - the trusted boundary.

    All agent operations must pass validate() before execution.
    The kernel uses fail-fast validation with deterministic logic only.
    """

    # Required checks that cannot be skipped
    REQUIRED_CHECKS = ["domain", "rbac", "risk", "contract", "audit"]

    def __init__(
        self,
        config: Optional[KernelConfig] = None,
        manifest_loader: Optional[ManifestLoader] = None,
        circuit_breaker_state: CircuitState = CircuitState.GREEN
    ):
        """
        Initialize ExecutionKernel.

        Args:
            config: Kernel configuration
            manifest_loader: Manifest loader (uses global if None)
            circuit_breaker_state: Initial circuit breaker state
        """
        self.config = config or KernelConfig()
        self.loader = manifest_loader or get_loader(environment=self.config.environment)
        self.circuit_state = circuit_breaker_state

        # Statistics
        self._stats = {
            "total_requests": 0,
            "approved": 0,
            "denied": 0,
            "by_reason": {},
            "executed": 0,
        }

        # Pre-load manifests for performance
        self._manifest_cache: Dict[str, Dict] = {}

        # ========================================================================
        # Operation Registry (Whitelist)
        # ========================================================================
        # Only registered operations can be executed - this is critical for security
        self.approved_operations: Dict[str, Callable] = {}

        # Intent Contracts: per-operation pre/post-condition validation
        self.contracts: Dict[str, "BaseContract"] = {}

        # Invariants: pre/post-condition checkers that must pass for ALL operations
        self.invariants: List[Callable[[Dict[str, Any]], bool]] = []

    # ========================================================================
    # Operation Registration (Whitelist Management)
    # ========================================================================

    def register_operation(self, name: str, func: Callable, description: str = "") -> None:
        """
        Register an operation as approved for execution.

        This is the ONLY way to allow operations - security by whitelist.
        Unregistered operations will be rejected regardless of other permissions.

        Args:
            name: Operation name (e.g., "write_file", "exec_code")
            func: Callable that executes the operation
            description: Human-readable description
        """
        self.approved_operations[name] = func
        logger.info(f"[KERNEL] Operation registered: {name} - {description}")

    def unregister_operation(self, name: str) -> None:
        """Remove an operation from the whitelist (emergency disable)."""
        if name in self.approved_operations:
            del self.approved_operations[name]
            logger.warning(f"[KERNEL] Operation UNREGISTERED: {name}")
    def register_contract(
        self,
        operation: str,
        contract: "BaseContract"
    ) -> None:
        """
        Register an IntentContract for an operation.

        The contract's pre-conditions will be checked before execution,
        and post-conditions will be checked after execution.

        Args:
            operation: Operation name
            contract: IntentContract or BaseContract to validate
        """
        self.contracts[operation] = contract
        logger.info(f"[KERNEL] Contract registered for: {operation}")

    def add_invariant(
        self,
        checker: Callable[[Dict[str, Any]], bool],
        name: str = ""
    ) -> None:
        """
        Add an invariant checker that runs before and after ALL operations.

        Invariants are security-critical checks that must always pass.
        If any invariant fails, the operation is blocked.

        Common invariants:
        - no_os_system: Block os.system, subprocess.call with shell=True
        - no_write_to_etc: Block writes to protected paths
        - code_injection: Block eval/exec patterns

        Args:
            checker: Function that takes payload dict and returns bool
            name: Human-readable name for logging
        """
        self.invariants.append(checker)
        logger.info(f"[KERNEL] Invariant added: {name or checker.__name__}")

    def _get_manifest_data(self, domain: Optional[str] = None) -> Optional[Dict]:
        """Get manifest data for a domain."""
        if not domain:
            domain = "default"
        try:
            return self.loader.load(domain=domain)
        except Exception:
            return None

    # ========================================================================
    # Main Entry Point: Execute (with validation)
    # ========================================================================

    def execute(
        self,
        operation: str,
        payload: Dict[str, Any],
        agent_id: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Any:
        """
        Execute an operation with full validation.

        This is the ONLY way to execute operations in the system.
        All checks must pass before execution.

        Args:
            operation: Operation name (must be registered)
            payload: Parameters to pass to the operation
            agent_id: Agent requesting execution
            context: Additional context for validation

        Returns:
            Result from the operation

        Raises:
            PermissionError: RBAC check failed
            ValueError: Operation not registered or invariant violation
            RuntimeError: Audit failure (if fail-closed)
        """
        # Build execution context
        exec_context = ExecutionContext(
            agent_id=agent_id,
            operation=operation,
            parameters=payload,
            request_id=context.get("request_id") if context else None
        )

        # 1. Validate first (skip if configured for testing)
        if not self.config.skip_manifest_validation:
            validation_result = self.validate(exec_context)
            if not validation_result.approved:
                self._stats["denied"] += 1
                logger.warning(
                    f"[KERNEL] Operation DENIED: {operation} by {agent_id} - "
                    f"{validation_result.reason.value}: {validation_result.message}"
                )
                raise PermissionError(
                    f"Operation {operation} denied: {validation_result.message}"
                )

        # 2. Check operation is registered (whitelist) - ALWAYS checked
        if operation not in self.approved_operations:
            self._stats["denied"] += 1
            logger.error(f"[KERNEL] Unknown operation: {operation}")
            raise ValueError(f"Unknown operation: {operation}. Not registered in whitelist.")

        # 3. Check IntentContract pre-conditions (if registered)
        if operation in self.contracts:
            contract = self.contracts[operation]
            manifest_data = self._get_manifest_data(exec_context.domain)
            pre_result = contract.check_pre(exec_context, manifest_data)
            if not pre_result.approved:
                self._stats["denied"] += 1
                logger.warning(
                    f"[KERNEL] Contract pre-condition FAILED: {operation} by {agent_id} - {pre_result.message}"
                )
                raise PermissionError(f"Contract pre-condition failed: {pre_result.message}")

        # 4. Check invariants (pre-execution) - ALWAYS checked
        for checker in self.invariants:
            if not checker(payload):
                self._stats["denied"] += 1
                logger.error(f"[KERNEL] Invariant violation BEFORE {operation} by {agent_id}")
                raise ValueError(f"Invariant violation before execution: {operation}")

        # 5. Execute
        start_time = time.time()
        try:
            logger.info(f"[KERNEL] EXECUTING: {operation} by {agent_id}")
            result = self.approved_operations[operation](**payload)

            # 6. Check IntentContract post-conditions (if registered)
            if operation in self.contracts:
                contract = self.contracts[operation]
                manifest_data = self._get_manifest_data(exec_context.domain)
                post_result = contract.check_post(exec_context, result, manifest_data)
                if not post_result.passed:
                    self._stats["denied"] += 1
                    logger.error(
                        f"[KERNEL] Contract post-condition FAILED: {operation} by {agent_id}"
                    )
                    raise ValueError(f"Contract post-condition failed: {post_result.failed_conditions}")

            # 7. Check invariants (post-execution)
            for checker in self.invariants:
                if not checker(payload):
                    self._stats["denied"] += 1
                    logger.error(f"[KERNEL] Invariant violation AFTER {operation} by {agent_id}")
                    raise ValueError(f"Invariant violation after execution: {operation}")

            # 6. Update stats
            self._stats["executed"] += 1
            self._stats["approved"] += 1
            duration = time.time() - start_time

            logger.info(
                f"[KERNEL] SUCCESS: {operation} by {agent_id} "
                f"({duration*1000:.1f}ms)"
            )

            return result

        except Exception as e:
            self._stats["denied"] += 1
            logger.error(f"[KERNEL] EXECUTION FAILED: {operation} by {agent_id} - {e}")
            raise

    # ========================================================================
    # Validation
    # ========================================================================

    def validate(self, context: ExecutionContext) -> ValidationResult:
        """
        Validate an execution request.

        This is the main entry point. All checks must pass for approval.

        Args:
            context: ExecutionContext with request details

        Returns:
            ValidationResult with decision and details
        """
        self._stats["total_requests"] += 1
        start_time = time.time()

        # Fail-fast validation chain
        # Each check returns immediately on failure

        # 1. Domain enabled check
        result = self._check_domain_enabled(context)
        if not result.approved:
            return self._finalize_result(result, "domain_check")

        # 2. RBAC permission check
        if self.config.enable_rbac:
            result = self._check_rbac(context)
            if not result.approved:
                return self._finalize_result(result, "rbac_check")

        # 3. Risk level threshold check
        result = self._check_risk_threshold(context)
        if not result.approved:
            return self._finalize_result(result, "risk_check")

        # 4. Intent Contract pre-conditions
        result = self._check_pre_conditions(context)
        if not result.approved:
            return self._finalize_result(result, "contract_check")

        # 5. Circuit Breaker state check
        if self.config.enable_circuit_breaker:
            result = self._check_circuit_breaker(context)
            if not result.approved:
                return self._finalize_result(result, "circuit_breaker")

        # 6. Resource limits check
        result = self._check_resource_limits(context)
        if not result.approved:
            return self._finalize_result(result, "resource_check")

        # 7. Audit log (fail-closed if configured)
        if self.config.enable_audit:
            result = self._audit_request(context)
            if not result.approved and self.config.audit_fail_closed:
                return self._finalize_result(result, "audit_log")

        # All checks passed
        result.approved = True
        result.reason = DecisionReason.APPROVED
        result.message = "All validation checks passed"

        return self._finalize_result(result, "approved", time.time() - start_time)

    def _finalize_result(
        self,
        result: ValidationResult,
        check_name: str,
        elapsed: float = 0.0
    ) -> ValidationResult:
        """Finalize and track validation result."""
        result.check_name = check_name
        result.elapsed_ms = elapsed * 1000
        result.timestamp = datetime.utcnow().isoformat()

        # Update statistics
        if result.approved:
            self._stats["approved"] += 1
        else:
            self._stats["denied"] += 1
            reason_key = result.reason.value if isinstance(result.reason, DecisionReason) else str(result.reason)
            self._stats["by_reason"][reason_key] = self._stats["by_reason"].get(reason_key, 0) + 1

        logger.info(
            f"Kernel validation: {check_name} -> {result.reason.value} "
            f"(agent={result.context.agent_id}, op={result.context.operation})"
        )

        return result

    # ========================================================================
    # Validation Checks
    # ========================================================================

    def _check_domain_enabled(self, context: ExecutionContext) -> ValidationResult:
        """Check if the domain is enabled for this operation."""
        # Get domain from context or operation contract
        domain = context.domain
        if not domain:
            contract = self.loader.get_operation_contract(context.operation)
            if contract and "domains" in contract:
                domains = contract["domains"]
                domain = domains[0] if domains else "system"
                context.domain = domain
            else:
                domain = "system"

        if not self.loader.is_domain_enabled(domain):
            return ValidationResult(
                approved=False,
                context=context,
                reason=DecisionReason.DOMAIN_DISABLED,
                message=f"Domain '{domain}' is currently disabled",
                severity=Severity.MEDIUM
            )

        return ValidationResult(approved=True, context=context, reason=DecisionReason.PENDING)

    def _check_rbac(self, context: ExecutionContext) -> ValidationResult:
        """
        Check RBAC permissions.

        This is a stub - actual RBAC integration happens in Phase 2.
        For now, we check if operation requires explicit permission.
        """
        contract = self.loader.get_operation_contract(context.operation)

        # If no contract found, allow (fail-open for unknown operations)
        # Real implementation would deny unknown operations
        if not contract:
            return ValidationResult(
                approved=True,
                context=context,
                reason=DecisionReason.PENDING,
                message="No contract found (allowing for now)"
            )

        # Check if operation requires specific permission
        required_permission = contract.get("required_permission")
        if required_permission:
            # Stub: would check agent's actual permissions here
            # For now, assume agent has permission if specified in context
            agent_permissions = context.parameters.get("_permissions", [])
            if required_permission not in agent_permissions:
                return ValidationResult(
                    approved=False,
                    context=context,
                    reason=DecisionReason.PERMISSION_DENIED,
                    message=f"Permission '{required_permission}' required",
                    severity=Severity.HIGH
                )

        return ValidationResult(approved=True, context=context, reason=DecisionReason.PENDING)

    def _check_risk_threshold(self, context: ExecutionContext) -> ValidationResult:
        """Check if operation risk level exceeds threshold."""
        risk_level = self.loader.get_risk_level(context.operation, default=0.5)
        threshold = self.config.default_risk_threshold

        # Adjust threshold based on circuit breaker state
        if self.circuit_state == CircuitState.AMBER:
            threshold *= 0.7  # More restrictive
        elif self.circuit_state == CircuitState.RED:
            threshold *= 0.3  # Very restrictive
        elif self.circuit_state == CircuitState.BLACK:
            threshold = 0.0  # Block everything

        if risk_level > threshold:
            return ValidationResult(
                approved=False,
                context=context,
                reason=DecisionReason.RISK_TOO_HIGH,
                message=f"Risk level {risk_level:.2f} exceeds threshold {threshold:.2f}",
                severity=Severity.HIGH if risk_level > 0.8 else Severity.MEDIUM
            )

        # Store risk level for downstream checks
        if not context.intent_contract:
            context.intent_contract = {}
        context.intent_contract["_risk_level"] = risk_level

        return ValidationResult(approved=True, context=context, reason=DecisionReason.PENDING)

    def _check_pre_conditions(self, context: ExecutionContext) -> ValidationResult:
        """Check Intent Contract pre-conditions."""
        # First check if there's a registered IntentContract
        if context.operation in self.contracts:
            intent_contract = self.contracts[context.operation]
            manifest_data = self._get_manifest_data(context.domain)
            result = intent_contract.check_pre(context, manifest_data)
            if not result.approved:
                return ValidationResult(
                    approved=False,
                    context=context,
                    reason=result.reason,
                    message=f"IntentContract pre-condition failed: {result.message}",
                    severity=result.severity,
                    details=result.details,
                    check_name=result.check_name
                )
            return ValidationResult(approved=True, context=context, reason=DecisionReason.PENDING)

        # Fallback to manifest-based conditions
        contract = self.loader.get_operation_contract(context.operation)
        if not contract:
            return ValidationResult(approved=True, context=context, reason=DecisionReason.PENDING)

        pre_conditions = contract.get("pre_conditions", [])

        for condition in pre_conditions:
            result = self._evaluate_condition(condition, context)
            if not result.passed:
                return ValidationResult(
                    approved=False,
                    context=context,
                    reason=DecisionReason.PRE_CONDITION_FAILED,
                    message=f"Pre-condition failed: {condition.get('type', 'unknown')}",
                    details={"condition": condition, "result": result},
                    severity=Severity.HIGH
                )

        return ValidationResult(approved=True, context=context, reason=DecisionReason.PENDING)

    def _check_circuit_breaker(self, context: ExecutionContext) -> ValidationResult:
        """Check circuit breaker state."""
        if self.circuit_state == CircuitState.BLACK:
            return ValidationResult(
                approved=False,
                context=context,
                reason=DecisionReason.CIRCUIT_OPEN,
                message="Circuit breaker in BLACK state - all operations blocked",
                severity=Severity.CRITICAL
            )

        if self.circuit_state == CircuitState.RED:
            # Only allow read operations in RED state
            read_ops = {"read_file", "search_code", "get_dependencies"}
            if context.operation not in read_ops:
                return ValidationResult(
                    approved=False,
                    context=context,
                    reason=DecisionReason.CIRCUIT_OPEN,
                    message=f"Circuit breaker in RED state - only read operations allowed",
                    severity=Severity.HIGH
                )

        if self.circuit_state == CircuitState.AMBER:
            contract = self.loader.get_operation_contract(context.operation)
            if contract and contract.get("requires_approval", False):
                return ValidationResult(
                    approved=False,
                    context=context,
                    reason=DecisionReason.APPROVAL_REQUIRED,
                    message="Operation requires approval in AMBER state",
                    severity=Severity.MEDIUM
                )

        return ValidationResult(approved=True, context=context, reason=DecisionReason.PENDING)

    def _check_resource_limits(self, context: ExecutionContext) -> ValidationResult:
        """Check resource limits."""
        limits = self.config.resource_limits

        # Check token count if provided
        token_count = context.parameters.get("_token_count", 0)
        if token_count > limits.max_tokens:
            return ValidationResult(
                approved=False,
                context=context,
                reason=DecisionReason.RESOURCE_LIMIT,
                message=f"Token count {token_count} exceeds limit {limits.max_tokens}",
                severity=Severity.MEDIUM
            )

        # Check execution time estimate if provided
        time_estimate = context.parameters.get("_time_estimate", 0)
        if time_estimate > limits.max_execution_time:
            return ValidationResult(
                approved=False,
                context=context,
                reason=DecisionReason.RESOURCE_LIMIT,
                message=f"Execution time {time_estimate}s exceeds limit {limits.max_execution_time}s",
                severity=Severity.MEDIUM
            )

        return ValidationResult(approved=True, context=context, reason=DecisionReason.PENDING)

    def _audit_request(self, context: ExecutionContext) -> ValidationResult:
        """
        Audit log the request.

        Returns DENIED if audit fails and fail_closed is True.
        """
        try:
            audit_entry = {
                "request_id": context.request_id,
                "agent_id": context.agent_id,
                "operation": context.operation,
                "domain": context.domain,
                "timestamp": context.timestamp,
                "iso_timestamp": datetime.utcnow().isoformat(),
                "parameters_hash": hashlib.sha256(
                    str(sorted(context.parameters.items())).encode()
                ).hexdigest()[:16],
            }

            # In production, this would write to a tamper-evident log
            logger.info(f"Audit: {audit_entry}")

            return ValidationResult(
                approved=True,
                context=context,
                reason=DecisionReason.PENDING,
                details={"audit_entry": audit_entry}
            )

        except Exception as e:
            logger.error(f"Audit logging failed: {e}")
            if self.config.audit_fail_closed:
                return ValidationResult(
                    approved=False,
                    context=context,
                    reason=DecisionReason.AUDIT_FAILED,
                    message="Audit logging failed - operation blocked",
                    severity=Severity.CRITICAL,
                    details={"error": str(e)}
                )
            # Continue anyway if not fail-closed
            return ValidationResult(approved=True, context=context, reason=DecisionReason.PENDING)

    # ========================================================================
    # Condition Evaluation
    # ========================================================================

    def _evaluate_condition(self, condition: Dict, context: ExecutionContext) -> "ConditionResult":
        """Evaluate a single pre-condition."""
        condition_type = condition.get("type")

        # Built-in condition evaluators
        evaluators: Dict[str, Callable] = {
            "file_exists": self._eval_file_exists,
            "not_protected_path": self._eval_not_protected_path,
            "agent_has_permission": self._eval_agent_has_permission,
            "risk_level_acceptable": self._eval_risk_acceptable,
        }

        evaluator = evaluators.get(condition_type)
        if not evaluator:
            # Unknown condition - fail safe
            return ConditionResult(passed=False, error=f"Unknown condition type: {condition_type}")

        return evaluator(condition, context)

    def _eval_file_exists(self, condition: Dict, context: ExecutionContext) -> "ConditionResult":
        """Check if a file exists (stub)."""
        path = condition.get("path")
        if not path:
            path = context.parameters.get("path")
        if not path:
            return ConditionResult(passed=False, error="No path specified")
        # Stub: would check actual file system
        return ConditionResult(passed=True)

    def _eval_not_protected_path(self, condition: Dict, context: ExecutionContext) -> "ConditionResult":
        """Check that path is not in protected list."""
        path = context.parameters.get("path", "")
        protected_paths = ["/etc/", "/sys/", "/proc/", ".env", ".ssh/"]
        for protected in protected_paths:
            if protected in path or path.startswith(protected):
                return ConditionResult(
                    passed=False,
                    error=f"Path '{path}' is in protected path '{protected}'"
                )
        return ConditionResult(passed=True)

    def _eval_agent_has_permission(self, condition: Dict, context: ExecutionContext) -> "ConditionResult":
        """Check if agent has specific permission."""
        permission = condition.get("permission")
        agent_permissions = context.parameters.get("_permissions", [])
        has_permission = permission in agent_permissions
        return ConditionResult(
            passed=has_permission,
            error=f"Missing permission: {permission}" if not has_permission else None
        )

    def _eval_risk_acceptable(self, condition: Dict, context: ExecutionContext) -> "ConditionResult":
        """Check if risk level is acceptable."""
        max_risk = condition.get("max_risk", 0.5)
        current_risk = context.intent_contract.get("_risk_level", 0.5) if context.intent_contract else 0.5
        return ConditionResult(
            passed=current_risk <= max_risk,
            error=f"Risk {current_risk} exceeds max {max_risk}" if current_risk > max_risk else None
        )

    # ========================================================================
    # Public API
    # ========================================================================

    def set_circuit_state(self, state: CircuitState) -> None:
        """Update circuit breaker state."""
        old_state = self.circuit_state
        self.circuit_state = state
        logger.warning(f"Circuit breaker state: {old_state.value} -> {state.value}")

    def get_stats(self) -> Dict[str, Any]:
        """Get kernel statistics."""
        total = self._stats["total_requests"]
        return {
            **self._stats,
            "approval_rate": self._stats["approved"] / total if total > 0 else 0.0,
            "circuit_state": self.circuit_state.value,
        }


@dataclass
class ConditionResult:
    """Result of evaluating a condition."""
    passed: bool
    error: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


# =============================================================================
# Global Kernel Instance
# =============================================================================

_global_kernel: Optional[ExecutionKernel] = None


def get_kernel(
    environment: str = "prod",
    config: Optional[KernelConfig] = None,
    reload: bool = False
) -> ExecutionKernel:
    """Get global ExecutionKernel instance."""
    global _global_kernel

    if _global_kernel is None or reload:
        if config is None:
            config = KernelConfig(environment=environment)
        _global_kernel = ExecutionKernel(config=config)

    return _global_kernel
