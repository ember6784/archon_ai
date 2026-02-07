"""
MAT (Multi-Agent Team) Components for Archon AI
================================================

This package contains the security and autonomy components adapted
from Multi-Agent Team for Archon AI:

**Core Components:**
- CircuitBreaker: 4-level autonomy system (GREEN/AMBER/RED/BLACK)
- SiegeMode: Full autonomy when host is offline
- ProjectCurator: Meta-agent for project management
- DebatePipeline: Multi-agent decision making
- AgentScoreboard: Performance metrics for agents

**Agency Templates:**
- Safety-vaccinated role templates for dynamic agents
- TemplateLoader for loading and validating roles
- VaccinationSystem for ensuring agent safety

Usage:
    from mat import CircuitBreaker, SiegeMode, ProjectCurator, DebatePipeline

    # Circuit Breaker for autonomy management
    cb = CircuitBreaker()
    level = cb.check_level()

    # Siege Mode for offline autonomy
    siege = SiegeMode(circuit_breaker=cb, curator=curator)
    await siege.activate()

    # Debate Pipeline for decisions
    pipeline = DebatePipeline()
    result = await pipeline.debate(code, requirements)
"""

__version__ = "0.1.0"

# Circuit Breaker
from mat.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    AutonomyLevel,
    OperationType,
    SystemState,
    HumanActivity,
    require_autonomy_level,
    set_global_circuit_breaker
)

# Siege Mode
from mat.siege_mode import (
    SiegeMode,
    SiegeConfig,
    SiegeState,
    SiegeTrigger,
    TaskSelectionStrategy,
    SiegeSession,
    VirtualCTOReport,
    create_siege_mode
)

# Project Curator
from mat.project_curator import (
    ProjectCurator,
    CuratorDecision,
    CuratorRecommendation,
    WorkPlan,
    Task,
    TaskQueue,
    create_project_curator
)

# Debate Pipeline
from mat.debate_pipeline import (
    DebatePipeline,
    DebatePhase,
    DebateState,
    DebateResult,
    VerdictType
)

# Agent Scoreboard
from mat.agent_scoreboard import (
    Scoreboard,
    AgentMetrics,
    DebateOutcome,
    ScoreboardConfig,
    VerdictType as ScoreboardVerdictType,
    get_scoreboard,
    record_agent_performance,
    get_agent_metrics
)

__all__ = [
    # Circuit Breaker
    "CircuitBreaker",
    "CircuitBreakerConfig",
    "AutonomyLevel",
    "OperationType",
    "SystemState",
    "HumanActivity",
    "require_autonomy_level",
    "set_global_circuit_breaker",

    # Siege Mode
    "SiegeMode",
    "SiegeConfig",
    "SiegeState",
    "SiegeTrigger",
    "TaskSelectionStrategy",
    "SiegeSession",
    "VirtualCTOReport",
    "create_siege_mode",

    # Project Curator
    "ProjectCurator",
    "CuratorDecision",
    "CuratorRecommendation",
    "WorkPlan",
    "Task",
    "TaskQueue",
    "create_project_curator",

    # Debate Pipeline
    "DebatePipeline",
    "DebatePhase",
    "DebateState",
    "DebateResult",
    "VerdictType",

    # Agent Scoreboard
    "Scoreboard",
    "AgentMetrics",
    "DebateOutcome",
    "ScoreboardConfig",
    "get_scoreboard",
    "record_agent_performance",
    "get_agent_metrics",
]
