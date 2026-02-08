# archon/kernel/intent_contract.py
"""
Intent Contract - Pre/Post-Condition Validation

This module provides the IntentContract class for validating operation
contracts against execution context and results.

Architecture:
    1. Pre-condition validation: check BEFORE execution
    2. Post-condition validation: check AFTER execution
    3. Invariant validation: check ALWAYS (before and after)

Contracts are composed using logical operators (AND, OR, NOT).
"""

import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Union

from .validation import (
    ValidationResult,
    DecisionReason,
    Severity,
    PostConditionResult,
    InvariantResult,
    ValidationError,
)


logger = logging.getLogger(__name__)


# =============================================================================
# CONTRACT OPERATORS
# =============================================================================

class ContractOperator(Enum):
    """Logical operators for contract composition."""
    AND = "and"
    OR = "or"
    NOT = "not"


# =============================================================================
# BASE CONTRACT CLASS
# =============================================================================

class BaseContract(ABC):
    """
    Base class for all contracts.

    Contracts can be composed using logical operators:
    - contract1 & contract2  → AND composition
    - contract1 | contract2  → OR composition
    - ~contract              → NOT composition
    """

    @abstractmethod
    def check_pre(
        self,
        context: "ExecutionContext",
        manifest_data: Optional[Dict] = None
    ) -> ValidationResult:
        """Check pre-conditions before execution."""
        pass

    @abstractmethod
    def check_post(
        self,
        context: "ExecutionContext",
        execution_result: Any,
        manifest_data: Optional[Dict] = None
    ) -> PostConditionResult:
        """Check post-conditions after execution."""
        pass

    def __and__(self, other: "BaseContract") -> "AndContract":
        """Compose with AND operator."""
        return AndContract(self, other)

    def __or__(self, other: "BaseContract") -> "OrContract":
        """Compose with OR operator."""
        return OrContract(self, other)

    def __invert__(self) -> "NotContract":
        """Compose with NOT operator."""
        return NotContract(self)


# =============================================================================
# PRIMITIVE CONTRACTS
# =============================================================================

class AlwaysAllow(BaseContract):
    """Contract that always allows operations."""

    def check_pre(
        self,
        context: "ExecutionContext",
        manifest_data: Optional[Dict] = None
    ) -> ValidationResult:
        from .execution_kernel import ExecutionContext
        return ValidationResult(
            approved=True,
            context=context,
            reason=DecisionReason.APPROVED,
            message="Always allowed",
            check_name="always_allow"
        )

    def check_post(
        self,
        context: "ExecutionContext",
        execution_result: Any,
        manifest_data: Optional[Dict] = None
    ) -> PostConditionResult:
        return PostConditionResult(
            passed=True,
            results=[{"name": "always_allow", "passed": True}]
        )


class AlwaysDeny(BaseContract):
    """Contract that always denies operations."""

    def __init__(self, reason: str = "Operation denied by policy"):
        self.reason = reason

    def check_pre(
        self,
        context: "ExecutionContext",
        manifest_data: Optional[Dict] = None
    ) -> ValidationResult:
        return ValidationResult(
            approved=False,
            context=context,
            reason=DecisionReason.PRE_CONDITION_FAILED,
            message=self.reason,
            severity=Severity.HIGH,
            check_name="always_deny"
        )

    def check_post(
        self,
        context: "ExecutionContext",
        execution_result: Any,
        manifest_data: Optional[Dict] = None
    ) -> PostConditionResult:
        return PostConditionResult(
            passed=False,
            failed_conditions=[{"name": "always_deny", "reason": self.reason}]
        )


class RequirePermission(BaseContract):
    """Contract that requires specific permission."""

    def __init__(
        self,
        permission: str,
        resource: Optional[str] = None
    ):
        self.permission = permission
        self.resource = resource

    def check_pre(
        self,
        context: "ExecutionContext",
        manifest_data: Optional[Dict] = None
    ) -> ValidationResult:
        """
        Check if agent has required permission.

        In production, this would query the RBAC system.
        For now, we check the context parameters.
        """
        # Check if permission is in context (simulating RBAC)
        agent_permissions = context.parameters.get("permissions", [])

        if self.permission in agent_permissions:
            return ValidationResult(
                approved=True,
                context=context,
                reason=DecisionReason.APPROVED,
                message=f"Permission {self.permission} granted",
                check_name="require_permission"
            )

        return ValidationResult(
            approved=False,
            context=context,
            reason=DecisionReason.PERMISSION_DENIED,
            message=f"Missing required permission: {self.permission}",
            severity=Severity.HIGH,
            details={"required_permission": self.permission, "resource": self.resource},
            check_name="require_permission"
        )

    def check_post(
        self,
        context: "ExecutionContext",
        execution_result: Any,
        manifest_data: Optional[Dict] = None
    ) -> PostConditionResult:
        # Post-condition always passes if pre-condition passed
        return PostConditionResult(passed=True)


class RequireDomainEnabled(BaseContract):
    """Contract that requires a domain to be enabled."""

    def __init__(self, domain: str):
        self.domain = domain

    def check_pre(
        self,
        context: "ExecutionContext",
        manifest_data: Optional[Dict] = None
    ) -> ValidationResult:
        """Check if domain is enabled in manifest."""
        if not manifest_data:
            return ValidationResult(
                approved=False,
                context=context,
                reason=DecisionReason.DOMAIN_NOT_FOUND,
                message=f"No manifest data available for domain: {self.domain}",
                severity=Severity.MEDIUM,
                check_name="require_domain_enabled"
            )

        # Check if domain exists and is enabled
        domains = manifest_data.get("domains", {})
        if self.domain not in domains:
            return ValidationResult(
                approved=False,
                context=context,
                reason=DecisionReason.DOMAIN_NOT_FOUND,
                message=f"Domain not found: {self.domain}",
                severity=Severity.MEDIUM,
                details={"domain": self.domain},
                check_name="require_domain_enabled"
            )

        domain_config = domains[self.domain]
        if not domain_config.get("enabled", True):
            return ValidationResult(
                approved=False,
                context=context,
                reason=DecisionReason.DOMAIN_DISABLED,
                message=f"Domain is disabled: {self.domain}",
                severity=Severity.HIGH,
                details={"domain": self.domain},
                check_name="require_domain_enabled"
            )

        return ValidationResult(
            approved=True,
            context=context,
            reason=DecisionReason.APPROVED,
            message=f"Domain enabled: {self.domain}",
            check_name="require_domain_enabled"
        )

    def check_post(
        self,
        context: "ExecutionContext",
        execution_result: Any,
        manifest_data: Optional[Dict] = None
    ) -> PostConditionResult:
        return PostConditionResult(passed=True)


class MaxOperationSize(BaseContract):
    """Contract that limits operation size."""

    def __init__(self, max_size_bytes: int):
        self.max_size_bytes = max_size_bytes

    def check_pre(
        self,
        context: "ExecutionContext",
        manifest_data: Optional[Dict] = None
    ) -> ValidationResult:
        """Check if operation payload is within size limits."""
        # Estimate size from parameters
        payload_str = str(context.parameters)
        estimated_size = len(payload_str.encode())

        if estimated_size > self.max_size_bytes:
            return ValidationResult(
                approved=False,
                context=context,
                reason=DecisionReason.RESOURCE_LIMIT,
                message=f"Operation too large: {estimated_size} > {self.max_size_bytes} bytes",
                severity=Severity.MEDIUM,
                details={
                    "size_bytes": estimated_size,
                    "max_bytes": self.max_size_bytes
                },
                check_name="max_operation_size"
            )

        return ValidationResult(
            approved=True,
            context=context,
            reason=DecisionReason.APPROVED,
            message=f"Operation size acceptable: {estimated_size} bytes",
            check_name="max_operation_size"
        )

    def check_post(
        self,
        context: "ExecutionContext",
        execution_result: Any,
        manifest_data: Optional[Dict] = None
    ) -> PostConditionResult:
        return PostConditionResult(passed=True)


class ProtectedPathCheck(BaseContract):
    """Contract that blocks access to protected paths."""

    PROTECTED_PATHS = [
        "/etc/", "/sys/", "/proc/", "/root/", "/boot/",
        "~/.ssh/", "~/.aws/", "~/credentials/",
        "/.ssh/", "/.aws/", "/.credentials/",  # Also check without ~
        ".env", ".pem", ".key"
    ]

    def __init__(self, path_parameter: str = "path"):
        self.path_parameter = path_parameter

    def check_pre(
        self,
        context: "ExecutionContext",
        manifest_data: Optional[Dict] = None
    ) -> ValidationResult:
        """Check if operation attempts to access protected paths."""
        path = context.parameters.get(self.path_parameter, "")

        if not path:
            return ValidationResult(
                approved=True,
                context=context,
                reason=DecisionReason.APPROVED,
                message="No path specified",
                check_name="protected_path_check"
            )

        # Check against protected paths
        for protected in self.PROTECTED_PATHS:
            if path.startswith(protected) or protected in path:
                return ValidationResult(
                    approved=False,
                    context=context,
                    reason=DecisionReason.PRE_CONDITION_FAILED,
                    message=f"Access to protected path blocked: {path}",
                    severity=Severity.CRITICAL,
                    details={"path": path, "protected_pattern": protected},
                    check_name="protected_path_check"
                )

        return ValidationResult(
            approved=True,
            context=context,
            reason=DecisionReason.APPROVED,
            message=f"Path check passed: {path}",
            check_name="protected_path_check"
        )

    def check_post(
        self,
        context: "ExecutionContext",
        execution_result: Any,
        manifest_data: Optional[Dict] = None
    ) -> PostConditionResult:
        return PostConditionResult(passed=True)


class RequireManifestContract(BaseContract):
    """Contract that validates against manifest operation contract."""

    def __init__(self, operation: str):
        self.operation = operation

    def check_pre(
        self,
        context: "ExecutionContext",
        manifest_data: Optional[Dict] = None
    ) -> ValidationResult:
        """Check pre-conditions from manifest."""
        if not manifest_data:
            return ValidationResult(
                approved=False,
                context=context,
                reason=DecisionReason.DOMAIN_NOT_FOUND,
                message="No manifest data available",
                severity=Severity.HIGH,
                check_name="require_manifest_contract"
            )

        # Get operation contract from manifest
        operations = manifest_data.get("operations", {})
        if self.operation not in operations:
            # Unknown operation - deny by default
            return ValidationResult(
                approved=False,
                context=context,
                reason=DecisionReason.PRE_CONDITION_FAILED,
                message=f"Unknown operation: {self.operation}",
                severity=Severity.HIGH,
                details={"operation": self.operation},
                check_name="require_manifest_contract"
            )

        op_config = operations[self.operation]

        # Check if operation is enabled
        if not op_config.get("enabled", True):
            return ValidationResult(
                approved=False,
                context=context,
                reason=DecisionReason.DOMAIN_DISABLED,
                message=f"Operation is disabled: {self.operation}",
                severity=Severity.HIGH,
                details={"operation": self.operation},
                check_name="require_manifest_contract"
            )

        # Check domain constraints
        domain = context.domain or "default"
        if domain not in op_config.get("allowed_domains", [domain]):
            return ValidationResult(
                approved=False,
                context=context,
                reason=DecisionReason.PERMISSION_DENIED,
                message=f"Domain not allowed for operation: {domain}",
                severity=Severity.HIGH,
                details={"operation": self.operation, "domain": domain},
                check_name="require_manifest_contract"
            )

        return ValidationResult(
            approved=True,
            context=context,
            reason=DecisionReason.APPROVED,
            message=f"Operation contract validated: {self.operation}",
            details={
                "operation": self.operation,
                "risk_level": op_config.get("risk_level", 0.5)
            },
            check_name="require_manifest_contract"
        )

    def check_post(
        self,
        context: "ExecutionContext",
        execution_result: Any,
        manifest_data: Optional[Dict] = None
    ) -> PostConditionResult:
        """Check post-conditions from manifest."""
        if not manifest_data:
            return PostConditionResult(passed=True)

        operations = manifest_data.get("operations", {})
        if self.operation not in operations:
            return PostConditionResult(passed=True)

        op_config = operations[self.operation]
        post_conditions = op_config.get("post_conditions", {})
        results = []
        failed = []

        # Check each post-condition
        for condition_name, condition_config in post_conditions.items():
            result = self._check_condition(
                condition_name,
                condition_config,
                execution_result
            )
            results.append(result)
            if not result["passed"]:
                failed.append(result)

        return PostConditionResult(
            passed=len(failed) == 0,
            results=results,
            failed_conditions=failed
        )

    def _check_condition(
        self,
        name: str,
        config: Dict,
        execution_result: Any
    ) -> Dict[str, Any]:
        """Check a single post-condition."""
        operator = config.get("operator", "==")
        expected = config.get("expected")
        path = config.get("path")

        # Extract value from result using path (if specified)
        if path:
            actual = self._get_nested_value(execution_result, path)
        else:
            actual = execution_result

        # Perform comparison
        passed = self._compare(actual, expected, operator)

        return {
            "name": name,
            "passed": passed,
            "operator": operator,
            "expected": expected,
            "actual": str(actual)[:100]  # Truncate for logging
        }

    def _get_nested_value(self, obj: Any, path: str) -> Any:
        """Get nested value from object using dot notation."""
        keys = path.split(".")
        value = obj

        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
            elif hasattr(value, key):
                value = getattr(value, key)
            else:
                return None

        return value

    def _compare(self, actual: Any, expected: Any, operator: str) -> bool:
        """Compare values using operator."""
        if operator == "==":
            return actual == expected
        elif operator == "!=":
            return actual != expected
        elif operator == ">":
            try:
                return actual > expected
            except TypeError:
                return False
        elif operator == "<":
            try:
                return actual < expected
            except TypeError:
                return False
        elif operator == ">=":
            try:
                return actual >= expected
            except TypeError:
                return False
        elif operator == "<=":
            try:
                return actual <= expected
            except TypeError:
                return False
        elif operator == "in":
            return actual in expected if expected else False
        elif operator == "contains":
            return expected in actual if actual else False
        elif operator == "matches":
            try:
                return bool(re.match(expected, actual))
            except (TypeError, re.error):
                return False
        else:
            return False


class CustomInvariant(BaseContract):
    """Contract with custom invariant checker."""

    def __init__(
        self,
        name: str,
        checker: Callable[[Dict[str, Any]], bool],
        failure_message: str = "Invariant violated"
    ):
        self.name = name
        self.checker = checker
        self.failure_message = failure_message

    def check_pre(
        self,
        context: "ExecutionContext",
        manifest_data: Optional[Dict] = None
    ) -> ValidationResult:
        """Check invariant before execution."""
        try:
            if self.checker(context.parameters):
                return ValidationResult(
                    approved=True,
                    context=context,
                    reason=DecisionReason.APPROVED,
                    message=f"Invariant satisfied: {self.name}",
                    check_name=self.name
                )
            else:
                return ValidationResult(
                    approved=False,
                    context=context,
                    reason=DecisionReason.INVARIANT_VIOLATED,
                    message=self.failure_message,
                    severity=Severity.HIGH,
                    details={"invariant": self.name},
                    check_name=self.name
                )
        except Exception as e:
            logger.error(f"[CONTRACT] Invariant check error: {e}")
            return ValidationResult(
                approved=False,
                context=context,
                reason=DecisionReason.INTERNAL_ERROR,
                message=f"Invariant check failed: {str(e)}",
                severity=Severity.CRITICAL,
                details={"invariant": self.name, "error": str(e)},
                check_name=self.name
            )

    def check_post(
        self,
        context: "ExecutionContext",
        execution_result: Any,
        manifest_data: Optional[Dict] = None
    ) -> PostConditionResult:
        """Check invariant after execution."""
        try:
            held = self.checker(context.parameters)
            return PostConditionResult(
                passed=held,
                results=[{
                    "name": self.name,
                    "passed": held,
                    "description": self.failure_message if not held else "Invariant held"
                }],
                failed_conditions=[{
                    "name": self.name,
                    "reason": self.failure_message
                }] if not held else []
            )
        except Exception as e:
            return PostConditionResult(
                passed=False,
                failed_conditions=[{
                    "name": self.name,
                    "reason": f"Invariant check error: {str(e)}"
                }]
            )


# =============================================================================
# COMPOSITE CONTRACTS
# =============================================================================

class AndContract(BaseContract):
    """Contract that requires ALL sub-contracts to pass."""

    def __init__(self, *contracts: BaseContract):
        self.contracts = contracts

    def check_pre(
        self,
        context: "ExecutionContext",
        manifest_data: Optional[Dict] = None
    ) -> ValidationResult:
        """Check all pre-conditions."""
        results = []
        all_approved = True

        for contract in self.contracts:
            result = contract.check_pre(context, manifest_data)
            results.append(result)
            if not result.approved:
                all_approved = False

        # Find first failure reason
        failed_result = next((r for r in results if not r.approved), None)

        if failed_result:
            return ValidationResult(
                approved=False,
                context=context,
                reason=failed_result.reason,
                message=f"AND contract failed: {failed_result.check_name}",
                severity=failed_result.severity,
                details={
                    "failed_contract": failed_result.check_name,
                    "all_results": [r.to_dict() for r in results]
                },
                check_name="and_contract"
            )

        return ValidationResult(
            approved=True,
            context=context,
            reason=DecisionReason.APPROVED,
            message="All AND contracts passed",
            details={"count": len(results)},
            check_name="and_contract"
        )

    def check_post(
        self,
        context: "ExecutionContext",
        execution_result: Any,
        manifest_data: Optional[Dict] = None
    ) -> PostConditionResult:
        """Check all post-conditions."""
        all_results = []
        all_failed = []

        for contract in self.contracts:
            result = contract.check_post(context, execution_result, manifest_data)
            all_results.extend(result.results)
            all_failed.extend(result.failed_conditions)

        return PostConditionResult(
            passed=len(all_failed) == 0,
            results=all_results,
            failed_conditions=all_failed
        )


class OrContract(BaseContract):
    """Contract that requires AT LEAST ONE sub-contract to pass."""

    def __init__(self, *contracts: BaseContract):
        self.contracts = contracts

    def check_pre(
        self,
        context: "ExecutionContext",
        manifest_data: Optional[Dict] = None
    ) -> ValidationResult:
        """Check pre-conditions - pass if ANY passes."""
        results = []
        any_approved = False

        for contract in self.contracts:
            result = contract.check_pre(context, manifest_data)
            results.append(result)
            if result.approved:
                any_approved = True

        if any_approved:
            return ValidationResult(
                approved=True,
                context=context,
                reason=DecisionReason.APPROVED,
                message="OR contract passed",
                details={"count": len(results)},
                check_name="or_contract"
            )

        # All failed
        return ValidationResult(
            approved=False,
            context=context,
            reason=DecisionReason.PRE_CONDITION_FAILED,
            message="All OR contracts failed",
            severity=Severity.HIGH,
            details={
                "all_results": [r.to_dict() for r in results]
            },
            check_name="or_contract"
        )

    def check_post(
        self,
        context: "ExecutionContext",
        execution_result: Any,
        manifest_data: Optional[Dict] = None
    ) -> PostConditionResult:
        """Check post-conditions - pass if ANY passes."""
        all_results = []
        all_failed = []

        for contract in self.contracts:
            result = contract.check_post(context, execution_result, manifest_data)
            all_results.extend(result.results)
            if result.passed:
                # At least one passed
                return PostConditionResult(
                    passed=True,
                    results=all_results
                )
            all_failed.extend(result.failed_conditions)

        return PostConditionResult(
            passed=False,
            results=all_results,
            failed_conditions=all_failed
        )


class NotContract(BaseContract):
    """Contract that inverts the result of another contract."""

    def __init__(self, contract: BaseContract):
        self.contract = contract

    def check_pre(
        self,
        context: "ExecutionContext",
        manifest_data: Optional[Dict] = None
    ) -> ValidationResult:
        """Invert pre-condition result."""
        result = self.contract.check_pre(context, manifest_data)

        return ValidationResult(
            approved=not result.approved,
            context=context,
            reason=DecisionReason.APPROVED if not result.approved else result.reason,
            message=f"NOT({result.check_name}): {result.message}",
            severity=result.severity,
            details={"original_result": result.to_dict()},
            check_name=f"not_{result.check_name}"
        )

    def check_post(
        self,
        context: "ExecutionContext",
        execution_result: Any,
        manifest_data: Optional[Dict] = None
    ) -> PostConditionResult:
        """Invert post-condition result."""
        result = self.contract.check_post(context, execution_result, manifest_data)

        return PostConditionResult(
            passed=not result.passed,
            results=[{
                "name": f"not_{self.contract.__class__.__name__}",
                "passed": not result.passed,
                "original_passed": result.passed
            }]
        )


# =============================================================================
# INTENT CONTRACT - Main Contract Class
# =============================================================================

@dataclass
class IntentContractConfig:
    """Configuration for IntentContract."""
    name: str
    description: str = ""
    pre_contracts: List[BaseContract] = field(default_factory=list)
    post_contracts: List[BaseContract] = field(default_factory=list)
    fail_fast: bool = True  # Stop checking on first failure


class IntentContract(BaseContract):
    """
    Main Intent Contract class.

    Composes multiple contracts and validates them in order.

    Usage:
        contract = IntentContract("my_operation")
        contract.add_pre_check(RequirePermission("write"))
        contract.add_pre_check(ProtectedPathCheck())

        result = contract.validate_pre(context, manifest_data)
    """

    def __init__(
        self,
        name: str,
        description: str = "",
        fail_fast: bool = True
    ):
        self.name = name
        self.description = description
        self.fail_fast = fail_fast
        self.pre_contracts: List[BaseContract] = []
        self.post_contracts: List[BaseContract] = []

    def add_pre_check(self, contract: BaseContract) -> "IntentContract":
        """Add a pre-condition check."""
        self.pre_contracts.append(contract)
        return self

    def add_post_check(self, contract: BaseContract) -> "IntentContract":
        """Add a post-condition check."""
        self.post_contracts.append(contract)
        return self

    def check_pre(
        self,
        context: "ExecutionContext",
        manifest_data: Optional[Dict] = None
    ) -> ValidationResult:
        """
        Check all pre-conditions.

        Returns:
            ValidationResult with combined result of all checks
        """
        if not self.pre_contracts:
            # No pre-conditions = always allowed
            return ValidationResult(
                approved=True,
                context=context,
                reason=DecisionReason.APPROVED,
                message="No pre-conditions",
                check_name=self.name
            )

        results = []
        failures = []

        for contract in self.pre_contracts:
            result = contract.check_pre(context, manifest_data)
            results.append(result)

            if not result.approved:
                failures.append(result)

                # Fail fast on first failure
                if self.fail_fast:
                    return ValidationResult(
                        approved=False,
                        context=context,
                        reason=result.reason,
                        message=f"Pre-condition failed: {result.check_name}",
                        severity=result.severity,
                        details={
                            "contract": self.name,
                            "failed_check": result.check_name,
                            "check_results": [r.to_dict() for r in results]
                        },
                        check_name=self.name
                    )

        # If any failures, deny (for non-fail-fast case)
        if failures:
            return ValidationResult(
                approved=False,
                context=context,
                reason=failures[0].reason,
                message=f"{len(failures)} pre-condition(s) failed",
                severity=failures[0].severity,
                details={
                    "contract": self.name,
                    "failures": [f.check_name for f in failures],
                    "check_results": [r.to_dict() for r in results]
                },
                check_name=self.name
            )

        # All passed
        return ValidationResult(
            approved=True,
            context=context,
            reason=DecisionReason.APPROVED,
            message=f"All pre-conditions passed: {self.name}",
            details={
                "contract": self.name,
                "checks_count": len(results)
            },
            check_name=self.name
        )

    def check_post(
        self,
        context: "ExecutionContext",
        execution_result: Any,
        manifest_data: Optional[Dict] = None
    ) -> PostConditionResult:
        """
        Check all post-conditions.

        Returns:
            PostConditionResult with combined result of all checks
        """
        all_results = []
        all_failed = []

        for contract in self.post_contracts:
            result = contract.check_post(context, execution_result, manifest_data)
            all_results.extend(result.results)
            all_failed.extend(result.failed_conditions)

            if self.fail_fast and result.failed_conditions:
                # Fail fast
                break

        return PostConditionResult(
            passed=len(all_failed) == 0,
            results=all_results,
            failed_conditions=all_failed,
            execution_output=str(execution_result)[:500] if execution_result else None
        )

    def validate(
        self,
        context: "ExecutionContext",
        manifest_data: Optional[Dict] = None
    ) -> ValidationResult:
        """Alias for check_pre - for backward compatibility."""
        return self.check_pre(context, manifest_data)


# =============================================================================
# CONTRACT BUILDER
# =============================================================================

class ContractBuilder:
    """
    Builder for creating IntentContracts with fluent API.

    Usage:
        contract = (ContractBuilder("write_file")
                   .require_permission("file.write")
                   .protect_paths()
                   .max_size(10_000_000)
                   .build())
    """

    def __init__(self, name: str):
        self.name = name
        self.description = ""
        self.fail_fast = True
        self._pre_contracts: List[BaseContract] = []
        self._post_contracts: List[BaseContract] = []

    def with_description(self, desc: str) -> "ContractBuilder":
        """Set contract description."""
        self.description = desc
        return self

    def require_permission(self, permission: str, resource: Optional[str] = None) -> "ContractBuilder":
        """Add permission requirement."""
        self._pre_contracts.append(RequirePermission(permission, resource))
        return self

    def require_domain(self, domain: str) -> "ContractBuilder":
        """Add domain requirement."""
        self._pre_contracts.append(RequireDomainEnabled(domain))
        return self

    def protect_paths(self, path_param: str = "path") -> "ContractBuilder":
        """Add protected path check."""
        self._pre_contracts.append(ProtectedPathCheck(path_param))
        return self

    def max_size(self, max_bytes: int) -> "ContractBuilder":
        """Add size limit."""
        self._pre_contracts.append(MaxOperationSize(max_bytes))
        return self

    def add_pre(self, contract: BaseContract) -> "ContractBuilder":
        """Add custom pre-condition contract."""
        self._pre_contracts.append(contract)
        return self

    def add_post(self, contract: BaseContract) -> "ContractBuilder":
        """Add custom post-condition contract."""
        self._post_contracts.append(contract)
        return self

    def add_invariant(
        self,
        name: str,
        checker: Callable[[Dict], bool],
        failure_message: str = "Invariant violated"
    ) -> "ContractBuilder":
        """Add custom invariant."""
        self._pre_contracts.append(CustomInvariant(name, checker, failure_message))
        return self

    def with_fail_fast(self, enabled: bool = True) -> "ContractBuilder":
        """Set fail-fast mode."""
        self.fail_fast = enabled
        return self

    def build(self) -> IntentContract:
        """Build the IntentContract."""
        contract = IntentContract(
            name=self.name,
            description=self.description,
            fail_fast=self.fail_fast
        )
        contract.pre_contracts = self._pre_contracts
        contract.post_contracts = self._post_contracts
        return contract


# =============================================================================
# PREDEFINED CONTRACTS
# =============================================================================

# Common operation contracts
READ_FILE_CONTRACT = (
    ContractBuilder("read_file")
    .require_permission("file.read")
    .protect_paths()
    .build()
)

WRITE_FILE_CONTRACT = (
    ContractBuilder("write_file")
    .require_permission("file.write")
    .protect_paths()
    .max_size(100_000_000)  # 100 MB
    .build()
)

EXEC_CODE_CONTRACT = (
    ContractBuilder("exec_code")
    .max_size(1_000_000)  # 1 MB - check first
    .require_permission("code.execute")
    .build()
)

DELETE_FILE_CONTRACT = (
    ContractBuilder("delete_file")
    .require_permission("file.delete")
    .protect_paths()
    .build()
)


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # Base classes
    "BaseContract",
    "IntentContract",
    "IntentContractConfig",
    "ContractBuilder",

    # Primitive contracts
    "AlwaysAllow",
    "AlwaysDeny",
    "RequirePermission",
    "RequireDomainEnabled",
    "MaxOperationSize",
    "ProtectedPathCheck",
    "RequireManifestContract",
    "CustomInvariant",

    # Composite contracts
    "AndContract",
    "OrContract",
    "NotContract",

    # Predefined contracts
    "READ_FILE_CONTRACT",
    "WRITE_FILE_CONTRACT",
    "EXEC_CODE_CONTRACT",
    "DELETE_FILE_CONTRACT",
]
