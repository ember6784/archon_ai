# tests/integration/test_formal_invariants.py
"""
Tests for Formal Verification Invariants with Z3 Solver.

Tests work both with and without Z3 installed.
Without Z3, tests use simple fallback checkers.
"""

import pytest
from typing import Dict, Any

from kernel.formal_invariants import (
    Z3InvariantChecker,
    Z3_AVAILABLE,
    sharpe_ratio_invariant,
    position_limit_invariant,
    drawdown_invariant,
    no_market_manipulation_invariant,
    create_safety_invariants,
    create_trading_invariants,
    AndInvariant,
    OrInvariant,
    NotInvariant,
)

from kernel.invariants import (
    no_code_injection,
    no_shell_injection,
    no_protected_path_access,
)


# =============================================================================
# Z3 AVAILABILITY CHECKS
# =============================================================================

@pytest.mark.skipif(not Z3_AVAILABLE, reason="Z3 not installed")
class TestZ3InvariantChecker:
    """Tests for Z3-based invariant checker."""

    def test_declare_real_variable(self):
        """Test declaring real variables."""
        checker = Z3InvariantChecker()
        x = checker.declare_variable("x", "Real")
        y = checker.declare_variable("y", "Real")

        assert x is not None
        assert y is not None
        assert "x" in checker.variables
        assert "y" in checker.variables

    def test_add_and_check_invariant(self):
        """Test adding and checking invariants."""
        checker = Z3InvariantChecker()
        sharpe = checker.declare_variable("sharpe", "Real")

        # Sharpe must be >= 1.0
        import z3
        checker.add_invariant(sharpe >= 1.0, "sharpe >= 1.0")

        # Check with valid context
        context = {"sharpe": 1.5}
        assert checker.check_pre(context) is True

        # Check with invalid context
        context = {"sharpe": 0.5}
        assert checker.check_pre(context) is False

    def test_compose_invariants(self):
        """Test composing multiple invariants."""
        checker = Z3InvariantChecker()
        x = checker.declare_variable("x", "Real")
        y = checker.declare_variable("y", "Real")

        import z3
        checker.add_invariant(z3.And(x > 0, y > 0), "x > 0 and y > 0")
        checker.add_invariant(x + y < 100, "x + y < 100")

        # Valid context
        assert checker.check_pre({"x": 10, "y": 20}) is True

        # Invalid: x is negative
        assert checker.check_pre({"x": -5, "y": 20}) is False

        # Invalid: sum too large
        assert checker.check_pre({"x": 60, "y": 50}) is False

    def test_prove_property(self):
        """Test formal property proving."""
        checker = Z3InvariantChecker()
        x = checker.declare_variable("x", "Real")

        import z3
        # Invariant: x > 0
        checker.add_invariant(x > 0, "x > 0")

        # Prove that x > -1 (should hold given x > 0)
        assert checker.prove_property(x > -1) is True

        # Prove that x > 1 (should NOT hold - counterexample exists: x = 0.5)
        assert checker.prove_property(x > 1) is False

    def test_find_counterexample(self):
        """Test finding counterexamples."""
        checker = Z3InvariantChecker()
        x = checker.declare_variable("x", "Real")

        import z3
        checker.add_invariant(x > 0, "x > 0")

        # Property x > 10 doesn't always hold
        counterexample = checker.find_counterexample(x > 10)
        assert counterexample is not None
        assert "x" in counterexample
        # Counterexample should have x <= 10
        assert float(counterexample["x"]) <= 10

    def test_statistics_tracking(self):
        """Test that statistics are tracked correctly."""
        checker = Z3InvariantChecker()
        x = checker.declare_variable("x", "Real")

        import z3
        checker.add_invariant(x > 0, "x > 0")

        # Run several checks
        checker.check_pre({"x": 1})  # Pass
        checker.check_pre({"x": -1})  # Fail
        checker.check_pre({"x": 5})  # Pass

        stats = checker.get_stats()
        assert stats["checks_total"] == 3
        assert stats["checks_passed"] == 2
        assert stats["checks_failed"] == 1


# =============================================================================
# TRADING DOMAIN INVARIANTS
# =============================================================================

class TestTradingInvariants:
    """Tests for trading-specific invariants."""

    def test_sharpe_ratio_invariant_pass(self):
        """Test Sharpe ratio invariant with valid value."""
        invariant = sharpe_ratio_invariant(min_sharpe=1.0)

        # With Z3, this returns a checker; without Z3, simple function
        if Z3_AVAILABLE:
            result = invariant.check_pre({"sharpe": 1.5})
        else:
            result = invariant({"sharpe": 1.5})

        assert result is True

    def test_sharpe_ratio_invariant_fail(self):
        """Test Sharpe ratio invariant with invalid value."""
        invariant = sharpe_ratio_invariant(min_sharpe=1.0)

        if Z3_AVAILABLE:
            result = invariant.check_pre({"sharpe": 0.5})
        else:
            result = invariant({"sharpe": 0.5})

        assert result is False

    def test_position_limit_invariant_within_bounds(self):
        """Test position limit invariant within bounds."""
        invariant = position_limit_invariant(max_position=1000000)

        if Z3_AVAILABLE:
            result = invariant.check_pre({"position": 500000})
        else:
            result = invariant({"position": 500000})

        assert result is True

    def test_position_limit_invariant_exceeds_upper(self):
        """Test position limit invariant exceeds upper bound."""
        invariant = position_limit_invariant(max_position=1000000)

        if Z3_AVAILABLE:
            result = invariant.check_pre({"position": 1500000})
        else:
            result = invariant({"position": 1500000})

        assert result is False

    def test_position_limit_invariant_exceeds_lower(self):
        """Test position limit invariant exceeds lower bound (short)."""
        invariant = position_limit_invariant(max_position=1000000)

        if Z3_AVAILABLE:
            result = invariant.check_pre({"position": -1500000})
        else:
            result = invariant({"position": -1500000})

        assert result is False

    def test_drawdown_invariant_within_limit(self):
        """Test drawdown invariant within limit."""
        invariant = drawdown_invariant(max_drawdown=0.2)

        if Z3_AVAILABLE:
            result = invariant.check_pre({"peak": 100.0, "current": 90.0})
        else:
            result = invariant({"peak": 100.0, "current": 90.0})

        assert result is True  # 10% drawdown < 20% limit

    def test_drawdown_invariant_exceeds_limit(self):
        """Test drawdown invariant exceeds limit."""
        invariant = drawdown_invariant(max_drawdown=0.2)

        if Z3_AVAILABLE:
            result = invariant.check_pre({"peak": 100.0, "current": 70.0})
        else:
            result = invariant({"peak": 100.0, "current": 70.0})

        assert result is False  # 30% drawdown > 20% limit


# =============================================================================
# MARKET MANIPULATION DETECTION
# =============================================================================

class TestMarketManipulationInvariant:
    """Tests for market manipulation detection."""

    def test_normal_trading_passes(self):
        """Test normal trading passes manipulation check."""
        invariant = no_market_manipulation_invariant()

        context = {
            "orders_placed": 50,
            "orders_cancelled": 10,  # 20% cancel rate
            "counterparties": ["A", "B", "C", "D", "E"]  # 5 different
        }

        assert invariant(context) is True

    def test_layering_detected(self):
        """Test layering (high cancel rate) is detected."""
        invariant = no_market_manipulation_invariant()

        context = {
            "orders_placed": 150,
            "orders_cancelled": 140,  # 93% cancel rate - suspicious
        }

        assert invariant(context) is False

    def test_wash_trading_detected(self):
        """Test wash trading (trading with self) is detected."""
        invariant = no_market_manipulation_invariant()

        context = {
            "orders_placed": 10,
            "orders_cancelled": 0,
            "counterparties": ["SELF", "SELF", "SELF", "SELF", "SELF"]  # All same
        }

        assert invariant(context) is False


# =============================================================================
# PREBUILT INVARIANT SETS
# =============================================================================

class TestPrebuiltInvariantSets:
    """Tests for prebuilt invariant sets."""

    def test_create_safety_invariants(self):
        """Test safety invariant set creation."""
        invariants = create_safety_invariants()

        assert len(invariants) >= 4

        # Test each invariant
        assert invariants[0]({"code": "print('hello')"}) is True  # no_code_injection
        # Shell injection checks for specific patterns
        assert invariants[1]({"code": "os.system('rm -rf /')"}) is False  # no_shell_injection
        assert invariants[2]({"path": "/etc/passwd"}) is False  # no_protected_path_access

    def test_create_trading_invariants(self):
        """Test trading invariant set creation."""
        invariants = create_trading_invariants(
            min_sharpe=1.0,
            max_position=1000000,
            max_drawdown=0.2
        )

        assert len(invariants) == 4

        # Test all pass
        context = {
            "sharpe": 1.5,
            "position": 500000,
            "peak": 100.0,
            "current": 90.0,
            "orders_placed": 10,
            "orders_cancelled": 2,
            "counterparties": ["A", "B"]
        }

        results = [inv(context) for inv in invariants]
        assert all(results)

    def test_trading_invariants_detect_violations(self):
        """Test trading invariants detect violations."""
        invariants = create_trading_invariants()

        # Violating Sharpe
        context = {
            "sharpe": 0.5,  # Too low
            "position": 500000,
            "peak": 100.0,
            "current": 90.0,
        }

        results = [inv(context) for inv in invariants]
        assert not all(results)  # At least Sharpe should fail


# =============================================================================
# INVARIANT COMPOSITION
# =============================================================================

class TestInvariantComposition:
    """Tests for invariant composition operators."""

    def test_and_invariant_all_pass(self):
        """Test AND invariant when all pass."""
        inv = AndInvariant(
            lambda ctx: ctx.get("x", 0) > 0,
            lambda ctx: ctx.get("y", 0) > 0
        )

        assert inv({"x": 1, "y": 1}) is True

    def test_and_invariant_one_fails(self):
        """Test AND invariant when one fails."""
        inv = AndInvariant(
            lambda ctx: ctx.get("x", 0) > 0,
            lambda ctx: ctx.get("y", 0) > 0
        )

        assert inv({"x": 1, "y": -1}) is False

    def test_or_invariant_one_passes(self):
        """Test OR invariant when one passes."""
        inv = OrInvariant(
            lambda ctx: ctx.get("x", 0) > 10,
            lambda ctx: ctx.get("y", 0) > 10
        )

        assert inv({"x": 5, "y": 15}) is True

    def test_or_invariant_all_fail(self):
        """Test OR invariant when all fail."""
        inv = OrInvariant(
            lambda ctx: ctx.get("x", 0) > 10,
            lambda ctx: ctx.get("y", 0) > 10
        )

        assert inv({"x": 5, "y": 5}) is False

    def test_not_invariant_inverts(self):
        """Test NOT invariant inverts result."""
        always_true = lambda ctx: True
        always_false = lambda ctx: False

        inv_true = NotInvariant(always_true)
        inv_false = NotInvariant(always_false)

        assert inv_true({}) is False
        assert inv_false({}) is True


# =============================================================================
# INTEGRATION TESTS
# =============================================================================

class TestFormalInvariantIntegration:
    """Integration tests with ExecutionKernel."""

    def test_z3_invariant_with_kernel(self):
        """Test Z3 invariant integration with ExecutionKernel."""
        from kernel.execution_kernel import ExecutionKernel, KernelConfig

        kernel = ExecutionKernel(config=KernelConfig(skip_manifest_validation=True))

        # Add trading invariant
        trading_inv = position_limit_invariant(max_position=1000000)

        # If Z3 is available, use the checker directly
        if Z3_AVAILABLE and hasattr(trading_inv, 'check_pre'):
            # Add to kernel as wrapper
            def z3_wrapper(payload):
                return trading_inv.check_pre(payload)
            kernel.add_invariant(z3_wrapper, "position_limit_z3")
        else:
            kernel.add_invariant(trading_inv, "position_limit")

        # Register test operation
        def trade(position: int) -> str:
            return f"Traded: {position}"

        kernel.register_operation("trade", trade, "Trade operation")

        # Valid trade
        result = kernel.execute("trade", {"position": 500000}, "test_agent", {})
        assert "Traded:" in result

        # Invalid trade (exceeds limit)
        with pytest.raises(ValueError):
            kernel.execute("trade", {"position": 2000000}, "test_agent", {})


# =============================================================================
# RUN TESTS
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
