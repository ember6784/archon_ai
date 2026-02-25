# archon/kernel/verification_metrics.py
"""
Verification Metrics & Efficacy Monitoring
===========================================

Метрики эффективности верификации для Archon AI.

Предоставляет:
- Отслеживание precision/recall для каждого барьера
- Обнаружение false negatives (критически важно!)
- Анализ consensus и fragility
- Cost efficiency tracking
- Trend analysis и anomaly detection

Usage:
    from verification_metrics import VerificationMetricsCollector, get_metrics_collector
    
    collector = get_metrics_collector()
    
    # Запись результатов проверки
    collector.record_barrier_check(
        barrier_name="intent_contract",
        barrier_level=1,
        blocked=True,
        was_threat=True,  # Ground truth из manual review
        latency_ms=15.2
    )
    
    # Получение метрик
    metrics = collector.finalize_window()
    print(f"Overall confidence: {metrics.overall_confidence}")
    
    # Trend analysis
    trends = collector.get_trend_analysis(hours=24)
"""

import json
import logging
import statistics
from collections import defaultdict, deque
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


logger = logging.getLogger(__name__)


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class BarrierMetrics:
    """
    Метрики для отдельного барьера безопасности.
    
    Использует confusion matrix для расчёта precision/recall.
    """
    barrier_name: str
    barrier_level: int  # 1-5
    
    # Confusion matrix
    true_positives: int = 0      # Нашли реальную угрозу
    false_positives: int = 0     # Заблокировали легитимное (ложная тревога)
    true_negatives: int = 0      # Пропустили легитимное
    false_negatives: int = 0     # Пропустили угрозу (ОПАСНО!)
    
    # Latency
    latencies_ms: List[float] = field(default_factory=list)
    
    # Timing
    first_check: Optional[str] = None
    last_check: Optional[str] = None
    total_checks: int = 0
    
    def record_check(self, blocked: bool, was_threat: bool, latency_ms: float) -> None:
        """Записать результат проверки."""
        now = datetime.now().isoformat()
        
        if self.first_check is None:
            self.first_check = now
        self.last_check = now
        self.total_checks += 1
        
        self.latencies_ms.append(latency_ms)
        
        if blocked and was_threat:
            self.true_positives += 1
        elif blocked and not was_threat:
            self.false_positives += 1
        elif not blocked and not was_threat:
            self.true_negatives += 1
        else:  # not blocked and was_threat
            self.false_negatives += 1
            
    @property
    def precision(self) -> float:
        """TP / (TP + FP) - точность блокировок."""
        denominator = self.true_positives + self.false_positives
        if denominator == 0:
            return 1.0
        return self.true_positives / denominator
    
    @property
    def recall(self) -> float:
        """TP / (TP + FN) - полнота обнаружения."""
        denominator = self.true_positives + self.false_negatives
        if denominator == 0:
            return 1.0
        return self.true_positives / denominator
    
    @property
    def f1_score(self) -> float:
        """F1 = 2 * (precision * recall) / (precision + recall)."""
        if self.precision + self.recall == 0:
            return 0.0
        return 2 * (self.precision * self.recall) / (self.precision + self.recall)
    
    @property
    def false_negative_rate(self) -> float:
        """FN / (FN + TP) - опасный показатель."""
        denominator = self.false_negatives + self.true_positives
        if denominator == 0:
            return 0.0
        return self.false_negatives / denominator
    
    @property
    def specificity(self) -> float:
        """TN / (TN + FP) - специфичность."""
        denominator = self.true_negatives + self.false_positives
        if denominator == 0:
            return 1.0
        return self.true_negatives / denominator
    
    @property
    def avg_latency_ms(self) -> float:
        if not self.latencies_ms:
            return 0.0
        return statistics.mean(self.latencies_ms)
    
    @property
    def max_latency_ms(self) -> float:
        if not self.latencies_ms:
            return 0.0
        return max(self.latencies_ms)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "barrier_name": self.barrier_name,
            "barrier_level": self.barrier_level,
            "true_positives": self.true_positives,
            "false_positives": self.false_positives,
            "true_negatives": self.true_negatives,
            "false_negatives": self.false_negatives,
            "precision": self.precision,
            "recall": self.recall,
            "f1_score": self.f1_score,
            "false_negative_rate": self.false_negative_rate,
            "specificity": self.specificity,
            "avg_latency_ms": self.avg_latency_ms,
            "max_latency_ms": self.max_latency_ms,
            "total_checks": self.total_checks,
            "first_check": self.first_check,
            "last_check": self.last_check,
        }


@dataclass
class VerificationMetrics:
    """
    Полные метрики эффективности системы верификации.
    
    Композитный score доверия к системе.
    """
    
    # === Идентификация ===
    timestamp: str
    window_minutes: int
    metrics_id: str = field(default_factory=lambda: f"vm_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    
    # === Coverage Metrics ===
    total_operations: int = 0
    operations_checked: int = 0
    coverage_ratio: float = 0.0
    
    # === Barrier Performance ===
    barrier_stats: Dict[str, BarrierMetrics] = field(default_factory=dict)
    
    # === Consensus Metrics ===
    debate_participation_rate: float = 0.0
    consensus_convergence_rate: float = 0.0
    avg_consensus_score: float = 0.0
    consensus_scores: List[float] = field(default_factory=list)
    
    # === Entropy Metrics ===
    avg_fragility_index: float = 0.0
    fragility_scores: List[float] = field(default_factory=list)
    high_fragility_debates: int = 0
    
    # === Circuit Breaker Metrics ===
    level_transition_rate: float = 0.0
    false_escalations: int = 0
    missed_escalations: int = 0
    level_transitions: List[Dict[str, str]] = field(default_factory=list)
    
    # === Cost Metrics ===
    avg_tokens_per_verification: float = 0.0
    avg_latency_ms: float = 0.0
    verification_cost_usd: float = 0.0
    total_tokens: int = 0
    total_latency_ms: float = 0.0
    
    # === Security Metrics ===
    blocked_operations: int = 0
    allowed_operations: int = 0
    critical_blocks: int = 0  # Блокировки CRITICAL severity
    
    def calculate_overall_confidence(self) -> float:
        """
        Композитный score доверия к системе верификации.
        
        Формула с весами:
        - Coverage: 25%
        - Barrier Quality (avg F1): 30%
        - Consensus Stability: 20%
        - System Stability: 15%
        - Cost Efficiency: 10%
        """
        if not self.barrier_stats:
            return 0.5  # Нейтральное значение при отсутствии данных
            
        # Coverage score
        coverage_score = self.coverage_ratio
        
        # Barrier quality (средний F1 всех барьеров)
        barrier_f1_scores = [
            b.f1_score for b in self.barrier_stats.values()
        ]
        barrier_quality = statistics.mean(barrier_f1_scores) if barrier_f1_scores else 0.5
        
        # Consensus stability
        consensus_score = self.consensus_convergence_rate
        if self.high_fragility_debates > 0:
            consensus_score *= 0.9  # Штраф за high fragility
            
        # System stability (обратно пропорционально transition rate)
        stability = max(0, 1.0 - self.level_transition_rate * 10)
        
        # Cost efficiency (оптимально: 1000-5000 tokens)
        if self.avg_tokens_per_verification == 0:
            cost_score = 1.0
        elif self.avg_tokens_per_verification < 1000:
            cost_score = 0.9  # Хорошо, но может быть недостаточно thorough
        elif self.avg_tokens_per_verification < 5000:
            cost_score = 1.0  # Оптимально
        elif self.avg_tokens_per_verification < 10000:
            cost_score = 0.8
        else:
            cost_score = max(0, 1.0 - (self.avg_tokens_per_verification - 10000) / 50000)
            
        # False negative penalty (критически важно!)
        fn_rate = self._calculate_overall_fn_rate()
        fn_penalty = max(0.5, 1.0 - fn_rate * 5)  # Серьёзный штраф за FN
        
        overall = (
            0.25 * coverage_score +
            0.30 * barrier_quality +
            0.20 * consensus_score +
            0.15 * stability +
            0.10 * cost_score
        ) * fn_penalty
        
        return max(0.0, min(1.0, overall))
    
    def _calculate_overall_fn_rate(self) -> float:
        """Расчёт общего false negative rate."""
        total_fn = sum(b.false_negatives for b in self.barrier_stats.values())
        total_tp = sum(b.true_positives for b in self.barrier_stats.values())
        
        if total_tp + total_fn == 0:
            return 0.0
        return total_fn / (total_tp + total_fn)
    
    def get_barrier_summary(self) -> Dict[str, Any]:
        """Сводка по всем барьерам."""
        return {
            name: {
                "precision": round(b.precision, 3),
                "recall": round(b.recall, 3),
                "f1": round(b.f1_score, 3),
                "fn_rate": round(b.false_negative_rate, 3),
                "avg_latency_ms": round(b.avg_latency_ms, 2),
                "total_checks": b.total_checks,
            }
            for name, b in self.barrier_stats.items()
        }
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "metrics_id": self.metrics_id,
            "timestamp": self.timestamp,
            "window_minutes": self.window_minutes,
            "overall_confidence": round(self.calculate_overall_confidence(), 4),
            "coverage": {
                "total_operations": self.total_operations,
                "operations_checked": self.operations_checked,
                "coverage_ratio": round(self.coverage_ratio, 4),
            },
            "barriers": self.get_barrier_summary(),
            "consensus": {
                "participation_rate": round(self.debate_participation_rate, 4),
                "convergence_rate": round(self.consensus_convergence_rate, 4),
                "avg_score": round(self.avg_consensus_score, 4),
            },
            "entropy": {
                "avg_fragility": round(self.avg_fragility_index, 4),
                "high_fragility_count": self.high_fragility_debates,
            },
            "stability": {
                "transition_rate": round(self.level_transition_rate, 4),
                "false_escalations": self.false_escalations,
                "missed_escalations": self.missed_escalations,
            },
            "cost": {
                "avg_tokens": round(self.avg_tokens_per_verification, 2),
                "avg_latency_ms": round(self.avg_latency_ms, 2),
                "cost_usd": round(self.verification_cost_usd, 4),
            },
            "security": {
                "blocked": self.blocked_operations,
                "allowed": self.allowed_operations,
                "critical_blocks": self.critical_blocks,
            }
        }


@dataclass
class AnomalyReport:
    """Отчёт об аномалиях в системе верификации."""
    timestamp: str
    anomaly_type: str
    severity: str  # low, medium, high, critical
    description: str
    affected_barrier: Optional[str] = None
    metric_value: Optional[float] = None
    threshold: Optional[float] = None
    recommendation: str = ""


# =============================================================================
# Metrics Collector
# =============================================================================

class VerificationMetricsCollector:
    """
    Сборщик и анализатор метрик верификации.
    
    Потокобезопасный (single-threaded), сбора метрик в time-window'ях.
    """
    
    # Цены на токены (примерные, USD per 1K tokens)
    TOKEN_COSTS = {
        "gpt-4o": 0.005,
        "gpt-4o-mini": 0.0006,
        "claude-3.5-sonnet": 0.003,
        "claude-3-haiku": 0.0008,
    }
    
    def __init__(self, storage_dir: str = "data/verification_metrics"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        
        # История метрик (в памяти)
        self._metrics_history: deque = deque(maxlen=10000)
        self._anomalies: deque = deque(maxlen=1000)
        
        # Счётчики текущего окна
        self._reset_window()
        
        # Загрузка истории
        self._load_history()
        
        logger.info(f"[VerificationMetrics] Initialized, storage: {storage_dir}")
        
    def _reset_window(self) -> None:
        """Сброс счётчиков нового окна."""
        self._window_start = datetime.now()
        self._operation_counts: Dict[str, int] = defaultdict(int)
        self._barrier_counters: Dict[str, BarrierMetrics] = {}
        self._consensus_scores: List[float] = []
        self._fragility_scores: List[float] = []
        self._level_transitions: List[Dict[str, str]] = []
        self._total_tokens = 0
        self._total_latency_ms = 0.0
        self._blocked_operations = 0
        self._allowed_operations = 0
        
    def record_barrier_check(
        self,
        barrier_name: str,
        barrier_level: int,
        blocked: bool,
        was_threat: bool,
        latency_ms: float
    ) -> None:
        """
        Записать результат проверки барьером.
        
        Args:
            barrier_name: Имя барьера (например, "intent_contract")
            barrier_level: Уровень барьера (1-5)
            blocked: True если барьер заблокировал операцию
            was_threat: True если операция была реальной угрозой
                       (требует ground truth из manual review)
            latency_ms: Время проверки в миллисекундах
        """
        if barrier_name not in self._barrier_counters:
            self._barrier_counters[barrier_name] = BarrierMetrics(
                barrier_name=barrier_name,
                barrier_level=barrier_level
            )
            
        self._barrier_counters[barrier_name].record_check(
            blocked=blocked,
            was_threat=was_threat,
            latency_ms=latency_ms
        )
        
        self._operation_counts["total_checks"] += 1
        self._total_latency_ms += latency_ms
        
        if blocked:
            self._blocked_operations += 1
        else:
            self._allowed_operations += 1
            
        # Проверяем на критические условия
        if not blocked and was_threat:
            # FALSE NEGATIVE - критически опасно!
            self._alert_false_negative(barrier_name)
            
    def record_debate_outcome(
        self,
        consensus_score: float,
        fragility_index: float,
        tokens_used: int,
        model_family: str = "unknown"
    ) -> None:
        """
        Записать результаты дебата.
        
        Args:
            consensus_score: Score согласия (0-1)
            fragility_index: Индекс хрупкости решения
            tokens_used: Количество использованных токенов
            model_family: Семейство модели (для cost calculation)
        """
        self._consensus_scores.append(consensus_score)
        self._fragility_scores.append(fragility_index)
        self._total_tokens += tokens_used
        
        self._operation_counts["debates"] += 1
        
        # Оценка стоимости
        cost_per_1k = self.TOKEN_COSTS.get(model_family, 0.002)
        self._operation_counts["cost_usd"] += tokens_used / 1000 * cost_per_1k
        
    def record_circuit_transition(
        self,
        from_level: str,
        to_level: str,
        reason: str,
        human_present: bool = False
    ) -> None:
        """
        Записать переход Circuit Breaker.
        
        Args:
            from_level: Исходный уровень
            to_level: Новый уровень
            reason: Причина перехода
            human_present: Был ли человек онлайн
        """
        self._level_transitions.append({
            "timestamp": datetime.now().isoformat(),
            "from": from_level,
            "to": to_level,
            "reason": reason,
        })
        
        self._operation_counts["transitions"] += 1
        
        # Детекция ложных эскалаций
        if from_level == "GREEN" and to_level in ["AMBER", "RED"]:
            if human_present or "backlog" in reason.lower():
                # Проверяем, был ли недавно human activity
                self._operation_counts["possible_false_escalations"] += 1
                
    def record_operation(self, operation_type: str, checked: bool = True) -> None:
        """Записать факт операции."""
        self._operation_counts["total_operations"] += 1
        if checked:
            self._operation_counts["checked_operations"] += 1
            
    def record_critical_block(self, reason: str) -> None:
        """Записать критическую блокировку."""
        self._operation_counts["critical_blocks"] += 1
        logger.warning(f"[VerificationMetrics] Critical block: {reason}")
        
    def finalize_window(self, force: bool = False) -> Optional[VerificationMetrics]:
        """
        Завершить окно сбора и создать метрики.
        
        Args:
            force: Принудительно завершить даже если окно маленькое
            
        Returns:
            VerificationMetrics или None если недостаточно данных
        """
        window_duration = (datetime.now() - self._window_start).total_seconds() / 60
        
        # Минимальное окно - 1 минута (если не force)
        if window_duration < 1 and not force:
            return None
            
        # Собираем метрики
        metrics = VerificationMetrics(
            timestamp=datetime.now().isoformat(),
            window_minutes=int(window_duration),
            
            total_operations=self._operation_counts["total_operations"],
            operations_checked=self._operation_counts["checked_operations"],
            coverage_ratio=(
                self._operation_counts["checked_operations"] / 
                max(self._operation_counts["total_operations"], 1)
            ),
            
            barrier_stats=self._barrier_counters,
            
            debate_participation_rate=(
                self._operation_counts["debates"] / 
                max(self._operation_counts["total_operations"], 1)
            ),
            consensus_convergence_rate=self._calculate_convergence_rate(),
            avg_consensus_score=statistics.mean(self._consensus_scores) if self._consensus_scores else 0.5,
            consensus_scores=list(self._consensus_scores),
            
            avg_fragility_index=statistics.mean(self._fragility_scores) if self._fragility_scores else 0.0,
            fragility_scores=list(self._fragility_scores),
            high_fragility_debates=sum(1 for f in self._fragility_scores if f > 0.3),
            
            level_transition_rate=(
                self._operation_counts["transitions"] / max(window_duration, 1)
            ),
            false_escalations=self._operation_counts.get("possible_false_escalations", 0),
            missed_escalations=0,  # Требует external monitoring
            level_transitions=list(self._level_transitions),
            
            avg_tokens_per_verification=(
                self._total_tokens / max(self._operation_counts["debates"], 1)
            ),
            avg_latency_ms=(
                self._total_latency_ms / max(self._operation_counts["total_checks"], 1)
            ),
            verification_cost_usd=self._operation_counts.get("cost_usd", 0.0),
            total_tokens=self._total_tokens,
            total_latency_ms=self._total_latency_ms,
            
            blocked_operations=self._blocked_operations,
            allowed_operations=self._allowed_operations,
            critical_blocks=self._operation_counts.get("critical_blocks", 0),
        )
        
        # Проверяем на аномалии
        self._detect_anomalies(metrics)
        
        # Сохраняем
        self._metrics_history.append(metrics)
        self._persist_metrics(metrics)
        
        # Сбрасываем окно
        self._reset_window()
        
        return metrics
    
    def _calculate_convergence_rate(self) -> float:
        """Расчёт convergence rate."""
        if not self._consensus_scores:
            return 0.0
        high_consensus = sum(1 for s in self._consensus_scores if s > 0.7)
        return high_consensus / len(self._consensus_scores)
    
    def _detect_anomalies(self, metrics: VerificationMetrics) -> None:
        """Детекция аномалий в метриках."""
        now = datetime.now().isoformat()
        
        # 1. Высокий false negative rate
        for name, barrier in metrics.barrier_stats.items():
            if barrier.false_negative_rate > 0.05:  # >5% FN
                anomaly = AnomalyReport(
                    timestamp=now,
                    anomaly_type="high_false_negative_rate",
                    severity="critical",
                    description=f"Barrier {name} has high FN rate",
                    affected_barrier=name,
                    metric_value=barrier.false_negative_rate,
                    threshold=0.05,
                    recommendation="Immediate review required - security bypass possible"
                )
                self._anomalies.append(anomaly)
                
            # 2. Низкая precision (много ложных тревог)
            if barrier.total_checks > 10 and barrier.precision < 0.5:
                anomaly = AnomalyReport(
                    timestamp=now,
                    anomaly_type="low_precision",
                    severity="medium",
                    description=f"Barrier {name} has low precision",
                    affected_barrier=name,
                    metric_value=barrier.precision,
                    threshold=0.5,
                    recommendation="Tune barrier thresholds to reduce false positives"
                )
                self._anomalies.append(anomaly)
                
        # 3. Высокая fragility
        if metrics.avg_fragility_index > 0.3:
            anomaly = AnomalyReport(
                timestamp=now,
                anomaly_type="high_fragility",
                severity="high",
                description="High decision fragility detected",
                metric_value=metrics.avg_fragility_index,
                threshold=0.3,
                recommendation="Consider lowering model temperature or increasing consensus threshold"
            )
            self._anomalies.append(anomaly)
            
        # 4. Низкий overall confidence
        confidence = metrics.calculate_overall_confidence()
        if confidence < 0.5:
            anomaly = AnomalyReport(
                timestamp=now,
                anomaly_type="low_confidence",
                severity="high",
                description="Overall verification confidence is low",
                metric_value=confidence,
                threshold=0.5,
                recommendation="System may need additional barriers or manual review"
            )
            self._anomalies.append(anomaly)
            
    def get_trend_analysis(self, hours: int = 24) -> Dict[str, Any]:
        """
        Анализ трендов за последние N часов.
        
        Args:
            hours: Период анализа
            
        Returns:
            Dict с анализом трендов
        """
        cutoff = datetime.now() - timedelta(hours=hours)
        recent = [m for m in self._metrics_history if datetime.fromisoformat(m.timestamp) > cutoff]
        
        if not recent:
            return {
                "error": "No data for analysis",
                "period_hours": hours,
            }
            
        # Расчёт трендов
        confidence_values = [m.calculate_overall_confidence() for m in recent]
        fn_rates = [
            sum(b.false_negatives for b in m.barrier_stats.values()) / 
            max(sum(b.true_positives + b.false_negatives for b in m.barrier_stats.values()), 1)
            for m in recent
        ]
        
        # Тренд (линейная регрессия упрощённая)
        def calc_trend(values: List[float]) -> str:
            if len(values) < 3:
                return "insufficient_data"
            first_half = statistics.mean(values[:len(values)//2])
            second_half = statistics.mean(values[len(values)//2:])
            diff = second_half - first_half
            if diff > 0.1:
                return "improving"
            elif diff < -0.1:
                return "degrading"
            return "stable"
            
        # Аномалии
        recent_anomalies = [
            a for a in self._anomalies 
            if datetime.fromisoformat(a.timestamp) > cutoff
        ]
        
        critical_anomalies = [a for a in recent_anomalies if a.severity == "critical"]
        
        return {
            "period_hours": hours,
            "data_points": len(recent),
            "confidence": {
                "avg": round(statistics.mean(confidence_values), 4),
                "min": round(min(confidence_values), 4),
                "max": round(max(confidence_values), 4),
                "trend": calc_trend(confidence_values),
            },
            "false_negative_rate": {
                "avg": round(statistics.mean(fn_rates), 4),
                "max": round(max(fn_rates), 4),
                "trend": calc_trend(fn_rates),
            },
            "anomalies": {
                "total": len(recent_anomalies),
                "critical": len(critical_anomalies),
                "by_type": self._count_anomalies_by_type(recent_anomalies),
            },
            "recommendation": self._generate_recommendation(recent[-1], critical_anomalies),
        }
    
    def _count_anomalies_by_type(self, anomalies: List[AnomalyReport]) -> Dict[str, int]:
        """Подсчёт аномалий по типу."""
        counts = defaultdict(int)
        for a in anomalies:
            counts[a.anomaly_type] += 1
        return dict(counts)
    
    def _generate_recommendation(
        self,
        latest: VerificationMetrics,
        critical_anomalies: List[AnomalyReport]
    ) -> str:
        """Генерация рекомендаций."""
        recommendations = []
        
        if critical_anomalies:
            recs = set(a.recommendation for a in critical_anomalies)
            recommendations.extend(recs)
            
        confidence = latest.calculate_overall_confidence()
        if confidence < 0.6:
            recommendations.append("LOW_CONFIDENCE: Consider adding verification barriers")
            
        if latest.avg_fragility_index > 0.3:
            recommendations.append("HIGH_FRAGILITY: Use lower-temperature models")
            
        if latest.false_escalations > 2:
            recommendations.append("FALSE_ESCALATIONS: Adjust Circuit Breaker thresholds")
            
        return "; ".join(recommendations) if recommendations else "OK"
    
    def get_current_status(self) -> Dict[str, Any]:
        """Получить текущий статус системы верификации."""
        if not self._metrics_history:
            return {"status": "initializing", "message": "No metrics collected yet"}
            
        latest = self._metrics_history[-1]
        confidence = latest.calculate_overall_confidence()
        
        # Определяем статус
        if confidence > 0.8:
            status = "healthy"
        elif confidence > 0.6:
            status = "warning"
        else:
            status = "critical"
            
        return {
            "status": status,
            "overall_confidence": round(confidence, 4),
            "last_update": latest.timestamp,
            "window_minutes": latest.window_minutes,
            "operations_tracked": latest.total_operations,
            "barriers_active": len(latest.barrier_stats),
            "recent_anomalies": len([a for a in self._anomalies if 
                datetime.fromisoformat(a.timestamp) > datetime.now() - timedelta(hours=1)]),
        }
    
    def export_metrics(self, format: str = "json", hours: int = 24) -> str:
        """
        Экспорт метрик.
        
        Args:
            format: "json" или "csv"
            hours: За сколько последних часов
        """
        cutoff = datetime.now() - timedelta(hours=hours)
        recent = [m for m in self._metrics_history if datetime.fromisoformat(m.timestamp) > cutoff]
        
        if format == "json":
            return json.dumps(
                [m.to_dict() for m in recent],
                indent=2,
                default=str
            )
        elif format == "csv":
            import csv
            import io
            
            if not recent:
                return ""
                
            output = io.StringIO()
            writer = csv.writer(output)
            
            # Headers
            headers = ["timestamp", "confidence", "coverage", "avg_fn_rate", "avg_latency_ms"]
            writer.writerow(headers)
            
            for m in recent:
                fn_rate = sum(b.false_negatives for b in m.barrier_stats.values()) / max(
                    sum(b.true_positives + b.false_negatives for b in m.barrier_stats.values()), 1
                )
                writer.writerow([
                    m.timestamp,
                    m.calculate_overall_confidence(),
                    m.coverage_ratio,
                    fn_rate,
                    m.avg_latency_ms,
                ])
                
            return output.getvalue()
        else:
            raise ValueError(f"Unsupported format: {format}")
    
    def _alert_false_negative(self, barrier_name: str) -> None:
        """Alert при false negative (пропуск угрозы)."""
        logger.critical(
            f"🚨 FALSE NEGATIVE in {barrier_name}! "
            f"Security threat was not detected!"
        )
        # TODO: Интеграция с PagerDuty/Slack/Email
        
    def _persist_metrics(self, metrics: VerificationMetrics) -> None:
        """Сохранение метрик в файл."""
        file_path = self.storage_dir / f"metrics_{datetime.now():%Y%m%d}.jsonl"
        
        try:
            with open(file_path, "a") as f:
                f.write(json.dumps(metrics.to_dict(), default=str) + "\n")
        except Exception as e:
            logger.error(f"Failed to persist metrics: {e}")
            
    def _load_history(self) -> None:
        """Загрузка истории метрик."""
        try:
            for file_path in sorted(self.storage_dir.glob("metrics_*.jsonl")):
                with open(file_path, "r") as f:
                    for line in f:
                        if line.strip():
                            # Парсим базовые поля
                            data = json.loads(line)
                            # Создаём упрощённый объект для хранения
                            # Используем SimpleNamespace для доступа к полям через точку
                            from types import SimpleNamespace
                            ns = SimpleNamespace(**data)
                            self._metrics_history.append(ns)
                            
            logger.info(f"Loaded {len(self._metrics_history)} historical metrics")
        except Exception as e:
            logger.warning(f"Failed to load metrics history: {e}")


# =============================================================================
# Singleton Instance
# =============================================================================

_global_collector: Optional[VerificationMetricsCollector] = None


def get_metrics_collector(storage_dir: str = "data/verification_metrics") -> VerificationMetricsCollector:
    """Get global metrics collector instance."""
    global _global_collector
    if _global_collector is None:
        _global_collector = VerificationMetricsCollector(storage_dir)
    return _global_collector


def set_metrics_collector(collector: VerificationMetricsCollector) -> None:
    """Set global metrics collector instance."""
    global _global_collector
    _global_collector = collector


# =============================================================================
# Convenience Functions
# =============================================================================

def record_barrier_check(
    barrier_name: str,
    barrier_level: int,
    blocked: bool,
    was_threat: bool,
    latency_ms: float
) -> None:
    """Convenience function для записи проверки барьера."""
    collector = get_metrics_collector()
    collector.record_barrier_check(
        barrier_name=barrier_name,
        barrier_level=barrier_level,
        blocked=blocked,
        was_threat=was_threat,
        latency_ms=latency_ms
    )


def record_debate_outcome(
    consensus_score: float,
    fragility_index: float,
    tokens_used: int,
    model_family: str = "unknown"
) -> None:
    """Convenience function для записи результатов дебата."""
    collector = get_metrics_collector()
    collector.record_debate_outcome(
        consensus_score=consensus_score,
        fragility_index=fragility_index,
        tokens_used=tokens_used,
        model_family=model_family
    )


def get_current_confidence() -> float:
    """Получить текущий confidence score."""
    collector = get_metrics_collector()
    status = collector.get_current_status()
    return status.get("overall_confidence", 0.5)


__all__ = [
    # Classes
    "BarrierMetrics",
    "VerificationMetrics",
    "AnomalyReport",
    "VerificationMetricsCollector",
    # Functions
    "get_metrics_collector",
    "set_metrics_collector",
    "record_barrier_check",
    "record_debate_outcome",
    "get_current_confidence",
]
