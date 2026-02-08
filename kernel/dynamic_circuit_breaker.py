# archon/kernel/dynamic_circuit_breaker.py
"""
Dynamic Circuit Breaker with ChaosMonkey integration.

The Circuit Breaker dynamically adjusts strictness based on:
- Agent "наглость" (cheekiness) - high rejection rates
- Agent reputation from Scoreboard
- Panic mode for sudden spikes (Siege Mode)

Strictness levels: 0.0 (loose) to 1.0 (strict).
"""

import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, Optional, Callable

from .execution_kernel import CircuitState


logger = logging.getLogger(__name__)


class PanicMode(Enum):
    """Panic mode states for emergency situations."""
    NORMAL = "normal"       # Normal operation
    ELEVATED = "elevated"   # Rejection rate rising
    PANIC = "panic"         # Immediate lockdown (Siege Mode)


@dataclass
class AgentReputation:
    """Reputation data for an agent."""
    agent_id: str
    score: float = 1.0  # 0.0 (untrusted) to 1.0 (perfect)
    total_requests: int = 0
    rejected_requests: int = 0
    forbidden_attempts: int = 0
    last_forbidden: Optional[datetime] = None
    successful_operations: int = 0

    @property
    def rejection_rate(self) -> float:
        """Calculate rejection rate."""
        if self.total_requests == 0:
            return 0.0
        return self.rejected_requests / self.total_requests

    @property
    def is_trusted(self) -> bool:
        """Check if agent is trusted."""
        return self.score >= 0.7 and self.forbidden_attempts < 3

    def update_score(self) -> None:
        """Update score based on performance."""
        if self.total_requests < 5:
            return  # Not enough data

        # Base score from rejection rate
        rejection_penalty = self.rejection_rate * 0.5

        # Forbidden attempts have heavy penalty
        forbidden_penalty = min(self.forbidden_attempts * 0.15, 0.4)

        # Success bonus
        success_bonus = min(self.successful_operations * 0.02, 0.2)

        # Calculate new score
        self.score = max(0.0, min(1.0, 1.0 - rejection_penalty - forbidden_penalty + success_bonus))

        logger.debug(
            f"Agent {self.agent_id} score: {self.score:.2f} "
            f"(rejection={self.rejection_rate:.2f}, forbidden={self.forbidden_attempts})"
        )


@dataclass
class MetricsSnapshot:
    """Snapshot of metrics for a time window."""
    timestamp: datetime
    total_requests: int = 0
    rejected_requests: int = 0
    forbidden_attempts: int = 0
    agent_rejections: Dict[str, int] = field(default_factory=dict)

    @property
    def rejection_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return self.rejected_requests / self.total_requests


@dataclass
class CircuitBreakerConfig:
    """Configuration for DynamicCircuitBreaker."""
    # Strictness settings
    initial_strictness: float = 0.5
    min_strictness: float = 0.0
    max_strictness: float = 1.0

    # Metrics window
    window_size: int = 5  # Number of snapshots to keep
    window_duration: float = 60.0  # Seconds per window

    # Adjustment settings
    max_adjust_step: float = 0.1  # Max change per adjustment
    high_nag_threshold: float = 0.3  # Rejection rate > 30% = "наглый"
    low_nag_threshold: float = 0.1  # Rejection rate < 10% = safe

    # Panic mode settings
    panic_threshold: float = 0.8  # Single window rejection > 80% triggers panic
    panic_duration: float = 300.0  # Panic lasts 5 minutes
    panic_recovery_rate: float = 0.05  # How fast to recover from panic
    min_panic_cycles: int = 3  # Minimum cycles to stay in panic (prevents ping-pong)

    # Agent reputation
    trust_decay_rate: float = 0.01  # Score decay per hour
    forbidden_penalty: float = 0.2  # Penalty per forbidden attempt
    agent_strictness_multiplier: float = 1.5  # Max multiplier for untrusted agents


class DynamicCircuitBreaker:
    """
    Dynamic Circuit Breaker with ChaosMonkey integration.

    Adjusts strictness based on agent behavior metrics:
    - High rejection rates → increase strictness (agents are "наглые")
    - Low rejection rates → decrease strictness (safe environment)
    - Sudden spikes → panic mode (immediate lockdown)
    - Agent reputation → per-agent risk adjustment
    """

    def __init__(
        self,
        config: Optional[CircuitBreakerConfig] = None,
        chaos_monkey: Optional[Any] = None  # mat.chaos_engine.ChaosEngine
    ):
        """
        Initialize DynamicCircuitBreaker.

        Args:
            config: Circuit breaker configuration
            chaos_monkey: Optional ChaosEngine for integration
        """
        self.config = config or CircuitBreakerConfig()
        self.chaos_monkey = chaos_monkey

        # Current state
        self.strictness = self.config.initial_strictness
        self.circuit_state = CircuitState.GREEN
        self.panic_mode = PanicMode.NORMAL
        self.panic_start: Optional[datetime] = None

        # Panic cooldown (prevents ping-pong between panic/relax)
        self.panic_cooldown: int = 0  # Cycles remaining in cooldown

        # Metrics tracking
        self.metrics_window: deque[MetricsSnapshot] = deque(maxlen=self.config.window_size)
        self.current_window = MetricsSnapshot(timestamp=datetime.now())

        # Agent reputations
        self.agent_reputations: Dict[str, AgentReputation] = {}

        # Per-agent strictness adjustments (agent_id → multiplier)
        self.agent_strictness: Dict[str, float] = {}

        # Per-operation thresholds (can override global strictness)
        self.operation_thresholds: Dict[str, float] = {
            "exec_code": 0.8,
            "delete_file": 0.7,
            "trade_execute": 0.9,
            "network_request": 0.6,
        }

        # Callbacks
        self.on_state_change: Optional[Callable[[CircuitState, CircuitState], None]] = None
        self.on_panic_mode: Optional[Callable[[PanicMode, PanicMode], None]] = None

    # ========================================================================
    # Public API
    # ========================================================================

    def is_allowed(
        self,
        operation: str,
        agent_id: str,
        context: Optional[Dict[str, Any]] = None
    ) -> tuple[bool, str]:
        """
        Check if operation is allowed under current strictness level.

        Uses per-agent thresholds based on reputation.

        Args:
            operation: Operation name (e.g., "exec_code")
            agent_id: Agent making the request
            context: Additional context for decision

        Returns:
            Tuple of (allowed: bool, reason: str)
        """
        # Check panic mode first
        if self.panic_mode == PanicMode.PANIC:
            return False, "PANIC_MODE: All operations blocked"

        # Get agent-specific threshold (based on reputation)
        agent_threshold = self.get_agent_threshold(agent_id)

        # Get operation-specific threshold if defined, otherwise use agent threshold
        op_threshold = self.operation_thresholds.get(operation, agent_threshold)

        # Use the stricter of agent or operation threshold
        effective_threshold = max(agent_threshold, op_threshold)

        # Estimate operation risk
        reputation = self._get_agent_reputation(agent_id)
        op_risk = self._estimate_operation_risk(operation, context, reputation)

        if op_risk > effective_threshold:
            logger.warning(
                f"Operation {operation} denied for agent {agent_id} "
                f"(risk {op_risk:.2f} > threshold {effective_threshold:.2f}, "
                f"agent_reputation={reputation.score:.2f})"
            )
            return False, f"Risk {op_risk:.2f} exceeds threshold {effective_threshold:.2f}"

        return True, "Allowed"

    def record_request(
        self,
        agent_id: str,
        operation: str,
        approved: bool,
        forbidden: bool = False
    ) -> None:
        """
        Record a request outcome for metrics tracking.

        Args:
            agent_id: Agent making the request
            operation: Operation performed
            approved: Whether the request was approved
            forbidden: Whether this was a forbidden attempt
        """
        self.current_window.total_requests += 1
        if not approved:
            self.current_window.rejected_requests += 1
            self.current_window.agent_rejections[agent_id] = \
                self.current_window.agent_rejections.get(agent_id, 0) + 1
        if forbidden:
            self.current_window.forbidden_attempts += 1

        # Update agent reputation
        reputation = self._get_agent_reputation(agent_id)
        reputation.total_requests += 1
        if not approved:
            reputation.rejected_requests += 1
        if forbidden:
            reputation.forbidden_attempts += 1
            reputation.last_forbidden = datetime.now()
        if approved:
            reputation.successful_operations += 1
        reputation.update_score()

        # Check for panic trigger
        if self._should_trigger_panic():
            self._enter_panic_mode()

    def adjust_strictness(self, metrics: Optional[Dict[str, float]] = None, reason: Optional[str] = None) -> None:
        """
        Adjust strictness based on metrics from Chaos Monkey or internal tracking.

        Uses cooldown mechanism to prevent ping-pong between panic/relax:
        - Once panic mode is triggered, stays in panic for at least min_panic_cycles
        - Gradual recovery after cooldown expires

        Args:
            metrics: Optional dict from ChaosMonkey (e.g., {'rejection_rate': 0.35})
                    If None, uses internal metrics_window.
            reason: Human-readable reason for adjustment (e.g., 'DebatePipeline violations')
        """
        # Rotate window if needed
        self._rotate_window_if_needed()

        if metrics:
            # Use external metrics from ChaosMonkey
            rejection_rate = metrics.get("rejection_rate", 0.0)
        else:
            # Use internal metrics
            rejection_rate = self._average_rejection_rate()

        # Check for immediate panic trigger
        if rejection_rate >= self.config.panic_threshold:
            self._enter_panic_mode()
            self.panic_cooldown = self.config.min_panic_cycles
            panic_reason = reason or f"Rejection rate {rejection_rate:.2f} >= {self.config.panic_threshold}"
            logger.critical(f"[KERNEL] PANIC MODE. Strictness={self.strictness:.2f}. Reason: {panic_reason}")
            return

        # Handle panic mode with cooldown
        if self.panic_mode == PanicMode.PANIC:
            if self.panic_cooldown > 0:
                # Still in cooldown - maintain panic
                self.panic_cooldown -= 1
                logger.warning(f"[KERNEL] PANIC COOLDOWN: {self.panic_cooldown} cycles remaining")
                return
            # Cooldown expired - check if safe to exit
            if self._should_exit_panic():
                self._exit_panic_mode()
            return

        # Handle cooldown active (even if not in full panic)
        if self.panic_cooldown > 0:
            # High strictness due to cooldown - increase or maintain
            delta = min(self.config.max_adjust_step, self.config.max_strictness - self.strictness)
            self.strictness += delta
            if rejection_rate > self.config.high_nag_threshold:
                # Still "наглый" - reset cooldown
                self.panic_cooldown = self.config.min_panic_cycles
            else:
                # Decaying cooldown
                self.panic_cooldown -= 1
            cooldown_reason = reason or "Cooldown active"
            logger.warning(
                f"[KERNEL] Strictness={self.strictness:.2f}. Reason: {cooldown_reason}. " 
                f"Cooldown cycles left: {self.panic_cooldown}"
            )
            self._update_circuit_state()
            return

        # Normal strictness adjustment
        old_strictness = self.strictness

        if rejection_rate > self.config.high_nag_threshold:
            # Agents are being "наглые" - increase strictness
            delta = min(self.config.max_adjust_step, self.config.max_strictness - self.strictness)
            self.strictness += delta
            self.panic_cooldown = self.config.min_panic_cycles  # Enter cooldown
            increase_reason = reason or f"High наглость: {rejection_rate:.2f}"
            logger.warning(
                f"[KERNEL] Strictness RAISED to {self.strictness:.2f} (was {old_strictness:.2f}). "
                f"Reason: {increase_reason}"
            )
        elif rejection_rate < self.config.low_nag_threshold:
            # Safe environment - decrease strictness
            delta = min(self.config.max_adjust_step, self.strictness - self.config.min_strictness)
            self.strictness -= delta
            decrease_reason = reason or f"Low наглость: {rejection_rate:.2f}"
            logger.info(
                f"[KERNEL] Strictness lowered to {self.strictness:.2f} (was {old_strictness:.2f}). "
                f"Reason: {decrease_reason}"
            )

        # Update circuit state based on strictness
        self._update_circuit_state()

        if self.strictness != old_strictness and self.on_state_change:
            self.on_state_change(self.circuit_state, self.circuit_state)

    def get_agent_reputation(self, agent_id: str) -> AgentReputation:
        """Get reputation data for an agent."""
        return self._get_agent_reputation(agent_id)

    def reset_panic_mode(self) -> None:
        """Manually exit panic mode."""
        if self.panic_mode != PanicMode.NORMAL:
            self._exit_panic_mode()

    def get_agent_threshold(self, agent_id: str) -> float:
        """
        Get per-agent strictness threshold based on reputation.

        Formula: threshold = base_strictness * (1.5 - reputation_score)

        Examples:
        - Reputation 1.0 (perfect) → threshold = base * 0.5 (more lenient)
        - Reputation 0.5 (average) → threshold = base * 1.0 (normal)
        - Reputation 0.0 (untrusted) → threshold = base * 1.5 (stricter)

        Args:
            agent_id: Agent to get threshold for

        Returns:
            Adjusted threshold for this agent
        """
        base = self.strictness
        reputation = self._get_agent_reputation(agent_id)

        # Calculate multiplier: 1.5 - score
        # This means untrusted agents get up to 1.5x stricter threshold
        multiplier = self.config.agent_strictness_multiplier - reputation.score

        # Clamp multiplier to reasonable range
        multiplier = max(0.5, min(1.5, multiplier))

        return base * multiplier

    # ========================================================================
    # Internal Methods
    # ========================================================================

    def _get_agent_reputation(self, agent_id: str) -> AgentReputation:
        """Get or create agent reputation."""
        if agent_id not in self.agent_reputations:
            self.agent_reputations[agent_id] = AgentReputation(agent_id=agent_id)
        return self.agent_reputations[agent_id]

    def _adjust_for_reputation(self, threshold: float, reputation: AgentReputation) -> float:
        """
        Adjust threshold based on agent reputation.

        Lower reputation = higher threshold (more restrictive).
        """
        # Untrusted agents get lower thresholds (harder to pass)
        if not reputation.is_trusted:
            return threshold * 0.7

        # Highly trusted agents get some leniency
        if reputation.score >= 0.9:
            return threshold * 1.1

        return threshold

    def _estimate_operation_risk(
        self,
        operation: str,
        context: Optional[Dict[str, Any]],
        reputation: AgentReputation
    ) -> float:
        """
        Estimate operation risk considering agent reputation.

        Formula:
        risk = base_risk * (2.0 - agent_reputation)

        Lower reputation = higher effective risk.
        """
        # Base risk from operation
        base_risks = {
            "read_file": 0.0,
            "write_file": 0.3,
            "delete_file": 0.8,
            "exec_code": 0.9,
            "trade_execute": 0.95,
            "network_request": 0.6,
            "git_commit": 0.5,
        }

        base_risk = base_risks.get(operation, self.strictness)

        # Adjust by reputation (2.0 - score means 0.0 score doubles the risk)
        reputation_factor = 2.0 - reputation.score
        adjusted_risk = base_risk * reputation_factor

        # Clamp to valid range
        return max(0.0, min(1.0, adjusted_risk))

    def _average_rejection_rate(self) -> float:
        """Calculate average rejection rate over the window."""
        if not self.metrics_window:
            return self.current_window.rejection_rate

        total_requests = sum(w.total_requests for w in self.metrics_window)
        total_rejections = sum(w.rejected_requests for w in self.metrics_window)

        if total_requests == 0:
            return 0.0
        return total_rejections / total_requests

    def _rotate_window_if_needed(self) -> None:
        """Start a new metrics window if duration has passed."""
        now = datetime.now()
        elapsed = (now - self.current_window.timestamp).total_seconds()

        if elapsed >= self.config.window_duration:
            # Save current window
            self.metrics_window.append(self.current_window)
            # Start new window
            self.current_window = MetricsSnapshot(timestamp=now)

    def _should_trigger_panic(self) -> bool:
        """Check if panic mode should be triggered."""
        # Check current window for extreme rejection rate
        if self.current_window.total_requests >= 10:
            current_rate = self.current_window.rejection_rate
            if current_rate >= self.config.panic_threshold:
                logger.critical(
                    f"PANIC TRIGGER: Rejection rate {current_rate:.2f} >= {self.config.panic_threshold}"
                )
                return True
        return False

    def _should_exit_panic(self) -> bool:
        """Check if panic mode should end."""
        if self.panic_start is None:
            return True

        elapsed = (datetime.now() - self.panic_start).total_seconds()
        if elapsed >= self.config.panic_duration:
            # Check if conditions have improved
            if self._average_rejection_rate() < self.config.high_nag_threshold:
                return True
        return False

    def _enter_panic_mode(self) -> None:
        """Enter panic mode (Siege Mode)."""
        old_mode = self.panic_mode
        self.panic_mode = PanicMode.PANIC
        self.panic_start = datetime.now()
        self.strictness = 1.0  # Maximum strictness

        old_state = self.circuit_state
        self.circuit_state = CircuitState.BLACK

        logger.critical("PANIC MODE ACTIVATED - Entering Siege Mode")

        if self.on_panic_mode and old_mode != self.panic_mode:
            self.on_panic_mode(old_mode, self.panic_mode)
        if self.on_state_change and old_state != self.circuit_state:
            self.on_state_change(old_state, self.circuit_state)

    def _exit_panic_mode(self) -> None:
        """Exit panic mode."""
        old_mode = self.panic_mode
        self.panic_mode = PanicMode.NORMAL
        self.panic_start = None

        # Gradually reduce strictness
        self.strictness = max(self.config.initial_strictness, self.strictness - 0.2)

        old_state = self.circuit_state
        self._update_circuit_state()

        logger.warning("PANIC MODE DEACTIVATED - Recovering to normal operation")

        if self.on_panic_mode and old_mode != self.panic_mode:
            self.on_panic_mode(old_mode, self.panic_mode)
        if self.on_state_change and old_state != self.circuit_state:
            self.on_state_change(old_state, self.circuit_state)

    def _update_circuit_state(self) -> None:
        """Update circuit state based on strictness."""
        old_state = self.circuit_state

        if self.strictness >= 0.9:
            self.circuit_state = CircuitState.RED
        elif self.strictness >= 0.6:
            self.circuit_state = CircuitState.AMBER
        else:
            self.circuit_state = CircuitState.GREEN

        if old_state != self.circuit_state and self.on_state_change:
            self.on_state_change(old_state, self.circuit_state)

    def get_status(self) -> Dict[str, Any]:
        """Get current circuit breaker status."""
        return {
            "strictness": self.strictness,
            "circuit_state": self.circuit_state.value,
            "panic_mode": self.panic_mode.value,
            "panic_start": self.panic_start.isoformat() if self.panic_start else None,
            "avg_rejection_rate": self._average_rejection_rate(),
            "current_window": {
                "total_requests": self.current_window.total_requests,
                "rejected_requests": self.current_window.rejected_requests,
                "forbidden_attempts": self.current_window.forbidden_attempts,
                "rejection_rate": self.current_window.rejection_rate,
            },
            "agents": {
                agent_id: {
                    "score": rep.score,
                    "rejection_rate": rep.rejection_rate,
                    "forbidden_attempts": rep.forbidden_attempts,
                    "is_trusted": rep.is_trusted,
                }
                for agent_id, rep in self.agent_reputations.items()
            },
        }


# =============================================================================
# Global Instance
# =============================================================================

_global_breaker: Optional[DynamicCircuitBreaker] = None


def get_circuit_breaker(
    config: Optional[CircuitBreakerConfig] = None,
    chaos_monkey: Optional[Any] = None,
    reload: bool = False
) -> DynamicCircuitBreaker:
    """Get global DynamicCircuitBreaker instance."""
    global _global_breaker

    if _global_breaker is None or reload:
        _global_breaker = DynamicCircuitBreaker(config=config, chaos_monkey=chaos_monkey)

    return _global_breaker
