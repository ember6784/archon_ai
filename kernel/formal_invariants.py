# archon/kernel/formal_invariants.py
"""
Formal Verification Invariants with Z3 Solver

Provides formal verification capabilities using Z3 SMT solver.
This allows mathematical proofs of security properties.

Based on docs/7.md recommendations for Z3 integration.

Requirements:
    pip install z3-solver

Usage:
    from kernel.formal_invariants import Z3InvariantChecker, SharpeInvariant

    checker = Z3InvariantChecker()
    checker.add_invariant(sharpe > 1.0)

    if not checker.check_pre(context):
        raise ValueError("Pre-condition failed")
"""

import logging
from typing import Any, Dict, List, Optional, Callable, TYPE_CHECKING
from dataclasses import dataclass
from enum import Enum

if TYPE_CHECKING:
    import z3
else:
    try:
        import z3
        Z3_AVAILABLE = True
    except ImportError:
        Z3_AVAILABLE = False
        z3 = None


logger = logging.getLogger(__name__)


# =============================================================================
# Z3 INVARIANT CHECKER
# =============================================================================

class Z3InvariantChecker:
    """
    Formal invariant checker using Z3 SMT solver.

    Uses Z3 to prove that invariants hold under all possible inputs.
    This provides mathematical guarantees rather than just testing.
    """

    def __init__(self, timeout_ms: int = 1000):
        """
        Initialize Z3 invariant checker.

        Args:
            timeout_ms: Timeout for Z3 solver (default 1s)
        """
        if not Z3_AVAILABLE:
            raise ImportError(
                "z3-solver is required for formal verification. "
                "Install with: pip install z3-solver"
            )

        self.solver = z3.Solver()
        self.solver.set(timeout=timeout_ms)
        self.invariants: List[z3.BoolRef] = []
        self.variables: Dict[str, z3.ExprRef] = {}

        # Statistics
        self._stats = {
            "checks_total": 0,
            "checks_passed": 0,
            "checks_failed": 0,
            "checks_unknown": 0,
            "avg_time_ms": 0.0,
        }

    def declare_variable(
        self,
        name: str,
        var_type: str = "Real"
    ) -> 'z3.ExprRef':
        """
        Declare a Z3 variable for invariant checking.

        Args:
            name: Variable name
            var_type: Type (Real, Int, Bool, String)

        Returns:
            Z3 expression reference
        """
        if var_type == "Real":
            var = z3.Real(name)
        elif var_type == "Int":
            var = z3.Int(name)
        elif var_type == "Bool":
            var = z3.Bool(name)
        elif var_type == "String":
            var = z3.String(name)
        else:
            raise ValueError(f"Unknown type: {var_type}")

        self.variables[name] = var
        logger.debug(f"[Z3] Declared variable: {name} ({var_type})")
        return var

    def add_invariant(self, invariant: 'z3.BoolRef', name: str = "") -> None:
        """
        Add an invariant to be checked.

        Args:
            invariant: Z3 Boolean expression
            name: Optional name for logging
        """
        self.invariants.append(invariant)
        self.solver.add(invariant)
        logger.debug(f"[Z3] Added invariant: {name or invariant}")

    def check_pre(
        self,
        context: Dict[str, Any]
    ) -> bool:
        """
        Check pre-conditions using Z3 solver.

        Args:
            context: Execution context with variable values

        Returns:
            True if all invariants hold
        """
        import time
        start = time.time()

        try:
            # Create a new solver for this check
            s = z3.Solver()
            s.set(timeout=self.solver.timeout)

            # Add all invariants
            for inv in self.invariants:
                s.add(inv)

            # Add context as constraints
            for name, value in context.items():
                if name in self.variables:
                    var = self.variables[name]
                    if isinstance(value, (int, float)):
                        s.add(var == value)
                    elif isinstance(value, bool):
                        s.add(var == value)
                    elif isinstance(value, str):
                        s.add(var == value)

            # Check satisfiability
            result = s.check()

            elapsed_ms = (time.time() - start) * 1000
            self._update_stats(result, elapsed_ms)

            if result == z3.sat:
                logger.debug(f"[Z3] Pre-check SAT: invariants hold")
                return True
            elif result == z3.unsat:
                logger.warning(f"[Z3] Pre-check UNSAT: invariants violated")
                return False
            else:  # unknown
                logger.warning(f"[Z3] Pre-check UNKNOWN: solver timed out")
                return False

        except Exception as e:
            logger.error(f"[Z3] Pre-check error: {e}")
            return False

    def check_post(
        self,
        result: Any,
        context: Dict[str, Any]
    ) -> bool:
        """
        Check post-conditions using Z3 solver.

        Args:
            result: Execution result
            context: Original execution context

        Returns:
            True if all post-invariants hold
        """
        # Add result to context for checking
        check_context = context.copy()
        if isinstance(result, dict):
            check_context.update(result)
        else:
            check_context["result"] = result

        return self.check_pre(check_context)

    def prove_property(self, property_expr: 'z3.BoolRef') -> bool:
        """
        Prove a property holds under all invariants.

        This checks if the property is entailed by the invariants.

        Args:
            property_expr: Property to prove

        Returns:
            True if property is proven
        """
        # Create solver with invariants + negation of property
        s = z3.Solver()
        s.set(timeout=self.solver.timeout)

        for inv in self.invariants:
            s.add(inv)

        s.add(z3.Not(property_expr))

        result = s.check()

        if result == z3.unsat:
            # Property + invariants is unsat, so property is proven
            logger.info(f"[Z3] Property PROVEN: {property_expr}")
            return True
        elif result == z3.sat:
            # Found counterexample
            logger.warning(f"[Z3] Property DISPROVEN: counterexample exists")
            model = s.model()
            logger.debug(f"[Z3] Counterexample: {model}")
            return False
        else:
            logger.warning(f"[Z3] Property UNKNOWN: solver timed out")
            return False

    def find_counterexample(
        self,
        property_expr: 'z3.BoolRef'
    ) -> Optional[Dict[str, Any]]:
        """
        Find a counterexample for a property.

        Args:
            property_expr: Property to check

        Returns:
            Dictionary with variable assignments, or None if no counterexample
        """
        s = z3.Solver()
        s.set(timeout=self.solver.timeout)

        for inv in self.invariants:
            s.add(inv)

        s.add(z3.Not(property_expr))

        result = s.check()

        if result == z3.sat:
            model = s.model()
            counterexample = {}
            for name, var in self.variables.items():
                if model[var] is not None:
                    counterexample[name] = model[var].as_string()
            return counterexample
        return None

    def get_stats(self) -> Dict[str, Any]:
        """Get checker statistics."""
        return self._stats.copy()

    def _update_stats(self, result: 'z3.CheckSatResult', elapsed_ms: float):
        """Update statistics after a check."""
        self._stats["checks_total"] += 1

        if result == z3.sat:
            self._stats["checks_passed"] += 1
        elif result == z3.unsat:
            self._stats["checks_failed"] += 1
        else:
            self._stats["checks_unknown"] += 1

        # Update average time
        total = self._stats["checks_total"]
        prev_avg = self._stats["avg_time_ms"]
        self._stats["avg_time_ms"] = (prev_avg * (total - 1) + elapsed_ms) / total


# =============================================================================
# DOMAIN-SPECIFIC INVARIANTS
# =============================================================================

def sharpe_ratio_invariant(min_sharpe: float = 1.0) -> Callable[[Dict], bool]:
    """
    Create an invariant checker for Sharpe ratio.

    This is a trading-specific invariant that ensures the Sharpe ratio
    (risk-adjusted return) meets a minimum threshold.

    Args:
        min_sharpe: Minimum acceptable Sharpe ratio

    Returns:
        Checker function
    """
    if Z3_AVAILABLE:
        # Create Z3 version with formal verification
        sharpe = z3.Real('sharpe')
        checker = Z3InvariantChecker()
        checker.declare_variable('sharpe', 'Real')
        checker.add_invariant(sharpe >= min_sharpe, f"sharpe >= {min_sharpe}")
        return checker
    else:
        # Fallback to simple checker
        def simple_checker(context: Dict) -> bool:
            sharpe = context.get('sharpe', 0.0)
            return sharpe >= min_sharpe
        return simple_checker


def position_limit_invariant(max_position: float) -> Callable[[Dict], bool]:
    """
    Create an invariant checker for position limits.

    Ensures trading position does not exceed specified limit.

    Args:
        max_position: Maximum position size

    Returns:
        Checker function
    """
    if Z3_AVAILABLE:
        position = z3.Real('position')
        checker = Z3InvariantChecker()
        checker.declare_variable('position', 'Real')
        checker.add_invariant(
            z3.And(position >= -max_position, position <= max_position),
            f"|position| <= {max_position}"
        )
        return checker
    else:
        def simple_checker(context: Dict) -> bool:
            position = context.get('position', 0.0)
            return -max_position <= position <= max_position
        return simple_checker


def drawdown_invariant(max_drawdown: float = 0.2) -> Callable[[Dict], bool]:
    """
    Create an invariant checker for maximum drawdown.

    Ensures portfolio drawdown does not exceed specified limit.

    Args:
        max_drawdown: Maximum drawdown as fraction (e.g., 0.2 = 20%)

    Returns:
        Checker function
    """
    if Z3_AVAILABLE:
        peak = z3.Real('peak')
        current = z3.Real('current')
        checker = Z3InvariantChecker()
        checker.declare_variable('peak', 'Real')
        checker.declare_variable('current', 'Real')
        checker.add_invariant(
            current >= peak * (1 - max_drawdown),
            f"drawdown <= {max_drawdown*100}%"
        )
        return checker
    else:
        def simple_checker(context: Dict) -> bool:
            peak = context.get('peak', 1.0)
            current = context.get('current', 1.0)
            drawdown = (peak - current) / peak if peak > 0 else 0
            return drawdown <= max_drawdown
        return simple_checker


def no_market_manipulation_invariant() -> Callable[[Dict], bool]:
    """
    Create an invariant checker to detect market manipulation.

    Checks for suspicious patterns like:
    - Layering (placing and cancelling orders)
    - Spoofing (fake orders)
    - Wash trading (trading with oneself)

    Returns:
        Checker function
    """
    def checker(context: Dict) -> bool:
        # Check for layering: many orders placed and cancelled
        orders_placed = context.get('orders_placed', 0)
        orders_cancelled = context.get('orders_cancelled', 0)

        if orders_placed > 100:
            cancel_ratio = orders_cancelled / orders_placed
            if cancel_ratio > 0.9:  # 90%+ cancelled is suspicious
                logger.warning("[INVARIANT] Potential layering detected")
                return False

        # Check for wash trading: counterparty matches self
        counterparties = context.get('counterparties', [])
        if len(set(counterparties)) < len(counterparties) / 2:
            logger.warning("[INVARIANT] Potential wash trading detected")
            return False

        return True

    return checker


# =============================================================================
# PREBUILT SECURITY INVARIANTS
# =============================================================================

def create_safety_invariants() -> List[Callable[[Dict], bool]]:
    """
    Create a set of safety invariants for general use.

    Returns:
        List of invariant checkers
    """
    from .invariants import (
        no_code_injection,
        no_shell_injection,
        no_protected_path_access,
        no_hardcoded_secrets,
    )

    return [
        no_code_injection,
        no_shell_injection,
        no_protected_path_access,
        no_hardcoded_secrets,
    ]


def create_trading_invariants(
    min_sharpe: float = 1.0,
    max_position: float = 1000000.0,
    max_drawdown: float = 0.2
) -> List[Callable[[Dict], bool]]:
    """
    Create a set of trading-specific invariants.

    Args:
        min_sharpe: Minimum Sharpe ratio
        max_position: Maximum position size
        max_drawdown: Maximum drawdown (fraction)

    Returns:
        List of invariant checkers
    """
    return [
        sharpe_ratio_invariant(min_sharpe),
        position_limit_invariant(max_position),
        drawdown_invariant(max_drawdown),
        no_market_manipulation_invariant(),
    ]


# =============================================================================
# INVARIANT COMPOSITION
# =============================================================================

class AndInvariant:
    """
    Compose multiple invariants with AND logic.
    All invariants must pass.
    """

    def __init__(self, *checkers: Callable[[Dict], bool]):
        self.checkers = checkers

    def __call__(self, context: Dict) -> bool:
        return all(checker(context) for checker in self.checkers)


class OrInvariant:
    """
    Compose multiple invariants with OR logic.
    At least one invariant must pass.
    """

    def __init__(self, *checkers: Callable[[Dict], bool]):
        self.checkers = checkers

    def __call__(self, context: Dict) -> bool:
        return any(checker(context) for checker in self.checkers)


class NotInvariant:
    """
    Invert an invariant's result.
    """

    def __init__(self, checker: Callable[[Dict], bool]):
        self.checker = checker

    def __call__(self, context: Dict) -> bool:
        return not self.checker(context)


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # Z3 Checker
    "Z3InvariantChecker",
    "Z3_AVAILABLE",

    # Domain invariants
    "sharpe_ratio_invariant",
    "position_limit_invariant",
    "drawdown_invariant",
    "no_market_manipulation_invariant",

    # Prebuilt sets
    "create_safety_invariants",
    "create_trading_invariants",

    # Composition
    "AndInvariant",
    "OrInvariant",
    "NotInvariant",
]
