"""
State Machine V3.0: Engineering Debate Pipeline
================================================
Детерминированный компилятор инженерных решений с LLM

Архитектура:
- DRAFT → NORMALIZE → SIEGE → FORTIFY → NORMALIZE → FINAL_ASSAULT → FREEZE → JUDGMENT
- Формальные контракты (Input/Output schemas)
- Event Sourcing для персистентности
- AST Fingerprinting для структурного анализа
- Pytest как сигнал (улика), а не судья
"""

from typing import Dict, List, Optional, Any, Tuple, Set
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
import json
import hashlib
import ast
import re
from collections import deque
from functools import lru_cache


# ============================================================================
# STATE MACHINE DEFINITION
# ============================================================================

class DebateState(Enum):
    """Состояния State Machine"""
    DRAFT = "draft"                              # Builder предлагает решение
    NORMALIZE_SEMANTIC = "normalize_semantic"    # Канонизация логики
    SIEGE = "siege"                              # Skeptic атакует
    FORTIFY = "fortify"                          # Builder чинит (constraints!)
    NORMALIZE_SYNTAX = "normalize_syntax"        # Black/Ruff форматирование
    FINAL_ASSAULT = "final_assault"              # Skeptic проверяет починку
    FREEZE = "freeze"                            # Блокировка артефактов
    JUDGMENT = "judgment"                        # Auditor + анализ

    # ========================================================================
    # FEEDBACK LOOP STATES (цикл обратной связи)
    # ========================================================================
    ASSIGN_FIXER = "assign_fixer"                # Назначение исполнителя для исправления
    FIX = "fix"                                  # Исправление кода
    VERIFY = "verify"                            # Проверка исправлений
    RE_DEBATE = "re_debate"                      # Повторный дебат после исправлений
    COMPLETE = "complete"                        # Процесс завершён (APPROVED или max iterations)

    # ========================================================================
    # EVOLUTION CYCLE STATES (Self-Evolution Debates)
    # ========================================================================
    EVOLUTION_START = "evolution_start"          # Начало цикла эволюции
    STAGNATION_CHECK = "stagnation_check"        # Проверка на отсутствие изменений (NoOpDetector)
    GROUNDING = "grounding"                      # Запуск реальных тестов (PytestSandbox)
    FRESH_EYE = "fresh_eye"                      # FreshEyeCritic - критик без контекста
    SENIOR_AUDITOR = "senior_auditor"            # SeniorAuditor - финальный арбитраж
    VETO_POWER = "veto_power"                    # Откат файла при REJECT вердикте


# ============================================================================
# FORMAL CONTRACTS (Input/Output Schemas)
# ============================================================================

@dataclass
class StateTransition:
    """Запись о переходе состояния (Event Sourcing)"""
    state_id: str
    timestamp: str
    from_state: Optional[str]
    to_state: str
    artifact_hash: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Artifact:
    """Артефакт на каждом этапе"""
    content: str
    hash: str
    content_type: str  # "code", "vulnerability_list", "report"
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    @classmethod
    def create(cls, content: str, content_type: str, **metadata):
        """Создать артефакт с автоматическим хешированием"""
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        return cls(
            content=content,
            hash=content_hash,
            content_type=content_type,
            metadata=metadata
        )


@dataclass
class DraftInput:
    """Input для состояния DRAFT"""
    task: str
    task_type: str
    context: Dict[str, Any]
    constraints: List[str] = field(default_factory=list)


@dataclass
class DraftOutput:
    """Output из состояния DRAFT"""
    proposed_code: str
    rationale: str
    confidence: float
    # Artifact fields (composition instead of inheritance)
    _artifact_content: str = field(init=False)
    _artifact_hash: str = field(init=False)
    _artifact_type: str = field(init=False, default="code")
    _artifact_metadata: Dict[str, Any] = field(init=False, default_factory=dict)

    def __post_init__(self):
        self._artifact_content = self.proposed_code
        self._artifact_hash = hashlib.sha256(self.proposed_code.encode()).hexdigest()

    @property
    def hash(self) -> str:
        return self._artifact_hash


@dataclass
class NormalizedOutput:
    """Output из состояния NORMALIZE"""
    canonical_code: str
    normalization_stats: Dict[str, int]
    # Artifact fields
    _artifact_content: str = field(init=False)
    _artifact_hash: str = field(init=False)
    _artifact_type: str = field(init=False, default="canonical_code")
    _artifact_metadata: Dict[str, Any] = field(init=False, default_factory=dict)

    def __post_init__(self):
        self._artifact_content = self.canonical_code
        self._artifact_hash = hashlib.sha256(self.canonical_code.encode()).hexdigest()

    @property
    def hash(self) -> str:
        return self._artifact_hash


@dataclass
class VulnerabilityReport:
    """Output из состояния SIEGE"""
    vulnerabilities: List[Dict[str, Any]]
    attack_vector: List[str]
    severity_scores: List[float]
    # Artifact fields
    _artifact_content: str = field(init=False)
    _artifact_hash: str = field(init=False)
    _artifact_type: str = field(init=False, default="vulnerability_list")
    _artifact_metadata: Dict[str, Any] = field(init=False, default_factory=dict)

    def __post_init__(self):
        self._artifact_content = json.dumps(self.vulnerabilities, ensure_ascii=False)
        self._artifact_hash = hashlib.sha256(self._artifact_content.encode()).hexdigest()

    @property
    def hash(self) -> str:
        return self._artifact_hash


@dataclass
class FortifiedOutput:
    """Output из состояния FORTIFY (с constraints!)"""
    fixed_code: str
    applied_fixes: List[str]
    new_symbols_added: List[str]  # Для проверки constraints
    # Artifact fields
    _artifact_content: str = field(init=False)
    _artifact_hash: str = field(init=False)
    _artifact_type: str = field(init=False, default="code")
    _artifact_metadata: Dict[str, Any] = field(init=False, default_factory=dict)

    def __post_init__(self):
        self._artifact_content = self.fixed_code
        self._artifact_hash = hashlib.sha256(self.fixed_code.encode()).hexdigest()

    @property
    def hash(self) -> str:
        return self._artifact_hash


@dataclass
class ImmutableArtifact:
    """Output из состояния FREEZE (неизменяемый)"""
    frozen_code: str
    frozen_at: str
    ast_fingerprint: Set[str]
    test_results: Optional[Dict[str, Any]] = None
    # Artifact fields
    _artifact_content: str = field(init=False)
    _artifact_hash: str = field(init=False)
    _artifact_type: str = field(init=False, default="immutable_artifact")
    _artifact_metadata: Dict[str, Any] = field(init=False, default_factory=dict)

    def __post_init__(self):
        self._artifact_content = self.frozen_code
        self._artifact_hash = hashlib.sha256(self.frozen_code.encode()).hexdigest()

    @property
    def hash(self) -> str:
        return self._artifact_hash


@dataclass
class JudgmentOutcome:
    """Output из состояния JUDGMENT"""
    status: str  # "ACCEPTED", "ACCEPTED_WITH_RISKS", "REJECTED", "MANUAL_REVIEW"
    consensus_score: float
    cosine_similarity: float
    jaccard_similarity: float
    change_magnitude: int
    final_code: str
    unresolved_risks: List[str]
    auditor_report: str
    decision_trace: Dict[str, Any]


# ============================================================================
# FEEDBACK LOOP CONTRACTS
# ============================================================================

@dataclass
class FixAssignment:
    """Output из состояния ASSIGN_FIXER"""
    assigned_fixer: str  # "builder", "human", "auto_fix"
    fix_priority: List[str]  # ["high", "medium", "low"]
    issues_to_fix: List[Dict[str, Any]]  # [{"issue": "...", "severity": "high", "location": "..."}]
    fix_plan: str  # План исправления
    estimated_effort: str  # "5 minutes", "15 minutes", etc.
    requires_human_intervention: bool


@dataclass
class FixOutput:
    """Output из состояния FIX"""
    fixed_code: str
    changes_made: List[Dict[str, Any]]  # [{"location": "...", "change": "...", "reason": "..."}]
    fix_summary: str
    success: bool
    errors: List[str] = field(default_factory=list)


@dataclass
class VerifyOutput:
    """Output из состояния VERIFY"""
    verification_status: str  # "verified", "failed", "partial"
    verification_report: str
    remaining_issues: List[str]
    regression_tests_passed: bool
    ready_for_re_debate: bool


@dataclass
class ReDebateOutcome:
    """Output из состояния RE_DEBATE"""
    new_status: str  # "approved", "warning", "rejected", "unchanged"
    new_consensus_score: float
    improvements_made: bool
    new_issues: List[str]
    should_continue_loop: bool
    iteration_number: int


@dataclass
class CompleteOutcome:
    """Output из состояния COMPLETE"""
    final_status: str  # "approved", "rejected_after_max_iterations", "manual_review_required"
    total_iterations: int
    final_code: str
    all_issues_resolved: bool
    requires_manual_review: bool
    summary: str


# ============================================================================
# EVOLUTION CYCLE CONTRACTS (Self-Evolution Debates)
# ============================================================================

@dataclass
class StagnationReport:
    """Output из состояния STAGNATION_CHECK"""
    has_changes: bool  # True если есть реальные изменения
    is_no_op: bool  # True если только косметические изменения
    jaccard_similarity: float  # Степень сходства кода
    cfg_difference: int  # Разница в Control Flow Graph
    stagnation_count: int  # Счётчик стагнаций
    recommendation: str  # "continue", "increase_aggression", "escalate"


@dataclass
class GroundingResult:
    """Output из состояния GROUNDING"""
    tests_executed: bool
    tests_passed: int
    tests_failed: int
    test_errors: List[str]
    real_errors_found: bool
    should_fix: bool  # True если нужно вызывать FIX вместо споров
    error_summary: str


@dataclass
class FreshEyeResult:
    """Output из состояния FRESH_EYE"""
    status: str  # "approved", "rejected", "needs_changes"
    confidence: float
    issues_found: List[str]
    blind_spots: List[str]  # Проблемы, которые другие агенты пропустили
    rationale: str
    recommendation: str


@dataclass
class SeniorAuditorDecision:
    """Output из состояния SENIOR_AUDITOR"""
    status: str  # "approved", "revert", "reject"
    confidence: float
    rationale: str
    constitutional_violations: List[str]
    respects_grounding: bool  # True если учёл результаты тестов
    respects_reflection: bool  # True если учёл прошлые ошибки
    final_code: str
    veto_active: bool  # True если сработал Veto Power
    # Intent Verifier — присваивались динамически, добавлены явно
    intent_score: Optional[float] = None
    intent_violations: List[str] = field(default_factory=list)


# ============================================================================
# AST FINGERPRINTING
# ============================================================================

class StructuralFingerprint(ast.NodeVisitor):
    """
    AST-based fingerprinting для структурного diff анализа

    Использует:
    - Module namespacing (избегает коллизий)
    - Diff-based extraction (только измененное)
    - Полная поддержка async, nested defs, inheritance
    """

    def __init__(self, module_name: str):
        self.module = module_name
        self.symbols: Set[str] = set()

    def _add(self, prefix: str, name: str):
        """Добавить символ с namespace"""
        self.symbols.add(f"{self.module}::{prefix}:{name}")

    def visit_ClassDef(self, node: ast.ClassDef):
        """Извлечь класс с наследованием"""
        self._add("class", node.name)

        # Наследование
        for base in node.bases:
            if isinstance(base, ast.Name):
                self._add("inherits", base.id)
            elif isinstance(base, ast.Attribute):
                self._add("inherits", base.attr)

        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef):
        """Извлечь функцию"""
        self._add("func", node.name)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        """Извлечь async функцию"""
        self._add("async_func", node.name)
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import):
        """Извлечь импорты"""
        for alias in node.names:
            self._add("import", alias.name)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        """Извлечь from imports"""
        module = node.module or ""
        for alias in node.names:
            self._add("from_import", f"{module}.{alias.name}")

    def extract_fingerprint(self, code: str) -> Set[str]:
        """
        Извлечь fingerprint из кода

        ВАЖНО: Это работает на diff'е, не на whole file!
        """
        tree = _parse_ast_cached(code)
        if tree is None:
            return set()

        self.visit(tree)
        return self.symbols


@lru_cache(maxsize=512)
def _parse_ast_cached(code: str) -> Optional[ast.AST]:
    """
    Кэшированное парсинг AST для производительности.

    Примечание: Кэширует только успешно распарсенные деревья.
    """
    try:
        return ast.parse(code)
    except SyntaxError:
        return None


def calculate_jaccard(set_a: Set[str], set_b: Set[str]) -> float:
    """
    Jaccard similarity coefficient

    J(A,B) = |A ∩ B| / |A ∪ B|

    0.0 = полностью разные
    1.0 = идентичные
    """
    if not set_a and not set_b:
        return 1.0

    intersection = set_a.intersection(set_b)
    union = set_a.union(set_b)

    return len(intersection) / len(union) if union else 0.0


# ============================================================================
# STATE MACHINE ENGINE
# ============================================================================

class DebateStateMachine:
    """
    State Machine для управления дебатами

    Event Sourcing:
    - Каждый переход записывается в debate_history.jsonl
    - Replayability: можно восстановить любое состояние

    Scoreboard Integration:
    - Автоматически записывает метрики агентов при завершении дебата
    """

    def __init__(self, debate_id: str, workspace, scoreboard=None):
        """
        Инициализация State Machine

        Args:
            debate_id: Уникальный ID дебата
            workspace: Путь к рабочей директории
            scoreboard: Опциональный Scoreboard для записи метрик
        """
        self.debate_id = debate_id
        self.workspace = Path(workspace) if isinstance(workspace, str) else workspace
        self.current_state: Optional[DebateState] = None
        self.artifacts: Dict[str, Artifact] = {}
        self.history: deque = deque(maxlen=1000)  # Event sourcing
        self.history_file = self.workspace / "debates" / f"{debate_id}_history.jsonl"
        self.entropy_markers: Dict[str, "EntropyMarker"] = {}

        # Scoreboard для записи метрик
        self._scoreboard = scoreboard

        # Отслеживание участников и их метрик во время дебата
        self._participants: Dict[str, Dict] = {}  # agent_id -> {tokens, time, start_time}
        self._debate_start_time: Optional[str] = None

        # Создаем директорию
        self.history_file.parent.mkdir(parents=True, exist_ok=True)

    def _log_transition(self, to_state: DebateState, artifact: Artifact, **metadata):
        """
        Записать переход в историю (Event Sourcing)

        Args:
            to_state: Целевое состояние
            artifact: Артефакт перехода
            **metadata: Дополнительные метаданные, включая:
                - entropy_marker: EntropyMarker (опционально)
                - model_version: str (для создания EntropyMarker)
                - model_family: str
                - temperature: float
                - confidence_score: float
        """
        # Извлекаем или создаём EntropyMarker
        entropy_marker = metadata.pop('entropy_marker', None)

        if entropy_marker is None:
            model_version = metadata.pop('model_version', None)
            model_family = metadata.pop('model_family', None)
            temperature = metadata.pop('temperature', None)
            confidence_score = metadata.pop('confidence_score', 0.0)

            if model_version and model_family:
                entropy_marker = EntropyMarker(
                    model_version=model_version,
                    model_family=model_family,
                    temperature=temperature or 0.0,
                    confidence_score=confidence_score
                )

        transition = StateTransition(
            state_id=f"{self.debate_id}_{len(self.history)}",
            timestamp=datetime.utcnow().isoformat(),
            from_state=self.current_state.value if self.current_state else None,
            to_state=to_state.value,
            artifact_hash=artifact.hash,
            metadata=metadata
        )

        self.history.append(transition)
        self.current_state = to_state
        self.artifacts[to_state.value] = artifact

        if entropy_marker:
            self.entropy_markers[transition.state_id] = entropy_marker

        # Append-only запись в файл
        transition_dict = transition.__dict__.copy()
        if entropy_marker:
            transition_dict['entropy_marker'] = entropy_marker.to_dict()

        with open(self.history_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(transition_dict, ensure_ascii=False) + '\n')

    def _load_history(self) -> List[StateTransition]:
        """Загрузить историю из файла (для replay), включая десериализацию EntropyMarker."""
        transitions = []
        if not self.history_file.exists():
            return transitions

        with open(self.history_file, 'r', encoding='utf-8') as f:
            for line in f:
                data = json.loads(line.strip())

                # Десериализуем EntropyMarker если есть
                raw_marker = data.pop('entropy_marker', None)
                if raw_marker:
                    marker = EntropyMarker(**raw_marker)
                    state_id = data.get('state_id', '')
                    self.entropy_markers[state_id] = marker

                transitions.append(StateTransition(**data))

        return transitions

    def get_artifact(self, state: DebateState) -> Optional[Artifact]:
        """Получить артефакт из состояния"""
        return self.artifacts.get(state.value)

    def get_current_timestamp(self) -> str:
        """Получить текущую метку времени в ISO формате"""
        return datetime.now().isoformat()

    def replay_to_state(self, target_state: DebateState) -> bool:
        """
        Replay истории до конкретного состояния

        Возвращает True, если успешно восстановлено
        """
        transitions = self._load_history()

        for transition in transitions:
            if transition.to_state == target_state.value:
                self.current_state = DebateState(transition.to_state)
                return True

        return False

    # -------------------------------------------------------------------------
    # SCOREBOARD INTEGRATION
    # -------------------------------------------------------------------------

    def register_participant(self, agent_id: str, agent_type: str = "agent") -> None:
        """
        Зарегистрировать участника дебата

        Args:
            agent_id: ID агента (например, "security_expert", "builder")
            agent_type: Тип агента (builder, skeptic, auditor, и т.д.)
        """
        self._participants[agent_id] = {
            "agent_type": agent_type,
            "tokens_used": 0,
            "start_time": datetime.now(),
            "responses": 0
        }

        if not self._debate_start_time:
            self._debate_start_time = datetime.now().isoformat()

    def track_participant_activity(
        self,
        agent_id: str,
        tokens_used: int = 0,
        response_time: float = 0.0
    ) -> None:
        """
        Отследить активность участника

        Args:
            agent_id: ID агента
            tokens_used: Количество использованных токенов
            response_time: Время ответа в секундах
        """
        if agent_id not in self._participants:
            self.register_participant(agent_id)

        participant = self._participants[agent_id]
        participant["tokens_used"] = participant.get("tokens_used", 0) + tokens_used
        participant["responses"] = participant.get("responses", 0) + 1
        participant["last_activity"] = datetime.now()

    def finalize_debate(
        self,
        verdict: str,
        consensus_score: float,
        value_scores: Dict[str, float] = None,
        veto_applied: Dict[str, bool] = None
    ) -> Dict[str, Any]:
        """
        Завершить дебат и записать метрики в Scoreboard

        Args:
            verdict: Верdict (approved, rejected, warning, etc.)
            consensus_score: Общий консенсус (0-1)
            value_scores: Оценки value для каждого агента
            veto_applied: Применялся ли veto для каждого агента

        Returns:
            Словарь с результатами записи
        """
        if not self._scoreboard:
            return {"scoreboard_enabled": False, "reason": "No scoreboard configured"}

        if not self._participants:
            return {"scoreboard_enabled": False, "reason": "No participants tracked"}

        value_scores = value_scores or {}
        veto_applied = veto_applied or {}

        results = {}
        debate_end_time = datetime.now()
        debate_duration = (
            (debate_end_time - datetime.fromisoformat(self._debate_start_time)).total_seconds()
            if self._debate_start_time else 0
        )

        for agent_id, participant in self._participants.items():
            # Формируем outcome для каждого участника
            outcome = {
                "consensus_score": consensus_score,
                "tokens_used": participant.get("tokens_used", 0),
                "response_time": debate_duration / max(len(self._participants), 1),
                "verdict": verdict,
                "value_score": value_scores.get(agent_id, 0.5),
                "veto_applied": veto_applied.get(agent_id, False),
                "debate_id": self.debate_id
            }

            # Записываем в scoreboard
            try:
                from agent_scoreboard import AgentMetrics
                metrics = self._scoreboard.record_debate(agent_id, outcome)
                results[agent_id] = {
                    "recorded": True,
                    "value_score": metrics.value_score,
                    "cost_efficiency": metrics.cost_efficiency
                }
            except Exception as e:
                results[agent_id] = {
                    "recorded": False,
                    "error": str(e)
                }

        return {
            "scoreboard_enabled": True,
            "participants_count": len(self._participants),
            "results": results
        }

    def set_scoreboard(self, scoreboard) -> None:
        """Установить Scoreboard (для отложенной инициализации)"""
        self._scoreboard = scoreboard

    def get_scoreboard(self):
        """Получить текущий Scoreboard"""
        return self._scoreboard


# ============================================================================
# STATE CONTRACTS (Input/Output Validation)
# ============================================================================

class StateContracts:
    """
    Валидация контрактов состояний

    Каждое состояние:
    - Input contract (что должно прийти)
    - Output contract (what должно выйти)
    - Pre-condition (перед выполнением)
    - Post-condition (после выполнения)
    """

    @staticmethod
    def validate_draft_input(data: Any) -> bool:
        """Валидация input для DRAFT"""
        if not isinstance(data, DraftInput):
            return False
        return bool(data.task and data.task_type)

    @staticmethod
    def validate_draft_output(artifact: Artifact) -> bool:
        """Валидация output из DRAFT"""
        return (
            artifact.content_type == "code" and
            len(artifact.content) > 0 and
            "rationale" in artifact.metadata
        )

    @staticmethod
    def validate_normalize_output(artifact: Artifact) -> bool:
        """Валидация output из NORMALIZE"""
        return (
            artifact.content_type == "canonical_code" and
            "normalization_stats" in artifact.metadata
        )

    @staticmethod
    def validate_siege_output(artifact: Artifact) -> bool:
        """Валидация output из SIEGE"""
        return (
            artifact.content_type == "vulnerability_list" and
            "vulnerabilities" in artifact.metadata
        )

    @staticmethod
    def validate_fortify_output(artifact: Artifact) -> bool:
        """Валидация output из FORTIFY"""
        # КРИТИЧНО: проверяем constraints
        return (
            artifact.content_type == "code" and
            "new_symbols_added" in artifact.metadata and
            len(artifact.metadata.get("new_symbols_added", [])) == 0
            # Builder не должен добавлять новые subsystems!
        )

    @staticmethod
    def validate_freeze_output(artifact: Artifact) -> bool:
        """Валидация output из FREEZE"""
        return (
            artifact.content_type == "immutable_artifact" and
            "ast_fingerprint" in artifact.metadata and
            "frozen_at" in artifact.metadata
        )

    # ========================================================================
    # EVOLUTION CYCLE VALIDATORS
    # ========================================================================

    @staticmethod
    def validate_stagnation_report(data: Any) -> bool:
        """Валидация StagnationReport"""
        if not isinstance(data, StagnationReport):
            return False
        return (
            isinstance(data.has_changes, bool) and
            isinstance(data.is_no_op, bool) and
            0.0 <= data.jaccard_similarity <= 1.0
        )

    @staticmethod
    def validate_grounding_result(data: Any) -> bool:
        """Валидация GroundingResult"""
        if not isinstance(data, GroundingResult):
            return False
        return (
            isinstance(data.tests_executed, bool) and
            isinstance(data.tests_passed, int) and
            isinstance(data.tests_failed, int) and
            data.tests_passed >= 0 and
            data.tests_failed >= 0
        )

    @staticmethod
    def validate_fresh_eye_result(data: Any) -> bool:
        """Валидация FreshEyeResult"""
        if not isinstance(data, FreshEyeResult):
            return False
        return (
            data.status in ["approved", "rejected", "needs_changes"] and
            0.0 <= data.confidence <= 1.0 and
            isinstance(data.issues_found, list)
        )

    @staticmethod
    def validate_senior_auditor_decision(data: Any) -> bool:
        """Валидация SeniorAuditorDecision"""
        if not isinstance(data, SeniorAuditorDecision):
            return False
        return (
            data.status in ["approved", "revert", "reject"] and
            0.0 <= data.confidence <= 1.0 and
            isinstance(data.constitutional_violations, list)
        )


# ============================================================================
# ENTROPY MARKER (Фиксация состояния модели)
# ============================================================================

@dataclass
class EntropyMarker:
    """
    Маркер энтропии - фиксация состояния "мозга" в момент принятия решения.

    Зачем это нужно:
    - Если через месяц запустить Replay и увидеть другой результат,
      можно сравнить system_fingerprint
    - Если fingerprint изменился → провайдер обновил модель "под капотом"
    - Старые дебаты больше не валидны для этой версии "мозга"

    Использование:
    - Добавляется в каждый Artifact.metadata
    - Сохраняется в DecisionTrace для аудита
    """
    model_version: str                    # Версия модели (например "gpt-4o-2024-11-20")
    model_family: str                     # Семейство (openai, anthropic, google, xai)
    temperature: float                    # Temperature параметр
    top_p: Optional[float] = None         # top_p sampling
    seed: Optional[int] = None            # Seed если используется
    system_fingerprint: str = ""          # Уникальный ID инстанса модели от API
    confidence_score: float = 0.0         # logprobs/confidence для ключевого решения

    def to_dict(self) -> Dict[str, Any]:
        """Сериализация в словарь"""
        return {
            "model_version": self.model_version,
            "model_family": self.model_family,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "seed": self.seed,
            "system_fingerprint": self.system_fingerprint,
            "confidence_score": self.confidence_score,
        }

    @property
    def is_deterministic(self) -> bool:
        """Можно ли считать этот вызов детерминированным"""
        return self.seed is not None and self.temperature == 0.0

    @property
    def fragility_index(self) -> float:
        """
        Индекс хрупкости решения.
        High fragility = высокая вероятность изменения при другом seed
        """
        uncertainty = self.temperature if self.temperature > 0 else 0.1
        if self.seed is not None:
            uncertainty *= 0.5  # Seed снижает неопределённость

        return (1.0 - self.confidence_score) * uncertainty

    def get_warning(self) -> Optional[str]:
        """Возвращает предупреждение если решение нестабильно"""
        fragility = self.fragility_index

        if fragility > 0.3:
            return f"High fragility! ({fragility:.2f}) - Auditor is unsure and Intent is borderline."
        if self.temperature > 0.7 and self.seed is None:
            return f"High uncertainty (temp={self.temperature}, no seed) - Replay may differ."
        if self.system_fingerprint:
            return None  # Есть fingerprint - можно отследить изменения
        return "Missing system_fingerprint - Cannot detect model updates."

    @classmethod
    def from_model_response(
        cls,
        model_version: str,
        model_family: str,
        temperature: float,
        response_metadata: Dict[str, Any]
    ) -> "EntropyMarker":
        """
        Создаёт EntropyMarker из ответа LLM API.

        Args:
            model_version: Версия модели
            model_family: Семейство модели
            temperature: Использованная температура
            response_metadata: Metadata из ответа API (system_fingerprint, logprobs и т.д.)
        """
        return cls(
            model_version=model_version,
            model_family=model_family,
            temperature=temperature,
            top_p=response_metadata.get("top_p"),
            seed=response_metadata.get("seed"),
            system_fingerprint=response_metadata.get("system_fingerprint", ""),
            confidence_score=response_metadata.get("confidence_score", 0.0)
        )


# ============================================================================
# DECISION TRACE (для обучения Orchestrator)
# ============================================================================

@dataclass
class DecisionTrace:
    """
    Decision trace для машинного анализа

    Используется для:
    - Отладки
    - Обучения Orchestrator
    - Доказательства принятия решения
    - Аудита изменений модели через EntropyMarker
    """
    path: List[str]
    metrics: Dict[str, float]
    signals: Dict[str, Any]
    escalations: List[str] = field(default_factory=list)
    state_transitions: List[StateTransition] = field(default_factory=list)
    # Entropy markers для отслеживания состояния моделей
    entropy_markers: Dict[str, EntropyMarker] = field(default_factory=dict)
    # Ключ - state_id, значение - EntropyMarker для этого перехода

    def to_json(self) -> str:
        """Сериализация в JSON"""
        return json.dumps({
            "path": self.path,
            "metrics": self.metrics,
            "signals": self.signals,
            "escalations": self.escalations,
            "state_transitions": [
                {
                    "state_id": t.state_id,
                    "timestamp": t.timestamp,
                    "from_state": t.from_state,
                    "to_state": t.to_state,
                    "artifact_hash": t.artifact_hash
                }
                for t in self.state_transitions
            ],
            "entropy_markers": {
                state_id: marker.to_dict()
                for state_id, marker in self.entropy_markers.items()
            }
        }, ensure_ascii=False, indent=2)

    def add_entropy_marker(self, state_id: str, marker: EntropyMarker) -> None:
        """Добавить EntropyMarker для перехода состояния"""
        self.entropy_markers[state_id] = marker

    def get_entropy_marker(self, state_id: str) -> Optional[EntropyMarker]:
        """Получить EntropyMarker для конкретного состояния"""
        return self.entropy_markers.get(state_id)

    def check_entropy_drift(self, other_trace: "DecisionTrace") -> List[str]:
        """
        Проверить drift энтропии между двумя трейсами.

        Возвращает список предупреждений если:
        - model_version изменился
        - system_fingerprint изменился
        - significally разные temperature/seed
        """
        warnings = []

        for state_id, my_marker in self.entropy_markers.items():
            other_marker = other_trace.get_entropy_marker(state_id)

            if other_marker is None:
                warnings.append(f"State {state_id}: No entropy marker in other trace")
                continue

            if my_marker.model_version != other_marker.model_version:
                warnings.append(
                    f"State {state_id}: Model version changed "
                    f"({my_marker.model_version} -> {other_marker.model_version})"
                )

            if my_marker.system_fingerprint and other_marker.system_fingerprint:
                if my_marker.system_fingerprint != other_marker.system_fingerprint:
                    warnings.append(
                        f"State {state_id}: System fingerprint changed! "
                        f"Model may have been updated."
                    )

        return warnings

    def get_fragility_report(self) -> Dict[str, Any]:
        """
        Отчёт о хрупкости решений.

        Возвращает aggregated fragility metrics для всех переходов.
        """
        if not self.entropy_markers:
            return {"error": "No entropy markers in trace"}

        fragility_scores = []
        high_fragility_states = []

        for state_id, marker in self.entropy_markers.items():
            fragility = marker.fragility_index
            fragility_scores.append(fragility)

            if fragility > 0.3:
                warning = marker.get_warning()
                high_fragility_states.append({
                    "state": state_id,
                    "fragility": fragility,
                    "warning": warning
                })

        avg_fragility = sum(fragility_scores) / len(fragility_scores) if fragility_scores else 0.0

        return {
            "average_fragility": avg_fragility,
            "max_fragility": max(fragility_scores) if fragility_scores else 0.0,
            "high_fragility_count": len(high_fragility_states),
            "high_fragility_states": high_fragility_states,
            "overall_risk": "HIGH" if avg_fragility > 0.25 else "MEDIUM" if avg_fragility > 0.15 else "LOW"
        }


# ============================================================================
# CONSENSUS CALCULATOR V3.0 (с Jaccard)
# ============================================================================

class ConsensusCalculatorV3:
    """
    Расчет консенсуса с AST fingerprinting

    Формула:
    Consensus = 0.7 * CosineSim + 0.3 * Jaccard(AST)

    Плюс "наказание за трусость":
    if ChangeMagnitude < MIN_EXPECTED and risks > 0:
        consensus *= 0.7
    """

    @staticmethod
    def calculate_consensus(
        solution_a: str,
        solution_b: str,
        fingerprint_a: Set[str],
        fingerprint_b: Set[str],
        risks: List[str]
    ) -> Tuple[float, Dict[str, float]]:
        """
        Полный расчет консенсуса

        Returns:
            (consensus_score, breakdown)
        """
        # 1. Cosine Similarity (семантика)
        # sklearn - опциональная зависимость, gracefully degrade если недоступен
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.metrics.pairwise import cosine_similarity
            import numpy as np

            vectorizer = TfidfVectorizer()
            tfidf_matrix = vectorizer.fit_transform([solution_a, solution_b])
            cosine_sim = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])[0][0]
        except ImportError:
            # sklearn не установлен - используем fallback
            cosine_sim = 0.5  # Нейтральное значение
        except Exception:
            cosine_sim = 0.0

        # 2. Jaccard (структура)
        jaccard_sim = calculate_jaccard(fingerprint_a, fingerprint_b)

        # 3. Change Magnitude (наказание за трусость)
        change_magnitude = len(fingerprint_a.symmetric_difference(fingerprint_b))
        min_expected = 3  # Минимум 3 символа должно меняться

        if change_magnitude < min_expected and len(risks) > 0:
            # Builder "сделал вид, что исправил"
            penalty = 0.7
        else:
            penalty = 1.0

        # 4. Финальная формула
        consensus = (0.7 * cosine_sim + 0.3 * jaccard_sim) * penalty

        breakdown = {
            "cosine_similarity": float(cosine_sim),
            "jaccard_similarity": float(jaccard_sim),
            "change_magnitude": change_magnitude,
            "penalty_applied": penalty < 1.0,
            "final_consensus": float(consensus)
        }

        return consensus, breakdown


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    # Core
    "DebateState",
    "DebateStateMachine",
    "StructuralFingerprint",
    "calculate_jaccard",
    "ConsensusCalculatorV3",
    "StateContracts",
    "DecisionTrace",
    "EntropyMarker",
    # Base artifacts
    "Artifact",
    "StateTransition",
    # Simple debate contracts
    "DraftInput",
    "DraftOutput",
    "NormalizedOutput",
    "VulnerabilityReport",
    "FortifiedOutput",
    "ImmutableArtifact",
    "JudgmentOutcome",
    # Feedback loop contracts
    "FixAssignment",
    "FixOutput",
    "VerifyOutput",
    "ReDebateOutcome",
    "CompleteOutcome",
    # Evolution cycle contracts
    "StagnationReport",
    "GroundingResult",
    "FreshEyeResult",
    "SeniorAuditorDecision",
]
