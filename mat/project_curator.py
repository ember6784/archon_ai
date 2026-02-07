"""
Project Curator - Chief Architect
=================================

From Text Document.txt:
> "Chief Architect (Project Curator) is above the debate pipeline.
> He doesn't write code. He watches the Project Map and ReflectiveMemory.
>
> Why he's needed: While Builder and Skeptic argue about a 10-line function,
> the Architect sees that the entire module is obsolete. He makes the decision:
> 'This file is too bloated, pipeline, instead of refactoring — split it into three parts.'
>
> Autonomy: He can plan tasks ahead. You go online, draft 10 ideas,
> and the Architect himself queues the debates and runs them by priority."

**Functions:**
1. Analyze Project Map (index + dependencies)
2. Integration with ReflectiveMemory (lessons from past debates)
3. Plan tasks ahead (backlog -> priority queue)
4. Select agents from agency_templates/roles/
5. Make architectural decisions (split/merge/refactor)
6. Human-in-the-loop for critical changes

This is a simplified version adapted for Archon AI.
"""

from __future__ import annotations
import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Set, Optional, Any
from enum import Enum
import json

logger = logging.getLogger(__name__)


class CuratorDecision(Enum):
    """Curator decision types"""
    PROCEED = "proceed"           # Proceed as is
    MODIFY = "modify"           # Change approach
    SPLIT = "split"              # Split task
    ESCALATE = "escalate"        # Escalate to human
    BLOCK = "block"              # Block (dangerous)


@dataclass
class CuratorRecommendation:
    """Curator recommendation"""
    decision: CuratorDecision
    reason: str
    suggested_agents: List[str] = field(default_factory=list)
    architectural_changes: Optional[Dict[str, Any]] = None
    requires_human_approval: bool = False


@dataclass
class Task:
    """Task in the queue"""
    id: str
    task_type: str
    title: str
    priority: str
    target_module: Optional[str] = None
    description: Optional[str] = None
    depends_on: List[str] = field(default_factory=list)
    status: str = "pending"
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "task_type": self.task_type,
            "title": self.title,
            "priority": self.priority,
            "target_module": self.target_module,
            "description": self.description,
            "depends_on": self.depends_on,
            "status": self.status,
            "metadata": self.metadata,
            "created_at": self.created_at
        }


@dataclass
class WorkPlan:
    """Work plan (set of tasks)"""
    id: str
    created_at: str
    title: str
    description: str
    tasks: List[Task]
    total_estimated_duration: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "created_at": self.created_at,
            "title": self.title,
            "description": self.description,
            "tasks": [t.to_dict() for t in self.tasks],
            "total_estimated_duration": self.total_estimated_duration,
            "task_count": len(self.tasks)
        }


class TaskQueue:
    """Simple task queue for Project Curator"""

    def __init__(self, storage_path: Optional[Path] = None):
        self.storage_path = storage_path or Path("data/task_queue.json")
        self.tasks: Dict[str, Task] = {}
        self._load()

    def add(
        self,
        task_type: str,
        title: str,
        priority: str,
        target_module: Optional[str] = None,
        description: Optional[str] = None,
        depends_on: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Task:
        """Add a task to the queue"""
        task_id = f"task_{int(datetime.now().timestamp() * 1000)}"
        task = Task(
            id=task_id,
            task_type=task_type,
            title=title,
            priority=priority,
            target_module=target_module,
            description=description,
            depends_on=depends_on or [],
            metadata=metadata or {}
        )
        self.tasks[task_id] = task
        self._save()
        return task

    def get(self, task_id: str) -> Optional[Task]:
        """Get task by ID"""
        return self.tasks.get(task_id)

    def get_next(self, max_priority: Optional[str] = None) -> Optional[Task]:
        """Get next pending task by priority"""
        priority_order = ["P0_CRITICAL", "P1_HIGH", "P2_MEDIUM", "P3_LOW"]
        pending = [t for t in self.tasks.values() if t.status == "pending"]

        for priority in priority_order:
            if max_priority and priority_order.index(priority) > priority_order.index(max_priority):
                continue
            for task in pending:
                if task.priority == priority:
                    # Check if dependencies are met
                    if all(self.tasks.get(dep, Task(id="", task_type="", title="", priority="")).status == "completed" for dep in task.depends_on):
                        return task
        return None

    def get_pending(self) -> List[Task]:
        """Get all pending tasks"""
        return [t for t in self.tasks.values() if t.status == "pending"]

    def update_status(self, task_id: str, status: str) -> None:
        """Update task status"""
        if task_id in self.tasks:
            self.tasks[task_id].status = status
            self._save()

    def get_stats(self) -> Dict[str, Any]:
        """Get queue statistics"""
        statuses = {}
        for task in self.tasks.values():
            statuses[task.status] = statuses.get(task.status, 0) + 1
        return {
            "total": len(self.tasks),
            "by_status": statuses
        }

    def _save(self) -> None:
        """Save to file"""
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.storage_path, 'w', encoding='utf-8') as f:
            json.dump({k: t.to_dict() for k, t in self.tasks.items()}, f, indent=2)

    def _load(self) -> None:
        """Load from file"""
        if not self.storage_path.exists():
            return
        try:
            with open(self.storage_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            for task_id, task_data in data.items():
                self.tasks[task_id] = Task(**task_data)
        except Exception as e:
            logger.error(f"Failed to load task queue: {e}")


class ProjectCurator:
    """
    Chief Architect - top-level agent

    Located above the debate pipeline and manages the entire
    autonomous development process.

    **Main Functions:**
    1. Analyze modules and recommend approaches
    2. Plan tasks through TaskQueue
    3. Select appropriate agents from agency_templates/
    4. Make architectural decisions
    5. Integration with Circuit Breaker for autonomy checks
    """

    def __init__(
        self,
        project_root: str | Path,
        storage_path: Optional[Path] = None,
        circuit_breaker=None
    ):
        self.project_root = Path(project_root)

        # Determine storage path
        if storage_path is None:
            storage_path = self.project_root / "data"

        # Components
        self.task_queue = TaskQueue(storage_path / "task_queue.json")
        self.circuit_breaker = circuit_breaker

        # Decision history
        self.decision_history: List[Dict[str, Any]] = []

        # Critical paths (protected from changes)
        self._protected_paths = ["core/", "production/", "security/", "auth/"]

        logger.info(f"[ProjectCurator] Initialized for {self.project_root}")

    async def initialize(self) -> None:
        """Initialize curator"""
        logger.info("[ProjectCurator] Initializing...")
        logger.info("[ProjectCurator] Ready")

    async def analyze_module(
        self,
        module_path: str,
        requirements: str
    ) -> CuratorRecommendation:
        """
        Analyze task and give recommendation

        From Text Document.txt:
        > "While Builder and Skeptic argue about a 10-line function,
        > the Architect sees that the entire module is obsolete"

        With Circuit Breaker integration:
        > "Curator should not do SPLIT/MERGE in RED/BLACK mode"
        > "core/ and production/ are protected from changes in AMBER+"
        """
        module_name = str(module_path).replace('\\', '/').replace('.py', '')

        # Circuit Breaker Check
        autonomy_level = None
        if self.circuit_breaker:
            from mat.circuit_breaker import AutonomyLevel
            autonomy_level = self.circuit_breaker.check_level()
            logger.info(f"[ProjectCurator] Current autonomy level: {autonomy_level.value if autonomy_level else 'N/A'}")

            # BLACK mode - only read and monitor
            if autonomy_level == AutonomyLevel.BLACK:
                return CuratorRecommendation(
                    decision=CuratorDecision.BLOCK,
                    reason=f"System in BLACK mode - only monitoring allowed",
                    suggested_agents=[],
                    requires_human_approval=True
                )

        # Protected Paths Check
        is_protected = any(
            module_name.startswith(path) or f"/{path}" in module_name
            for path in self._protected_paths
        )

        if is_protected and autonomy_level:
            # In AMBER and higher - protected paths require approval
            if autonomy_level != AutonomyLevel.GREEN:
                return CuratorRecommendation(
                    decision=CuratorDecision.ESCALATE,
                    reason=f"Module '{module_name}' is in protected path. Requires human approval in {autonomy_level.value} mode.",
                    suggested_agents=["security_expert", "auditor"],
                    requires_human_approval=True
                )

        # Select agents
        agents = self._select_agents_for_task(module_name, requirements)

        return CuratorRecommendation(
            decision=CuratorDecision.PROCEED,
            reason="Module looks good for processing",
            suggested_agents=agents,
            requires_human_approval=False
        )

    def _select_agents_for_task(
        self,
        module_path: str,
        requirements: str
    ) -> List[str]:
        """Select agents from agency_templates/"""
        requirements_lower = requirements.lower()
        agents = []

        # Domain-specific selection
        if any(term in requirements_lower for term in [
            "security", "vulnerability", "attack", "injection", "auth"
        ]):
            agents.append("security_expert")

        if any(term in requirements_lower for term in [
            "performance", "speed", "optimization", "latency", "memory"
        ]):
            agents.append("performance_guru")

        if any(term in requirements_lower for term in [
            "database", "sql", "query", "migration", "schema"
        ]):
            agents.append("database_architect")

        if any(term in requirements_lower for term in [
            "ux", "ui", "interface", "user experience", "design"
        ]):
            agents.append("ux_researcher")

        if any(term in requirements_lower for term in [
            "deploy", "docker", "kubernetes", "ci/cd", "infrastructure"
        ]):
            agents.append("devops_engineer")

        # Always add base agents
        if not agents:
            agents = ["builder", "skeptic", "auditor"]
        elif "builder" not in agents:
            agents.append("builder")
        if "skeptic" not in agents:
            agents.append("skeptic")
        if "auditor" not in agents:
            agents.append("auditor")

        return agents

    async def plan_work(
        self,
        goal: str,
        modules: Optional[List[str]] = None,
        priority: str = "P2_MEDIUM"
    ) -> WorkPlan:
        """
        Create work plan

        From Text Document.txt:
        > "You go online, draft 10 ideas, and the Architect himself
        > queues the debates and runs them by priority"
        """
        tasks = []

        # If modules specified - create tasks for them
        if modules:
            for module in modules:
                task = self.task_queue.add(
                    task_type="ANALYZE",
                    title=f"Analyze {module}",
                    priority=priority,
                    target_module=module,
                    description=f"Analysis task for {module}"
                )
                tasks.append(task)

        # Calculate total duration
        total_duration = sum(t.estimated_duration if hasattr(t, 'estimated_duration') else 1.0 for t in tasks)

        plan = WorkPlan(
            id=f"plan_{int(datetime.now().timestamp())}",
            created_at=datetime.now().isoformat(),
            title=goal,
            description=f"Auto-generated plan with {len(tasks)} tasks",
            tasks=tasks,
            total_estimated_duration=total_duration
        )

        logger.info(f"[ProjectCurator] Created plan: {plan.id} with {len(tasks)} tasks")
        return plan

    async def execute_plan(
        self,
        plan: WorkPlan,
        auto_approve: bool = False
    ) -> Dict[str, Any]:
        """
        Execute plan

        Args:
            auto_approve: Auto-approve tasks (no HITL)
        """
        results = {
            "plan_id": plan.id,
            "total_tasks": len(plan.tasks),
            "completed": 0,
            "failed": 0,
            "blocked": 0,
            "results": []
        }

        for task in plan.tasks:
            # Check if human approval needed
            if not auto_approve and task.priority in ["P0_CRITICAL", "P1_HIGH"]:
                logger.warning(f"[ProjectCurator] Task requires approval: {task.id}")
                results["blocked"] += 1
                results["results"].append({
                    "task_id": task.id,
                    "status": "blocked",
                    "reason": "Requires human approval"
                })
                continue

            # Execute task
            try:
                result = await self._execute_task(task)
                results["completed"] += 1
                results["results"].append({
                    "task_id": task.id,
                    "status": "completed",
                    "result": result
                })
            except Exception as e:
                logger.error(f"[ProjectCurator] Task failed: {task.id} - {e}")
                results["failed"] += 1
                results["results"].append({
                    "task_id": task.id,
                    "status": "failed",
                    "error": str(e)
                })

        return results

    async def _execute_task(self, task: Task) -> Dict[str, Any]:
        """Execute single task"""
        logger.info(f"[ProjectCurator] Executing task: {task.id}")

        if task.task_type == "ANALYZE":
            return await self._analyze_task(task)
        elif task.task_type == "DEBATE":
            return await self._debate_task(task)
        else:
            return {"status": "skipped", "reason": "Task type not implemented"}

    async def _analyze_task(self, task: Task) -> Dict[str, Any]:
        """Execute analysis task"""
        module = task.target_module
        return {
            "module": module,
            "status": "analyzed",
            "task_id": task.id
        }

    async def _debate_task(self, task: Task) -> Dict[str, Any]:
        """Execute debate task"""
        # This would integrate with DebatePipeline
        # For now, return a placeholder
        return {
            "status": "pending",
            "reason": "Debate integration pending",
            "task_id": task.id
        }

    # Circuit Breaker Integration

    def get_autonomy_level(self) -> Optional[str]:
        """Get current autonomy level"""
        if not self.circuit_breaker:
            return None
        from mat.circuit_breaker import AutonomyLevel
        level = self.circuit_breaker.check_level()
        return level.value if level else None

    def can_execute_operation(self, operation_type: str) -> bool:
        """
        Check if operation can be executed

        Args:
            operation_type: "modify_core", "architecture_change", "deploy_production", etc.

        Returns:
            True if operation allowed
        """
        if not self.circuit_breaker:
            return True

        from mat.circuit_breaker import OperationType
        try:
            operation = OperationType[operation_type.upper()]
            return self.circuit_breaker.can_execute(operation)
        except KeyError:
            logger.warning(f"[ProjectCurator] Unknown operation type: {operation_type}")
            return False

    def record_human_activity(self, action: str = "curator_interaction") -> None:
        """
        Record human activity (reset countdown for Circuit Breaker)

        Args:
            action: Action description
        """
        if self.circuit_breaker:
            self.circuit_breaker.record_human_activity(action)
            logger.info(f"[ProjectCurator] Human activity recorded: {action}")

    def get_status_report(self) -> Dict[str, Any]:
        """Get system status"""
        # Get current autonomy level
        autonomy_level = None
        if self.circuit_breaker:
            from mat.circuit_breaker import AutonomyLevel
            autonomy_level = self.circuit_breaker.check_level()

        return {
            "project_root": str(self.project_root),
            "tasks_in_queue": len(self.task_queue.tasks),
            "pending_tasks": len(self.task_queue.get_pending()),
            "decision_history_count": len(self.decision_history),
            "autonomy_level": autonomy_level.value if autonomy_level else None,
            "protected_paths": self._protected_paths
        }

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict"""
        return {
            "project_root": str(self.project_root),
            "task_queue": {
                "stats": self.task_queue.get_stats(),
                "pending": len(self.task_queue.get_pending())
            },
            "circuit_breaker_available": self.circuit_breaker is not None
        }


def create_project_curator(
    project_root: str | Path,
    storage_path: Optional[Path] = None,
    circuit_breaker=None
) -> ProjectCurator:
    """Factory function for creating Project Curator"""
    return ProjectCurator(project_root, storage_path, circuit_breaker)


__all__ = [
    # Core
    "ProjectCurator",
    "CuratorDecision",
    "CuratorRecommendation",
    "WorkPlan",
    "Task",
    "TaskQueue",
    # Factory
    "create_project_curator"
]
