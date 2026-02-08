"""
MAT (Multi-Agent Team) Components for Archon AI
================================================

This package contains the security and autonomy components adapted
from Multi-Agent Team for Archon AI:

**Core Components:**
- CircuitBreaker: 4-level autonomy system (GREEN/AMBER/RED/BLACK)
- SiegeMode: Full autonomy when host is offline
- ProjectCurator: Meta-agent for project management
- DebatePipeline: Multi-agent decision making with LLM integration
- AgentScoreboard: Performance metrics for agents

**LLM Integration (Phase 3):**
- LLMRouter: Multi-provider LLM router with 14+ models
- TaskType: Automatic model selection by task type
- Support for OpenAI, Anthropic, Google, Groq, xAI, GLM, HuggingFace, Cerebras

**Agency Templates:**
- Safety-vaccinated role templates for dynamic agents
- TemplateLoader for loading and validating roles
- VaccinationSystem for ensuring agent safety
- Debate roles: Builder, Skeptic, Auditor

Usage:
    from mat import CircuitBreaker, SiegeMode, ProjectCurator, DebatePipeline, LLMRouter

    # Circuit Breaker for autonomy management
    cb = CircuitBreaker()
    level = cb.check_level()

    # Siege Mode for offline autonomy
    siege = SiegeMode(circuit_breaker=cb, curator=curator)
    await siege.activate()

    # LLM Router for multi-provider support
    router = LLMRouter(quality_preference="balanced")
    response = await router.call(messages, task_type=TaskType.CODE_GENERATION)

    # Debate Pipeline for decisions
    pipeline = DebatePipeline(llm_router=router)
    result = await pipeline.debate(code, requirements)
"""

__version__ = "0.1.0"

# Circuit Breaker (State Machine V3.0)
from mat.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerExecutor,
    AutonomyLevel,
    OperationType,
    SystemState,
    HumanActivity,
    HumanActivityDetector,
    require_autonomy_level,
    set_global_circuit_breaker,
    CanaryResult,
    CanaryDeployment,
    AlertChannel,
    ConsoleAlert,
    EmailAlert,
    TelegramAlert,
    CompositeAlert,
    setup_alerts
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

# Debate Pipeline (State Machine V3.0)
from mat.debate_pipeline import (
    DebateStateMachine as DebateStateMachine,
    DebateState,
    StateTransition,
    Artifact,
    DraftInput,
    DraftOutput,
    NormalizedOutput,
    VulnerabilityReport,
    FortifiedOutput,
    ImmutableArtifact,
    JudgmentOutcome,
    FixAssignment,
    FixOutput,
    VerifyOutput,
    ReDebateOutcome,
    CompleteOutcome,
    StagnationReport,
    GroundingResult,
    FreshEyeResult,
    SeniorAuditorDecision,
    StructuralFingerprint,
    StateContracts,
    EntropyMarker,
    DecisionTrace,
    ConsensusCalculatorV3
)

# Agent Scoreboard
from mat.agent_scoreboard import (
    Scoreboard,
    ScoreboardDashboard,
    ScoreboardIntegration,
    AgentMetrics,
    DebateOutcome,
    ScoreboardConfig,
    VerdictType as ScoreboardVerdictType,
    get_scoreboard,
    record_agent_performance,
    get_agent_metrics
)

# LLM Router (Phase 3)
try:
    from mat.llm_router import (
        LLMRouter,
        TaskType,
        LLMMessage,
        LLMResponse,
        ModelConfig
    )
    _llm_router_available = True
except ImportError:
    _llm_router_available = False

__all__ = [
    # Circuit Breaker (State Machine V3.0)
    "CircuitBreaker",
    "CircuitBreakerConfig",
    "CircuitBreakerExecutor",
    "AutonomyLevel",
    "OperationType",
    "SystemState",
    "HumanActivity",
    "HumanActivityDetector",
    "require_autonomy_level",
    "set_global_circuit_breaker",
    "CanaryResult",
    "CanaryDeployment",
    "AlertChannel",
    "ConsoleAlert",
    "EmailAlert",
    "TelegramAlert",
    "CompositeAlert",
    "setup_alerts",

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

    # Debate Pipeline (State Machine V3.0)
    "DebateStateMachine",  # Original class from multi_agent_team
    "DebatePipeline",  # Alias for DebateStateMachine (backward compatibility)
    "DebateState",
    "StateTransition",
    "Artifact",
    "DraftInput",
    "DraftOutput",
    "NormalizedOutput",
    "VulnerabilityReport",
    "FortifiedOutput",
    "ImmutableArtifact",
    "JudgmentOutcome",
    "FixAssignment",
    "FixOutput",
    "VerifyOutput",
    "ReDebateOutcome",
    "CompleteOutcome",
    "StagnationReport",
    "GroundingResult",
    "FreshEyeResult",
    "SeniorAuditorDecision",
    "StructuralFingerprint",
    "StateContracts",
    "EntropyMarker",
    "DecisionTrace",
    "ConsensusCalculatorV3",

    # Agent Scoreboard
    "Scoreboard",
    "ScoreboardDashboard",
    "ScoreboardIntegration",
    "AgentMetrics",
    "DebateOutcome",
    "ScoreboardConfig",
    "get_scoreboard",
    "record_agent_performance",
    "get_agent_metrics",

    # LLM Router (Phase 3)
    "LLMRouter",
    "TaskType",
    "LLMMessage",
    "LLMResponse",
    "ModelConfig",
]

# Backward compatibility aliases
DebatePipeline = DebateStateMachine  # Alias for existing code using DebatePipeline name
