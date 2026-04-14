import pytest
import time
from unittest.mock import MagicMock, patch
from kernel.execution_kernel import (
    ExecutionKernel,
    ExecutionContext,
    KernelConfig,
    FastPathConfig,
    CircuitState,
    ResourceLimits
)
from kernel.validation import DecisionReason, Severity, ValidationResult
from kernel.manifests import ManifestLoader

@pytest.fixture
def mock_loader():
    loader = MagicMock(spec=ManifestLoader)
    loader.is_domain_enabled.return_value = True
    loader.get_risk_level.return_value = 0.1
    loader.get_operation_contract.return_value = {}
    return loader

@pytest.fixture
def kernel(mock_loader):
    return ExecutionKernel(manifest_loader=mock_loader)

def test_execution_context_request_id():
    ctx1 = ExecutionContext(agent_id="a1", operation="op1", parameters={"p": 1})
    ctx2 = ExecutionContext(agent_id="a1", operation="op1", parameters={"p": 1})
    
    assert ctx1.request_id is not None
    assert len(ctx1.request_id) == 16
    # Same parameters should produce same request_id if timestamp is the same 
    # (but it's not here because it's default_factory=time.time)
    
    ctx3 = ExecutionContext(agent_id="a1", operation="op1", parameters={"p": 1}, request_id="custom")
    assert ctx3.request_id == "custom"

def test_register_operation(kernel):
    def my_op(x): return x + 1
    kernel.register_operation("add_one", my_op, "Adds one")
    assert "add_one" in kernel.approved_operations
    assert kernel.approved_operations["add_one"] == my_op
    
    kernel.unregister_operation("add_one")
    assert "add_one" not in kernel.approved_operations

def test_fast_path_eligibility(kernel, mock_loader):
    context = ExecutionContext(agent_id="a1", operation="read_file", parameters={})
    
    # 1. Default should be eligible
    mock_loader.get_risk_level.return_value = 0.1
    assert kernel._is_fast_path_eligible(context) is True
    
    # 2. High risk -> not eligible
    mock_loader.get_risk_level.return_value = 0.5
    assert kernel._is_fast_path_eligible(context) is False
    
    # 3. Not in allowed operations -> not eligible
    context.operation = "delete_all"
    assert kernel._is_fast_path_eligible(context) is False
    
    # 4. Circuit breaker RED -> not eligible
    context.operation = "read_file"
    mock_loader.get_risk_level.return_value = 0.1
    kernel.circuit_state = CircuitState.RED
    assert kernel._is_fast_path_eligible(context) is False

def test_validate_domain_disabled(kernel, mock_loader):
    mock_loader.is_domain_enabled.return_value = False
    context = ExecutionContext(agent_id="a1", operation="op1", parameters={}, domain="restricted")
    
    result = kernel.validate(context)
    assert result.approved is False
    assert result.reason == DecisionReason.DOMAIN_DISABLED

def test_validate_rbac_fail(kernel, mock_loader):
    mock_loader.get_operation_contract.return_value = {"required_permission": "admin"}
    context = ExecutionContext(agent_id="a1", operation="op1", parameters={"_permissions": ["user"]})
    
    result = kernel.validate(context)
    assert result.approved is False
    assert result.reason == DecisionReason.PERMISSION_DENIED

def test_validate_risk_too_high(kernel, mock_loader):
    mock_loader.get_risk_level.return_value = 0.9
    kernel.config.default_risk_threshold = 0.5
    context = ExecutionContext(agent_id="a1", operation="op1", parameters={})
    
    result = kernel.validate(context)
    assert result.approved is False
    assert result.reason == DecisionReason.RISK_TOO_HIGH

def test_validate_circuit_breaker_black(kernel):
    kernel.circuit_state = CircuitState.BLACK
    context = ExecutionContext(agent_id="a1", operation="read_file", parameters={})
    
    result = kernel.validate(context)
    assert result.approved is False
    assert result.reason == DecisionReason.CIRCUIT_OPEN

def test_execute_success(kernel, mock_loader):
    mock_op = MagicMock(return_value="success")
    kernel.register_operation("test_op", mock_op)
    
    # Mock validation to pass
    kernel.validate = MagicMock(return_value=ValidationResult(approved=True, context=MagicMock(), reason=DecisionReason.APPROVED))
    
    result = kernel.execute("test_op", {"x": 1}, "agent1")
    assert result == "success"
    mock_op.assert_called_once_with(x=1)
    assert kernel._stats["executed"] == 1

def test_execute_unregistered(kernel):
    with pytest.raises(ValueError, match="Unknown operation"):
        kernel.execute("unknown", {}, "agent1")

def test_execute_validation_fail(kernel):
    kernel.validate = MagicMock(return_value=ValidationResult(approved=False, context=MagicMock(), reason=DecisionReason.RISK_TOO_HIGH, message="Too risky"))
    
    with pytest.raises(PermissionError, match="denied: Too risky"):
        kernel.execute("any_op", {}, "agent1")

def test_invariants(kernel):
    mock_op = MagicMock(return_value="ok")
    kernel.register_operation("op", mock_op)
    
    invariant = MagicMock(return_value=True)
    kernel.add_invariant(invariant, "test_invariant")
    
    kernel.execute("op", {"data": "val"}, "agent1")
    # Called twice: before and after
    assert invariant.call_count == 2
    
    # Now make invariant fail
    invariant.return_value = False
    with pytest.raises(ValueError, match="Invariant violation before execution"):
        kernel.execute("op", {"data": "bad"}, "agent1")

def test_execute_with_contract(kernel, mock_loader):
    mock_op = MagicMock(return_value="ok")
    kernel.register_operation("op", mock_op)
    
    mock_contract = MagicMock()
    mock_contract.check_pre.return_value = MagicMock(approved=True)
    mock_contract.check_post.return_value = MagicMock(passed=True)
    
    kernel.register_contract("op", mock_contract)
    
    kernel.execute("op", {"arg": 1}, "agent1")
    assert mock_contract.check_pre.called
    assert mock_contract.check_post.called

def test_audit_fail_closed(kernel):
    kernel.config.enable_audit = True
    kernel.config.audit_fail_closed = True
    
    with patch("kernel.execution_kernel.logger.info") as mock_log:
        mock_log.side_effect = Exception("Audit system down")
        context = ExecutionContext(agent_id="a1", operation="op1", parameters={})
        
        # We need to bypass other checks to reach audit
        kernel._check_domain_enabled = MagicMock(return_value=ValidationResult(approved=True, context=context, reason=DecisionReason.PENDING))
        kernel._check_rbac = MagicMock(return_value=ValidationResult(approved=True, context=context, reason=DecisionReason.PENDING))
        kernel._check_risk_threshold = MagicMock(return_value=ValidationResult(approved=True, context=context, reason=DecisionReason.PENDING))
        kernel._check_pre_conditions = MagicMock(return_value=ValidationResult(approved=True, context=context, reason=DecisionReason.PENDING))
        kernel._check_circuit_breaker = MagicMock(return_value=ValidationResult(approved=True, context=context, reason=DecisionReason.PENDING))
        kernel._check_resource_limits = MagicMock(return_value=ValidationResult(approved=True, context=context, reason=DecisionReason.PENDING))

        result = kernel.validate(context)
        assert result.approved is False
        assert result.reason == DecisionReason.AUDIT_FAILED
