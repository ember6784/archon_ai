"""
Agent Scoreboard - Performance Metrics for Multi-Agent Debates
=============================================================

Tracks agent performance to prevent "infinite hiring" of ineffective agents.
Implements metrics collection, analysis, and auto-actions for underperformers.

Usage:
    from agent_scoreboard import Scoreboard, AgentMetrics

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
import time
import logging
from datetime import datetime, timedelta
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional, Any
from collections import deque
from enum import Enum

logger = logging.getLogger(__name__)


class VerdictType(Enum):
    """Тип вердикта из дебатов"""
    APPROVED = "approved"
    APPROVED_WITH_RISKS = "approved_with_risks"
    WARNING = "warning"
    REJECTED = "rejected"
    MANUAL_REVIEW = "manual_review"


@dataclass
class AgentMetrics:
    """
    Метрики эффективности агента

    Используется для оценки производительности и принятия решений
    об отключении неэффективных агентов.
    """
    agent_id: str
    template_origin: Optional[str] = None  # Из какого шаблона создан

    # Участие в дебатах
    debates_participated: int = 0
    debates_approved: int = 0
    debates_rejected: int = 0

    # Консенсус (согласие с финальным решением)
    consensus_achieved: float = 0.0  # % согласий

    # Ресурсы
    avg_tokens_per_debate: int = 0
    total_tokens_used: int = 0
    avg_response_time: float = 0.0  # секунды
    total_response_time: float = 0.0

    # Качество
    value_score: float = 0.5  # Оценка от Auditor'а (0-1)
    veto_rate: float = 0.0    # Частота наложенного вето

    # Выживаемость (для динамических агентов)
    survival_rate: float = 1.0  # Сколько дебатов "выжил"

    # Эффективность
    cost_efficiency: float = 0.5  # value / cost (токены)

    # Статус
    is_active: bool = True
    disabled_reason: Optional[str] = None
    disabled_at: Optional[str] = None

    # Временные метки
    first_seen: str = field(default_factory=lambda: datetime.now().isoformat())
    last_seen: str = field(default_factory=lambda: datetime.now().isoformat())
    last_updated: str = field(default_factory=lambda: datetime.now().isoformat())

    def calculate_cost_efficiency(self) -> float:
        """Пересчитать cost efficiency"""
        if self.avg_tokens_per_debate == 0:
            return 0.0

        # Эффективность = value_score / (tokens / 1000)
        token_cost = self.avg_tokens_per_debate / 1000.0
        self.cost_efficiency = self.value_score / max(token_cost, 0.1)
        return self.cost_efficiency

    def to_dict(self) -> Dict[str, Any]:
        """Конвертировать в словарь"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentMetrics":
        """Создать из словаря"""
        return cls(**data)

    def update_debate(self, outcome: Dict[str, Any]) -> None:
        """
        Обновить метрики после дебата

        Args:
            outcome: Результат дебата
                - consensus_score: float (0-1)
                - tokens_used: int
                - response_time: float (seconds)
                - verdict: str (VerdictType)
                - value_score: float (0-1) - optional
                - veto_applied: bool
        """
        self.debates_participated += 1
        self.last_seen = datetime.now().isoformat()

        # Консенсус
        consensus = outcome.get("consensus_score", 0.5)
        self.consensus_achieved = (
            (self.consensus_achieved * (self.debates_participated - 1) + consensus)
            / self.debates_participated
        )

        # Верdict
        verdict = outcome.get("verdict", "unknown")
        if verdict in [VerdictType.APPROVED.value, VerdictType.APPROVED_WITH_RISKS.value]:
            self.debates_approved += 1
        elif verdict == VerdictType.REJECTED.value:
            self.debates_rejected += 1

        # Токены
        tokens = outcome.get("tokens_used", 0)
        self.total_tokens_used += tokens
        self.avg_tokens_per_debate = (
            (self.avg_tokens_per_debate * (self.debates_participated - 1) + tokens)
            / self.debates_participated
        )

        # Время ответа
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
                self.veto_rate * (self.debates_participated - 1)
            ) / self.debates_participated

        # Пересчитаем эффективность
        self.calculate_cost_efficiency()
        self.last_updated = datetime.now().isoformat()


@dataclass
class DebateOutcome:
    """Результат дебата для записи в Scoreboard"""
    agent_id: str
    consensus_score: float  # 0-1
    tokens_used: int
    response_time: float  # секунды
    verdict: str  # VerdictType
    value_score: float = 0.5
    veto_applied: bool = False
    debate_id: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class ScoreboardConfig:
    """Конфигурация Scoreboard"""
    # Базовая директория проекта (для абсолютных путей)
    base_dir: Optional[str] = None  # Если None - определяется автоматически

    # Пороги для авто-действий
    min_value_score: float = 0.3      # Ниже - агент неэффективен
    min_cost_efficiency: float = 0.5   # Ниже - отключить
    max_veto_rate: float = 0.5         # Выше - переобучить или удалить
    min_debates_for_evaluation: int = 5  # Минимум дебатов для оценки

    # Хранение (относительные base_dir или абсолютные)
    metrics_file: str = "memory/agent_scoreboard.json"
    history_file: str = "memory/agent_metrics_history.jsonl"

    # Авто-действия
    auto_disable_low_performers: bool = True
    auto_flag_for_retraining: bool = True

    def get_absolute_path(self, relative_path: str) -> str:
        """
        Преобразовать относительный путь в абсолютный

        Args:
            relative_path: Относительный или абсолютный путь

        Returns:
            Абсолютный путь
        """
        path = Path(relative_path)
        if path.is_absolute():
            return str(path)

        # Определяем base_dir
        if self.base_dir:
            base = Path(self.base_dir)
        else:
            # Определяем автоматически от расположения этого файла
            base = Path(__file__).parent

        return str(base / path)


class Scoreboard:
    """
    Scoreboard для отслеживания производительности агентов

    Функции:
    - Запись метрик после каждого дебата
    - Анализ производительности
    - Авто-отключение неэффективных агентов
    - История метрик для графиков
    """

    def __init__(self, config: Optional[ScoreboardConfig] = None):
        self.config = config or ScoreboardConfig()
        self._metrics: Dict[str, AgentMetrics] = {}
        self._history: deque = deque(maxlen=10000)  # История всех записей

        # Загружаем сохранённые метрики
        self._load_metrics()
        self._load_history()

        logger.info(f"Scoreboard initialized with {len(self._metrics)} agents")

    def record_debate(self, agent_id: str, outcome: Dict[str, Any]) -> AgentMetrics:
        """
        Записать результаты дебата для агента

        Args:
            agent_id: ID агента
            outcome: Словарь с результатами дебата

        Returns:
            Обновлённые метрики агента
        """
        # Создаём метрики если нет
        if agent_id not in self._metrics:
            self._metrics[agent_id] = AgentMetrics(agent_id=agent_id)

        # Обновляем метрики
        metrics = self._metrics[agent_id]
        metrics.update_debate(outcome)

        # Записываем в историю
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

        # Проверяем пороги (авто-действия)
        if metrics.debates_participated >= self.config.min_debates_for_evaluation:
            self._check_auto_actions(agent_id, metrics)

        # Сохраняем
        self._save_metrics()
        self._save_history()

        return metrics

    def record_debate_batch(self, outcomes: List[Dict[str, Any]]) -> Dict[str, AgentMetrics]:
        """
        Записать результаты нескольких агентов из одного дебата

        Args:
            outcomes: Список результатов для каждого агента

        Returns:
            Словарь agent_id -> метрики
        """
        results = {}
        for outcome in outcomes:
            agent_id = outcome.get("agent_id")
            if agent_id:
                results[agent_id] = self.record_debate(agent_id, outcome)

        return results

    def get_metrics(self, agent_id: str) -> Optional[AgentMetrics]:
        """Получить метрики агента"""
        return self._metrics.get(agent_id)

    def get_all_metrics(self) -> Dict[str, AgentMetrics]:
        """Получить метрики всех агентов"""
        return self._metrics.copy()

    def get_top_performers(self, limit: int = 5, metric: str = "cost_efficiency") -> List[AgentMetrics]:
        """
        Получить топ performers

        Args:
            limit: Количество результатов
            metric: Метрика для сортировки (cost_efficiency, value_score, consensus_achieved)

        Returns:
            Список лучших агентов
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
        Получить неэффективных агентов

        Args:
            threshold: Порог value_score

        Returns:
            Список агентов с value_score ниже порога
        """
        return [
            m for m in self._metrics.values()
            if m.is_active and m.value_score < threshold
            and m.debates_participated >= self.config.min_debates_for_evaluation
        ]

    def flag_underperformers(self, threshold: float = 0.3) -> List[str]:
        """
        Пометить неэффективных агентов для отключения

        Args:
            threshold: Порог value_score

        Returns:
            Список ID помеченных агентов
        """
        flagged = []

        for metrics in self.get_underperformers(threshold):
            self.disable_agent(
                metrics.agent_id,
                reason=f"Low value score: {metrics.value_score:.2f} < {threshold}"
            )
            flagged.append(metrics.agent_id)

        if flagged:
            logger.warning(f"Flagged {len(flagged)} underperforming agents: {flagged}")

        return flagged

    def disable_agent(self, agent_id: str, reason: str) -> None:
        """
        Отключить агента

        Args:
            agent_id: ID агента
            reason: Причина отключения
        """
        if agent_id in self._metrics:
            metrics = self._metrics[agent_id]
            metrics.is_active = False
            metrics.disabled_reason = reason
            metrics.disabled_at = datetime.now().isoformat()

            logger.info(f"Disabled agent {agent_id}: {reason}")
            self._save_metrics()

    def enable_agent(self, agent_id: str) -> None:
        """Включить агент обратно"""
        if agent_id in self._metrics:
            metrics = self._metrics[agent_id]
            metrics.is_active = True
            metrics.disabled_reason = None
            metrics.disabled_at = None

            logger.info(f"Re-enabled agent {agent_id}")
            self._save_metrics()

    def get_history(self, agent_id: str, limit: int = 100) -> List[Dict]:
        """
        Получить историю метрик агента

        Args:
            agent_id: ID агента
            limit: Максимальное количество записей

        Returns:
            Список исторических записей
        """
        history = [
            h for h in self._history
            if h.get("agent_id") == agent_id
        ]
        return history[-limit:]

    def get_statistics(self) -> Dict[str, Any]:
        """Получить общую статистику"""
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
        """Проверить и выполнить авто-действия"""
        if not self.config.auto_disable_low_performers:
            return

        # Низкая эффективность - отключаем
        if metrics.cost_efficiency < self.config.min_cost_efficiency:
            self.disable_agent(
                agent_id,
                reason=f"Low cost efficiency: {metrics.cost_efficiency:.2f} < {self.config.min_cost_efficiency}"
            )
            return

        # Низкий value score - отключаем
        if metrics.value_score < self.config.min_value_score:
            self.disable_agent(
                agent_id,
                reason=f"Low value score: {metrics.value_score:.2f} < {self.config.min_value_score}"
            )
            return

        # Высокий veto rate - метка для переобучения
        if metrics.veto_rate > self.config.max_veto_rate:
            logger.warning(
                f"Agent {agent_id} has high veto rate: {metrics.veto_rate:.2f}. "
                f"Consider retraining."
            )

    def _save_metrics(self) -> None:
        """Сохранить метрики в файл"""
        path = Path(self.config.get_absolute_path(self.config.metrics_file))
        path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            agent_id: metrics.to_dict()
            for agent_id, metrics in self._metrics.items()
        }

        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _load_metrics(self) -> None:
        """Загрузить метрики из файла"""
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
        """Сохранить историю в файл"""
        path = Path(self.config.get_absolute_path(self.config.history_file))
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, 'a', encoding='utf-8') as f:
            for entry in list(self._history)[-100:]:  # Последние 100
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')

    def _load_history(self) -> None:
        """Загрузить историю из файла"""
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
# CLI DASHBOARD
# =============================================================================

class ScoreboardDashboard:
    """CLI дашборд для просмотра метрик"""

    def __init__(self, scoreboard: Scoreboard):
        self.scoreboard = scoreboard

    def show_overview(self) -> None:
        """Показать обзорную статистику"""
        stats = self.scoreboard.get_statistics()

        print("\n" + "=" * 70)
        print("AGENT SCOREBOARD - OVERVIEW")
        print("=" * 70)

        print(f"\n📊 General Statistics:")
        print(f"  Total Agents:     {stats['total_agents']}")
        print(f"  Active Agents:    {stats['active_agents']}")
        print(f"  Disabled Agents:  {stats['disabled_agents']}")

        if stats['active_agents'] > 0:
            print(f"\n📈 Performance Metrics:")
            print(f"  Avg Value Score:     {stats['avg_value_score']:.3f}")
            print(f"  Avg Cost Efficiency: {stats['avg_cost_efficiency']:.3f}")
            print(f"  Avg Tokens/Debate:    {stats['avg_tokens_per_debate']:.0f}")

        print(f"\n📝 Total Activity:")
        print(f"  Debates Recorded:  {stats['total_debates_recorded']}")
        print(f"  Tokens Used:       {stats['total_tokens_used']:,}")

        print("\n" + "=" * 70)

    def show_top_performers(self, limit: int = 5) -> None:
        """Показать лучших агентов"""
        top = self.scoreboard.get_top_performers(limit=limit)

        print(f"\n🏆 TOP {limit} PERFORMERS (by cost efficiency)")
        print("-" * 70)

        for i, metrics in enumerate(top, 1):
            status = "✅" if metrics.is_active else "❌"
            print(f"{i}. {status} {metrics.agent_id:25s} | "
                  f"value: {metrics.value_score:.2f} | "
                  f"efficiency: {metrics.cost_efficiency:.2f} | "
                  f"debates: {metrics.debates_participated}")

        print()

    def show_underperformers(self, threshold: float = 0.3) -> None:
        """Показать неэффективных агентов"""
        under = self.scoreboard.get_underperformers(threshold=threshold)

        print(f"\n⚠️  UNDERPERFORMERS (value_score < {threshold})")
        print("-" * 70)

        if not under:
            print("  No underperformers found!")
        else:
            for metrics in under:
                print(f"  ❌ {metrics.agent_id:25s} | "
                      f"value: {metrics.value_score:.2f} | "
                      f"efficiency: {metrics.cost_efficiency:.2f} | "
                      f"debates: {metrics.debates_participated}")

        print()

    def show_agent_details(self, agent_id: str) -> None:
        """Показать детальную информацию об агенте"""
        metrics = self.scoreboard.get_metrics(agent_id)

        if not metrics:
            print(f"\n❌ Agent '{agent_id}' not found")
            return

        print(f"\n📋 AGENT DETAILS: {agent_id}")
        print("-" * 70)

        print(f"\n📊 Participation:")
        print(f"  Debates Participated:  {metrics.debates_participated}")
        print(f"  Approved:             {metrics.debates_approved}")
        print(f"  Rejected:             {metrics.debates_rejected}")

        print(f"\n📈 Performance:")
        print(f"  Consensus Achieved:   {metrics.consensus_achieved:.2%}")
        print(f"  Value Score:          {metrics.value_score:.2f}")
        print(f"  Cost Efficiency:      {metrics.cost_efficiency:.2f}")
        print(f"  Veto Rate:            {metrics.veto_rate:.2%}")

        print(f"\n💰 Resources:")
        print(f"  Avg Tokens/Debate:    {metrics.avg_tokens_per_debate:.0f}")
        print(f"  Total Tokens:         {metrics.total_tokens_used:,}")
        print(f"  Avg Response Time:    {metrics.avg_response_time:.2f}s")

        print(f"\n📅 Timeline:")
        print(f"  First Seen:  {metrics.first_seen}")
        print(f"  Last Seen:   {metrics.last_seen}")

        if not metrics.is_active:
            print(f"\n❌ STATUS: DISABLED")
            print(f"  Reason:   {metrics.disabled_reason}")
            print(f"  At:       {metrics.disabled_at}")
        else:
            print(f"\n✅ STATUS: ACTIVE")

        print()

    def show_leaderboard(self) -> None:
        """Показать полный leaderboard"""
        all_metrics = list(self.scoreboard._metrics.values())
        sorted_metrics = sorted(
            all_metrics,
            key=lambda m: m.cost_efficiency,
            reverse=True
        )

        print(f"\n📊 FULL LEADERBOARD ({len(sorted_metrics)} agents)")
        print("=" * 70)
        print(f"{'Rank':<5} {'Agent':<25} {'Value':<7} {'Eff':<7} {'Debates':<8} {'Status':<7}")
        print("-" * 70)

        for i, metrics in enumerate(sorted_metrics, 1):
            status = "Active" if metrics.is_active else "Disabled"
            print(f"{i:<5} {metrics.agent_id:<25} "
                  f"{metrics.value_score:<7.2f} "
                  f"{metrics.cost_efficiency:<7.2f} "
                  f"{metrics.debates_participated:<8} "
                  f"{status:<7}")

        print()


# =============================================================================
# INTEGRATION WITH DebateStateMachine
# =============================================================================

class ScoreboardIntegration:
    """
    Интеграция Scoreboard с DebateStateMachine

    Автоматически записывает метрики после каждого дебата.
    """

    def __init__(self, scoreboard: Scoreboard):
        self.scoreboard = scoreboard

    def record_debate_outcome(
        self,
        debate_id: str,
        participants: List[str],
        outcome: Dict[str, Any]
    ) -> None:
        """
        Записать результаты дебата для всех участников

        Args:
            debate_id: ID дебата
            participants: Список ID участников
            outcome: Результат дебата
        """
        consensus = outcome.get("consensus_score", 0.5)
        verdict = outcome.get("verdict", "unknown")

        for agent_id in participants:
            # Индивидуальный outcome для каждого агента
            agent_outcome = {
                "consensus_score": consensus,
                "tokens_used": outcome.get(f"{agent_id}_tokens", 1000),
                "response_time": outcome.get(f"{agent_id}_time", 5.0),
                "verdict": verdict,
                "value_score": outcome.get("value_score", 0.5),
                "veto_applied": outcome.get(f"{agent_id}_veto", False),
                "debate_id": debate_id
            }

            self.scoreboard.record_debate(agent_id, agent_outcome)


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

_global_scoreboard: Optional[Scoreboard] = None


def get_scoreboard() -> Scoreboard:
    """Получить глобальный Scoreboard"""
    global _global_scoreboard
    if _global_scoreboard is None:
        _global_scoreboard = Scoreboard()
    return _global_scoreboard


def record_agent_performance(agent_id: str, outcome: Dict[str, Any]) -> AgentMetrics:
    """Записать производительность агента"""
    scoreboard = get_scoreboard()
    return scoreboard.record_debate(agent_id, outcome)


def get_agent_metrics(agent_id: str) -> Optional[AgentMetrics]:
    """Получить метрики агента"""
    scoreboard = get_scoreboard()
    return scoreboard.get_metrics(agent_id)


__all__ = [
    # Core
    "AgentMetrics",
    "DebateOutcome",
    "ScoreboardConfig",
    "Scoreboard",
    "ScoreboardDashboard",
    "ScoreboardIntegration",
    # Convenience
    "get_scoreboard",
    "record_agent_performance",
    "get_agent_metrics"
]


# =============================================================================
# TESTS
# =============================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

    print("=" * 70)
    print("AGENT SCOREBOARD TESTS")
    print("=" * 70)

    # Очистка тестовых файлов
    import os
    test_metrics_file = "memory/test_agent_scoreboard.json"
    test_history_file = "memory/test_agent_metrics_history.jsonl"

    if os.path.exists(test_metrics_file):
        os.remove(test_metrics_file)
    if os.path.exists(test_history_file):
        os.remove(test_history_file)

    # Тест 1: Инициализация
    print("\n[Test 1] Initialization...")
    config = ScoreboardConfig(
        metrics_file=test_metrics_file,
        history_file=test_history_file,
        min_debates_for_evaluation=3  # Для тестов
    )
    scoreboard = Scoreboard(config)
    print(f"  ✓ Scoreboard created")

    # Тест 2: Запись дебатов
    print("\n[Test 2] Recording debates...")
    for i in range(10):
        scoreboard.record_debate("security_expert", {
            "consensus_score": 0.8 + (i % 3) * 0.1,
            "tokens_used": 1000 + i * 100,
            "response_time": 2.0 + i * 0.1,
            "verdict": "approved" if i % 2 == 0 else "approved_with_risks",
            "value_score": 0.7 + (i % 4) * 0.1,
            "veto_applied": i == 5
        })

    metrics = scoreboard.get_metrics("security_expert")
    assert metrics.debates_participated == 10
    assert metrics.value_score > 0.5
    print(f"  ✓ Recorded 10 debates")
    print(f"    Value score: {metrics.value_score:.2f}")
    print(f"    Cost efficiency: {metrics.cost_efficiency:.2f}")

    # Тест 3: Dashboard
    print("\n[Test 3] Dashboard...")
    dashboard = ScoreboardDashboard(scoreboard)
    dashboard.show_agent_details("security_expert")

    # Тест 4: Top performers
    print("\n[Test 4] Top performers...")
    scoreboard.record_debate("performance_guru", {
        "consensus_score": 0.9,
        "tokens_used": 500,
        "response_time": 1.5,
        "verdict": "approved",
        "value_score": 0.95
    })
    dashboard.show_top_performers(limit=3)

    # Тест 5: Disable underperformer
    print("\n[Test 5] Disable underperformer...")
    scoreboard.record_debate("low_performer", {
        "consensus_score": 0.2,
        "tokens_used": 5000,
        "response_time": 10.0,
        "verdict": "rejected",
        "value_score": 0.1
    })
    # Добавляем ещё чтобы преодолеть порог
    for _ in range(config.min_debates_for_evaluation):
        scoreboard.record_debate("low_performer", {
            "consensus_score": 0.2,
            "tokens_used": 5000,
            "response_time": 10.0,
            "verdict": "rejected",
            "value_score": 0.1
        })

    metrics = scoreboard.get_metrics("low_performer")
    print(f"  Low performer is_active: {metrics.is_active}")
    print(f"  Low performer disabled_reason: {metrics.disabled_reason}")

    print("\n" + "=" * 70)
    print("All tests passed!")
    print("=" * 70)

    # Cleanup
    if os.path.exists(test_metrics_file):
        os.remove(test_metrics_file)
    if os.path.exists(test_history_file):
        os.remove(test_history_file)
