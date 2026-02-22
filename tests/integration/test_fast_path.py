"""
Tests for ExecutionKernel Fast Path and security_level=light mode.

Covers:
- Fast path eligibility decisions
- Fast path execution (invariants still enforced)
- Fast path blocked in RED/BLACK circuit states
- security_level="light" relaxes risk threshold
- Fast path stats tracking
- Fast path disabled via config
"""

from unittest.mock import patch

import pytest

from kernel.execution_kernel import (
    CircuitState,
    ExecutionContext,
    ExecutionKernel,
    FastPathConfig,
    KernelConfig,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_kernel(
    fast_path_enabled: bool = True,
    fast_path_max_risk: float = 0.2,
    fast_path_ops: set | None = None,
    circuit_state: CircuitState = CircuitState.GREEN,
    security_level: str = "full",
    skip_manifest: bool = True,
) -> ExecutionKernel:
    fp_ops = fast_path_ops or {"read_file", "search_code", "get_data", "log", "list_directory"}
    config = KernelConfig(
        environment="test",
        skip_manifest_validation=skip_manifest,
        security_level=security_level,
        fast_path=FastPathConfig(
            enabled=fast_path_enabled,
            max_risk_score=fast_path_max_risk,
            allowed_operations=fp_ops,
        ),
    )
    kernel = ExecutionKernel(config=config, circuit_breaker_state=circuit_state)
    return kernel


def _make_context(operation: str, agent_id: str = "test_agent") -> ExecutionContext:
    return ExecutionContext(
        agent_id=agent_id,
        operation=operation,
        parameters={},
    )


# ---------------------------------------------------------------------------
# Fast path eligibility
# ---------------------------------------------------------------------------

class TestFastPathEligibility:
    def test_eligible_when_all_conditions_met(self) -> None:
        kernel = _make_kernel()
        ctx = _make_context("read_file")

        with patch.object(kernel.loader, "get_risk_level", return_value=0.1):
            assert kernel._is_fast_path_eligible(ctx) is True

    def test_not_eligible_when_fast_path_disabled(self) -> None:
        kernel = _make_kernel(fast_path_enabled=False)
        ctx = _make_context("read_file")

        with patch.object(kernel.loader, "get_risk_level", return_value=0.1):
            assert kernel._is_fast_path_eligible(ctx) is False

    def test_not_eligible_when_operation_not_allowed(self) -> None:
        kernel = _make_kernel(fast_path_ops={"read_file"})
        ctx = _make_context("write_file")

        with patch.object(kernel.loader, "get_risk_level", return_value=0.1):
            assert kernel._is_fast_path_eligible(ctx) is False

    def test_not_eligible_when_risk_too_high(self) -> None:
        kernel = _make_kernel(fast_path_max_risk=0.2)
        ctx = _make_context("read_file")

        with patch.object(kernel.loader, "get_risk_level", return_value=0.5):
            assert kernel._is_fast_path_eligible(ctx) is False

    def test_not_eligible_in_red_state(self) -> None:
        kernel = _make_kernel(circuit_state=CircuitState.RED)
        ctx = _make_context("read_file")

        with patch.object(kernel.loader, "get_risk_level", return_value=0.1):
            assert kernel._is_fast_path_eligible(ctx) is False

    def test_not_eligible_in_black_state(self) -> None:
        kernel = _make_kernel(circuit_state=CircuitState.BLACK)
        ctx = _make_context("read_file")

        with patch.object(kernel.loader, "get_risk_level", return_value=0.1):
            assert kernel._is_fast_path_eligible(ctx) is False

    def test_eligible_in_amber_state(self) -> None:
        kernel = _make_kernel(circuit_state=CircuitState.AMBER)
        ctx = _make_context("read_file")

        with patch.object(kernel.loader, "get_risk_level", return_value=0.1):
            assert kernel._is_fast_path_eligible(ctx) is True


# ---------------------------------------------------------------------------
# Fast path validation result
# ---------------------------------------------------------------------------

class TestFastPathValidation:
    def test_validate_returns_approved_via_fast_path(self) -> None:
        kernel = _make_kernel()
        ctx = _make_context("read_file")

        with patch.object(kernel.loader, "get_risk_level", return_value=0.1):
            result = kernel.validate(ctx)

        assert result.approved is True
        assert result.check_name == "fast_path"

    def test_fast_path_increments_hit_counter(self) -> None:
        kernel = _make_kernel()
        ctx = _make_context("read_file")

        with patch.object(kernel.loader, "get_risk_level", return_value=0.1):
            kernel.validate(ctx)
            kernel.validate(ctx)

        stats = kernel.get_stats()
        assert stats["fast_path_hits"] == 2

    def test_non_fast_path_op_does_not_increment_counter(self) -> None:
        kernel = _make_kernel()
        ctx = _make_context("write_file")

        with (
            patch.object(kernel.loader, "get_risk_level", return_value=0.3),
            patch.object(kernel.loader, "is_domain_enabled", return_value=True),
            patch.object(kernel.loader, "get_operation_contract", return_value=None),
        ):
            kernel.validate(ctx)

        stats = kernel.get_stats()
        assert stats["fast_path_hits"] == 0


# ---------------------------------------------------------------------------
# Fast path + invariants
# ---------------------------------------------------------------------------

class TestFastPathInvariantsEnforced:
    def test_invariants_still_block_fast_path_operations(self) -> None:
        kernel = _make_kernel(skip_manifest=False)
        kernel.register_operation("read_file", lambda path: "content")

        def always_false_invariant(payload):
            return False

        kernel.add_invariant(always_false_invariant, name="always_fail")

        with patch.object(kernel.loader, "get_risk_level", return_value=0.1):
            with pytest.raises(ValueError, match="Invariant violation"):
                kernel.execute("read_file", {"path": "/safe/file.txt"}, "agent_1")


# ---------------------------------------------------------------------------
# Fast path execute
# ---------------------------------------------------------------------------

class TestFastPathExecution:
    def test_execute_fast_path_operation_succeeds(self) -> None:
        kernel = _make_kernel(skip_manifest=False)
        kernel.register_operation("read_file", lambda path: f"content of {path}")

        with patch.object(kernel.loader, "get_risk_level", return_value=0.1):
            result = kernel.execute("read_file", {"path": "/tmp/test.txt"}, "agent_1")

        assert result == "content of /tmp/test.txt"

    def test_unregistered_operation_blocked_even_on_fast_path(self) -> None:
        kernel = _make_kernel(skip_manifest=False)

        with patch.object(kernel.loader, "get_risk_level", return_value=0.1):
            with pytest.raises(ValueError, match="Not registered in whitelist"):
                kernel.execute("read_file", {"path": "/tmp/test.txt"}, "agent_1")


# ---------------------------------------------------------------------------
# security_level="light"
# ---------------------------------------------------------------------------

class TestSecurityLightMode:
    def test_light_mode_relaxes_risk_threshold(self) -> None:
        full_config = KernelConfig(
            environment="test",
            skip_manifest_validation=False,
            security_level="full",
            default_risk_threshold=0.5,
        )
        light_config = KernelConfig(
            environment="test",
            skip_manifest_validation=False,
            security_level="light",
            default_risk_threshold=0.5,
        )

        full_kernel = ExecutionKernel(config=full_config)
        light_kernel = ExecutionKernel(config=light_config)

        ctx = _make_context("moderate_op")

        with (
            patch.object(full_kernel.loader, "get_risk_level", return_value=0.65),
            patch.object(full_kernel.loader, "is_domain_enabled", return_value=True),
            patch.object(full_kernel.loader, "get_operation_contract", return_value=None),
        ):
            full_result = full_kernel.validate(ctx)

        with (
            patch.object(light_kernel.loader, "get_risk_level", return_value=0.65),
            patch.object(light_kernel.loader, "is_domain_enabled", return_value=True),
            patch.object(light_kernel.loader, "get_operation_contract", return_value=None),
        ):
            light_result = light_kernel.validate(ctx)

        assert full_result.approved is False
        assert light_result.approved is True

    def test_get_stats_includes_security_level(self) -> None:
        kernel = _make_kernel(security_level="light")
        stats = kernel.get_stats()
        assert stats["security_level"] == "light"

    def test_full_mode_stats(self) -> None:
        kernel = _make_kernel(security_level="full")
        stats = kernel.get_stats()
        assert stats["security_level"] == "full"


# ---------------------------------------------------------------------------
# Stats and fast path rate
# ---------------------------------------------------------------------------

class TestKernelStats:
    def test_fast_path_rate_calculation(self) -> None:
        kernel = _make_kernel()

        with patch.object(kernel.loader, "get_risk_level", return_value=0.1):
            for _ in range(3):
                kernel.validate(_make_context("read_file"))

        with (
            patch.object(kernel.loader, "get_risk_level", return_value=0.9),
            patch.object(kernel.loader, "is_domain_enabled", return_value=True),
            patch.object(kernel.loader, "get_operation_contract", return_value=None),
        ):
            kernel.validate(_make_context("exec_code"))

        stats = kernel.get_stats()
        assert stats["fast_path_hits"] == 3
        assert stats["total_requests"] == 4
        assert stats["fast_path_rate"] == pytest.approx(0.75)

    def test_initial_stats_are_zero(self) -> None:
        kernel = _make_kernel()
        stats = kernel.get_stats()
        assert stats["total_requests"] == 0
        assert stats["fast_path_hits"] == 0
        assert stats["fast_path_rate"] == 0.0
