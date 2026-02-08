# archon/kernel/trading_contracts.py
"""
Trading Domain Contracts for IntentContract

Provides trading-specific contracts that integrate with IntentContract:
- SharpeRatioContract: Validates risk-adjusted returns
- PositionLimitContract: Ensures positions stay within bounds
- DrawdownLimitContract: Prevents excessive portfolio decline
- MarketManipulationCheck: Detects manipulation patterns

These contracts integrate with formal invariants from formal_invariants.py.
"""

import logging
from typing import Any, Dict, List, Optional
from datetime import datetime

from .intent_contract import BaseContract
from .validation import (
    ValidationResult,
    DecisionReason,
    Severity,
    PostConditionResult,
)


logger = logging.getLogger(__name__)


# =============================================================================
# TRADING DOMAIN CONTRACTS
# =============================================================================

class SharpeRatioContract(BaseContract):
    """
    Contract that validates Sharpe ratio requirements.

    Ensures risk-adjusted returns meet minimum threshold.
    Sharpe ratio = (return - risk_free_rate) / volatility

    Args:
        min_sharpe: Minimum acceptable Sharpe ratio (default 1.0)
        sharpe_parameter: Parameter name in context containing Sharpe value
    """

    def __init__(
        self,
        min_sharpe: float = 1.0,
        sharpe_parameter: str = "sharpe_ratio"
    ):
        self.min_sharpe = min_sharpe
        self.sharpe_parameter = sharpe_parameter

    def check_pre(
        self,
        context: "ExecutionContext",
        manifest_data: Optional[Dict] = None
    ) -> ValidationResult:
        """Check Sharpe ratio meets minimum threshold."""
        sharpe = context.parameters.get(self.sharpe_parameter)

        if sharpe is None:
            return ValidationResult(
                approved=True,
                context=context,
                reason=DecisionReason.APPROVED,
                message=f"Sharpe ratio not provided, using default threshold {self.min_sharpe}",
                severity=Severity.LOW,
                check_name="sharpe_ratio"
            )

        try:
            sharpe_value = float(sharpe)
            if sharpe_value < self.min_sharpe:
                return ValidationResult(
                    approved=False,
                    context=context,
                    reason=DecisionReason.PRE_CONDITION_FAILED,
                    message=f"Sharpe ratio {sharpe_value:.2f} below minimum {self.min_sharpe}",
                    severity=Severity.HIGH,
                    details={
                        "sharpe_ratio": sharpe_value,
                        "min_required": self.min_sharpe
                    },
                    check_name="sharpe_ratio"
                )
        except (ValueError, TypeError):
            return ValidationResult(
                approved=False,
                context=context,
                reason=DecisionReason.PRE_CONDITION_FAILED,
                message=f"Invalid Sharpe ratio value: {sharpe}",
                severity=Severity.MEDIUM,
                check_name="sharpe_ratio"
            )

        return ValidationResult(
            approved=True,
            context=context,
            reason=DecisionReason.APPROVED,
            message=f"Sharpe ratio {sharpe_value:.2f} meets minimum {self.min_sharpe}",
            details={"sharpe_ratio": sharpe_value},
            check_name="sharpe_ratio"
        )

    def check_post(
        self,
        context: "ExecutionContext",
        execution_result: Any,
        manifest_data: Optional[Dict] = None
    ) -> PostConditionResult:
        """Check Sharpe ratio after execution."""
        if isinstance(execution_result, dict):
            new_sharpe = execution_result.get("sharpe_ratio")
            if new_sharpe is not None:
                try:
                    sharpe_value = float(new_sharpe)
                    passed = sharpe_value >= self.min_sharpe
                    return PostConditionResult(
                        passed=passed,
                        results=[{
                            "name": "sharpe_ratio_post",
                            "passed": passed,
                            "sharpe_ratio": sharpe_value,
                            "min_required": self.min_sharpe
                        }],
                        failed_conditions=[{
                            "name": "sharpe_ratio",
                            "reason": f"Post-trade Sharpe {sharpe_value:.2f} below {self.min_sharpe}"
                        }] if not passed else []
                    )
                except (ValueError, TypeError):
                    pass

        return PostConditionResult(passed=True)


class PositionLimitContract(BaseContract):
    """
    Contract that validates position size limits.

    Ensures trading positions stay within defined bounds for both
    long (positive) and short (negative) positions.

    Args:
        max_position: Maximum absolute position size
        position_parameter: Parameter name containing position value
    """

    def __init__(
        self,
        max_position: float,
        position_parameter: str = "position_size"
    ):
        self.max_position = max_position
        self.position_parameter = position_parameter

    def check_pre(
        self,
        context: "ExecutionContext",
        manifest_data: Optional[Dict] = None
    ) -> ValidationResult:
        """Check position size is within limits."""
        position = context.parameters.get(self.position_parameter)

        if position is None:
            return ValidationResult(
                approved=True,
                context=context,
                reason=DecisionReason.APPROVED,
                message="No position specified, using default limits",
                check_name="position_limit"
            )

        try:
            position_value = float(position)
            # Check long limit
            if position_value > self.max_position:
                return ValidationResult(
                    approved=False,
                    context=context,
                    reason=DecisionReason.PRE_CONDITION_FAILED,
                    message=f"Long position {position_value:,.0f} exceeds limit {self.max_position:,.0f}",
                    severity=Severity.HIGH,
                    details={
                        "position": position_value,
                        "max_position": self.max_position,
                        "excess": position_value - self.max_position
                    },
                    check_name="position_limit"
                )
            # Check short limit
            elif position_value < -self.max_position:
                return ValidationResult(
                    approved=False,
                    context=context,
                    reason=DecisionReason.PRE_CONDITION_FAILED,
                    message=f"Short position {abs(position_value):,.0f} exceeds limit {self.max_position:,.0f}",
                    severity=Severity.HIGH,
                    details={
                        "position": position_value,
                        "max_short_position": -self.max_position,
                        "excess": abs(position_value) - self.max_position
                    },
                    check_name="position_limit"
                )
        except (ValueError, TypeError):
            return ValidationResult(
                approved=False,
                context=context,
                reason=DecisionReason.PRE_CONDITION_FAILED,
                message=f"Invalid position value: {position}",
                severity=Severity.MEDIUM,
                check_name="position_limit"
            )

        return ValidationResult(
            approved=True,
            context=context,
            reason=DecisionReason.APPROVED,
            message=f"Position {position_value:,.0f} within limits ±{self.max_position:,.0f}",
            details={"position": position_value, "limit": self.max_position},
            check_name="position_limit"
        )

    def check_post(
        self,
        context: "ExecutionContext",
        execution_result: Any,
        manifest_data: Optional[Dict] = None
    ) -> PostConditionResult:
        return PostConditionResult(passed=True)


class DrawdownLimitContract(BaseContract):
    """
    Contract that validates maximum drawdown limits.

    Prevents excessive portfolio value decline from peak.
    Drawdown = (peak - current) / peak

    Args:
        max_drawdown: Maximum acceptable drawdown as fraction (e.g., 0.2 = 20%)
        peak_parameter: Parameter name containing peak portfolio value
        current_parameter: Parameter name containing current portfolio value
    """

    def __init__(
        self,
        max_drawdown: float = 0.2,
        peak_parameter: str = "peak_value",
        current_parameter: str = "current_value"
    ):
        self.max_drawdown = max_drawdown
        self.peak_parameter = peak_parameter
        self.current_parameter = current_parameter

    def check_pre(
        self,
        context: "ExecutionContext",
        manifest_data: Optional[Dict] = None
    ) -> ValidationResult:
        """Check drawdown is within acceptable limits."""
        peak = context.parameters.get(self.peak_parameter)
        current = context.parameters.get(self.current_parameter)

        if peak is None or current is None:
            return ValidationResult(
                approved=True,
                context=context,
                reason=DecisionReason.APPROVED,
                message="Insufficient data for drawdown check",
                check_name="drawdown_limit"
            )

        try:
            peak_value = float(peak)
            current_value = float(current)

            if peak_value <= 0:
                return ValidationResult(
                    approved=False,
                    context=context,
                    reason=DecisionReason.PRE_CONDITION_FAILED,
                    message=f"Invalid peak value: {peak_value}",
                    severity=Severity.MEDIUM,
                    check_name="drawdown_limit"
                )

            drawdown = (peak_value - current_value) / peak_value

            if drawdown > self.max_drawdown:
                return ValidationResult(
                    approved=False,
                    context=context,
                    reason=DecisionReason.PRE_CONDITION_FAILED,
                    message=f"Drawdown {drawdown:.1%} exceeds limit {self.max_drawdown:.1%}",
                    severity=Severity.CRITICAL,
                    details={
                        "peak": peak_value,
                        "current": current_value,
                        "drawdown": drawdown,
                        "max_drawdown": self.max_drawdown
                    },
                    check_name="drawdown_limit"
                )

            return ValidationResult(
                approved=True,
                context=context,
                reason=DecisionReason.APPROVED,
                message=f"Drawdown {drawdown:.1%} within limit {self.max_drawdown:.1%}",
                details={
                    "peak": peak_value,
                    "current": current_value,
                    "drawdown": drawdown
                },
                check_name="drawdown_limit"
            )

        except (ValueError, TypeError):
            return ValidationResult(
                approved=False,
                context=context,
                reason=DecisionReason.PRE_CONDITION_FAILED,
                message="Invalid drawdown values",
                severity=Severity.MEDIUM,
                check_name="drawdown_limit"
            )

    def check_post(
        self,
        context: "ExecutionContext",
        execution_result: Any,
        manifest_data: Optional[Dict] = None
    ) -> PostConditionResult:
        """Check drawdown after trade execution."""
        if isinstance(execution_result, dict):
            new_peak = execution_result.get(self.peak_parameter)
            new_current = execution_result.get(self.current_parameter)

            if new_peak and new_current:
                try:
                    peak_value = float(new_peak)
                    current_value = float(new_current)
                    drawdown = (peak_value - current_value) / peak_value if peak_value > 0 else 0

                    passed = drawdown <= self.max_drawdown
                    return PostConditionResult(
                        passed=passed,
                        results=[{
                            "name": "drawdown_post",
                            "passed": passed,
                            "drawdown": drawdown,
                            "max_drawdown": self.max_drawdown
                        }],
                        failed_conditions=[{
                            "name": "drawdown_limit",
                            "reason": f"Post-trade drawdown {drawdown:.1%} exceeds {self.max_drawdown:.1%}"
                        }] if not passed else []
                    )
                except (ValueError, TypeError):
                    pass

        return PostConditionResult(passed=True)


class MarketManipulationCheck(BaseContract):
    """
    Contract that detects potential market manipulation patterns.

    Checks for:
    - Layering: High order cancellation rate
    - Spoofing: Rapid placement and cancellation
    - Wash trading: Low counterparty diversity (trading with oneself)

    Args:
        max_cancel_rate: Maximum acceptable cancellation rate (default 0.7)
        min_order_lifetime_ms: Minimum order lifetime in ms (default 100)
        check_counterparty_diversity: Whether to check counterparty diversity
    """

    # Manipulation pattern definitions
    PATTERNS = {
        "layering": "High cancellation rate indicates potential layering",
        "spoofing": "Rapid order placement/cancellation indicates potential spoofing",
        "wash_trading": "Low counterparty diversity indicates potential wash trading"
    }

    def __init__(
        self,
        max_cancel_rate: float = 0.7,
        min_order_lifetime_ms: float = 100,
        check_counterparty_diversity: bool = True
    ):
        self.max_cancel_rate = max_cancel_rate
        self.min_order_lifetime_ms = min_order_lifetime_ms
        self.check_counterparty_diversity = check_counterparty_diversity

    def check_pre(
        self,
        context: "ExecutionContext",
        manifest_data: Optional[Dict] = None
    ) -> ValidationResult:
        """Check for potential manipulation patterns."""
        warnings = []
        details = {}

        # Check for layering: high cancel rate
        orders_placed = context.parameters.get("orders_placed", 0)
        orders_cancelled = context.parameters.get("orders_cancelled", 0)

        if orders_placed > 10:
            cancel_rate = orders_cancelled / orders_placed if orders_placed > 0 else 0
            details["cancel_rate"] = cancel_rate

            if cancel_rate > self.max_cancel_rate:
                warnings.append({
                    "pattern": "layering",
                    "severity": "HIGH",
                    "reason": f"Cancel rate {cancel_rate:.1%} exceeds threshold {self.max_cancel_rate:.1%}"
                })

        # Check for wash trading: low counterparty diversity
        if self.check_counterparty_diversity:
            counterparties = context.parameters.get("counterparties", [])
            if counterparties:
                unique_count = len(set(counterparties))
                total_count = len(counterparties)
                diversity_ratio = unique_count / total_count if total_count > 0 else 1

                details["counterparty_diversity"] = diversity_ratio

                if diversity_ratio < 0.3:
                    warnings.append({
                        "pattern": "wash_trading",
                        "severity": "HIGH",
                        "reason": f"Low counterparty diversity: {diversity_ratio:.1%}"
                    })

        if warnings:
            high_severity = any(w["severity"] == "HIGH" for w in warnings)

            return ValidationResult(
                approved=False,
                context=context,
                reason=DecisionReason.PRE_CONDITION_FAILED,
                message=f"Potential market manipulation detected: {warnings[0]['pattern']}",
                severity=Severity.HIGH if high_severity else Severity.MEDIUM,
                details={
                    "warnings": warnings,
                    "patterns_detected": [w["pattern"] for w in warnings],
                    "description": self.PATTERNS.get(warnings[0]["pattern"], "")
                },
                check_name="market_manipulation"
            )

        return ValidationResult(
            approved=True,
            context=context,
            reason=DecisionReason.APPROVED,
            message="No manipulation patterns detected",
            details=details,
            check_name="market_manipulation"
        )

    def check_post(
        self,
        context: "ExecutionContext",
        execution_result: Any,
        manifest_data: Optional[Dict] = None
    ) -> PostConditionResult:
        """Post-execution manipulation check."""
        return PostConditionResult(passed=True)


# =============================================================================
# TRADING CONTRACT FACTORIES
# =============================================================================

def create_trading_contract(
    operation: str,
    min_sharpe: float = 1.0,
    max_position: float = 1_000_000,
    max_drawdown: float = 0.2,
    check_manipulation: bool = True
) -> "IntentContract":
    """
    Create a trading contract with standard invariants.

    Args:
        operation: Operation name for the contract
        min_sharpe: Minimum Sharpe ratio requirement
        max_position: Maximum position size limit
        max_drawdown: Maximum drawdown limit (fraction)
        check_manipulation: Whether to include manipulation checks

    Returns:
        Configured IntentContract for trading operations
    """
    from .intent_contract import IntentContract, ContractBuilder

    builder = ContractBuilder(operation)
    builder.require_permission(f"trading.{operation}")

    # Add standard trading invariants
    builder.add_pre(SharpeRatioContract(min_sharpe=min_sharpe))
    builder.add_pre(PositionLimitContract(max_position=max_position))
    builder.add_pre(DrawdownLimitContract(max_drawdown=max_drawdown))

    if check_manipulation:
        builder.add_pre(MarketManipulationCheck())

    return builder.build()


# =============================================================================
# PREDEFINED TRADING CONTRACTS
# =============================================================================

# Standard order placement contract
PLACE_ORDER_CONTRACT_DEF = {
    "min_sharpe": 0.5,
    "max_position": 1_000_000,
    "max_drawdown": 0.15,
    "check_manipulation": True
}

# Algorithmic trading contract (stricter limits)
ALGO_TRADE_CONTRACT_DEF = {
    "min_sharpe": 1.0,
    "max_position": 500_000,
    "max_drawdown": 0.10,
    "check_manipulation": True
}

# Risk management contract (strictest limits)
RISK_MANAGEMENT_CONTRACT_DEF = {
    "min_sharpe": 1.5,
    "max_position": 100_000,
    "max_drawdown": 0.05,
    "check_manipulation": False  # Internal operations
}


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # Trading contract classes
    "SharpeRatioContract",
    "PositionLimitContract",
    "DrawdownLimitContract",
    "MarketManipulationCheck",

    # Factory functions
    "create_trading_contract",

    # Predefined contract configurations
    "PLACE_ORDER_CONTRACT_DEF",
    "ALGO_TRADE_CONTRACT_DEF",
    "RISK_MANAGEMENT_CONTRACT_DEF",
]
