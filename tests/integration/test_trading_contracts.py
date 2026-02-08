# tests/integration/test_trading_contracts.py
"""
Tests for Trading Domain Contracts

Tests the trading-specific IntentContract extensions:
- SharpeRatioContract: Validates risk-adjusted returns
- PositionLimitContract: Ensures positions stay within bounds
- DrawdownLimitContract: Prevents excessive drawdown
- MarketManipulationCheck: Detects manipulation patterns
"""

import pytest

from kernel.execution_kernel import ExecutionKernel, KernelConfig, ExecutionContext
from kernel.trading_contracts import (
    SharpeRatioContract,
    PositionLimitContract,
    DrawdownLimitContract,
    MarketManipulationCheck,
    create_trading_contract,
    PLACE_ORDER_CONTRACT_DEF,
    ALGO_TRADE_CONTRACT_DEF,
    RISK_MANAGEMENT_CONTRACT_DEF,
)
from kernel.intent_contract import ContractBuilder


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def trading_context():
    """Create a trading execution context."""
    return ExecutionContext(
        operation="place_order",
        agent_id="trading_agent",
        domain="trading",
        parameters={}
    )


@pytest.fixture
def trading_kernel():
    """Create kernel for trading contract tests."""
    config = KernelConfig(
        environment="test",
        skip_manifest_validation=True,
        enable_audit=False,
    )
    kernel = ExecutionKernel(config=config)

    # Register trading operations
    kernel.register_operation("place_order", lambda **kwargs: {"status": "filled"}, "Place order")
    kernel.register_operation("algo_trade", lambda **kwargs: {"status": "executed"}, "Algo trade")
    kernel.register_operation("risk_check", lambda **kwargs: {"status": "approved"}, "Risk check")

    return kernel


# =============================================================================
# SHARPE RATIO CONTRACT TESTS
# =============================================================================

class TestSharpeRatioContract:
    """Tests for Sharpe ratio contract."""

    def test_sharpe_ratio_pass(self, trading_context):
        """Test Sharpe ratio within acceptable limit."""
        contract = SharpeRatioContract(min_sharpe=1.0)
        trading_context.parameters = {"sharpe_ratio": 1.5}

        result = contract.check_pre(trading_context, None)

        assert result.approved is True
        assert "1.50" in result.message

    def test_sharpe_ratio_fail(self, trading_context):
        """Test Sharpe ratio below minimum threshold."""
        contract = SharpeRatioContract(min_sharpe=1.0)
        trading_context.parameters = {"sharpe_ratio": 0.5}

        result = contract.check_pre(trading_context, None)

        assert result.approved is False
        assert "below minimum" in result.message
        assert result.details["sharpe_ratio"] == 0.5

    def test_sharpe_ratio_missing(self, trading_context):
        """Test handling of missing Sharpe ratio."""
        contract = SharpeRatioContract(min_sharpe=1.0)
        trading_context.parameters = {}

        result = contract.check_pre(trading_context, None)

        # Should allow with warning
        assert result.approved is True
        assert result.severity.name == "LOW"

    def test_sharpe_ratio_invalid(self, trading_context):
        """Test handling of invalid Sharpe ratio value."""
        contract = SharpeRatioContract(min_sharpe=1.0)
        trading_context.parameters = {"sharpe_ratio": "invalid"}

        result = contract.check_pre(trading_context, None)

        assert result.approved is False
        assert "Invalid" in result.message

    def test_sharpe_ratio_post_check_pass(self, trading_context):
        """Test post-condition check with valid Sharpe."""
        contract = SharpeRatioContract(min_sharpe=1.0)
        trading_context.parameters = {"sharpe_ratio": 1.2}

        result = contract.check_post(
            trading_context,
            {"sharpe_ratio": 1.3},
            None
        )

        assert result.passed is True
        assert result.results[0]["sharpe_ratio"] == 1.3

    def test_sharpe_ratio_post_check_fail(self, trading_context):
        """Test post-condition check with Sharpe below threshold."""
        contract = SharpeRatioContract(min_sharpe=1.0)
        trading_context.parameters = {"sharpe_ratio": 1.2}

        result = contract.check_post(
            trading_context,
            {"sharpe_ratio": 0.8},
            None
        )

        assert result.passed is False
        assert len(result.failed_conditions) > 0


# =============================================================================
# POSITION LIMIT CONTRACT TESTS
# =============================================================================

class TestPositionLimitContract:
    """Tests for position limit contract."""

    def test_position_within_limit(self, trading_context):
        """Test position within acceptable limit."""
        contract = PositionLimitContract(max_position=1_000_000)
        trading_context.parameters = {"position_size": 500_000}

        result = contract.check_pre(trading_context, None)

        assert result.approved is True
        assert "within limits" in result.message

    def test_position_exceeds_long_limit(self, trading_context):
        """Test position exceeds long limit."""
        contract = PositionLimitContract(max_position=1_000_000)
        trading_context.parameters = {"position_size": 1_500_000}

        result = contract.check_pre(trading_context, None)

        assert result.approved is False
        assert "exceeds limit" in result.message
        assert result.details["excess"] == 500_000

    def test_position_exceeds_short_limit(self, trading_context):
        """Test short position exceeds limit."""
        contract = PositionLimitContract(max_position=1_000_000)
        trading_context.parameters = {"position_size": -1_500_000}

        result = contract.check_pre(trading_context, None)

        assert result.approved is False
        assert "Short position" in result.message
        assert "exceeds limit" in result.message

    def test_position_at_limit_boundary(self, trading_context):
        """Test position exactly at limit boundary."""
        contract = PositionLimitContract(max_position=1_000_000)

        # Test positive boundary
        trading_context.parameters = {"position_size": 1_000_000}
        result = contract.check_pre(trading_context, None)
        assert result.approved is True

        # Test negative boundary
        trading_context.parameters = {"position_size": -1_000_000}
        result = contract.check_pre(trading_context, None)
        assert result.approved is True

    def test_position_zero(self, trading_context):
        """Test zero position (neutral)."""
        contract = PositionLimitContract(max_position=1_000_000)
        trading_context.parameters = {"position_size": 0}

        result = contract.check_pre(trading_context, None)

        assert result.approved is True


# =============================================================================
# DRAWDOWN LIMIT CONTRACT TESTS
# =============================================================================

class TestDrawdownLimitContract:
    """Tests for drawdown limit contract."""

    def test_drawdown_within_limit(self, trading_context):
        """Test drawdown within acceptable limit."""
        contract = DrawdownLimitContract(max_drawdown=0.2)
        trading_context.parameters = {
            "peak_value": 100.0,
            "current_value": 90.0
        }

        result = contract.check_pre(trading_context, None)

        assert result.approved is True
        assert "within limit" in result.message

    def test_drawdown_exceeds_limit(self, trading_context):
        """Test drawdown exceeds maximum."""
        contract = DrawdownLimitContract(max_drawdown=0.2)
        trading_context.parameters = {
            "peak_value": 100.0,
            "current_value": 70.0
        }

        result = contract.check_pre(trading_context, None)

        assert result.approved is False
        assert "exceeds limit" in result.message
        assert result.details["drawdown"] == 0.3

    def test_drawdown_at_peak(self, trading_context):
        """Test zero drawdown (at peak)."""
        contract = DrawdownLimitContract(max_drawdown=0.2)
        trading_context.parameters = {
            "peak_value": 100.0,
            "current_value": 100.0
        }

        result = contract.check_pre(trading_context, None)

        assert result.approved is True
        assert result.details["drawdown"] == 0.0

    def test_drawdown_invalid_peak(self, trading_context):
        """Test invalid peak value."""
        contract = DrawdownLimitContract(max_drawdown=0.2)
        trading_context.parameters = {
            "peak_value": 0,
            "current_value": 90.0
        }

        result = contract.check_pre(trading_context, None)

        assert result.approved is False
        assert "Invalid peak" in result.message

    def test_drawdown_missing_data(self, trading_context):
        """Test missing drawdown data."""
        contract = DrawdownLimitContract(max_drawdown=0.2)
        trading_context.parameters = {"peak_value": 100.0}

        result = contract.check_pre(trading_context, None)

        # Should allow with info message
        assert result.approved is True
        assert "Insufficient data" in result.message

    def test_drawdown_post_check(self, trading_context):
        """Test post-condition drawdown check."""
        contract = DrawdownLimitContract(max_drawdown=0.2)
        trading_context.parameters = {
            "peak_value": 100.0,
            "current_value": 95.0
        }

        # Post-trade with new values
        result = contract.check_post(
            trading_context,
            {
                "peak_value": 100.0,
                "current_value": 85.0  # 15% drawdown - still within 20% limit
            },
            None
        )

        assert result.passed is True
        assert result.results[0]["drawdown"] == 0.15


# =============================================================================
# MARKET MANIPULATION CHECK TESTS
# =============================================================================

class TestMarketManipulationCheck:
    """Tests for market manipulation detection."""

    def test_normal_trading_passes(self, trading_context):
        """Test normal trading pattern passes."""
        contract = MarketManipulationCheck()
        trading_context.parameters = {
            "orders_placed": 50,
            "orders_cancelled": 10,  # 20% cancel rate
            "counterparties": ["A", "B", "C", "D", "E"]
        }

        result = contract.check_pre(trading_context, None)

        assert result.approved is True
        assert "No manipulation" in result.message

    def test_layering_detected(self, trading_context):
        """Test layering (high cancel rate) is detected."""
        contract = MarketManipulationCheck(max_cancel_rate=0.7)
        trading_context.parameters = {
            "orders_placed": 150,
            "orders_cancelled": 140,  # 93% cancel rate
        }

        result = contract.check_pre(trading_context, None)

        assert result.approved is False
        assert "layering" in result.details["patterns_detected"]

    def test_wash_trading_detected(self, trading_context):
        """Test wash trading (low diversity) is detected."""
        contract = MarketManipulationCheck()
        trading_context.parameters = {
            "orders_placed": 10,
            "counterparties": ["SELF", "SELF", "SELF", "SELF", "SELF"]
        }

        result = contract.check_pre(trading_context, None)

        assert result.approved is False
        assert "wash_trading" in result.details["patterns_detected"]

    def test_diverse_counterparties_pass(self, trading_context):
        """Test diverse counterparties pass wash trading check."""
        contract = MarketManipulationCheck()
        trading_context.parameters = {
            "orders_placed": 10,
            "counterparties": ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"]
        }

        result = contract.check_pre(trading_context, None)

        assert result.approved is True

    def test_manipulation_details_in_result(self, trading_context):
        """Test manipulation details are included in result."""
        contract = MarketManipulationCheck()
        trading_context.parameters = {
            "orders_placed": 100,
            "orders_cancelled": 80,
            "counterparties": ["SELF"] * 10
        }

        result = contract.check_pre(trading_context, None)

        assert result.approved is False
        assert "warnings" in result.details
        assert len(result.details["warnings"]) == 2  # Both layering and wash trading


# =============================================================================
# INTEGRATED CONTRACT TESTS
# =============================================================================

class TestIntegratedTradingContracts:
    """Tests for integrated trading contracts."""

    def test_place_order_contract(self, trading_context):
        """Test standard place order contract."""
        config = PLACE_ORDER_CONTRACT_DEF
        contract = create_trading_contract(
            operation="place_order",
            **config
        )

        # Valid trade with permissions
        trading_context.parameters = {
            "permissions": ["trading.place_order"],
            "sharpe_ratio": 1.5,
            "position_size": 500_000,
            "peak_value": 100.0,
            "current_value": 95.0,
            "orders_placed": 20,
            "orders_cancelled": 5,
            "counterparties": ["A", "B", "C"]
        }

        result = contract.check_pre(trading_context, None)
        assert result.approved is True

    def test_place_order_contract_fails_position(self, trading_context):
        """Test place order contract fails on position limit."""
        config = PLACE_ORDER_CONTRACT_DEF
        contract = create_trading_contract(
            operation="place_order",
            **config
        )

        trading_context.parameters = {
            "permissions": ["trading.place_order"],
            "sharpe_ratio": 1.5,
            "position_size": 2_000_000,  # Exceeds 1M limit
            "peak_value": 100.0,
            "current_value": 95.0,
        }

        result = contract.check_pre(trading_context, None)
        assert result.approved is False
        assert "position" in result.details.get("failed_check", "").lower()

    def test_algo_trade_strict_limits(self, trading_context):
        """Test algo trading has stricter limits."""
        config = ALGO_TRADE_CONTRACT_DEF
        contract = create_trading_contract(
            operation="algo_trade",
            **config
        )

        # Within algo limits
        trading_context.parameters = {
            "permissions": ["trading.algo_trade"],
            "sharpe_ratio": 1.2,
            "position_size": 400_000,
            "peak_value": 100.0,
            "current_value": 92.0,  # 8% drawdown
        }

        result = contract.check_pre(trading_context, None)
        assert result.approved is True

    def test_risk_management_strictest(self, trading_context):
        """Test risk management has strictest limits."""
        config = RISK_MANAGEMENT_CONTRACT_DEF
        contract = create_trading_contract(
            operation="risk_management",
            **config
        )

        # Within risk management limits
        trading_context.parameters = {
            "permissions": ["trading.risk_management"],
            "sharpe_ratio": 2.0,
            "position_size": 50_000,
            "peak_value": 100.0,
            "current_value": 98.0,  # 2% drawdown
        }

        result = contract.check_pre(trading_context, None)
        assert result.approved is True

    def test_risk_management_fails_lower_sharpe(self, trading_context):
        """Test risk management fails on low Sharpe."""
        config = RISK_MANAGEMENT_CONTRACT_DEF
        contract = create_trading_contract(
            operation="risk_management",
            **config
        )

        trading_context.parameters = {
            "sharpe_ratio": 1.0,  # Below 1.5 requirement
            "position_size": 50_000,
            "peak_value": 100.0,
            "current_value": 98.0,
        }

        result = contract.check_pre(trading_context, None)
        assert result.approved is False


# =============================================================================
# CONTRACT BUILDER INTEGRATION
# =============================================================================

class TestContractBuilderIntegration:
    """Tests for ContractBuilder with trading contracts."""

    def test_builder_with_sharpe_contract(self, trading_context):
        """Test ContractBuilder with SharpeRatioContract."""
        contract = (ContractBuilder("trade_with_sharpe")
                   .add_pre(SharpeRatioContract(min_sharpe=0.8))
                   .build())

        trading_context.parameters = {"sharpe_ratio": 1.0}
        result = contract.check_pre(trading_context, None)
        assert result.approved is True

    def test_builder_multiple_trading_contracts(self, trading_context):
        """Test ContractBuilder with multiple trading contracts."""
        contract = (ContractBuilder("full_trade_check")
                   .add_pre(SharpeRatioContract(min_sharpe=1.0))
                   .add_pre(PositionLimitContract(max_position=500_000))
                   .add_pre(DrawdownLimitContract(max_drawdown=0.15))
                   .build())

        trading_context.parameters = {
            "sharpe_ratio": 1.2,
            "position_size": 300_000,
            "peak_value": 100.0,
            "current_value": 92.0,
        }

        result = contract.check_pre(trading_context, None)
        assert result.approved is True

    def test_builder_composition_trading(self, trading_context):
        """Test composing trading contracts with AND logic."""
        from kernel.intent_contract import AndContract

        sharpe_contract = SharpeRatioContract(min_sharpe=1.0)
        position_contract = PositionLimitContract(max_position=1_000_000)

        combined = sharpe_contract & position_contract

        trading_context.parameters = {
            "sharpe_ratio": 1.5,
            "position_size": 500_000
        }

        result = combined.check_pre(trading_context, None)
        assert result.approved is True


# =============================================================================
# RUN TESTS
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
