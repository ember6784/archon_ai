"""
Agent Scoreboard - Performance Metrics for Multi-Agent Debates
=============================================================

Tracks agent performance to prevent "infinite hiring" of ineffective agents.
Implements metrics collection, analysis, and auto-actions for underperformers.

Usage:
    from mat.agent_scoreboard import Scoreboard, AgentMetrics

    scoreboard = Scoreboard()
    scoreboard.record_debate("security_expert", outcome={
        "consensus_score": 0.8,
        "tokens_used": 1500,
        "response_time": 3.2,
        "verdict": "approved"
    })

    metrics = scoreboard.get_metrics("security_expert")
    if metrics.cost_efficiency < 0.5:
        scoreboard.disable_agent("security_expert", reason="Low cost efficiency")
"""

import json
import logging
from datetime import datetime
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional, Any
from collections import deque
from enum import Enum

logger = logging.getLogger(__name__)


class VerdictType(Enum):
    """Verdict type from debates"""
    APPROVED = "approved"
    APPROVED_WITH_RISKS = "approved_with_risks"
    WARNING = "warning"
    REJECTED = "rejected"
    MANUAL_REVIEW = "manual_review"


@dataclass
class AgentMetrics:
    """
    Agent performance metrics

    Used for evaluating performance and making decisions
    about disabling ineffective agents.
    """
    agent_id: str
    template_origin: Optional[str] = None  # Which template created it

    # Debate participation
    debates_participated: int = 0
    debates_approved: int = 0
    debates_rejected: int = 0

    # Consensus (agreement with final decision)
    consensus_achieved: float = 0.0  # % agreements

    # Resources
    avg_tokens_per_debate: int = 0
    total_tokens_used: int = 0
    avg_response_time: float = 0.0  # seconds
    total_response_time: float = 0.0

    # Quality
    value_score: float = 0.5  # Score from Auditor (0-1)
    veto_rate: float = 0.0    # Veto frequency

    # Survival (for dynamic agents)
    survival_rate: float = 1.0  # How many debates "survived"

    # Efficiency
    cost_efficiency: float = 0.5  # value / cost (tokens)

    # Status
    is_active: bool = True
    disabled_reason: Optional[str] = None
    disabled_at: Optional[str] = None

    # Timestamps
    first_seen: str = field(default_factory=lambda: datetime.now().isoformat())
    last_seen: str = field(default_factory=lambda: datetime.now().isoformat())
    last_updated: str = field(default_factory=lambda: datetime.now().isoformat())

    def calculate_cost_efficiency(self) -> float:
        """Recalculate cost efficiency"""
        if self.avg_tokens_per_debate == 0:
            return 0.0

        # Efficiency = value_score / (tokens / 1000)
        token_cost = self.avg_tokens_per_debate / 1000.0
        self.cost_efficiency = self.value_score / max(token_cost, 0.1)
        return self.cost_efficiency

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentMetrics":
        """Create from dict"""
        return cls(**data)

    def update_debate(self, outcome: Dict[str, Any]) -> None:
        """
        Update metrics after debate

        Args:
            outcome: Debate result
                - consensus_score: float (0-1)
                - tokens_used: int
                - response_time: float (seconds)
                - verdict: str (VerdictType)
                - value_score: float (0-1) - optional
                - veto_applied: bool
        """
        self.debates_participated += 1
        self.last_seen = datetime.now().isoformat()

        # Consensus
        consensus = outcome.get("consensus_score", 0.5)
        self.consensus_achieved = (
            (self.consensus_achieved * (self.debates_participated - 1) + consensus)
            / self.debates_participated
        )

        # Verdict
        verdict = outcome.get("verdict", "unknown")
        if verdict in [VerdictType.APPROVED.value, VerdictType.APPROVED_WITH_RISKS.value]:
            self.debates_approved += 1
        elif verdict == VerdictType.REJECTED.value:
            self.debates_rejected += 1

        # Tokens
        tokens = outcome.get("tokens_used", 0)
        self.total_tokens_used += tokens
        self.avg_tokens_per_debate = (
            (self.avg_tokens_per_debate * (self.debates_participated - 1) + tokens)
            / self.debates_participated
        )

        # Response time
        response_time = outcome.get("response_time", 0)
        self.total_response_time += response_time
        self.avg_response_time = self.total_response_time / self.debates_participated

        # Value score
        value = outcome.get("value_score", 0.5)
        self.value_score = (
            (self.value_score * (self.debates_participated - 1) + value)
            / self.debates_participated
        )

        # Veto rate
        if outcome.get("veto_applied", False):
            self.veto_rate = (
                (self.veto_rate * (self.debates_participated - 1) + 1.0)
                / self.debates_participated
            )
        else:
            self.veto_rate = (
                (self.veto_rate * (self.debates_participated - 1))
            ) / self.debates_participated

        # Recalculate efficiency
        self.calculate_cost_efficiency()
        self.last_updated = datetime.now().isoformat()


@dataclass
class DebateOutcome:
    """Debate result for recording in Scoreboard"""
    agent_id: str
    consensus_score: float  # 0-1
    tokens_used: int
    response_time: float  # seconds
    verdict: str  # VerdictType
    value_score: float = 0.5
    veto_applied: bool = False
    debate_id: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class ScoreboardConfig:
    """Scoreboard configuration"""
    # Base directory of project (for absolute paths)
    base_dir: Optional[str] = None

    # Thresholds for auto-actions
    min_value_score: float = 0.3      # Below - agent ineffective
    min_cost_efficiency: float = 0.5   # Below - disable
    max_veto_rate: float = 0.5         # Above - retrain or remove
    min_debates_for_evaluation: int = 5  # Min debates for evaluation

    # Storage (relative to base_dir or absolute)
    metrics_file: str = "data/agent_scoreboard.json"
    history_file: str = "data/agent_metrics_history.jsonl"

    # Auto-actions
    auto_disable_low_performers: bool = True
    auto_flag_for_retraining: bool = True

    def get_absolute_path(self, relative_path: str) -> str:
        """Convert relative path to absolute"""
        path = Path(relative_path)
        if path.is_absolute():
            return str(path)

        if self.base_dir:
            base = Path(self.base_dir)
        else:
            base = Path(__file__).parent.parent

        return str(base / path)


class Scoreboard:
    """
    Scoreboard for tracking agent performance

    Functions:
    - Record metrics after each debate
    - Analyze performance
    - Auto-disable ineffective agents
    - Metrics history for charts
    """

    def __init__(self, config: Optional[ScoreboardConfig] = None):
        self.config = config or ScoreboardConfig()
        self._metrics: Dict[str, AgentMetrics] = {}
        self._history: deque = deque(maxlen=10000)  # History of all entries

        # Load saved metrics
        self._load_metrics()
        self._load_history()

        logger.info(f"Scoreboard initialized with {len(self._metrics)} agents")

    def record_debate(self, agent_id: str, outcome: Dict[str, Any]) -> AgentMetrics:
        """
        Record debate results for agent

        Args:
            agent_id: Agent ID
            outcome: Debate result dict

        Returns:
            Updated agent metrics
        """
        # Create metrics if not exists
        if agent_id not in self._metrics:
            self._metrics[agent_id] = AgentMetrics(agent_id=agent_id)

        # Update metrics
        metrics = self._metrics[agent_id]
        metrics.update_debate(outcome)

        # Record to history
        self._history.append({
            "timestamp": datetime.now().isoformat(),
            "agent_id": agent_id,
            "outcome": outcome,
            "metrics_snapshot": {
                "debates_participated": metrics.debates_participated,
                "value_score": metrics.value_score,
                "cost_efficiency": metrics.cost_efficiency
            }
        })

        # Check thresholds (auto-actions)
        if metrics.debates_participated >= self.config.min_debates_for_evaluation:
            self._check_auto_actions(agent_id, metrics)

        # Save
        self._save_metrics()
        self._save_history()

        return metrics

    def record_debate_batch(self, outcomes: List[Dict[str, Any]]) -> Dict[str, AgentMetrics]:
        """
        Record results for multiple agents from one debate

        Args:
            outcomes: List of results for each agent

        Returns:
            Dict agent_id -> metrics
        """
        results = {}
        for outcome in outcomes:
            agent_id = outcome.get("agent_id")
            if agent_id:
                results[agent_id] = self.record_debate(agent_id, outcome)

        return results

    def get_metrics(self, agent_id: str) -> Optional[AgentMetrics]:
        """Get agent metrics"""
        return self._metrics.get(agent_id)

    def get_all_metrics(self) -> Dict[str, AgentMetrics]:
        """Get all agent metrics"""
        return self._metrics.copy()

    def get_top_performers(self, limit: int = 5, metric: str = "cost_efficiency") -> List[AgentMetrics]:
        """
        Get top performers

        Args:
            limit: Number of results
            metric: Metric for sorting (cost_efficiency, value_score, consensus_achieved)

        Returns:
            List of best agents
        """
        active = [m for m in self._metrics.values() if m.is_active]
        sorted_metrics = sorted(
            active,
            key=lambda m: getattr(m, metric, 0),
            reverse=True
        )
        return sorted_metrics[:limit]

    def get_underperformers(self, threshold: float = 0.3) -> List[AgentMetrics]:
        """
        Get ineffective agents

        Args:
            threshold: Value score threshold

        Returns:
            List of agents with value_score below threshold
        """
        return [
            m for m in self._metrics.values()
            if m.is_active and m.value_score < threshold
            and m.debates_participated >= self.config.min_debates_for_evaluation
        ]

    def disable_agent(self, agent_id: str, reason: str) -> None:
        """
        Disable agent

        Args:
            agent_id: Agent ID
            reason: Disable reason
        """
        if agent_id in self._metrics:
            metrics = self._metrics[agent_id]
            metrics.is_active = False
            metrics.disabled_reason = reason
            metrics.disabled_at = datetime.now().isoformat()

            logger.info(f"Disabled agent {agent_id}: {reason}")
            self._save_metrics()

    def enable_agent(self, agent_id: str) -> None:
        """Re-enable agent"""
        if agent_id in self._metrics:
            metrics = self._metrics[agent_id]
            metrics.is_active = True
            metrics.disabled_reason = None
            metrics.disabled_at = None

            logger.info(f"Re-enabled agent {agent_id}")
            self._save_metrics()

    def get_statistics(self) -> Dict[str, Any]:
        """Get general statistics"""
        all_metrics = list(self._metrics.values())
        active = [m for m in all_metrics if m.is_active]

        if not active:
            return {
                "total_agents": len(all_metrics),
                "active_agents": 0,
                "disabled_agents": len(all_metrics),
            }

        return {
            "total_agents": len(all_metrics),
            "active_agents": len(active),
            "disabled_agents": len(all_metrics) - len(active),
            "avg_value_score": sum(m.value_score for m in active) / len(active),
            "avg_cost_efficiency": sum(m.cost_efficiency for m in active) / len(active),
            "avg_tokens_per_debate": sum(m.avg_tokens_per_debate for m in active) / len(active),
            "total_debates_recorded": sum(m.debates_participated for m in all_metrics),
            "total_tokens_used": sum(m.total_tokens_used for m in all_metrics),
        }

    def _check_auto_actions(self, agent_id: str, metrics: AgentMetrics) -> None:
        """Check and execute auto-actions"""
        if not self.config.auto_disable_low_performers:
            return

        # Low efficiency - disable
        if metrics.cost_efficiency < self.config.min_cost_efficiency:
            self.disable_agent(
                agent_id,
                reason=f"Low cost efficiency: {metrics.cost_efficiency:.2f} < {self.config.min_cost_efficiency}"
            )
            return

        # Low value score - disable
        if metrics.value_score < self.config.min_value_score:
            self.disable_agent(
                agent_id,
                reason=f"Low value score: {metrics.value_score:.2f} < {self.config.min_value_score}"
            )
            return

        # High veto rate - flag for retraining
        if metrics.veto_rate > self.config.max_veto_rate:
            logger.warning(
                f"Agent {agent_id} has high veto rate: {metrics.veto_rate:.2f}. "
                f"Consider retraining."
            )

    def _save_metrics(self) -> None:
        """Save metrics to file"""
        path = Path(self.config.get_absolute_path(self.config.metrics_file))
        path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            agent_id: metrics.to_dict()
            for agent_id, metrics in self._metrics.items()
        }

        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _load_metrics(self) -> None:
        """Load metrics from file"""
        path = Path(self.config.get_absolute_path(self.config.metrics_file))
        if not path.exists():
            return

        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            for agent_id, metrics_data in data.items():
                self._metrics[agent_id] = AgentMetrics.from_dict(metrics_data)

            logger.info(f"Loaded metrics for {len(self._metrics)} agents")
        except Exception as e:
            logger.error(f"Failed to load metrics: {e}")

    def _save_history(self) -> None:
        """Save history to file"""
        path = Path(self.config.get_absolute_path(self.config.history_file))
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, 'a', encoding='utf-8') as f:
            for entry in list(self._history)[-100:]:  # Last 100
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')

    def _load_history(self) -> None:
        """Load history from file"""
        path = Path(self.config.get_absolute_path(self.config.history_file))
        if not path.exists():
            return

        try:
            with open(path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        self._history.append(json.loads(line))

            logger.info(f"Loaded {len(self._history)} history entries")
        except Exception as e:
            logger.error(f"Failed to load history: {e}")


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

_global_scoreboard: Optional[Scoreboard] = None


def get_scoreboard() -> Scoreboard:
    """Get global Scoreboard"""
    global _global_scoreboard
    if _global_scoreboard is None:
        _global_scoreboard = Scoreboard()
    return _global_scoreboard


def record_agent_performance(agent_id: str, outcome: Dict[str, Any]) -> AgentMetrics:
    """Record agent performance"""
    scoreboard = get_scoreboard()
    return scoreboard.record_debate(agent_id, outcome)


def get_agent_metrics(agent_id: str) -> Optional[AgentMetrics]:
    """Get agent metrics"""
    scoreboard = get_scoreboard()
    return scoreboard.get_metrics(agent_id)


__all__ = [
    # Core
    "AgentMetrics",
    "DebateOutcome",
    "ScoreboardConfig",
    "Scoreboard",
    "VerdictType",
    # Convenience
    "get_scoreboard",
    "record_agent_performance",
    "get_agent_metrics"
]
