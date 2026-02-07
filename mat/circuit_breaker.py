"""
Circuit Breaker - Graduated Autonomy System
============================================

Implements "Siege Mode" with 4 autonomy levels:
- GREEN: Host online, full access
- AMBER: No contact 2h+ + backlog > 5, restricted access
- RED: No contact 6h+ + critical issue, canary deployments only
- BLACK: Critical error, monitoring only

This is the MAT (Multi-Agent Team) component adapted for Archon AI.

Usage:
    from mat.circuit_breaker import CircuitBreaker, AutonomyLevel, OperationType

    cb = CircuitBreaker()
    level = cb.check_level()

    if cb.can_execute(OperationType.MODIFY_CORE):
        # Execute operation
        pass
"""

import json
import time
import logging
from enum import Enum, auto
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Callable, Any
from collections import deque

logger = logging.getLogger(__name__)


class AutonomyLevel(Enum):
    """Autonomy levels of the system"""
    GREEN = "green"      # Full access
    AMBER = "amber"      # Restricted access
    RED = "red"          # Canary deployments only
    BLACK = "black"      # Monitoring only


class OperationType(Enum):
    """Operation types for permission checking"""
    READ_ONLY = auto()           # Reading, analysis
    DEBATE_SAFE = auto()         # Debates on safe zones
    SHADOW_AGENT = auto()        # Creating shadow agents
    MODIFY_CODE = auto()         # Modifying code
    MODIFY_CORE = auto()         # Modifying core system
    ARCHITECTURE_CHANGE = auto() # Architecture changes
    DEPLOY_CANARY = auto()       # Canary deployment
    DEPLOY_PRODUCTION = auto()   # Production deployment
    FULL_AUTONOMY = auto()       # Full autonomy


@dataclass
class CircuitBreakerConfig:
    """Circuit Breaker configuration"""
    # Base directory of project (for absolute paths)
    base_dir: Optional[str] = None

    # Timeouts for level transitions
    amber_timeout_minutes: int = 120      # 2 hours to AMBER
    red_timeout_minutes: int = 360        # 6 hours to RED

    # Thresholds
    amber_backlog_threshold: int = 5      # backlog > 5 for AMBER
    red_critical_threshold: int = 1       # >= 1 critical for RED

    # Canary deployment
    canary_traffic_percentage: float = 10.0  # 10% traffic on canary
    canary_success_threshold: float = 0.95   # 95% success to continue

    # Paths (relative to base_dir or absolute)
    state_file: str = "data/circuit_breaker_state.json"
    human_activity_file: str = "data/human_activity.log"

    # Alerts
    alert_on_black: bool = True
    alert_on_red: bool = True
    alert_callback: Optional[Callable] = None

    def get_absolute_path(self, relative_path: str) -> str:
        """Convert relative path to absolute"""
        path = Path(relative_path)
        if path.is_absolute():
            return str(path)

        # Determine base_dir
        if self.base_dir:
            base = Path(self.base_dir)
        else:
            base = Path(__file__).parent.parent

        return str(base / path)


@dataclass
class SystemState:
    """Current system state"""
    backlog_size: int = 0
    critical_issues: int = 0
    failed_deployments: int = 0
    last_error: Optional[str] = None
    resource_usage: Dict[str, float] = field(default_factory=dict)


@dataclass
class HumanActivity:
    """Human activity record"""
    last_seen: datetime
    last_action: str
    activity_history: deque = field(default_factory=lambda: deque(maxlen=100))

    def minutes_since_last_seen(self) -> float:
        """Minutes since last contact"""
        return (datetime.now() - self.last_seen).total_seconds() / 60


class CircuitBreaker:
    """
    Circuit Breaker for managing system autonomy.

    Implements 4 autonomy levels with automatic transitions
    based on human activity and system state.
    """

    # Permissions by level and operation type
    PERMISSIONS = {
        AutonomyLevel.GREEN: {
            OperationType.READ_ONLY: True,
            OperationType.DEBATE_SAFE: True,
            OperationType.SHADOW_AGENT: True,
            OperationType.MODIFY_CODE: True,
            OperationType.MODIFY_CORE: True,
            OperationType.ARCHITECTURE_CHANGE: True,
            OperationType.DEPLOY_CANARY: True,
            OperationType.DEPLOY_PRODUCTION: True,
            OperationType.FULL_AUTONOMY: True,
        },
        AutonomyLevel.AMBER: {
            OperationType.READ_ONLY: True,
            OperationType.DEBATE_SAFE: True,
            OperationType.SHADOW_AGENT: True,
            OperationType.MODIFY_CODE: True,
            OperationType.MODIFY_CORE: False,  # Requires approval
            OperationType.ARCHITECTURE_CHANGE: False,
            OperationType.DEPLOY_CANARY: True,
            OperationType.DEPLOY_PRODUCTION: False,
            OperationType.FULL_AUTONOMY: False,
        },
        AutonomyLevel.RED: {
            OperationType.READ_ONLY: True,
            OperationType.DEBATE_SAFE: True,
            OperationType.SHADOW_AGENT: True,
            OperationType.MODIFY_CODE: False,  # Only via canary
            OperationType.MODIFY_CORE: False,
            OperationType.ARCHITECTURE_CHANGE: False,
            OperationType.DEPLOY_CANARY: True,  # Canary only
            OperationType.DEPLOY_PRODUCTION: False,
            OperationType.FULL_AUTONOMY: False,
        },
        AutonomyLevel.BLACK: {
            OperationType.READ_ONLY: True,  # Monitoring only
            OperationType.DEBATE_SAFE: False,
            OperationType.SHADOW_AGENT: False,
            OperationType.MODIFY_CODE: False,
            OperationType.MODIFY_CORE: False,
            OperationType.ARCHITECTURE_CHANGE: False,
            OperationType.DEPLOY_CANARY: False,
            OperationType.DEPLOY_PRODUCTION: False,
            OperationType.FULL_AUTONOMY: False,
        },
    }

    def __init__(self, config: Optional[CircuitBreakerConfig] = None):
        self.config = config or CircuitBreakerConfig()
        self.current_level: AutonomyLevel = AutonomyLevel.GREEN
        self.system_state = SystemState()
        self.human_activity: Optional[HumanActivity] = None
        self._level_history: deque = deque(maxlen=100)
        self._alert_sent: Dict[AutonomyLevel, bool] = {
            AutonomyLevel.AMBER: False,
            AutonomyLevel.RED: False,
            AutonomyLevel.BLACK: False,
        }

        # Load state
        self._load_state()
        self._load_human_activity()

        logger.info(f"Circuit Breaker initialized at level: {self.current_level.value}")

    def check_level(self) -> AutonomyLevel:
        """Determine current autonomy level"""
        # Check BLACK (critical error)
        if self.system_state.critical_issues >= self.config.red_critical_threshold * 2:
            if self.current_level != AutonomyLevel.BLACK:
                self._escalate(AutonomyLevel.BLACK, "Multiple critical issues detected")
            return AutonomyLevel.BLACK

        # Check RED (long absence + critical issues)
        if self.human_activity:
            minutes_away = self.human_activity.minutes_since_last_seen()

            if (minutes_away >= self.config.red_timeout_minutes and
                self.system_state.critical_issues >= self.config.red_critical_threshold):
                if self.current_level != AutonomyLevel.RED:
                    self._escalate(AutonomyLevel.RED,
                        f"No human contact for {minutes_away:.0f}min + {self.system_state.critical_issues} critical issues")
                return AutonomyLevel.RED

            # Check AMBER (absence + backlog)
            if (minutes_away >= self.config.amber_timeout_minutes and
                self.system_state.backlog_size >= self.config.amber_backlog_threshold):
                if self.current_level == AutonomyLevel.GREEN:
                    self._escalate(AutonomyLevel.AMBER,
                        f"No human contact for {minutes_away:.0f}min + backlog {self.system_state.backlog_size}")
                return AutonomyLevel.AMBER

        # If human appeared - reset to GREEN
        if (self.current_level != AutonomyLevel.GREEN and
            self.human_activity and
            self.human_activity.minutes_since_last_seen() < self.config.amber_timeout_minutes):
            self._de_escalate(AutonomyLevel.GREEN, "Human activity detected")

        return self.current_level

    def can_execute(self, operation: OperationType) -> bool:
        """Check if operation can be executed at current level"""
        level = self.check_level()
        allowed = self.PERMISSIONS.get(level, {}).get(operation, False)

        if not allowed:
            logger.warning(f"Operation {operation.name} denied at level {level.value}")

        return allowed

    def require_approval(self, operation: OperationType) -> bool:
        """Check if operation requires human approval"""
        level = self.check_level()

        # No approval on GREEN (except architecture)
        if level == AutonomyLevel.GREEN:
            return operation in [OperationType.ARCHITECTURE_CHANGE]

        # On AMBER approval needed for core changes
        if level == AutonomyLevel.AMBER:
            return operation in [OperationType.MODIFY_CORE, OperationType.ARCHITECTURE_CHANGE,
                                OperationType.DEPLOY_PRODUCTION]

        # On RED and BLACK - almost everything needs approval
        if level in [AutonomyLevel.RED, AutonomyLevel.BLACK]:
            return operation != OperationType.READ_ONLY

        return True

    def record_human_activity(self, action: str = "activity") -> None:
        """Record human activity"""
        now = datetime.now()

        if self.human_activity is None:
            self.human_activity = HumanActivity(last_seen=now, last_action=action)
        else:
            self.human_activity.last_seen = now
            self.human_activity.last_action = action
            self.human_activity.activity_history.append({
                "timestamp": now.isoformat(),
                "action": action
            })

        # Reset alerts
        self._alert_sent = {level: False for level in self._alert_sent}

        # Save
        self._save_human_activity()

        # If not GREEN - reset
        if self.current_level != AutonomyLevel.GREEN:
            self._de_escalate(AutonomyLevel.GREEN, f"Human activity: {action}")

        logger.info(f"Human activity recorded: {action}")

    def update_system_state(self, state: SystemState) -> None:
        """Update system state"""
        self.system_state = state
        self._save_state()

        # Re-check level
        self.check_level()

    def _escalate(self, new_level: AutonomyLevel, reason: str) -> None:
        """Escalate autonomy level (restrict access)"""
        old_level = self.current_level
        self.current_level = new_level

        self._level_history.append({
            "timestamp": datetime.now().isoformat(),
            "from": old_level.value,
            "to": new_level.value,
            "reason": reason
        })

        logger.warning(f"ESCALATION: {old_level.value} -> {new_level.value} | {reason}")

        # Send alert
        self._send_alert(new_level, reason)

        self._save_state()

    def _de_escalate(self, new_level: AutonomyLevel, reason: str) -> None:
        """De-escalate autonomy level (expand access)"""
        old_level = self.current_level
        self.current_level = new_level

        self._level_history.append({
            "timestamp": datetime.now().isoformat(),
            "from": old_level.value,
            "to": new_level.value,
            "reason": reason
        })

        logger.info(f"DE-ESCALATION: {old_level.value} -> {new_level.value} | {reason}")

        self._save_state()

    def _send_alert(self, level: AutonomyLevel, reason: str) -> None:
        """Send alert about level change"""
        if level == AutonomyLevel.AMBER and not self._alert_sent[level]:
            message = f"AMBER Alert: Autonomy restricted | {reason}"
            logger.warning(message)
            self._alert_sent[level] = True

            if self.config.alert_callback:
                self.config.alert_callback(level, message)

        elif level == AutonomyLevel.RED and not self._alert_sent[level]:
            message = f"RED Alert: Limited autonomy mode | {reason}"
            logger.error(message)
            self._alert_sent[level] = True

            if self.config.alert_on_red and self.config.alert_callback:
                self.config.alert_callback(level, message)

        elif level == AutonomyLevel.BLACK and not self._alert_sent[level]:
            message = f"BLACK Alert: System halted | {reason}"
            logger.critical(message)
            self._alert_sent[level] = True

            if self.config.alert_on_black and self.config.alert_callback:
                self.config.alert_callback(level, message)

    def _save_state(self) -> None:
        """Save state to file"""
        state = {
            "current_level": self.current_level.value,
            "system_state": {
                "backlog_size": self.system_state.backlog_size,
                "critical_issues": self.system_state.critical_issues,
                "failed_deployments": self.system_state.failed_deployments,
                "last_error": self.system_state.last_error,
                "resource_usage": self.system_state.resource_usage,
            },
            "history": list(self._level_history),
            "timestamp": datetime.now().isoformat()
        }

        path = Path(self.config.get_absolute_path(self.config.state_file))
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=2, ensure_ascii=False)

    def _load_state(self) -> None:
        """Load state from file"""
        path = Path(self.config.get_absolute_path(self.config.state_file))
        if not path.exists():
            return

        try:
            with open(path, 'r', encoding='utf-8') as f:
                state = json.load(f)

            self.current_level = AutonomyLevel(state.get("current_level", "green"))

            sys_state = state.get("system_state", {})
            self.system_state = SystemState(
                backlog_size=sys_state.get("backlog_size", 0),
                critical_issues=sys_state.get("critical_issues", 0),
                failed_deployments=sys_state.get("failed_deployments", 0),
                last_error=sys_state.get("last_error"),
                resource_usage=sys_state.get("resource_usage", {})
            )

            logger.info(f"Loaded state: level={self.current_level.value}")
        except Exception as e:
            logger.error(f"Failed to load state: {e}")

    def _save_human_activity(self) -> None:
        """Save human activity"""
        if self.human_activity is None:
            return

        data = {
            "last_seen": self.human_activity.last_seen.isoformat(),
            "last_action": self.human_activity.last_action,
            "history": list(self.human_activity.activity_history)
        }

        path = Path(self.config.get_absolute_path(self.config.human_activity_file))
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _load_human_activity(self) -> None:
        """Load human activity"""
        path = Path(self.config.get_absolute_path(self.config.human_activity_file))
        if not path.exists():
            # Default - activity now
            self.record_human_activity("system_start")
            return

        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            self.human_activity = HumanActivity(
                last_seen=datetime.fromisoformat(data["last_seen"]),
                last_action=data.get("last_action", "unknown")
            )

            for item in data.get("history", []):
                self.human_activity.activity_history.append(item)

        except Exception as e:
            logger.error(f"Failed to load human activity: {e}")
            self.record_human_activity("system_start")

    def get_status(self) -> Dict[str, Any]:
        """Get full Circuit Breaker status"""
        level = self.check_level()

        return {
            "current_level": level.value,
            "level_emoji": self._get_level_emoji(level),
            "human_minutes_away": self.human_activity.minutes_since_last_seen() if self.human_activity else None,
            "system_state": {
                "backlog_size": self.system_state.backlog_size,
                "critical_issues": self.system_state.critical_issues,
                "failed_deployments": self.system_state.failed_deployments,
            },
            "permissions": {
                op.name: self.can_execute(op)
                for op in OperationType
            },
            "history": list(self._level_history)[-10:]  # Last 10 transitions
        }

    def _get_level_emoji(self, level: AutonomyLevel) -> str:
        """Get emoji for level"""
        return {
            AutonomyLevel.GREEN: "GREEN",
            AutonomyLevel.AMBER: "AMBER",
            AutonomyLevel.RED: "RED",
            AutonomyLevel.BLACK: "BLACK"
        }.get(level, "?")


# =============================================================================
# DECORATOR FOR AUTOMATIC CHECKS
# =============================================================================

def require_autonomy_level(min_level: AutonomyLevel):
    """
    Decorator for checking autonomy level.

    Usage:
        @require_autonomy_level(AutonomyLevel.GREEN)
        def modify_core_system():
            pass
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            # Get circuit breaker from kwargs or global context
            cb = kwargs.get('circuit_breaker') or _get_global_circuit_breaker()

            if cb is None:
                raise RuntimeError("CircuitBreaker not available")

            current = cb.check_level()
            level_order = [AutonomyLevel.GREEN, AutonomyLevel.AMBER,
                          AutonomyLevel.RED, AutonomyLevel.BLACK]

            if level_order.index(current) > level_order.index(min_level):
                raise PermissionError(
                    f"Operation requires {min_level.value} level, "
                    f"but current is {current.value}"
                )

            return func(*args, **kwargs)
        return wrapper
    return decorator


# Global instance (for simple usage)
_global_circuit_breaker: Optional[CircuitBreaker] = None


def _get_global_circuit_breaker() -> Optional[CircuitBreaker]:
    """Get global Circuit Breaker"""
    return _global_circuit_breaker


def set_global_circuit_breaker(cb: CircuitBreaker) -> None:
    """Set global Circuit Breaker"""
    global _global_circuit_breaker
    _global_circuit_breaker = cb


__all__ = [
    # Core
    "AutonomyLevel",
    "OperationType",
    "CircuitBreaker",
    "CircuitBreakerConfig",
    "SystemState",
    "HumanActivity",
    # Decorator
    "require_autonomy_level",
    "set_global_circuit_breaker"
]
