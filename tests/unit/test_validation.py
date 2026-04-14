import pytest
from kernel.validation import (
    Severity,
    DecisionReason,
    ValidationResult,
    ValidationResultBuilder,
    PostConditionResult,
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
    assert Severity.CRITICAL.value == "critical"

def test_decision_reason_enum():
    assert DecisionReason.APPROVED.value == "approved"
    assert DecisionReason.INVARIANT_VIOLATED.value == "invariant_violated"

def test_validation_result_init(mock_context):
    result = ValidationResult(
        approved=True,
        context=mock_context,
        reason=DecisionReason.APPROVED,
        message="All good"
    )
    assert result.approved is True
    assert result.details == {}
    assert result.timestamp == ""

def test_validation_result_to_dict(mock_context):
    result = ValidationResult(
        approved=False,
        context=mock_context,
        reason=DecisionReason.PERMISSION_DENIED,
        message="No access",
        severity=Severity.HIGH,
        details={"sensitive_token": "secret123", "public_info": "hello"},
        check_name="rbac_check"
    )
    
    d = result.to_dict()
    assert d["approved"] is False
    assert d["reason"] == "permission_denied"
    assert d["severity"] == "high"
    assert d["details"]["sensitive_token"] == "***REDACTED***"
    assert d["details"]["public_info"] == "hello"
    assert d["agent_id"] == "test_agent"
    assert d["operation"] == "test_op"

def test_validation_result_sanitize_nested(mock_context):
    result = ValidationResult(
        approved=True,
        context=mock_context,
        reason=DecisionReason.APPROVED,
        details={
            "nested": {
                "password": "123",
                "other": "val"
            }
        }
    )
    sanitized = result._sanitize_details(result.details)
    assert sanitized["nested"]["password"] == "***REDACTED***"
    assert sanitized["nested"]["other"] == "val"

def test_validation_result_warnings_suggestions(mock_context):
    result = ValidationResult(
        approved=True,
        context=mock_context,
        reason=DecisionReason.APPROVED
    )
    result.with_warning("Watch out").with_suggestion("Try this")
    assert "Watch out" in result.warnings
    assert "Try this" in result.suggestions

def test_validation_result_is_blocking(mock_context):
    # Case 1: Not approved -> blocking
    r1 = ValidationResult(approved=False, context=mock_context, reason=DecisionReason.PERMISSION_DENIED)
    assert r1.is_blocking() is True
    
    # Case 2: Approved but high severity (unlikely but possible by definition) -> blocking
    r2 = ValidationResult(approved=True, context=mock_context, reason=DecisionReason.APPROVED, severity=Severity.HIGH)
    assert r2.is_blocking() is True
    
    # Case 3: Approved, low severity -> not blocking
    r3 = ValidationResult(approved=True, context=mock_context, reason=DecisionReason.APPROVED, severity=Severity.LOW)
    assert r3.is_blocking() is False

def test_validation_result_should_debate(mock_context):
    # Case 1: Reason is DEBATE_REQUIRED
    r1 = ValidationResult(approved=False, context=mock_context, reason=DecisionReason.DEBATE_REQUIRED)
    assert r1.should_debate() is True
    
    # Case 2: Risk level > 0.5
    r2 = ValidationResult(approved=True, context=mock_context, reason=DecisionReason.APPROVED, details={"risk_level": 0.6})
    assert r2.should_debate() is True
    
    # Case 3: Risk level <= 0.5
    r3 = ValidationResult(approved=True, context=mock_context, reason=DecisionReason.APPROVED, details={"risk_level": 0.4})
    assert r3.should_debate() is False

def test_post_condition_result():
    res = PostConditionResult(
        passed=False,
        results=[{"name": "check1", "passed": True}, {"name": "check2", "passed": False}],
        failed_conditions=[{"condition": "c2", "error": "failed"}]
    )
    d = res.to_dict()
    assert d["passed"] is False
    assert d["total_checks"] == 2
    assert d["passed_checks"] == 1
    assert d["failed_checks"] == 1

def test_validation_error(mock_context):
    result = ValidationResult(approved=False, context=mock_context, reason=DecisionReason.INTERNAL_ERROR, message="Boom")
    with pytest.raises(ValidationError) as excinfo:
        raise ValidationError(result)
    assert str(excinfo.value) == "Boom"
    assert excinfo.value.result == result

def test_validation_result_builder(mock_context):
    builder = ValidationResultBuilder(mock_context)
    
    # Test approve
    res = builder.approve("Looks good").with_details(foo="bar").with_warning("W").with_suggestion("S").build()
    assert res.approved is True
    assert res.reason == DecisionReason.APPROVED
    assert res.message == "Looks good"
    assert res.details["foo"] == "bar"
    assert "W" in res.warnings
    assert "S" in res.suggestions
    
    # Test deny
    builder = ValidationResultBuilder(mock_context)
    res = builder.deny(DecisionReason.RISK_TOO_HIGH, "Too risky", Severity.HIGH).build()
    assert res.approved is False
    assert res.reason == DecisionReason.RISK_TOO_HIGH
    assert res.severity == Severity.HIGH
    assert res.message == "Too risky"
