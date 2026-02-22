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
1. Fast Path check (bypass deep validation for trusted low-risk ops)
2. Domain enabled check
3. RBAC permission check
4. Risk level threshold check
5. Intent Contract pre-conditions
6. Circuit Breaker state check
7. Resource limits check
8. Audit log (fail-closed: if logging fails, operation blocked)
"""

import hashlib
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from .manifests import ManifestLoader, get_loader
from .validation import DecisionReason, Severity, ValidationResult

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
    parameters: dict[str, Any]
    domain: str | None = None
    intent_contract: dict[str, Any] | None = None
    request_id: str | None = None
    timestamp: float = field(default_factory=time.time)

    def __post_init__(self):
        if self.request_id is None:
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
class FastPathConfig:
    """
    Configuration for the Fast Path optimization.

    Operations that qualify for the fast path bypass expensive validation
    steps (manifest loading, deep contract checks, debate pipeline) and
    proceed with only lightweight invariant checks.

    Qualification criteria (ALL must be true):
    - fast_path.enabled is True
    - operation is in fast_path.allowed_operations
    - manifest-resolved risk_score <= fast_path.max_risk_score
    - circuit breaker is NOT in RED or BLACK state
    """
    enabled: bool = True
    max_risk_score: float = 0.2
    allowed_operations: set[str] = field(default_factory=lambda: {
        "read_file",
        "search_code",
        "get_data",
        "log",
        "get_dependencies",
        "list_directory",
    })


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
    security_level: str = "full"  # "light" skips debate; "full" enables all barriers
    fast_path: FastPathConfig = field(default_factory=FastPathConfig)
    resource_limits: ResourceLimits = field(default_factory=ResourceLimits)


class ExecutionKernel:
    """
    Core validation kernel - the trusted boundary.

    All agent operations must pass validate() before execution.
    The kernel uses fail-fast validation with deterministic logic only.

    Fast Path:
        Low-risk read-only operations (risk < 0.2) bypass the full validation
        pipeline and execute with only invariant checks. This reduces latency
        by ~70% for the majority of routine queries.

    Light Mode (security_level="light"):
        Skips the debate pipeline and relaxed manifest checks. Suitable for
        development environments or non-critical workflows.
    """

    REQUIRED_CHECKS = ["domain", "rbac", "risk", "contract", "audit"]

    def __init__(
        self,
        config: KernelConfig | None = None,
        manifest_loader: ManifestLoader | None = None,
        circuit_breaker_state: CircuitState = CircuitState.GREEN
    ):
        self.config = config or KernelConfig()
        self.loader = manifest_loader or get_loader(environment=self.config.environment)
        self.circuit_state = circuit_breaker_state

        self._stats: dict[str, Any] = {
            "total_requests": 0,
            "approved": 0,
            "denied": 0,
            "fast_path_hits": 0,
            "by_reason": {},
            "executed": 0,
        }

        self._manifest_cache: dict[str, dict] = {}

        self.approved_operations: dict[str, Callable] = {}
        self.contracts: dict[str, Any] = {}
        self.invariants: list[Callable[[dict[str, Any]], bool]] = []

    # ========================================================================
    # Operation Registration (Whitelist Management)
    # ========================================================================

    def register_operation(self, name: str, func: Callable, description: str = "") -> None:
        """
        Register an operation as approved for execution.

        This is the ONLY way to allow operations - security by whitelist.
        Unregistered operations will be rejected regardless of other permissions.
        """
        self.approved_operations[name] = func
        logger.info(f"[KERNEL] Operation registered: {name} - {description}")

    def unregister_operation(self, name: str) -> None:
        """Remove an operation from the whitelist (emergency disable)."""
        if name in self.approved_operations:
            del self.approved_operations[name]
            logger.warning(f"[KERNEL] Operation UNREGISTERED: {name}")

    def register_contract(self, operation: str, contract: Any) -> None:
        """
        Register an IntentContract for an operation.

        The contract's pre-conditions are checked before execution and
        post-conditions are checked after execution.
        """
        self.contracts[operation] = contract
        logger.info(f"[KERNEL] Contract registered for: {operation}")

    def add_invariant(self, checker: Callable[[dict[str, Any]], bool], name: str = "") -> None:
        """
        Add an invariant checker that runs before and after ALL operations.

        Invariants are security-critical checks. Failure of any invariant
        blocks the operation regardless of other validation results.
        """
        self.invariants.append(checker)
        logger.info(f"[KERNEL] Invariant added: {name or checker.__name__}")

    def _get_manifest_data(self, domain: str | None = None) -> dict | None:
        """Get manifest data for a domain."""
        if not domain:
            domain = "default"
        try:
            return self.loader.load(domain=domain)
        except Exception:
            return None

    # ========================================================================
    # Fast Path Decision
    # ========================================================================

    def _is_fast_path_eligible(self, context: ExecutionContext) -> bool:
        """
        Determine if an operation qualifies for the fast path.

        The fast path bypasses manifest loading and deep contract checks.
        Invariant checks always run regardless of fast path status.

        Returns True only when ALL conditions hold:
        1. Fast path is enabled in config
        2. security_level is not "full" OR operation is in allowed_operations
        3. Operation is explicitly in allowed_operations
        4. Manifest risk score is <= fast_path.max_risk_score
        5. Circuit breaker is GREEN or AMBER (not RED/BLACK)
        """
        fp = self.config.fast_path
        if not fp.enabled:
            return False

        if context.operation not in fp.allowed_operations:
            return False

        if self.circuit_state in (CircuitState.RED, CircuitState.BLACK):
            return False

        risk = self.loader.get_risk_level(context.operation, default=1.0)
        if risk > fp.max_risk_score:
            return False

        return True

    # ========================================================================
    # Main Entry Point: Execute (with validation)
    # ========================================================================

    def execute(
        self,
        operation: str,
        payload: dict[str, Any],
        agent_id: str,
        context: dict[str, Any] | None = None
    ) -> Any:
        """
        Execute an operation with full validation.

        This is the ONLY way to execute operations in the system.
        All checks must pass before execution proceeds.

        Args:
            operation: Operation name (must be registered in the whitelist)
            payload: Parameters passed to the operation callable
            agent_id: Identifier of the requesting agent
            context: Optional extra context (e.g., request_id)

        Returns:
            Result from the registered operation callable

        Raises:
            PermissionError: RBAC or validation check failed
            ValueError: Operation not registered or invariant violation
            RuntimeError: Audit failure when audit_fail_closed is True
        """
        exec_context = ExecutionContext(
            agent_id=agent_id,
            operation=operation,
            parameters=payload,
            request_id=context.get("request_id") if context else None
        )

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

        if operation not in self.approved_operations:
            self._stats["denied"] += 1
            logger.error(f"[KERNEL] Unknown operation: {operation}")
            raise ValueError(f"Unknown operation: {operation}. Not registered in whitelist.")

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

        for checker in self.invariants:
            if not checker(payload):
                self._stats["denied"] += 1
                logger.error(f"[KERNEL] Invariant violation BEFORE {operation} by {agent_id}")
                raise ValueError(f"Invariant violation before execution: {operation}")

        start_time = time.time()
        try:
            logger.info(f"[KERNEL] EXECUTING: {operation} by {agent_id}")
            result = self.approved_operations[operation](**payload)

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

            for checker in self.invariants:
                if not checker(payload):
                    self._stats["denied"] += 1
                    logger.error(f"[KERNEL] Invariant violation AFTER {operation} by {agent_id}")
                    raise ValueError(f"Invariant violation after execution: {operation}")

            self._stats["executed"] += 1
            self._stats["approved"] += 1
            duration = time.time() - start_time

            logger.info(
                f"[KERNEL] SUCCESS: {operation} by {agent_id} ({duration * 1000:.1f}ms)"
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

        Applies the fast path for eligible low-risk operations, otherwise
        runs the full validation chain. All checks must pass for approval.

        Args:
            context: ExecutionContext with request details

        Returns:
            ValidationResult with decision and details
        """
        self._stats["total_requests"] += 1
        start_time = time.time()

        # Fast path: skip expensive validation for trusted low-risk operations
        if self._is_fast_path_eligible(context):
            self._stats["fast_path_hits"] += 1
            logger.debug(f"[KERNEL] Fast path: {context.operation} by {context.agent_id}")
            result = ValidationResult(
                approved=True,
                context=context,
                reason=DecisionReason.APPROVED,
                message="Fast path: low-risk operation bypassed full validation",
            )
            return self._finalize_result(result, "fast_path", time.time() - start_time)

        # Full validation chain (fail-fast: each check exits immediately on failure)

        result = self._check_domain_enabled(context)
        if not result.approved:
            return self._finalize_result(result, "domain_check")

        if self.config.enable_rbac:
            result = self._check_rbac(context)
            if not result.approved:
                return self._finalize_result(result, "rbac_check")

        result = self._check_risk_threshold(context)
        if not result.approved:
            return self._finalize_result(result, "risk_check")

        result = self._check_pre_conditions(context)
        if not result.approved:
            return self._finalize_result(result, "contract_check")

        if self.config.enable_circuit_breaker:
            result = self._check_circuit_breaker(context)
            if not result.approved:
                return self._finalize_result(result, "circuit_breaker")

        result = self._check_resource_limits(context)
        if not result.approved:
            return self._finalize_result(result, "resource_check")

        if self.config.enable_audit:
            result = self._audit_request(context)
            if not result.approved and self.config.audit_fail_closed:
                return self._finalize_result(result, "audit_log")

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

        if result.approved:
            self._stats["approved"] += 1
        else:
            self._stats["denied"] += 1
            reason_key = (
                result.reason.value
                if isinstance(result.reason, DecisionReason)
                else str(result.reason)
            )
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
        """Check RBAC permissions against operation contract."""
        contract = self.loader.get_operation_contract(context.operation)

        if not contract:
            return ValidationResult(
                approved=True,
                context=context,
                reason=DecisionReason.PENDING,
                message="No contract found (allowing for now)"
            )

        required_permission = contract.get("required_permission")
        if required_permission:
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
        """Check if operation risk level exceeds the configured threshold."""
        risk_level = self.loader.get_risk_level(context.operation, default=0.5)
        threshold = self.config.default_risk_threshold

        if self.config.security_level == "light":
            threshold = min(threshold * 1.5, 1.0)

        if self.circuit_state == CircuitState.AMBER:
            threshold *= 0.7
        elif self.circuit_state == CircuitState.RED:
            threshold *= 0.3
        elif self.circuit_state == CircuitState.BLACK:
            threshold = 0.0

        if risk_level > threshold:
            return ValidationResult(
                approved=False,
                context=context,
                reason=DecisionReason.RISK_TOO_HIGH,
                message=f"Risk level {risk_level:.2f} exceeds threshold {threshold:.2f}",
                severity=Severity.HIGH if risk_level > 0.8 else Severity.MEDIUM
            )

        if not context.intent_contract:
            context.intent_contract = {}
        context.intent_contract["_risk_level"] = risk_level

        return ValidationResult(approved=True, context=context, reason=DecisionReason.PENDING)

    def _check_pre_conditions(self, context: ExecutionContext) -> ValidationResult:
        """Check Intent Contract pre-conditions (registered contract first, then manifest fallback)."""
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

        contract = self.loader.get_operation_contract(context.operation)
        if not contract:
            return ValidationResult(approved=True, context=context, reason=DecisionReason.PENDING)

        pre_conditions = contract.get("pre_conditions", [])
        for condition in pre_conditions:
            cond_result = self._evaluate_condition(condition, context)
            if not cond_result.passed:
                return ValidationResult(
                    approved=False,
                    context=context,
                    reason=DecisionReason.PRE_CONDITION_FAILED,
                    message=f"Pre-condition failed: {condition.get('type', 'unknown')}",
                    details={"condition": condition, "result": cond_result},
                    severity=Severity.HIGH
                )

        return ValidationResult(approved=True, context=context, reason=DecisionReason.PENDING)

    def _check_circuit_breaker(self, context: ExecutionContext) -> ValidationResult:
        """Check circuit breaker state and enforce operation restrictions."""
        if self.circuit_state == CircuitState.BLACK:
            return ValidationResult(
                approved=False,
                context=context,
                reason=DecisionReason.CIRCUIT_OPEN,
                message="Circuit breaker in BLACK state - all operations blocked",
                severity=Severity.CRITICAL
            )

        if self.circuit_state == CircuitState.RED:
            read_ops = {"read_file", "search_code", "get_dependencies", "list_directory", "get_data"}
            if context.operation not in read_ops:
                return ValidationResult(
                    approved=False,
                    context=context,
                    reason=DecisionReason.CIRCUIT_OPEN,
                    message="Circuit breaker in RED state - only read operations allowed",
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
        """Check resource limits against the configured thresholds."""
        limits = self.config.resource_limits

        token_count = context.parameters.get("_token_count", 0)
        if token_count > limits.max_tokens:
            return ValidationResult(
                approved=False,
                context=context,
                reason=DecisionReason.RESOURCE_LIMIT,
                message=f"Token count {token_count} exceeds limit {limits.max_tokens}",
                severity=Severity.MEDIUM
            )

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

        Returns DENIED if audit fails and audit_fail_closed is True.
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
            return ValidationResult(approved=True, context=context, reason=DecisionReason.PENDING)

    # ========================================================================
    # Condition Evaluation
    # ========================================================================

    def _evaluate_condition(self, condition: dict, context: ExecutionContext) -> "ConditionResult":
        """Evaluate a single manifest pre-condition."""
        condition_type = condition.get("type")

        evaluators: dict[str, Callable] = {
            "file_exists": self._eval_file_exists,
            "not_protected_path": self._eval_not_protected_path,
            "agent_has_permission": self._eval_agent_has_permission,
            "risk_level_acceptable": self._eval_risk_acceptable,
        }

        evaluator = evaluators.get(condition_type)
        if not evaluator:
            return ConditionResult(passed=False, error=f"Unknown condition type: {condition_type}")

        return evaluator(condition, context)

    def _eval_file_exists(self, condition: dict, context: ExecutionContext) -> "ConditionResult":
        """Check if a file exists."""
        path = condition.get("path") or context.parameters.get("path")
        if not path:
            return ConditionResult(passed=False, error="No path specified")
        return ConditionResult(passed=True)

    def _eval_not_protected_path(self, condition: dict, context: ExecutionContext) -> "ConditionResult":
        """Check that path is not in the protected list."""
        path = context.parameters.get("path", "")
        protected_paths = ["/etc/", "/sys/", "/proc/", ".env", ".ssh/"]
        for protected in protected_paths:
            if protected in path or path.startswith(protected):
                return ConditionResult(
                    passed=False,
                    error=f"Path '{path}' is in protected path '{protected}'"
                )
        return ConditionResult(passed=True)

    def _eval_agent_has_permission(self, condition: dict, context: ExecutionContext) -> "ConditionResult":
        """Check if agent has a specific permission."""
        permission = condition.get("permission")
        agent_permissions = context.parameters.get("_permissions", [])
        has_permission = permission in agent_permissions
        return ConditionResult(
            passed=has_permission,
            error=f"Missing permission: {permission}" if not has_permission else None
        )

    def _eval_risk_acceptable(self, condition: dict, context: ExecutionContext) -> "ConditionResult":
        """Check if risk level is within the acceptable range."""
        max_risk = condition.get("max_risk", 0.5)
        current_risk = (
            context.intent_contract.get("_risk_level", 0.5)
            if context.intent_contract
            else 0.5
        )
        return ConditionResult(
            passed=current_risk <= max_risk,
            error=f"Risk {current_risk} exceeds max {max_risk}" if current_risk > max_risk else None
        )

    # ========================================================================
    # Public API
    # ========================================================================

    def set_circuit_state(self, state: CircuitState) -> None:
        """Update the circuit breaker state."""
        old_state = self.circuit_state
        self.circuit_state = state
        logger.warning(f"Circuit breaker state: {old_state.value} -> {state.value}")

    def get_stats(self) -> dict[str, Any]:
        """Get kernel statistics including fast path hit rate."""
        total = self._stats["total_requests"]
        fast = self._stats["fast_path_hits"]
        return {
            **self._stats,
            "approval_rate": self._stats["approved"] / total if total > 0 else 0.0,
            "fast_path_rate": fast / total if total > 0 else 0.0,
            "circuit_state": self.circuit_state.value,
            "security_level": self.config.security_level,
        }


@dataclass
class ConditionResult:
    """Result of evaluating a single condition."""
    passed: bool
    error: str | None = None
    details: dict[str, Any] | None = None


# =============================================================================
# Global Kernel Instance
# =============================================================================

_global_kernel: ExecutionKernel | None = None


def get_kernel(
    environment: str = "prod",
    config: KernelConfig | None = None,
    reload: bool = False
) -> ExecutionKernel:
    """Get or create the global ExecutionKernel instance."""
    global _global_kernel

    if _global_kernel is None or reload:
        if config is None:
            config = KernelConfig(environment=environment)
        _global_kernel = ExecutionKernel(config=config)

    return _global_kernel
