import pytest
import time
from unittest.mock import MagicMock, patch
from kernel.execution_kernel import (
    ExecutionKernel,
    ExecutionContext,
    KernelConfig,
    FastPathConfig,
    CircuitState,
    ResourceLimits,
    ConditionResult,
    get_kernel
)
from kernel.validation import DecisionReason, Severity, ValidationResult
from kernel.manifests import ManifestLoader

@pytest.fixture
def mock_loader():
    loader = MagicMock(spec=ManifestLoader)
    loader.is_domain_enabled.return_value = True
    loader.get_risk_level.return_value = 0.1
    loader.get_operation_contract.return_value = {}
    loader.load.return_value = {"domain": "test"}
    return loader

@pytest.fixture
def kernel(mock_loader):
    return ExecutionKernel(manifest_loader=mock_loader)

def test_execution_context_request_id():
    ctx1 = ExecutionContext(agent_id="a1", operation="op1", parameters={"p": 1})
    ctx2 = ExecutionContext(agent_id="a1", operation="op1", parameters={"p": 1})
    
    assert ctx1.request_id is not None
    assert len(ctx1.request_id) == 16
    
    # Custom request_id
    ctx3 = ExecutionContext(agent_id="a1", operation="op1", parameters={"p": 1}, request_id="custom")
    assert ctx3.request_id == "custom"

def test_register_operation(kernel):
    mock_op = MagicMock(return_value="ok")
    kernel.register_operation("my_op", mock_op, "Test operation")
    assert "my_op" in kernel.approved_operations
    assert kernel.approved_operations["my_op"] == mock_op
    
    kernel.unregister_operation("my_op")
    assert "my_op" not in kernel.approved_operations
    
    # Unregister non-existent
    kernel.unregister_operation("ghost") # Should not raise

def test_register_contract(kernel):
    mock_contract = MagicMock()
    kernel.register_contract("op1", mock_contract)
    assert kernel.contracts["op1"] == mock_contract

def test_add_invariant(kernel):
    def my_inv(p): return True
    kernel.add_invariant(my_inv, "check_something")
    assert my_inv in kernel.invariants

def test_fast_path_eligibility(kernel, mock_loader):
    context = ExecutionContext(agent_id="a1", operation="read_file", parameters={})
    
    # Eligible
    mock_loader.get_risk_level.return_value = 0.1
    assert kernel._is_fast_path_eligible(context) is True
    
    # Disabled in config
    kernel.config.fast_path.enabled = False
    assert kernel._is_fast_path_eligible(context) is False
    kernel.config.fast_path.enabled = True
    
    # Operation not allowed for fast path
    context.operation = "delete_file"
    assert kernel._is_fast_path_eligible(context) is False
    context.operation = "read_file"
    
    # High risk
    mock_loader.get_risk_level.return_value = 0.3
    assert kernel._is_fast_path_eligible(context) is False
    mock_loader.get_risk_level.return_value = 0.1
    
    # Circuit breaker RED/BLACK
    kernel.circuit_state = CircuitState.RED
    assert kernel._is_fast_path_eligible(context) is False
    kernel.circuit_state = CircuitState.BLACK
    assert kernel._is_fast_path_eligible(context) is False
    kernel.circuit_state = CircuitState.GREEN
    assert kernel._is_fast_path_eligible(context) is True

def test_validate_full_chain_success(kernel, mock_loader):
    context = ExecutionContext(agent_id="a1", operation="write_file", parameters={"path": "/tmp/test.txt"})
    mock_loader.get_risk_level.return_value = 0.3 # Not eligible for fast path
    
    result = kernel.validate(context)
    assert result.approved is True
    assert result.reason == DecisionReason.APPROVED
    assert result.check_name == "approved"

def test_validate_domain_disabled(kernel, mock_loader):
    mock_loader.is_domain_enabled.return_value = False
    context = ExecutionContext(agent_id="a1", operation="op1", parameters={}, domain="restricted")
    
    result = kernel.validate(context)
    assert result.approved is False
    assert result.reason == DecisionReason.DOMAIN_DISABLED

def test_validate_rbac(kernel, mock_loader):
    mock_loader.get_operation_contract.return_value = {"required_permission": "admin"}
    
    # Fail
    ctx_fail = ExecutionContext(agent_id="a1", operation="op1", parameters={"_permissions": ["user"]})
    assert kernel.validate(ctx_fail).approved is False
    
    # Success
    ctx_ok = ExecutionContext(agent_id="a1", operation="op1", parameters={"_permissions": ["admin"]})
    assert kernel.validate(ctx_ok).approved is True

def test_validate_risk_thresholds(kernel, mock_loader):
    mock_loader.get_risk_level.return_value = 0.4
    kernel.config.default_risk_threshold = 0.5
    context = ExecutionContext(agent_id="a1", operation="op1", parameters={})
    
    # Green - OK (0.4 < 0.5)
    kernel.circuit_state = CircuitState.GREEN
    assert kernel.validate(context).approved is True
    
    # Amber - Threshold 0.5 * 0.7 = 0.35. (0.4 > 0.35) -> Fail
    kernel.circuit_state = CircuitState.AMBER
    assert kernel.validate(context).approved is False
    
    # Red - Threshold 0.5 * 0.3 = 0.15. Fail.
    kernel.circuit_state = CircuitState.RED
    assert kernel.validate(context).approved is False
    
    # Black - Threshold 0.0. Fail.
    kernel.circuit_state = CircuitState.BLACK
    assert kernel.validate(context).approved is False

def test_validate_circuit_breaker_restrictions(kernel, mock_loader):
    # RED state - only read operations
    kernel.circuit_state = CircuitState.RED
    
    # Read op - OK
    ctx_read = ExecutionContext(agent_id="a1", operation="read_file", parameters={})
    assert kernel.validate(ctx_read).approved is True
    
    # Write op - Fail
    ctx_write = ExecutionContext(agent_id="a1", operation="write_file", parameters={})
    assert kernel.validate(ctx_write).approved is False
    assert kernel.validate(ctx_write).reason == DecisionReason.CIRCUIT_OPEN
    
    # AMBER state - requires approval check
    kernel.circuit_state = CircuitState.AMBER
    mock_loader.get_operation_contract.return_value = {"requires_approval": True}
    ctx_appr = ExecutionContext(agent_id="a1", operation="critical_op", parameters={})
    assert kernel.validate(ctx_appr).approved is False
    assert kernel.validate(ctx_appr).reason == DecisionReason.APPROVAL_REQUIRED

def test_validate_resource_limits(kernel, mock_loader):
    kernel.config.resource_limits = ResourceLimits(max_tokens=100, max_execution_time=10)
    mock_loader.get_risk_level.return_value = 0.5 # Bypasses fast path
    
    # Token limit
    ctx_tokens = ExecutionContext(agent_id="a1", operation="read_file", parameters={"_token_count": 150})
    assert kernel.validate(ctx_tokens).approved is False
    assert kernel.validate(ctx_tokens).reason == DecisionReason.RESOURCE_LIMIT
    
    # Time limit
    ctx_time = ExecutionContext(agent_id="a1", operation="read_file", parameters={"_time_estimate": 15})
    assert kernel.validate(ctx_time).approved is False
    
    # OK
    ctx_ok = ExecutionContext(agent_id="a1", operation="read_file", parameters={"_token_count": 50, "_time_estimate": 5})
    assert kernel.validate(ctx_ok).approved is True

def test_execute_full_flow(kernel, mock_loader):
    mock_op = MagicMock(return_value="result_data")
    kernel.register_operation("test_op", mock_op)
    
    # Success
    res = kernel.execute("test_op", {"x": 1}, "agent1")
    assert res == "result_data"
    mock_op.assert_called_with(x=1)
    
    # Unregistered
    with pytest.raises(ValueError, match="Unknown operation"):
        kernel.execute("ghost", {}, "agent1")
        
    # Validation Fail
    mock_loader.is_domain_enabled.return_value = False
    with pytest.raises(PermissionError, match="denied"):
        kernel.execute("test_op", {}, "agent1")

def test_execute_with_contract(kernel, mock_loader):
    mock_op = MagicMock(return_value="output")
    kernel.register_operation("op", mock_op)
    
    mock_contract = MagicMock()
    mock_contract.check_pre.return_value = MagicMock(approved=True)
    mock_contract.check_post.return_value = MagicMock(passed=True)
    
    kernel.register_contract("op", mock_contract)
    
    res = kernel.execute("op", {"arg": 1}, "agent1")
    assert res == "output"
    assert mock_contract.check_pre.called
    assert mock_contract.check_post.called
    
    # Pre-condition fail
    mock_contract.check_pre.return_value = MagicMock(approved=False, message="No way", reason=DecisionReason.PRE_CONDITION_FAILED, severity=Severity.HIGH, details={}, check_name="test")
    with pytest.raises(PermissionError, match="Contract pre-condition failed"):
        kernel.execute("op", {}, "agent1")
        
    # Post-condition fail
    mock_contract.check_pre.return_value = MagicMock(approved=True)
    mock_contract.check_post.return_value = MagicMock(passed=False, failed_conditions=["bad output"])
    with pytest.raises(ValueError, match="Contract post-condition failed"):
        kernel.execute("op", {}, "agent1")

def test_execute_invariants(kernel):
    mock_op = MagicMock(return_value="ok")
    kernel.register_operation("op", mock_op)
    
    inv_mock = MagicMock(return_value=True)
    kernel.add_invariant(inv_mock, "test_inv")
    
    kernel.execute("op", {"data": "val"}, "agent1")
    assert inv_mock.call_count == 2 # Before and after
    
    # Fail before
    inv_mock.side_effect = [False, True]
    with pytest.raises(ValueError, match="Invariant violation before"):
        kernel.execute("op", {"data": "bad"}, "agent1")
        
    # Fail after
    inv_mock.side_effect = [True, False]
    with pytest.raises(ValueError, match="Invariant violation after"):
        kernel.execute("op", {"data": "bad"}, "agent1")

def test_audit_fail_closed(kernel):
    kernel.config.enable_audit = True
    kernel.config.audit_fail_closed = True
    
    ctx = ExecutionContext(agent_id="a1", operation="op1", parameters={})
    
    # Mock hashlib to fail during audit
    with patch("kernel.execution_kernel.hashlib.sha256") as mock_hash:
        mock_hash.side_effect = Exception("Crypto error")
        
        # Manually trigger validation steps to reach audit
        kernel._check_domain_enabled = MagicMock(return_value=ValidationResult(approved=True, context=ctx, reason=DecisionReason.PENDING))
        kernel._check_rbac = MagicMock(return_value=ValidationResult(approved=True, context=ctx, reason=DecisionReason.PENDING))
        kernel._check_risk_threshold = MagicMock(return_value=ValidationResult(approved=True, context=ctx, reason=DecisionReason.PENDING))
        kernel._check_pre_conditions = MagicMock(return_value=ValidationResult(approved=True, context=ctx, reason=DecisionReason.PENDING))
        kernel._check_circuit_breaker = MagicMock(return_value=ValidationResult(approved=True, context=ctx, reason=DecisionReason.PENDING))
        kernel._check_resource_limits = MagicMock(return_value=ValidationResult(approved=True, context=ctx, reason=DecisionReason.PENDING))
        
        res = kernel.validate(ctx)
        assert res.approved is False
        assert res.reason == DecisionReason.AUDIT_FAILED

def test_kernel_stats(kernel):
    kernel.register_operation("read_file", lambda **kw: "ok")
    kernel.execute("read_file", {}, "agent1")
    
    stats = kernel.get_stats()
    assert stats["total_requests"] == 1
    assert stats["approved"] == 1
    assert stats["executed"] == 1
    assert stats["fast_path_hits"] == 1
    assert stats["approval_rate"] == 1.0
    assert stats["fast_path_rate"] == 1.0

def test_global_kernel():
    k1 = get_kernel(reload=True)
    k2 = get_kernel()
    assert k1 is k2
    
    k3 = get_kernel(reload=True)
    assert k1 is not k3

def test_evaluate_condition(kernel):
    # Test _eval_not_protected_path
    ctx_bad = ExecutionContext(agent_id="a1", operation="op", parameters={"path": "/etc/passwd"})
    res = kernel._eval_not_protected_path({}, ctx_bad)
    assert res.passed is False
    
    ctx_good = ExecutionContext(agent_id="a1", operation="op", parameters={"path": "/tmp/file"})
    res = kernel._eval_not_protected_path({}, ctx_good)
    assert res.passed is True
    
    # Test _eval_agent_has_permission
    ctx_perm = ExecutionContext(agent_id="a1", operation="op", parameters={"_permissions": ["read"]})
    assert kernel._eval_agent_has_permission({"permission": "read"}, ctx_perm).passed is True
    assert kernel._eval_agent_has_permission({"permission": "write"}, ctx_perm).passed is False
    
    # Test _eval_risk_acceptable
    ctx_risk = ExecutionContext(agent_id="a1", operation="op", parameters={})
    ctx_risk.intent_contract = {"_risk_level": 0.8}
    assert kernel._eval_risk_acceptable({"max_risk": 0.5}, ctx_risk).passed is False
    assert kernel._eval_risk_acceptable({"max_risk": 0.9}, ctx_risk).passed is True

def test_set_circuit_state(kernel):
    kernel.set_circuit_state(CircuitState.BLACK)
    assert kernel.circuit_state == CircuitState.BLACK
