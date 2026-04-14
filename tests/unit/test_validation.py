import pytest
from datetime import datetime
from kernel.validation import (
    Severity,
    DecisionReason,
    ValidationResult,
    ValidationResultBuilder,
    PostConditionResult,
    InvariantResult,
    ValidationError
)
from kernel.execution_kernel import ExecutionContext

@pytest.fixture
def mock_context():
    return ExecutionContext(
        agent_id="test_agent",
        operation="test_op",
        parameters={"param1": "val1"},
        domain="test_domain"
    )

def test_severity_enum():
    assert Severity.LOW.value == "low"
    assert Severity.MEDIUM.value == "medium"
    assert Severity.HIGH.value == "high"
    assert Severity.CRITICAL.value == "critical"

def test_decision_reason_enum():
    assert DecisionReason.APPROVED.value == "approved"
    assert DecisionReason.PENDING.value == "pending"
    assert DecisionReason.DOMAIN_DISABLED.value == "domain_disabled"
    assert DecisionReason.PERMISSION_DENIED.value == "permission_denied"
    assert DecisionReason.RISK_TOO_HIGH.value == "risk_too_high"
    assert DecisionReason.DEBATE_REQUIRED.value == "debate_required"
    assert DecisionReason.PRE_CONDITION_FAILED.value == "pre_condition_failed"
    assert DecisionReason.POST_CONDITION_FAILED.value == "post_condition_failed"
    assert DecisionReason.INVARIANT_VIOLATED.value == "invariant_violated"
    assert DecisionReason.CIRCUIT_OPEN.value == "circuit_open"
    assert DecisionReason.RESOURCE_LIMIT.value == "resource_limit"
    assert DecisionReason.AUDIT_FAILED.value == "audit_failed"
    assert DecisionReason.INTERNAL_ERROR.value == "internal_error"

def test_validation_result_init(mock_context):
    result = ValidationResult(
        approved=True,
        context=mock_context,
        reason=DecisionReason.APPROVED,
        message="All good",
        check_name="initial_check",
        elapsed_ms=1.5,
        timestamp="2023-01-01T00:00:00Z"
    )
    assert result.approved is True
    assert result.details == {}
    assert result.message == "All good"
    assert result.check_name == "initial_check"
    assert result.elapsed_ms == 1.5
    assert result.timestamp == "2023-01-01T00:00:00Z"

def test_validation_result_to_dict(mock_context):
    result = ValidationResult(
        approved=False,
        context=mock_context,
        reason=DecisionReason.PERMISSION_DENIED,
        message="No access",
        severity=Severity.HIGH,
        details={"sensitive_token": "secret123", "public_info": "hello"},
        check_name="rbac_check",
        elapsed_ms=10.0,
        timestamp="2023-01-01T12:00:00Z"
    )
    
    d = result.to_dict()
    assert d["approved"] is False
    assert d["reason"] == "permission_denied"
    assert d["severity"] == "high"
    assert d["message"] == "No access"
    assert d["check_name"] == "rbac_check"
    assert d["elapsed_ms"] == 10.0
    assert d["timestamp"] == "2023-01-01T12:00:00Z"
    assert d["details"]["sensitive_token"] == "***REDACTED***"
    assert d["details"]["public_info"] == "hello"
    assert d["agent_id"] == "test_agent"
    assert d["operation"] == "test_op"

def test_validation_result_sanitize_complex(mock_context):
    result = ValidationResult(
        approved=True,
        context=mock_context,
        reason=DecisionReason.APPROVED,
        details={
            "api_key": "sk-123",
            "user": {
                "password": "password123",
                "email": "test@example.com",
                "creds": {
                    "secret": "mysecret"
                }
            },
            "data": [1, 2, 3]
        }
    )
    sanitized = result._sanitize_details(result.details)
    assert sanitized["api_key"] == "***REDACTED***"
    assert sanitized["user"]["password"] == "***REDACTED***"
    assert sanitized["user"]["email"] == "test@example.com"
    assert sanitized["user"]["creds"]["secret"] == "***REDACTED***"
    assert sanitized["data"] == [1, 2, 3]

def test_validation_result_sanitize_none(mock_context):
    result = ValidationResult(approved=True, context=mock_context, reason=DecisionReason.APPROVED)
    assert result._sanitize_details(None) is None
    assert result._sanitize_details({}) is None

def test_validation_result_fluent_interface(mock_context):
    result = ValidationResult(
        approved=True,
        context=mock_context,
        reason=DecisionReason.APPROVED
    )
    res2 = result.with_warning("W1").with_suggestion("S1").with_warning("W2")
    assert res2 is result
    assert result.warnings == ["W1", "W2"]
    assert result.suggestions == ["S1"]

def test_validation_result_is_blocking(mock_context):
    # Case 1: Not approved -> blocking
    assert ValidationResult(approved=False, context=mock_context, reason=DecisionReason.PERMISSION_DENIED).is_blocking() is True
    
    # Case 2: Approved but high severity -> blocking
    assert ValidationResult(approved=True, context=mock_context, reason=DecisionReason.APPROVED, severity=Severity.HIGH).is_blocking() is True
    assert ValidationResult(approved=True, context=mock_context, reason=DecisionReason.APPROVED, severity=Severity.CRITICAL).is_blocking() is True
    
    # Case 3: Approved, low/medium severity -> not blocking
    assert ValidationResult(approved=True, context=mock_context, reason=DecisionReason.APPROVED, severity=Severity.LOW).is_blocking() is False
    assert ValidationResult(approved=True, context=mock_context, reason=DecisionReason.APPROVED, severity=Severity.MEDIUM).is_blocking() is False

def test_validation_result_should_debate(mock_context):
    # Case 1: Reason is DEBATE_REQUIRED
    assert ValidationResult(approved=False, context=mock_context, reason=DecisionReason.DEBATE_REQUIRED).should_debate() is True
    
    # Case 2: Risk level > 0.5
    assert ValidationResult(approved=True, context=mock_context, reason=DecisionReason.APPROVED, details={"risk_level": 0.51}).should_debate() is True
    
    # Case 3: Risk level <= 0.5
    assert ValidationResult(approved=True, context=mock_context, reason=DecisionReason.APPROVED, details={"risk_level": 0.5}).should_debate() is False
    assert ValidationResult(approved=True, context=mock_context, reason=DecisionReason.APPROVED, details={"risk_level": 0.1}).should_debate() is False
    assert ValidationResult(approved=True, context=mock_context, reason=DecisionReason.APPROVED, details={}).should_debate() is False

def test_post_condition_result():
    res = PostConditionResult(
        passed=False,
        results=[{"name": "check1", "passed": True}, {"name": "check2", "passed": False}],
        failed_conditions=[{"condition": "c2", "error": "failed"}],
        execution_output="some output"
    )
    assert res.execution_output == "some output"
    d = res.to_dict()
    assert d["passed"] is False
    assert d["total_checks"] == 2
    assert d["passed_checks"] == 1
    assert d["failed_checks"] == 1
    assert d["failed_conditions"] == [{"condition": "c2", "error": "failed"}]

def test_invariant_result():
    res = InvariantResult(held=True, description="No data loss")
    assert res.held is True
    assert res.description == "No data loss"
    assert res.violation_details is None
    assert res.fatal is False
    
    res_fatal = InvariantResult(held=False, description="System integrity", fatal=True, violation_details={"error": "corrupted"})
    assert res_fatal.held is False
    assert res_fatal.fatal is True
    assert res_fatal.violation_details == {"error": "corrupted"}

def test_validation_error(mock_context):
    result = ValidationResult(approved=False, context=mock_context, reason=DecisionReason.INTERNAL_ERROR, message="Boom")
    with pytest.raises(ValidationError) as excinfo:
        raise ValidationError(result)
    assert str(excinfo.value) == "Boom"
    assert excinfo.value.result == result

def test_validation_result_builder(mock_context):
    builder = ValidationResultBuilder(mock_context)
    
    # Default state
    assert builder.approved is False
    assert builder.reason == DecisionReason.PENDING
    
    # Test approve
    res = builder.approve("Success").with_details(foo="bar").with_warning("W").with_suggestion("S").build()
    assert res.approved is True
    assert res.reason == DecisionReason.APPROVED
    assert res.message == "Success"
    assert res.details["foo"] == "bar"
    assert "W" in res.warnings
    assert "S" in res.suggestions
    
    # Test deny
    builder = ValidationResultBuilder(mock_context)
    res = builder.deny(DecisionReason.RISK_TOO_HIGH, "Too risky", Severity.CRITICAL).build()
    assert res.approved is False
    assert res.reason == DecisionReason.RISK_TOO_HIGH
    assert res.severity == Severity.CRITICAL
    assert res.message == "Too risky"
    
    # Test fluent
    builder = ValidationResultBuilder(mock_context)
    res = builder.with_warning("W1").with_suggestion("S1").build()
    assert res.warnings == ["W1"]
    assert res.suggestions == ["S1"]
