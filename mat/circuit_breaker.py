"""
Circuit Breaker - Градуированная автономность системы
======================================================

Реализация "Режима Осады" с 4 уровнями автономности:
- 🟢 GREEN: Хозин online, полный доступ
- 🟡 AMBER: Нет связи 2ч + backlog > 5, ограниченный доступ  
- 🔴 RED: Нет связи 6ч + critical issue, канареечные деплои
- ⚫ BLACK: Критическая ошибка, только мониторинг и алерты

Usage:
    from circuit_breaker import CircuitBreaker, AutonomyLevel, OperationType
    
    cb = CircuitBreaker()
    level = cb.check_level()
    
    if cb.can_execute(OperationType.MODIFY_CORE):
        # Выполнить операцию
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
    """Уровни автономности системы"""
    GREEN = "green"      # Полный доступ
    AMBER = "amber"      # Ограниченный доступ
    RED = "red"          # Только канареечные деплои
    BLACK = "black"      # Только мониторинг


class OperationType(Enum):
    """Типы операций для проверки разрешений"""
    READ_ONLY = auto()           # Чтение, анализ
    DEBATE_SAFE = auto()         # Дебаты по безопасным зонам
    SHADOW_AGENT = auto()        # Создание shadow-агентов
    MODIFY_CODE = auto()         # Изменение кода
    MODIFY_CORE = auto()         # Изменение core системы
    ARCHITECTURE_CHANGE = auto() # Архитектурные изменения
    DEPLOY_CANARY = auto()       # Канареечный деплой
    DEPLOY_PRODUCTION = auto()   # Деплой в production
    FULL_AUTONOMY = auto()       # Полная автономия


@dataclass
class CircuitBreakerConfig:
    """Конфигурация Circuit Breaker"""
    # Базовая директория проекта (для абсолютных путей)
    base_dir: Optional[str] = None  # Если None - определяется автоматически

    # Таймауты для перехода между уровнями
    amber_timeout_minutes: int = 120      # 2 часа до AMBER
    red_timeout_minutes: int = 360        # 6 часов до RED

    # Пороги
    amber_backlog_threshold: int = 5      # backlog > 5 для AMBER
    red_critical_threshold: int = 1       # >= 1 critical для RED

    # Канареечный деплой
    canary_traffic_percentage: float = 10.0  # 10% трафика на канарейку
    canary_success_threshold: float = 0.95   # 95% успеха для продолжения

    # Пути (относительные base_dir или абсолютные)
    state_file: str = "memory/circuit_breaker_state.json"
    human_activity_file: str = "memory/human_activity.log"

    # Алерты
    alert_on_black: bool = True
    alert_on_red: bool = True
    alert_callback: Optional[Callable] = None

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


@dataclass
class SystemState:
    """Текущее состояние системы"""
    backlog_size: int = 0
    critical_issues: int = 0
    failed_deployments: int = 0
    last_error: Optional[str] = None
    resource_usage: Dict[str, float] = field(default_factory=dict)


@dataclass
class HumanActivity:
    """Активность человека"""
    last_seen: datetime
    last_action: str
    activity_history: deque = field(default_factory=lambda: deque(maxlen=100))
    
    def minutes_since_last_seen(self) -> float:
        """Минут с последнего контакта"""
        return (datetime.now() - self.last_seen).total_seconds() / 60


class CircuitBreaker:
    """
    Circuit Breaker для управления автономностью системы.
    
    Реализует 4 уровня автономности с автоматическим переходом
    между ними на основе активности человека и состояния системы.
    """
    
    # Разрешения по уровням и типам операций
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
            OperationType.MODIFY_CORE: False,  # Требует подтверждения
            OperationType.ARCHITECTURE_CHANGE: False,
            OperationType.DEPLOY_CANARY: True,
            OperationType.DEPLOY_PRODUCTION: False,
            OperationType.FULL_AUTONOMY: False,
        },
        AutonomyLevel.RED: {
            OperationType.READ_ONLY: True,
            OperationType.DEBATE_SAFE: True,
            OperationType.SHADOW_AGENT: True,
            OperationType.MODIFY_CODE: False,  # Только через канарейку
            OperationType.MODIFY_CORE: False,
            OperationType.ARCHITECTURE_CHANGE: False,
            OperationType.DEPLOY_CANARY: True,  # Только канареечные
            OperationType.DEPLOY_PRODUCTION: False,
            OperationType.FULL_AUTONOMY: False,
        },
        AutonomyLevel.BLACK: {
            OperationType.READ_ONLY: True,  # Только мониторинг
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
        
        # Загружаем состояние
        self._load_state()
        self._load_human_activity()
        
        logger.info(f"Circuit Breaker initialized at level: {self.current_level.value}")
    
    def check_level(self) -> AutonomyLevel:
        """
        Определить текущий уровень автономности.
        
        Returns:
            AutonomyLevel: Текущий уровень автономности
        """
        # Проверяем BLACK (критическая ошибка)
        if self.system_state.critical_issues >= self.config.red_critical_threshold * 2:
            if self.current_level != AutonomyLevel.BLACK:
                self._escalate(AutonomyLevel.BLACK, "Multiple critical issues detected")
            return AutonomyLevel.BLACK
        
        # Проверяем RED (долгое отсутствие + критические проблемы)
        if self.human_activity:
            minutes_away = self.human_activity.minutes_since_last_seen()
            
            if (minutes_away >= self.config.red_timeout_minutes and 
                self.system_state.critical_issues >= self.config.red_critical_threshold):
                if self.current_level != AutonomyLevel.RED:
                    self._escalate(AutonomyLevel.RED, 
                        f"No human contact for {minutes_away:.0f}min + {self.system_state.critical_issues} critical issues")
                return AutonomyLevel.RED
            
            # Проверяем AMBER (отсутствие + backlog)
            if (minutes_away >= self.config.amber_timeout_minutes and 
                self.system_state.backlog_size >= self.config.amber_backlog_threshold):
                if self.current_level == AutonomyLevel.GREEN:
                    self._escalate(AutonomyLevel.AMBER,
                        f"No human contact for {minutes_away:.0f}min + backlog {self.system_state.backlog_size}")
                return AutonomyLevel.AMBER
        
        # Если человек появился — сбрасываем до GREEN
        if (self.current_level != AutonomyLevel.GREEN and 
            self.human_activity and 
            self.human_activity.minutes_since_last_seen() < self.config.amber_timeout_minutes):
            self._de_escalate(AutonomyLevel.GREEN, "Human activity detected")
        
        return self.current_level
    
    def can_execute(self, operation: OperationType) -> bool:
        """
        Проверить, можно ли выполнить операцию на текущем уровне.
        
        Args:
            operation: Тип операции
            
        Returns:
            bool: True если операция разрешена
        """
        level = self.check_level()
        allowed = self.PERMISSIONS.get(level, {}).get(operation, False)
        
        if not allowed:
            logger.warning(f"Operation {operation.name} denied at level {level.value}")
        
        return allowed
    
    def require_approval(self, operation: OperationType) -> bool:
        """
        Проверить, требуется ли операция human approval.
        
        Args:
            operation: Тип операции
            
        Returns:
            bool: True если требуется подтверждение
        """
        level = self.check_level()
        
        # На GREEN не требуется (кроме архитектурных)
        if level == AutonomyLevel.GREEN:
            return operation in [OperationType.ARCHITECTURE_CHANGE]
        
        # На AMBER требуется для core изменений
        if level == AutonomyLevel.AMBER:
            return operation in [OperationType.MODIFY_CORE, OperationType.ARCHITECTURE_CHANGE, 
                                OperationType.DEPLOY_PRODUCTION]
        
        # На RED и BLACK — почти всё требует подтверждения
        if level in [AutonomyLevel.RED, AutonomyLevel.BLACK]:
            return operation != OperationType.READ_ONLY
        
        return True
    
    def record_human_activity(self, action: str = "activity") -> None:
        """
        Записать активность человека.
        
        Args:
            action: Описание действия
        """
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
        
        # Сбрасываем алерты
        self._alert_sent = {level: False for level in self._alert_sent}
        
        # Сохраняем
        self._save_human_activity()
        
        # Если был не GREEN — сбрасываем
        if self.current_level != AutonomyLevel.GREEN:
            self._de_escalate(AutonomyLevel.GREEN, f"Human activity: {action}")
        
        logger.info(f"Human activity recorded: {action}")
    
    def update_system_state(self, state: SystemState) -> None:
        """
        Обновить состояние системы.
        
        Args:
            state: Новое состояние
        """
        self.system_state = state
        self._save_state()
        
        # Перепроверяем уровень
        self.check_level()
    
    def _escalate(self, new_level: AutonomyLevel, reason: str) -> None:
        """Повысить уровень автономности (ограничить доступ)"""
        old_level = self.current_level
        self.current_level = new_level
        
        self._level_history.append({
            "timestamp": datetime.now().isoformat(),
            "from": old_level.value,
            "to": new_level.value,
            "reason": reason
        })
        
        logger.warning(f"🚨 ESCALATION: {old_level.value} → {new_level.value} | {reason}")
        
        # Отправляем алерт
        self._send_alert(new_level, reason)
        
        self._save_state()
    
    def _de_escalate(self, new_level: AutonomyLevel, reason: str) -> None:
        """Понизить уровень автономности (расширить доступ)"""
        old_level = self.current_level
        self.current_level = new_level
        
        self._level_history.append({
            "timestamp": datetime.now().isoformat(),
            "from": old_level.value,
            "to": new_level.value,
            "reason": reason
        })
        
        logger.info(f"✅ DE-ESCALATION: {old_level.value} → {new_level.value} | {reason}")
        
        self._save_state()
    
    def _send_alert(self, level: AutonomyLevel, reason: str) -> None:
        """Отправить алерт о смене уровня"""
        if level == AutonomyLevel.AMBER and not self._alert_sent[level]:
            message = f"⚠️ AMBER Alert: Autonomy restricted | {reason}"
            logger.warning(message)
            self._alert_sent[level] = True
            
            if self.config.alert_callback:
                self.config.alert_callback(level, message)
        
        elif level == AutonomyLevel.RED and not self._alert_sent[level]:
            message = f"🚨 RED Alert: Limited autonomy mode | {reason}"
            logger.error(message)
            self._alert_sent[level] = True
            
            if self.config.alert_on_red and self.config.alert_callback:
                self.config.alert_callback(level, message)
        
        elif level == AutonomyLevel.BLACK and not self._alert_sent[level]:
            message = f"☠️ BLACK Alert: System halted | {reason}"
            logger.critical(message)
            self._alert_sent[level] = True
            
            if self.config.alert_on_black and self.config.alert_callback:
                self.config.alert_callback(level, message)
    
    def _save_state(self) -> None:
        """Сохранить состояние в файл"""
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
        """Загрузить состояние из файла"""
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
        """Сохранить активность человека"""
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
        """Загрузить активность человека"""
        path = Path(self.config.get_absolute_path(self.config.human_activity_file))
        if not path.exists():
            # По умолчанию — активность сейчас
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
        """Получить полный статус Circuit Breaker"""
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
            "history": list(self._level_history)[-10:]  # Последние 10 переходов
        }
    
    def _get_level_emoji(self, level: AutonomyLevel) -> str:
        """Получить эмодзи для уровня"""
        return {
            AutonomyLevel.GREEN: "🟢",
            AutonomyLevel.AMBER: "🟡",
            AutonomyLevel.RED: "🔴",
            AutonomyLevel.BLACK: "⚫"
        }.get(level, "❓")


# =============================================================================
# HUMAN ACTIVITY DETECTOR
# =============================================================================

class HumanActivityDetector:
    """
    Детектор активности человека.
    
    Отслеживает различные источники активности:
    - CLI команды
    - Web UI взаимодействия
    - Git коммиты
    - Файловые операции
    """
    
    def __init__(self, circuit_breaker: CircuitBreaker):
        self.cb = circuit_breaker
        self._watchers: List[Callable] = []
    
    def record_cli_command(self, command: str) -> None:
        """Записать CLI команду как активность"""
        self.cb.record_human_activity(f"cli: {command[:50]}")
    
    def record_web_ui_action(self, action: str, details: str = "") -> None:
        """Записать действие в Web UI"""
        self.cb.record_human_activity(f"ui: {action} {details[:30]}")
    
    def record_git_commit(self, message: str) -> None:
        """Записать git коммит как активность"""
        self.cb.record_human_activity(f"git: {message[:50]}")
    
    def record_file_edit(self, file_path: str) -> None:
        """Записать редактирование файла"""
        self.cb.record_human_activity(f"edit: {Path(file_path).name}")
    
    def register_watcher(self, watcher: Callable) -> None:
        """Зарегистрировать кастомный watcher"""
        self._watchers.append(watcher)


# =============================================================================
# DECORATOR FOR AUTOMATIC CHECKS
# =============================================================================

def require_autonomy_level(min_level: AutonomyLevel):
    """
    Декоратор для проверки уровня автономности.
    
    Usage:
        @require_autonomy_level(AutonomyLevel.GREEN)
        def modify_core_system():
            pass
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            # Получаем circuit breaker из kwargs или глобального контекста
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


# Глобальный instance (для простоты использования)
_global_circuit_breaker: Optional[CircuitBreaker] = None


def _get_global_circuit_breaker() -> Optional[CircuitBreaker]:
    """Получить глобальный Circuit Breaker"""
    return _global_circuit_breaker


def set_global_circuit_breaker(cb: CircuitBreaker) -> None:
    """Установить глобальный Circuit Breaker"""
    global _global_circuit_breaker
    _global_circuit_breaker = cb


# =============================================================================
# TESTS
# =============================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    
    print("=" * 70)
    print("CIRCUIT BREAKER TESTS")
    print("=" * 70)
    
    # Тест 1: Инициализация
    print("\n[Test 1] Initialization...")
    cb = CircuitBreaker()
    print(f"  Initial level: {cb.current_level.value}")
    print(f"  ✓ Circuit Breaker created")
    
    # Тест 2: Проверка разрешений на GREEN
    print("\n[Test 2] Permissions on GREEN...")
    assert cb.can_execute(OperationType.MODIFY_CORE) == True
    assert cb.can_execute(OperationType.DEPLOY_PRODUCTION) == True
    print(f"  ✓ All operations allowed on GREEN")
    
    # Тест 3: Симуляция AMBER
    print("\n[Test 3] AMBER level simulation...")
    cb.human_activity.last_seen = datetime.now() - timedelta(minutes=130)
    cb.system_state.backlog_size = 6
    level = cb.check_level()
    print(f"  Level: {level.value}")
    assert level == AutonomyLevel.AMBER
    assert cb.can_execute(OperationType.MODIFY_CODE) == True
    assert cb.can_execute(OperationType.MODIFY_CORE) == False
    print(f"  ✓ AMBER restrictions working")
    
    # Тест 4: Возврат к GREEN
    print("\n[Test 4] Return to GREEN...")
    cb.record_human_activity("test_action")
    level = cb.check_level()
    print(f"  Level: {level.value}")
    assert level == AutonomyLevel.GREEN
    print(f"  ✓ Back to GREEN")
    
    # Тест 5: Симуляция RED
    print("\n[Test 5] RED level simulation...")
    cb.human_activity.last_seen = datetime.now() - timedelta(minutes=400)
    cb.system_state.critical_issues = 1  # 1 критическая проблема = RED
    level = cb.check_level()
    print(f"  Level: {level.value}")
    assert level == AutonomyLevel.RED
    assert cb.can_execute(OperationType.DEPLOY_CANARY) == True
    assert cb.can_execute(OperationType.MODIFY_CODE) == False
    print(f"  ✓ RED restrictions working")
    
    # Тест 6: Статус
    print("\n[Test 6] Get status...")
    status = cb.get_status()
    print(f"  Status keys: {list(status.keys())}")
    assert "current_level" in status
    assert "permissions" in status
    print(f"  ✓ Status retrieved")
    
    # Тест 7: Human Activity Detector
    print("\n[Test 7] Human Activity Detector...")
    detector = HumanActivityDetector(cb)
    detector.record_cli_command("python test.py")
    level = cb.check_level()
    assert level == AutonomyLevel.GREEN
    print(f"  ✓ Activity detector working")
    
    print("\n" + "=" * 70)
    print("All tests passed!")
    print("=" * 70)


# =============================================================================
# CANARY DEPLOYMENT
# =============================================================================

@dataclass
class CanaryResult:
    """Результат канареечного деплоя"""
    success: bool
    traffic_percentage: float
    error_rate: float
    latency_p95_ms: float
    total_requests: int
    error_messages: List[str] = field(default_factory=list)
    recommendation: str = ""


class CanaryDeployment:
    """
    Канареечный деплой для уровня RED.

    Постепенно прокачивает трафик на новую версию,
    откатывается если detecting проблемы.
    """

    def __init__(self, config: CircuitBreakerConfig):
        self.config = config
        self._active_canaries: Dict[str, Dict] = {}  # deployment_id -> info

    def start_canary(self, deployment_id: str, old_version: str, new_version: str) -> Dict[str, Any]:
        """
        Начать канареечный деплой

        Args:
            deployment_id: Уникальный ID деплоя
            old_version: Текущая версия
            new_version: Новая версия

        Returns:
            Стартовая информация
        """
        self._active_canaries[deployment_id] = {
            "old_version": old_version,
            "new_version": new_version,
            "started_at": datetime.now().isoformat(),
            "current_traffic": self.config.canary_traffic_percentage,
            "status": "running",
            "checks": []
        }

        return {
            "deployment_id": deployment_id,
            "traffic_percentage": self.config.canary_traffic_percentage,
            "estimated_steps": self._calculate_steps(),
            "status": "started"
        }

    def check_canary(self, deployment_id: str, metrics: Dict[str, Any]) -> CanaryResult:
        """
        Проверить метрики канареечного деплоя

        Args:
            deployment_id: ID деплоя
            metrics: Метрики (error_rate, latency_p95, total_requests, errors)

        Returns:
            CanaryResult с рекомендацией
        """
        if deployment_id not in self._active_canaries:
            return CanaryResult(
                success=False,
                traffic_percentage=0,
                error_rate=1.0,
                latency_p95_ms=999999,
                total_requests=0,
                error_messages=["Deployment not found"],
                recommendation="abort"
            )

        canary = self._active_canaries[deployment_id]

        error_rate = metrics.get("error_rate", 0)
        latency_p95 = metrics.get("latency_p95_ms", 0)
        total_requests = metrics.get("total_requests", 0)
        errors = metrics.get("errors", [])

        # Проверяем пороги
        success = error_rate < (1 - self.config.canary_success_threshold)
        latency_ok = latency_p95 < 1000  # 1 second threshold

        # Формируем рекомендацию
        if success and latency_ok:
            # Увеличиваем трафик
            current_traffic = canary["current_traffic"]
            new_traffic = min(current_traffic + 20, 100)

            if new_traffic >= 100:
                canary["status"] = "complete"
                recommendation = "full_rollout"
            else:
                canary["current_traffic"] = new_traffic
                recommendation = f"increase_to_{new_traffic}%"
        else:
            # Откат
            canary["status"] = "failed"
            recommendation = "rollback"

        result = CanaryResult(
            success=success and latency_ok,
            traffic_percentage=canary["current_traffic"],
            error_rate=error_rate,
            latency_p95_ms=latency_p95,
            total_requests=total_requests,
            error_messages=errors,
            recommendation=recommendation
        )

        canary["checks"].append({
            "timestamp": datetime.now().isoformat(),
            "result": result.__dict__
        })

        return result

    def rollback(self, deployment_id: str) -> Dict[str, Any]:
        """Откатить канареечный деплой"""
        if deployment_id in self._active_canaries:
            self._active_canaries[deployment_id]["status"] = "rolled_back"
            del self._active_canaries[deployment_id]

        return {
            "deployment_id": deployment_id,
            "status": "rolled_back",
            "timestamp": datetime.now().isoformat()
        }

    def _calculate_steps(self) -> int:
        """Рассчитать количество шагов для полного деплоя"""
        steps = []
        traffic = self.config.canary_traffic_percentage

        while traffic < 100:
            steps.append(traffic)
            traffic = min(traffic + 20, 100)

        return len(steps)


# =============================================================================
# ALERT SYSTEM
# =============================================================================

class AlertChannel:
    """Базовый класс для алерт-каналов"""

    def send(self, level: AutonomyLevel, message: str) -> bool:
        """Отправить алерт"""
        raise NotImplementedError


class ConsoleAlert(AlertChannel):
    """Консольный алерт (для отладки)"""

    def send(self, level: AutonomyLevel, message: str) -> bool:
        print(f"[{level.value.upper()} ALERT] {message}")
        return True


class EmailAlert(AlertChannel):
    """Email алерты"""

    def __init__(self, smtp_host: str, smtp_port: int, from_addr: str, to_addr: str,
                 username: str = None, password: str = None):
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.from_addr = from_addr
        self.to_addr = to_addr
        self.username = username
        self.password = password

    def send(self, level: AutonomyLevel, message: str) -> bool:
        """Отправить email алерт"""
        try:
            import smtplib
            from email.message import EmailMessage

            msg = EmailMessage()
            msg["From"] = self.from_addr
            msg["To"] = self.to_addr
            msg["Subject"] = f"[{level.value.upper()}] Multi-Agent System Alert"
            msg.set_content(message)

            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                if self.username and self.password:
                    server.starttls()
                    server.login(self.username, self.password)
                server.send_message(msg)

            logger.info(f"Email alert sent: {level.value}")
            return True
        except Exception as e:
            logger.error(f"Failed to send email alert: {e}")
            return False


class TelegramAlert(AlertChannel):
    """Telegram алерты через бот"""

    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.api_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    def send(self, level: AutonomyLevel, message: str) -> bool:
        """Отправить Telegram алерт"""
        try:
            import requests

            emoji = {
                AutonomyLevel.AMBER: "⚠️",
                AutonomyLevel.RED: "🚨",
                AutonomyLevel.BLACK: "☠️"
            }.get(level, "❓")

            text = f"{emoji} *{level.value.upper()} Alert*\n\n{message}"

            response = requests.post(
                self.api_url,
                json={
                    "chat_id": self.chat_id,
                    "text": text,
                    "parse_mode": "Markdown"
                },
                timeout=10
            )

            if response.status_code == 200:
                logger.info(f"Telegram alert sent: {level.value}")
                return True
            else:
                logger.error(f"Telegram API error: {response.text}")
                return False
        except Exception as e:
            logger.error(f"Failed to send Telegram alert: {e}")
            return False


class CompositeAlert(AlertChannel):
    """Композиция нескольких каналов алертов"""

    def __init__(self, channels: List[AlertChannel] = None):
        self.channels = channels or []

    def add_channel(self, channel: AlertChannel) -> None:
        """Добавить канал"""
        self.channels.append(channel)

    def send(self, level: AutonomyLevel, message: str) -> bool:
        """Отправить алерт во все каналы"""
        results = []
        for channel in self.channels:
            try:
                results.append(channel.send(level, message))
            except Exception:
                results.append(False)

        # Успех если хотя бы один канал сработал
        return any(results)


def setup_alerts(config: CircuitBreakerConfig) -> AlertChannel:
    """
    Настроить алерты из конфигурации или переменных окружения

    Args:
        config: Конфигурация Circuit Breaker

    Returns:
        AlertChannel: Композитный канал алертов
    """
    import os

    composite = CompositeAlert()

    # Всегда добавляем консоль
    composite.add_channel(ConsoleAlert())

    # Telegram если есть токен
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if bot_token and chat_id:
        composite.add_channel(TelegramAlert(bot_token, chat_id))

    # Email если есть настройки
    smtp_host = os.environ.get("SMTP_HOST")
    smtp_port = os.environ.get("SMTP_PORT", "587")
    from_addr = os.environ.get("EMAIL_FROM")
    to_addr = os.environ.get("EMAIL_TO")

    if smtp_host and from_addr and to_addr:
        composite.add_channel(EmailAlert(
            smtp_host=smtp_host,
            smtp_port=int(smtp_port),
            from_addr=from_addr,
            to_addr=to_addr,
            username=os.environ.get("EMAIL_USER"),
            password=os.environ.get("EMAIL_PASSWORD")
        ))

    return composite


# =============================================================================
# INTEGRATION WITH autonomous_executor
# =============================================================================

class CircuitBreakerExecutor:
    """
    Интеграция Circuit Breaker с autonomous_executor

    Автоматически проверяет разрешения перед выполнением операций.
    """

    def __init__(self, circuit_breaker: CircuitBreaker,
                 canary: Optional[CanaryDeployment] = None):
        self.cb = circuit_breaker
        self.canary = canary or CanaryDeployment(circuit_breaker.config)

    async def execute_with_breaker(
        self,
        operation: OperationType,
        func: Callable,
        *args,
        **kwargs
    ) -> Any:
        """
        Выполнить операцию с проверкой Circuit Breaker

        Args:
            operation: Тип операции
            func: Функция для выполнения
            *args: Аргументы функции
            **kwargs: Ключевые аргументы функции

        Returns:
            Результат функции

        Raises:
            PermissionError: Если операция не разрешена
        """
        level = self.cb.check_level()

        # Проверяем разрешение
        if not self.cb.can_execute(operation):
            raise PermissionError(
                f"Operation {operation.name} not allowed at level {level.value}"
            )

        # Проверяем требуется ли подтверждение
        if self.cb.require_approval(operation):
            logger.warning(f"Operation {operation.name} requires approval at level {level.value}")

            # На AMBER/RED можно продолжить с ограничениями
            if level in [AutonomyLevel.AMBER, AutonomyLevel.RED]:
                # Логика подтверждения здесь
                pass

        # На RED уровне для деплоя используем канарейку
        if level == AutonomyLevel.RED and operation == OperationType.DEPLOY_PRODUCTION:
            logger.info("Using canary deployment for RED level")
            # Запуск канареечного деплоя
            # ...

        # Выполняем операцию
        try:
            result = await func(*args, **kwargs) if kwargs.get('async', False) else func(*args, **kwargs)
            return result
        except Exception as e:
            logger.error(f"Operation {operation.name} failed: {e}")
            self.cb.system_state.last_error = str(e)
            self.cb.system_state.failed_deployments += 1
            raise


__all__ = [
    # Core
    "AutonomyLevel",
    "OperationType",
    "CircuitBreaker",
    "CircuitBreakerConfig",
    "SystemState",
    "HumanActivity",
    # Human detection
    "HumanActivityDetector",
    # Canary
    "CanaryDeployment",
    "CanaryResult",
    # Alerts
    "AlertChannel",
    "ConsoleAlert",
    "EmailAlert",
    "TelegramAlert",
    "CompositeAlert",
    "setup_alerts",
    # Integration
    "CircuitBreakerExecutor",
    # Decorator
    "require_autonomy_level",
    "set_global_circuit_breaker"
]
