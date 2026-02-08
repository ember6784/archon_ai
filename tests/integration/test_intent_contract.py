# tests/integration/test_intent_contract.py
"""
Integration Tests for Intent Contract System

Tests the complete contract validation flow:
- Pre-condition validation
- Post-condition validation
- Contract composition (AND, OR, NOT)
- Contract builder API
- Integration with ExecutionKernel
"""

import pytest
from unittest.mock import MagicMock

from kernel.intent_contract import (
    BaseContract,
    IntentContract,
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
from kernel.execution_kernel import ExecutionContext, KernelConfig
from kernel.validation import ValidationResult, DecisionReason, Severity


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def sample_context():
    """Create sample execution context."""
    return ExecutionContext(
        agent_id="test_agent",
        operation="read_file",
        parameters={
            "path": "/tmp/test.txt",
            "permissions": ["file.read"]
        }
    )


@pytest.fixture
def sample_manifest():
    """Create sample manifest data."""
    return {
        "domains": {
            "default": {"enabled": True},
            "files": {"enabled": True},
            "disabled_domain": {"enabled": False}
        },
        "operations": {
            "read_file": {
                "enabled": True,
                "risk_level": 0.2,
                "allowed_domains": ["default", "files"]
            },
            "write_file": {
                "enabled": True,
                "risk_level": 0.5,
                "allowed_domains": ["default", "files"],
                "post_conditions": {
                    "success": {
                        "operator": "==",
                        "expected": True,
                        "path": "success"
                    }
                }
            },
            "disabled_op": {
                "enabled": False,
                "risk_level": 0.8
            }
        }
    }


# =============================================================================
# PRIMITIVE CONTRACT TESTS
# =============================================================================

class TestAlwaysAllow:
    """Tests for AlwaysAllow contract."""

    def test_check_pre_always_allows(self, sample_context):
        """Test that AlwaysAllow always approves."""
        contract = AlwaysAllow()
        result = contract.check_pre(sample_context)

        assert result.approved
        assert result.reason == DecisionReason.APPROVED

    def test_check_post_always_passes(self, sample_context):
        """Test that post-condition always passes."""
        contract = AlwaysAllow()
        result = contract.check_post(sample_context, {"success": True})

        assert result.passed


class TestAlwaysDeny:
    """Tests for AlwaysDeny contract."""

    def test_check_pre_denies(self, sample_context):
        """Test that AlwaysDeny always rejects."""
        contract = AlwaysDeny("Not allowed")
        result = contract.check_pre(sample_context)

        assert not result.approved
        assert result.reason == DecisionReason.PRE_CONDITION_FAILED
        assert "Not allowed" in result.message


class TestRequirePermission:
    """Tests for RequirePermission contract."""

    def test_grants_when_permission_present(self, sample_context):
        """Test that permission is granted when present."""
        contract = RequirePermission("file.read")
        result = contract.check_pre(sample_context)

        assert result.approved
        assert "granted" in result.message.lower()

    def test_denies_when_permission_missing(self, sample_context):
        """Test that permission is denied when missing."""
        contract = RequirePermission("file.write")
        result = contract.check_pre(sample_context)

        assert not result.approved
        assert result.reason == DecisionReason.PERMISSION_DENIED

    def test_denies_with_resource_check(self, sample_context):
        """Test permission denial with resource specified."""
        contract = RequirePermission("file.write", resource="/etc/passwd")
        result = contract.check_pre(sample_context)

        assert not result.approved
        assert result.details.get("resource") == "/etc/passwd"


class TestRequireDomainEnabled:
    """Tests for RequireDomainEnabled contract."""

    def test_allows_when_domain_enabled(self, sample_context, sample_manifest):
        """Test that enabled domain is allowed."""
        contract = RequireDomainEnabled("files")
        result = contract.check_pre(sample_context, sample_manifest)

        assert result.approved

    def test_denies_when_domain_disabled(self, sample_context, sample_manifest):
        """Test that disabled domain is denied."""
        contract = RequireDomainEnabled("disabled_domain")
        result = contract.check_pre(sample_context, sample_manifest)

        assert not result.approved
        assert result.reason == DecisionReason.DOMAIN_DISABLED

    def test_denies_when_domain_not_found(self, sample_context, sample_manifest):
        """Test that missing domain is denied."""
        contract = RequireDomainEnabled("nonexistent")
        result = contract.check_pre(sample_context, sample_manifest)

        assert not result.approved
        assert result.reason == DecisionReason.DOMAIN_NOT_FOUND


class TestMaxOperationSize:
    """Tests for MaxOperationSize contract."""

    def test_allows_within_limit(self, sample_context):
        """Test that operation within limit is allowed."""
        contract = MaxOperationSize(max_size_bytes=10000)
        result = contract.check_pre(sample_context)

        assert result.approved

    def test_denies_when_exceeds_limit(self, sample_context):
        """Test that oversized operation is denied."""
        # Create large payload
        large_context = ExecutionContext(
            agent_id="test",
            operation="test",
            parameters={"data": "x" * 20000}  # 20KB
        )
        contract = MaxOperationSize(max_size_bytes=10000)
        result = contract.check_pre(large_context)

        assert not result.approved
        assert result.reason == DecisionReason.RESOURCE_LIMIT
        assert "too large" in result.message.lower()


class TestProtectedPathCheck:
    """Tests for ProtectedPathCheck contract."""

    def test_allows_safe_path(self, sample_context):
        """Test that safe paths are allowed."""
        contract = ProtectedPathCheck()
        result = contract.check_pre(sample_context)

        assert result.approved

    def test_blocks_etc_path(self, sample_context):
        """Test that /etc paths are blocked."""
        sample_context.parameters["path"] = "/etc/passwd"
        contract = ProtectedPathCheck()
        result = contract.check_pre(sample_context)

        assert not result.approved
        assert result.severity == Severity.CRITICAL

    def test_blocks_ssh_path(self, sample_context):
        """Test that .ssh paths are blocked."""
        sample_context.parameters["path"] = "/home/user/.ssh/id_rsa"
        contract = ProtectedPathCheck()
        result = contract.check_pre(sample_context)

        assert not result.approved

    def test_blocks_env_file(self, sample_context):
        """Test that .env files are blocked."""
        sample_context.parameters["path"] = "/app/.env"
        contract = ProtectedPathCheck()
        result = contract.check_pre(sample_context)

        assert not result.approved


class TestCustomInvariant:
    """Tests for CustomInvariant contract."""

    def test_passes_when_checker_true(self, sample_context):
        """Test that invariant passes when checker returns True."""
        contract = CustomInvariant(
            "test_invariant",
            lambda params: params.get("safe", False) is True
        )
        sample_context.parameters["safe"] = True
        result = contract.check_pre(sample_context)

        assert result.approved

    def test_fails_when_checker_false(self, sample_context):
        """Test that invariant fails when checker returns False."""
        contract = CustomInvariant(
            "test_invariant",
            lambda params: params.get("safe", False) is True
        )
        result = contract.check_pre(sample_context)

        assert not result.approved
        assert result.reason == DecisionReason.INVARIANT_VIOLATED


class TestRequireManifestContract:
    """Tests for RequireManifestContract contract."""

    def test_allows_known_enabled_operation(self, sample_context, sample_manifest):
        """Test that known enabled operation is allowed."""
        contract = RequireManifestContract("read_file")
        result = contract.check_pre(sample_context, sample_manifest)

        assert result.approved
        assert "risk_level" in result.details

    def test_denies_unknown_operation(self, sample_context, sample_manifest):
        """Test that unknown operation is denied."""
        contract = RequireManifestContract("unknown_op")
        result = contract.check_pre(sample_context, sample_manifest)

        assert not result.approved
        assert "Unknown operation" in result.message

    def test_denies_disabled_operation(self, sample_context, sample_manifest):
        """Test that disabled operation is denied."""
        contract = RequireManifestContract("disabled_op")
        result = contract.check_pre(sample_context, sample_manifest)

        assert not result.approved
        assert result.reason == DecisionReason.DOMAIN_DISABLED

    def test_checks_post_conditions(self, sample_context, sample_manifest):
        """Test post-condition validation."""
        contract = RequireManifestContract("write_file")
        result = contract.check_post(
            sample_context,
            {"success": True},
            sample_manifest
        )

        assert result.passed

    def test_fails_failed_post_condition(self, sample_context, sample_manifest):
        """Test post-condition failure detection."""
        contract = RequireManifestContract("write_file")
        result = contract.check_post(
            sample_context,
            {"success": False},
            sample_manifest
        )

        assert not result.passed
        assert len(result.failed_conditions) > 0


# =============================================================================
# COMPOSITE CONTRACT TESTS
# =============================================================================

class TestAndContract:
    """Tests for AND contract composition."""

    def test_passes_when_all_pass(self, sample_context, sample_manifest):
        """Test that AND passes when all sub-contracts pass."""
        contract = (
            RequirePermission("file.read") &
            RequireDomainEnabled("files") &
            ProtectedPathCheck()
        )
        result = contract.check_pre(sample_context, sample_manifest)

        assert result.approved

    def test_fails_when_one_fails(self, sample_context, sample_manifest):
        """Test that AND fails when any sub-contract fails."""
        contract = (
            RequirePermission("file.read") &
            RequirePermission("file.write") &  # Missing permission
            ProtectedPathCheck()
        )
        result = contract.check_pre(sample_context, sample_manifest)

        assert not result.approved

    def test_reports_first_failure(self, sample_context, sample_manifest):
        """Test that AND reports the first failure."""
        contract = (
            RequirePermission("file.write") &
            RequireDomainEnabled("files")
        )
        result = contract.check_pre(sample_context, sample_manifest)

        assert not result.approved
        assert "require_permission" in result.details.get("failed_contract", "")


class TestOrContract:
    """Tests for OR contract composition."""

    def test_passes_when_one_passes(self, sample_context):
        """Test that OR passes when any sub-contract passes."""
        contract = (
            RequirePermission("file.write") |
            RequirePermission("file.read") |  # This one passes
            RequirePermission("file.delete")
        )
        result = contract.check_pre(sample_context)

        assert result.approved

    def test_fails_when_all_fail(self, sample_context):
        """Test that OR fails when all sub-contracts fail."""
        contract = (
            RequirePermission("file.write") |
            RequirePermission("file.delete")
        )
        result = contract.check_pre(sample_context)

        assert not result.approved
        assert "All OR contracts failed" in result.message


class TestNotContract:
    """Tests for NOT contract composition."""

    def test_inverts_allow_to_deny(self, sample_context):
        """Test that NOT inverts allow to deny."""
        contract = ~AlwaysAllow()
        result = contract.check_pre(sample_context)

        assert not result.approved

    def test_inverts_deny_to_allow(self, sample_context):
        """Test that NOT inverts deny to allow."""
        contract = ~AlwaysDeny("Blocked")
        result = contract.check_pre(sample_context)

        assert result.approved


# =============================================================================
# INTENT CONTRACT TESTS
# =============================================================================

class TestIntentContract:
    """Tests for IntentContract main class."""

    def test_empty_contract_allows(self, sample_context):
        """Test that contract with no pre-conditions allows."""
        contract = IntentContract("empty_contract")
        result = contract.check_pre(sample_context)

        assert result.approved
        assert "No pre-conditions" in result.message

    def test_add_pre_check(self, sample_context):
        """Test adding pre-condition checks."""
        contract = IntentContract("test_contract")
        contract.add_pre_check(RequirePermission("file.read"))
        contract.add_pre_check(ProtectedPathCheck())

        result = contract.check_pre(sample_context)

        assert result.approved

    def test_fail_fast_stops_on_first_failure(self, sample_context):
        """Test that fail-fast stops checking on first failure."""
        contract = IntentContract("fail_fast", fail_fast=True)
        contract.add_pre_check(RequirePermission("file.write"))  # Fails
        contract.add_pre_check(RequirePermission("file.delete"))  # Also fails

        result = contract.check_pre(sample_context)

        assert not result.approved
        # Should report only one failure
        assert "require_permission" in result.details.get("failed_check", "")

    def test_continue_checks_all(self, sample_context):
        """Test that non-fail-fast checks all conditions."""
        contract = IntentContract("continue", fail_fast=False)
        contract.add_pre_check(RequirePermission("file.write"))
        contract.add_pre_check(RequirePermission("file.delete"))

        result = contract.check_pre(sample_context)

        assert not result.approved


class TestContractBuilder:
    """Tests for ContractBuilder fluent API."""

    def test_builder_creates_contract(self):
        """Test that builder creates valid contract."""
        contract = (ContractBuilder("test")
                   .require_permission("file.read")
                   .protect_paths()
                   .max_size(1000000)
                   .build())

        assert contract.name == "test"
        assert len(contract.pre_contracts) == 3

    def test_builder_with_all_options(self, sample_context):
        """Test builder with all options."""
        contract = (ContractBuilder("full_test")
                   .with_description("Full test contract")
                   .require_permission("file.read")
                   .require_domain("files")
                   .protect_paths()
                   .max_size(1000000)
                   .with_fail_fast(True)
                   .build())

        assert contract.description == "Full test contract"
        assert contract.fail_fast
        assert len(contract.pre_contracts) == 4

    def test_builder_with_custom_invariant(self, sample_context):
        """Test builder with custom invariant."""
        contract = (ContractBuilder("custom")
                   .add_invariant(
                       "check_positive",
                       lambda p: p.get("value", 0) > 0,
                       "Value must be positive"
                   )
                   .build())

        sample_context.parameters["value"] = -1
        result = contract.check_pre(sample_context)

        assert not result.approved
        assert "positive" in result.message


# =============================================================================
# PREDEFINED CONTRACTS TESTS
# =============================================================================

class TestPredefinedContracts:
    """Tests for predefined operation contracts."""

    def test_read_file_contract(self, sample_context):
        """Test READ_FILE_CONTRACT."""
        result = READ_FILE_CONTRACT.check_pre(sample_context)

        assert result.approved

    def test_write_file_contract_needs_permission(self, sample_context):
        """Test WRITE_FILE_CONTRACT requires write permission."""
        # Missing file.write permission
        result = WRITE_FILE_CONTRACT.check_pre(sample_context)

        assert not result.approved

    def test_write_file_contract_with_permission(self, sample_context):
        """Test WRITE_FILE_CONTRACT with proper permission."""
        sample_context.parameters["permissions"] = ["file.write"]
        result = WRITE_FILE_CONTRACT.check_pre(sample_context)

        assert result.approved

    def test_exec_code_contract_size_limit(self, sample_context):
        """Test EXEC_CODE_CONTRACT enforces size limit."""
        large_context = ExecutionContext(
            agent_id="test",
            operation="exec_code",
            parameters={"code": "x" * 2_000_000}  # 2MB
        )

        result = EXEC_CODE_CONTRACT.check_pre(large_context)

        assert not result.approved
        assert result.reason == DecisionReason.RESOURCE_LIMIT


# =============================================================================
# INTEGRATION TESTS
# =============================================================================

class TestContractIntegration:
    """Integration tests for contract system."""

    def test_complex_composition(self, sample_context, sample_manifest):
        """Test complex contract composition."""
        # (read AND protected) OR (write AND protected)
        contract = (
            (RequirePermission("file.read") & ProtectedPathCheck()) |
            (RequirePermission("file.write") & ProtectedPathCheck())
        )

        result = contract.check_pre(sample_context)

        assert result.approved

    def test_manifest_contract_integration(self, sample_context, sample_manifest):
        """Test manifest contract with domain checks."""
        contract = (
            RequireManifestContract("read_file") &
            RequireDomainEnabled("files")
        )

        result = contract.check_pre(sample_context, sample_manifest)

        assert result.approved

    def test_post_condition_validation_chain(self, sample_context, sample_manifest):
        """Test post-condition validation across multiple contracts."""
        contract = (
            RequireManifestContract("write_file") &
            ProtectedPathCheck()
        )

        # Simulate successful execution
        exec_result = {"success": True, "bytes_written": 1024}
        post_result = contract.check_post(sample_context, exec_result, sample_manifest)

        assert post_result.passed

    def test_full_workflow(self, sample_context, sample_manifest):
        """Test full workflow: pre-check -> execute -> post-check."""
        contract = IntentContract("full_workflow", fail_fast=True)
        contract.add_pre_check(RequireManifestContract("read_file"))
        contract.add_pre_check(RequireDomainEnabled("files"))
        contract.add_pre_check(ProtectedPathCheck())

        # Pre-check
        pre_result = contract.check_pre(sample_context, sample_manifest)
        assert pre_result.approved

        # Simulate execution
        exec_result = {"content": "file content", "size": 100}

        # Post-check
        post_result = contract.check_post(sample_context, exec_result, sample_manifest)
        assert post_result.passed


# =============================================================================
# RUN TESTS
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
