"""
Siege Mode - Full Autonomy When Host Offline
============================================

When host is offline for 5+ hours, system:
1. Activates Siege Mode
2. Selects tasks from backlog
3. Executes them through Debate Pipeline
4. Creates temporary agents if needed
5. Generates report for host

From Text Document.txt:
> "The system sees that there has been no connection with the 'host' for 5+ hours.
> It takes the list of tasks from the backlog. If a task requires new knowledge —
> it 'learns' or 'creates' a plugin agent itself. It runs debates.
>
> When you return — you have not just code, but a report from the 'Virtual CTO'
> about which specialists were hired and what decisions were made."

Usage:
    from mat.siege_mode import SiegeMode, SiegeConfig

    siege = SiegeMode(curator, config)
    await siege.start()  # Starts background task

    # When host returns:
    report = await siege.generate_report()
    print(f"Tasks completed: {report['tasks_completed']}")
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum, auto
from pathlib import Path
from typing import Dict, List, Optional, Any
from collections import deque

logger = logging.getLogger(__name__)


# ============================================================================
# ENUMS
# ============================================================================

class SiegeState(Enum):
    """Siege Mode states"""
    INACTIVE = "inactive"       # Host online, Siege not active
    PREPARING = "preparing"     # Preparing for autonomy
    ACTIVE = "active"           # Full autonomy
    DEBRIEFING = "debriefing"   # Report to host
    PAUSED = "paused"           # Paused (manually)


class SiegeTrigger(Enum):
    """Activation reasons"""
    TIMEOUT = "timeout"                 # Host offline > N hours
    MANUAL = "manual"                   # Manual activation
    BACKLOG_OVERFLOW = "backlog"        # Too many tasks
    CRITICAL_ISSUE = "critical"         # Critical problem


class TaskSelectionStrategy(Enum):
    """Task selection strategies"""
    PRIORITY_FIRST = "priority"         # Priority tasks first
    DEPENDENCY_CHAIN = "dependency"     # Considering dependencies
    QUICK_WINS = "quick_wins"           # Quick wins first
    BALANCED = "balanced"               # Balance speed and importance


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class SiegeConfig:
    """Siege Mode configuration"""
    # Timings
    activation_timeout_hours: float = 5.0      # Hours offline for activation
    check_interval_minutes: int = 15           # How often to check activity
    max_continuous_runtime_hours: float = 24.0 # Max hours of continuous runtime

    # Limits
    max_tasks_per_session: int = 50            # Max tasks per session
    max_agents_per_session: int = 10           # Max agents to create
    max_debates_per_hour: int = 5             # Debate limit (economy)

    # Strategies
    task_selection: TaskSelectionStrategy = TaskSelectionStrategy.BALANCED
    allow_core_modifications: bool = False     # Affect core/ in autonomy
    require_approval_threshold: float = 0.8   # Consensus for auto-apply

    # Protected paths (never touch in Siege Mode)
    protected_paths: List[str] = field(default_factory=lambda: [
        "core/", "production/", "security/", "auth/", "secrets/"
    ])

    # Storage
    state_file: str = "data/siege_mode_state.json"
    log_file: str = "data/siege_mode_log.json"


@dataclass
class SiegeSession:
    """Current session information"""
    session_id: str
    started_at: datetime
    trigger: SiegeTrigger
    initial_autonomy_level: str
    tasks_attempted: int = 0
    tasks_completed: int = 0
    tasks_failed: int = 0
    debates_conducted: int = 0
    agents_created: int = 0
    agents_used: List[str] = field(default_factory=list)
    modules_modified: List[str] = field(default_factory=list)
    critical_decisions: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "started_at": self.started_at.isoformat(),
            "trigger": self.trigger.value,
            "initial_autonomy_level": self.initial_autonomy_level,
            "tasks_attempted": self.tasks_attempted,
            "tasks_completed": self.tasks_completed,
            "tasks_failed": self.tasks_failed,
            "debates_conducted": self.debates_conducted,
            "agents_created": self.agents_created,
            "agents_used": self.agents_used,
            "modules_modified": self.modules_modified,
            "critical_decisions": self.critical_decisions
        }


@dataclass
class VirtualCTOReport:
    """Report from "Virtual CTO" to host"""
    session: SiegeSession
    duration_hours: float
    summary: str
    achievements: List[str]
    problems_solved: List[str]
    problems_blocked: List[str]
    recommendations: List[str]
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session": self.session.to_dict(),
            "duration_hours": round(self.duration_hours, 2),
            "summary": self.summary,
            "achievements": self.achievements,
            "problems_solved": self.problems_solved,
            "problems_blocked": self.problems_blocked,
            "recommendations": self.recommendations,
            "created_at": self.created_at.isoformat()
        }


# ============================================================================
# MAIN CLASS
# ============================================================================

class SiegeMode:
    """
    Siege Mode - Full Autonomy Mode

    When host is offline > N hours, system:
    1. Activates Siege Mode
    2. Selects tasks from backlog
    3. Executes them through Debate Pipeline
    4. Creates temporary agents if needed
    5. Maintains report for host
    """

    def __init__(
        self,
        circuit_breaker,
        curator=None,
        config: Optional[SiegeConfig] = None
    ):
        """
        Initialize Siege Mode

        Args:
            circuit_breaker: CircuitBreaker instance
            curator: Optional ProjectCurator instance
            config: Optional SiegeConfig
        """
        self.circuit_breaker = circuit_breaker
        self.curator = curator
        self.config = config or SiegeConfig()

        # State
        self.state = SiegeState.INACTIVE
        self.current_session: Optional[SiegeSession] = None
        self.session_history: List[SiegeSession] = []
        self._background_task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()

        # Metrics
        self._last_human_activity = datetime.now()
        self._tasks_completed_this_session = 0

        logger.info("[SiegeMode] Initialized")

    # =========================================================================
    # STATE MANAGEMENT
    # =========================================================================

    def get_state(self) -> SiegeState:
        """Get current state"""
        return self.state

    def is_active(self) -> bool:
        """Check if Siege Mode is active"""
        return self.state == SiegeState.ACTIVE

    def should_activate(self) -> Optional[SiegeTrigger]:
        """
        Check if Siege Mode should be activated

        Returns:
            SiegeTrigger if should activate, else None
        """
        if self.state == SiegeState.ACTIVE:
            return None

        # Check via Circuit Breaker
        if self.circuit_breaker:
            from mat.circuit_breaker import AutonomyLevel
            autonomy_level = self.circuit_breaker.check_level()

            # AMBER or above - consider activation
            if autonomy_level in [AutonomyLevel.AMBER, AutonomyLevel.RED]:
                # In BLACK only monitoring
                if autonomy_level == AutonomyLevel.BLACK:
                    return None

                # Check timeout
                hours_away = self._hours_since_last_activity()
                if hours_away >= self.config.activation_timeout_hours:
                    return SiegeTrigger.TIMEOUT

                # Check backlog
                if self.curator and hasattr(self.curator, 'task_queue'):
                    pending = len(self.curator.task_queue.get_pending())
                    if pending >= 20:  # Many tasks
                        return SiegeTrigger.BACKLOG_OVERFLOW

        return None

    def _hours_since_last_activity(self) -> float:
        """Hours since last activity"""
        return (datetime.now() - self._last_human_activity).total_seconds() / 3600

    # =========================================================================
    # ACTIVATION
    # =========================================================================

    async def activate(self, trigger: SiegeTrigger = SiegeTrigger.MANUAL) -> bool:
        """
        Activate Siege Mode

        Args:
            trigger: Activation reason

        Returns:
            True if successfully activated
        """
        if self.state == SiegeState.ACTIVE:
            logger.warning("[SiegeMode] Already active")
            return False

        # Check Circuit Breaker
        if self.circuit_breaker:
            from mat.circuit_breaker import AutonomyLevel
            autonomy_level = self.circuit_breaker.check_level()
            if autonomy_level == AutonomyLevel.BLACK:
                logger.error("[SiegeMode] Cannot activate in BLACK mode")
                return False

        logger.info(f"[SiegeMode] Activating - trigger: {trigger.value}")

        # Create session
        self.current_session = SiegeSession(
            session_id=self._generate_session_id(),
            started_at=datetime.now(),
            trigger=trigger,
            initial_autonomy_level=self._get_autonomy_level() or "unknown"
        )

        # Transition to active state
        self.state = SiegeState.ACTIVE
        self._tasks_completed_this_session = 0

        # Start background task
        self._stop_event.clear()
        self._background_task = asyncio.create_task(self._run_loop())

        # Save state
        await self._save_state()

        logger.info(f"[SiegeMode] Activated - session: {self.current_session.session_id}")
        return True

    async def deactivate(self, reason: str = "manual") -> bool:
        """
        Deactivate Siege Mode

        Args:
            reason: Deactivation reason

        Returns:
            True if successfully deactivated
        """
        if self.state != SiegeState.ACTIVE:
            return False

        logger.info(f"[SiegeMode] Deactivating - reason: {reason}")

        # Stop background task
        self._stop_event.set()
        if self._background_task:
            self._background_task.cancel()
            try:
                await self._background_task
            except asyncio.CancelledError:
                pass

        # Save session to history
        if self.current_session:
            self.session_history.append(self.current_session)

        self.state = SiegeState.INACTIVE
        self.current_session = None

        # Save state
        await self._save_state()

        logger.info("[SiegeMode] Deactivated")
        return True

    # =========================================================================
    # MAIN LOOP
    # =========================================================================

    async def _run_loop(self):
        """Siege Mode main loop"""
        logger.info("[SiegeMode] Starting main loop")

        try:
            while not self._stop_event.is_set():
                # Check limits
                if self._should_pause():
                    logger.warning("[SiegeMode] Pausing - limits reached")
                    await self.deactivate("limits")
                    break

                # Check autonomy level change
                if self._check_autonomy_change():
                    logger.info("[SiegeMode] Autonomy level changed to GREEN")
                    await self.deactivate("host_returned")
                    break

                # Execute task
                await self._execute_next_task()

                # Wait before next task
                await asyncio.sleep(self.config.check_interval_minutes * 60)

        except asyncio.CancelledError:
            logger.info("[SiegeMode] Loop cancelled")
        except Exception as e:
            logger.error(f"[SiegeMode] Loop error: {e}")

    async def _execute_next_task(self):
        """Execute next task"""
        if not self.current_session:
            return

        # Check task limit
        if self._tasks_completed_this_session >= self.config.max_tasks_per_session:
            logger.info("[SiegeMode] Task limit reached")
            return

        # Get next task (requires curator)
        if not self.curator or not hasattr(self.curator, 'task_queue'):
            logger.debug("[SiegeMode] No curator/task_queue available")
            return

        task = self._select_next_task()
        if not task:
            logger.info("[SiegeMode] No tasks available")
            return

        logger.info(f"[SiegeMode] Executing task: {task.id} - {task.title}")

        self.current_session.tasks_attempted += 1

        # Execute
        try:
            result = await self._execute_task(task)

            if result.get("status") == "completed":
                self.current_session.tasks_completed += 1
                self._tasks_completed_this_session += 1

                # Record modified modules
                if "module" in result:
                    module = result["module"]
                    if module not in self.current_session.modules_modified:
                        self.current_session.modules_modified.append(module)

                logger.info(f"[SiegeMode] Task completed: {task.id}")
            else:
                self.current_session.tasks_failed += 1
                logger.warning(f"[SiegeMode] Task failed: {task.id}")

        except Exception as e:
            self.current_session.tasks_failed += 1
            logger.error(f"[SiegeMode] Task error: {e}")

        # Save state
        await self._save_state()

    def _select_next_task(self) -> Optional[Any]:
        """Select next task by strategy"""
        queue = self.curator.task_queue

        if self.config.task_selection == TaskSelectionStrategy.PRIORITY_FIRST:
            return queue.get_next()

        elif self.config.task_selection == TaskSelectionStrategy.QUICK_WINS:
            pending = queue.get_pending()
            for task in pending:
                if task.status.value == "pending" and not task.depends_on:
                    return task
            return queue.get_next()

        else:  # BALANCED
            return queue.get_next(max_priority="P2_MEDIUM")

    async def _execute_task(self, task) -> Dict[str, Any]:
        """Execute a single task"""
        # Delegate to curator if available
        if hasattr(self.curator, '_execute_task'):
            return await self.curator._execute_task(task)
        return {
            "status": "skipped",
            "reason": "Task execution not implemented"
        }

    # =========================================================================
    # HELPERS
    # =========================================================================

    def _should_pause(self) -> bool:
        """Check if should pause"""
        if not self.current_session:
            return False

        # Task limit
        if self._tasks_completed_this_session >= self.config.max_tasks_per_session:
            return True

        # Time limit
        duration = (datetime.now() - self.current_session.started_at).total_seconds() / 3600
        if duration >= self.config.max_continuous_runtime_hours:
            return True

        return False

    def _check_autonomy_change(self) -> bool:
        """Check if autonomy level changed to GREEN"""
        if not self.circuit_breaker:
            return False

        from mat.circuit_breaker import AutonomyLevel
        level = self.circuit_breaker.check_level()
        return level == AutonomyLevel.GREEN

    def _get_autonomy_level(self) -> Optional[str]:
        """Get current autonomy level"""
        if not self.circuit_breaker:
            return None
        from mat.circuit_breaker import AutonomyLevel
        level = self.circuit_breaker.check_level()
        return level.value if level else None

    def _generate_session_id(self) -> str:
        """Generate session ID"""
        return f"siege_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    # =========================================================================
    # REPORT GENERATION
    # =========================================================================

    async def generate_report(self) -> VirtualCTOReport:
        """
        Generate "Virtual CTO" report

        Returns:
            VirtualCTOReport with session results
        """
        if not self.current_session and not self.session_history:
            return VirtualCTOReport(
                session=SiegeSession(
                    session_id="none",
                    started_at=datetime.now(),
                    trigger=SiegeTrigger.MANUAL,
                    initial_autonomy_level="unknown"
                ),
                duration_hours=0,
                summary="Siege Mode was not active",
                achievements=[],
                problems_solved=[],
                problems_blocked=[],
                recommendations=[]
            )

        # Use current or last session
        session = self.current_session or self.session_history[-1]

        # Calculate duration
        if self.current_session:
            duration = (datetime.now() - session.started_at).total_seconds() / 3600
        else:
            duration = 0  # TODO: save in session

        # Generate report
        return VirtualCTOReport(
            session=session,
            duration_hours=duration,
            summary=self._generate_summary(session),
            achievements=self._generate_achievements(session),
            problems_solved=self._generate_solved(session),
            problems_blocked=self._generate_blocked(session),
            recommendations=self._generate_recommendations(session)
        )

    def _generate_summary(self, session: SiegeSession) -> str:
        """Generate summary"""
        success_rate = (
            session.tasks_completed / session.tasks_attempted * 100
            if session.tasks_attempted > 0 else 0
        )

        return (
            f"Siege Mode session {session.session_id}: "
            f"{session.tasks_completed}/{session.tasks_attempted} tasks completed "
            f"({success_rate:.0f}% success rate), "
            f"{session.debates_conducted} debates, "
            f"{session.agents_created} agents created"
        )

    def _generate_achievements(self, session: SiegeSession) -> List[str]:
        """Generate achievements list"""
        achievements = []

        if session.tasks_completed > 0:
            achievements.append(f"Completed {session.tasks_completed} tasks")

        if session.debates_conducted > 0:
            achievements.append(f"Conducted {session.debates_conducted} debates")

        if session.agents_created > 0:
            achievements.append(f"Created {session.agents_created} specialized agents")

        if session.modules_modified:
            achievements.append(f"Modified {len(session.modules_modified)} modules")

        return achievements

    def _generate_solved(self, session: SiegeSession) -> List[str]:
        """Generate solved problems list"""
        solved = []

        # From curator's decision_history
        if self.curator and hasattr(self.curator, 'decision_history'):
            for decision in self.curator.decision_history[-20:]:
                if decision.get("type") == "debate":
                    verdict = decision.get("result", {}).get("verdict", {})
                    if verdict.get("status") == "approved":
                        module = decision.get("module", "unknown")
                        solved.append(f"Approved changes for {module}")

        return solved

    def _generate_blocked(self, session: SiegeSession) -> List[str]:
        """Generate blocked problems list"""
        blocked = []

        # From curator's decision_history
        if self.curator and hasattr(self.curator, 'decision_history'):
            for decision in self.curator.decision_history[-20:]:
                if decision.get("type") == "debate":
                    verdict = decision.get("result", {}).get("verdict", {})
                    if verdict.get("status") == "rejected":
                        module = decision.get("module", "unknown")
                        reason = verdict.get("justification", "no reason")[:50]
                        blocked.append(f"Rejected {module}: {reason}...")

        return blocked

    def _generate_recommendations(self, session: SiegeSession) -> List[str]:
        """Generate recommendations"""
        recommendations = []

        # If low task completion
        if session.tasks_attempted > 0:
            success_rate = session.tasks_completed / session.tasks_attempted
            if success_rate < 0.5:
                recommendations.append(
                    "Low task success rate. Consider checking LLM settings or priorities."
                )

        # If many agents created
        if session.agents_created > 5:
            recommendations.append(
                "Many specialized agents created. Consider adding permanent roles."
            )

        # General recommendations
        if not recommendations:
            recommendations.append(
                "Siege Mode working normally. Keep it up!"
            )

        return recommendations

    # =========================================================================
    # PERSISTENCE
    # =========================================================================

    async def _save_state(self):
        """Save state"""
        try:
            state = {
                "state": self.state.value,
                "current_session": self.current_session.to_dict() if self.current_session else None,
                "last_human_activity": self._last_human_activity.isoformat(),
                "tasks_completed_this_session": self._tasks_completed_this_session
            }

            state_file = Path(self.config.state_file)
            state_file.parent.mkdir(parents=True, exist_ok=True)

            with open(state_file, 'w', encoding='utf-8') as f:
                json.dump(state, f, indent=2, ensure_ascii=False)

        except Exception as e:
            logger.error(f"[SiegeMode] Failed to save state: {e}")

    async def load_state(self):
        """Load state"""
        try:
            state_file = Path(self.config.state_file)
            if not state_file.exists():
                return

            with open(state_file, 'r', encoding='utf-8') as f:
                state = json.load(f)

            self.state = SiegeState(state.get("state", "inactive"))
            self._last_human_activity = datetime.fromisoformat(
                state.get("last_human_activity", datetime.now().isoformat())
            )
            self._tasks_completed_this_session = state.get("tasks_completed_this_session", 0)

            if state.get("current_session"):
                session_data = state["current_session"]
                self.current_session = SiegeSession(
                    session_id=session_data["session_id"],
                    started_at=datetime.fromisoformat(session_data["started_at"]),
                    trigger=SiegeTrigger(session_data["trigger"]),
                    initial_autonomy_level=session_data["initial_autonomy_level"],
                    tasks_attempted=session_data.get("tasks_attempted", 0),
                    tasks_completed=session_data.get("tasks_completed", 0),
                    tasks_failed=session_data.get("tasks_failed", 0),
                    debates_conducted=session_data.get("debates_conducted", 0),
                    agents_created=session_data.get("agents_created", 0),
                    agents_used=session_data.get("agents_used", []),
                    modules_modified=session_data.get("modules_modified", []),
                    critical_decisions=session_data.get("critical_decisions", [])
                )

        except Exception as e:
            logger.error(f"[SiegeMode] Failed to load state: {e}")

    # =========================================================================
    # ACTIVITY TRACKING
    # =========================================================================

    def record_human_activity(self):
        """Record human activity"""
        self._last_human_activity = datetime.now()
        logger.debug("[SiegeMode] Human activity recorded")


# ============================================================================
# FACTORY FUNCTION
# ============================================================================

def create_siege_mode(
    circuit_breaker,
    curator=None,
    config: Optional[SiegeConfig] = None
) -> SiegeMode:
    """
    Create Siege Mode instance

    Args:
        circuit_breaker: CircuitBreaker instance
        curator: Optional ProjectCurator instance
        config: Optional configuration

    Returns:
        SiegeMode instance
    """
    return SiegeMode(circuit_breaker, curator, config)


__all__ = [
    # Core
    "SiegeMode",
    "SiegeConfig",
    "SiegeState",
    "SiegeTrigger",
    "TaskSelectionStrategy",
    "SiegeSession",
    "VirtualCTOReport",
    # Factory
    "create_siege_mode"
]
