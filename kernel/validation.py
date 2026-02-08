# archon/kernel/validation.py
"""
Type-safe validation results for ExecutionKernel.

Provides:
- ValidationResult: Standard result type for all validation checks
- DecisionReason: Enum of all possible decision reasons
- Severity: Severity levels for failures
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional, List
from datetime import datetime


class Severity(Enum):
    """Severity levels for validation failures."""
    LOW = "low"           # Informational, operation may proceed
    MEDIUM = "medium"     # Warning, operation blocked but not critical
    HIGH = "high"         # Serious violation, operation blocked
    CRITICAL = "critical" # Severe issue, potential attack


class DecisionReason(Enum):
    """Reasons for validation decisions."""

    # Positive outcomes
    APPROVED = "approved"         # All checks passed
    PENDING = "pending"           # Intermediate state, check continuing

    # Domain issues
    DOMAIN_DISABLED = "domain_disabled"  # Domain is not enabled
    DOMAIN_NOT_FOUND = "domain_not_found"  # Domain configuration missing

    # Permission issues
    PERMISSION_DENIED = "permission_denied"  # RBAC check failed
    APPROVAL_REQUIRED = "approval_required"  # Human approval needed

    # Risk issues
    RISK_TOO_HIGH = "risk_too_high"  # Operation exceeds risk threshold
    DEBATE_REQUIRED = "debate_required"  # Requires debate pipeline

    # Contract issues
    PRE_CONDITION_FAILED = "pre_condition_failed"  # Pre-condition check failed
    POST_CONDITION_FAILED = "post_condition_failed"  # Post-condition check failed
    INVARIANT_VIOLATED = "invariant_violated"  # Invariant check failed

    # Circuit breaker
    CIRCUIT_OPEN = "circuit_open"  # Circuit breaker blocking operations

    # Resource limits
    RESOURCE_LIMIT = "resource_limit"  # Token/time/memory limit exceeded
    RATE_LIMITED = "rate_limited"  # Too many requests

    # Audit issues
    AUDIT_FAILED = "audit_failed"  # Audit logging failed

    # System issues
    INTERNAL_ERROR = "internal_error"  # Kernel internal error
    TIMEOUT = "timeout"  # Validation timed out
    UNAVAILABLE = "unavailable"  # Required service unavailable


@dataclass
class ValidationResult:
    """
    Result of a validation check.

    All validation checks return this type for consistency.
    """

    approved: bool  # True if operation can proceed
    context: "ExecutionContext"  # The request context
    reason: DecisionReason  # Primary reason for decision
    message: str = ""  # Human-readable message
    severity: Severity = Severity.LOW  # Severity of failure (if not approved)
    details: Optional[Dict[str, Any]] = None  # Additional details
    check_name: str = ""  # Name of the check that produced this result
    elapsed_ms: float = 0.0  # Time taken for check
    timestamp: str = ""  # ISO timestamp of result

    # Additional metadata
    warnings: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)

    def __post_init__(self):
        if self.details is None:
            self.details = {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "approved": self.approved,
            "reason": self.reason.value if isinstance(self.reason, DecisionReason) else str(self.reason),
            "message": self.message,
            "severity": self.severity.value if isinstance(self.severity, Severity) else str(self.severity),
            "check_name": self.check_name,
            "elapsed_ms": self.elapsed_ms,
            "timestamp": self.timestamp,
            "warnings": self.warnings,
            "suggestions": self.suggestions,
            "details": self._sanitize_details(self.details),
            "agent_id": getattr(self.context, "agent_id", "unknown"),
            "operation": getattr(self.context, "operation", "unknown"),
        }

    def _sanitize_details(self, details: Optional[Dict]) -> Optional[Dict]:
        """Remove sensitive information from details."""
        if not details:
            return None

        # Remove keys that might contain sensitive data
        sensitive_keys = {"token", "password", "secret", "key", "auth", "credential"}
        sanitized = {}

        for key, value in details.items():
            key_lower = key.lower()
            if any(s in key_lower for s in sensitive_keys):
                sanitized[key] = "***REDACTED***"
            elif isinstance(value, dict):
                sanitized[key] = self._sanitize_details(value)
            else:
                sanitized[key] = value

        return sanitized

    def with_warning(self, warning: str) -> "ValidationResult":
        """Add a warning to this result."""
        self.warnings.append(warning)
        return self

    def with_suggestion(self, suggestion: str) -> "ValidationResult":
        """Add a suggestion to this result."""
        self.suggestions.append(suggestion)
        return self

    def is_blocking(self) -> bool:
        """Check if this result should block operation."""
        return not self.approved or self.severity in (Severity.HIGH, Severity.CRITICAL)

    def should_debate(self) -> bool:
        """Check if this operation requires debate."""
        return self.reason == DecisionReason.DEBATE_REQUIRED or (
            self.approved and
            self.details and
            self.details.get("risk_level", 0) > 0.5
        )


@dataclass
class PostConditionResult:
    """Result of post-condition validation after execution."""

    passed: bool  # True if all post-conditions satisfied
    results: List[Dict[str, Any]] = field(default_factory=list)
    failed_conditions: List[Dict] = field(default_factory=list)
    execution_output: Optional[Any] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "passed": self.passed,
            "total_checks": len(self.results),
            "passed_checks": sum(1 for r in self.results if r.get("passed", False)),
            "failed_checks": len(self.failed_conditions),
            "failed_conditions": self.failed_conditions,
        }


@dataclass
class InvariantResult:
    """Result of invariant validation."""

    held: bool  # True if invariant was maintained
    description: str = ""
    violation_details: Optional[Dict[str, Any]] = None
    fatal: bool = False  # If True, system cannot continue


class ValidationError(Exception):
    """Raised when validation fails critically."""

    def __init__(self, result: ValidationResult):
        self.result = result
        super().__init__(result.message)


# =============================================================================
# Result Builders
# =============================================================================

class ValidationResultBuilder:
    """Builder for creating ValidationResult objects."""

    def __init__(self, context: "ExecutionContext"):
        self.context = context
        self.approved = False
        self.reason = DecisionReason.PENDING
        self.message = ""
        self.severity = Severity.LOW
        self.details = {}
        self.warnings = []
        self.suggestions = []

    def approve(self, message: str = "Approved") -> "ValidationResultBuilder":
        """Mark as approved."""
        self.approved = True
        self.reason = DecisionReason.APPROVED
        self.message = message
        return self

    def deny(
        self,
        reason: DecisionReason,
        message: str,
        severity: Severity = Severity.MEDIUM
    ) -> "ValidationResultBuilder":
        """Mark as denied."""
        self.approved = False
        self.reason = reason
        self.message = message
        self.severity = severity
        return self

    def with_details(self, **kwargs) -> "ValidationResultBuilder":
        """Add details."""
        self.details.update(kwargs)
        return self

    def with_warning(self, warning: str) -> "ValidationResultBuilder":
        """Add warning."""
        self.warnings.append(warning)
        return self

    def with_suggestion(self, suggestion: str) -> "ValidationResultBuilder":
        """Add suggestion."""
        self.suggestions.append(suggestion)
        return self

    def build(self) -> ValidationResult:
        """Build the ValidationResult."""
        return ValidationResult(
            approved=self.approved,
            context=self.context,
            reason=self.reason,
            message=self.message,
            severity=self.severity,
            details=self.details if self.details else None,
            warnings=self.warnings,
            suggestions=self.suggestions,
        )
