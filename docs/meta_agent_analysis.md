# Анализ Мета-Агента ProjectCurator

> **Версия:** 1.0.0  
> **Дата:** 2025-02-25  
> **Компонент:** `mat/project_curator.py`

---

## 1. Обзор архитектуры

### 1.1 Роль в системе

```
┌─────────────────────────────────────────────────────────────────┐
│                     PROJECT CURATOR                              │
│                    (Chief Architect)                             │
│                                                                  │
│  "While Builder and Skeptic argue about a 10-line function,    │
│   the Architect sees that the entire module is obsolete"        │
└─────────────────────────────────────────────────────────────────┘
                              │
         ┌────────────────────┼────────────────────┐
         ▼                    ▼                    ▼
   ┌───────────┐      ┌──────────────┐     ┌─────────────┐
   │ TaskQueue │      │CircuitBreaker│     │ DebatePipe  │
   │ (backlog) │      │ (autonomy)   │     │ (execution) │
   └───────────┘      └──────────────┘     └─────────────┘
```

### 1.2 Ключевые функции

| Функция | Описание | Статус |
|---------|----------|--------|
| Анализ модулей | Оценка архитектурных решений | ✅ Реализовано |
| Планирование задач | Создание WorkPlan из целей | ✅ Реализовано |
| Выбор агентов | Domain-specific selection | ✅ Реализовано |
| Интеграция с CB | Проверка AutonomyLevel | ✅ Реализовано |
| Защита путей | Protected paths check | ✅ Реализовано |
| Execution | Запуск Debate Pipeline | ⚠️ Заглушка |

---

## 2. Структура данных

### 2.1 CuratorDecision (Enum)

```python
class CuratorDecision(Enum):
    PROCEED = "proceed"      # Продолжить как есть
    MODIFY = "modify"        # Изменить подход
    SPLIT = "split"          # Разбить задачу
    ESCALATE = "escalate"    # Эскалировать человеку
    BLOCK = "block"          # Заблокировать (опасно)
```

### 2.2 Task (Dataclass)

```python
@dataclass
class Task:
    id: str                    # task_{timestamp_ms}
    task_type: str             # ANALYZE, DEBATE, etc.
    title: str                 # Описание
    priority: str              # P0_CRITICAL → P3_LOW
    target_module: str         # Целевой модуль
    description: str           # Детали
    depends_on: List[str]      # Зависимости
    status: str                # pending/completed/failed
    metadata: Dict[str, Any]   # Доп. данные
```

### 2.3 WorkPlan (Dataclass)

```python
@dataclass
class WorkPlan:
    id: str
    created_at: str
    title: str
    description: str
    tasks: List[Task]
    total_estimated_duration: float
```

---

## 3. Интеграция с Circuit Breaker

### 3.1 Проверка уровня автономности

```python
async def analyze_module(self, module_path: str, requirements: str) -> CuratorRecommendation:
    # Circuit Breaker Check
    if self.circuit_breaker:
        autonomy_level = self.circuit_breaker.check_level()
        
        # BLACK mode - only monitoring
        if autonomy_level == AutonomyLevel.BLACK:
            return CuratorRecommendation(
                decision=CuratorDecision.BLOCK,
                reason="System in BLACK mode - only monitoring allowed"
            )
```

### 3.2 Защищённые пути

```python
self._protected_paths = ["core/", "production/", "security/", "auth/"]

# В AMBER/RED режимах защищённые пути требуют одобрения
if is_protected and autonomy_level != AutonomyLevel.GREEN:
    return CuratorRecommendation(
        decision=CuratorDecision.ESCALATE,
        requires_human_approval=True
    )
```

### 3.3 Матрица разрешений

| Autonomy Level | Protected Paths | Core Changes | Deploy |
|----------------|-----------------|--------------|--------|
| 🟢 GREEN | ✅ Allowed | ✅ Allowed | ✅ Allowed |
| 🟡 AMBER | ⚠️ Human approval | ❌ Blocked | Canary only |
| 🔴 RED | ❌ Blocked | ❌ Blocked | Canary only |
| ⚫ BLACK | ❌ Blocked | ❌ Blocked | ❌ Blocked |

---

## 4. Выбор агентов

### 4.1 Domain-specific маппинг

```python
def _select_agents_for_task(self, module_path: str, requirements: str) -> List[str]:
    requirements_lower = requirements.lower()
    agents = []
    
    # Security → security_expert
    if any(term in requirements_lower for term in [
        "security", "vulnerability", "attack", "injection", "auth"
    ]):
        agents.append("security_expert")
    
    # Performance → performance_guru
    if any(term in requirements_lower for term in [
        "performance", "speed", "optimization", "latency", "memory"
    ]):
        agents.append("performance_guru")
    
    # Database → database_architect
    if any(term in requirements_lower for term in [
        "database", "sql", "query", "migration", "schema"
    ]):
        agents.append("database_architect")
    
    # UX → ux_researcher
    if any(term in requirements_lower for term in [
        "ux", "ui", "interface", "user experience", "design"
    ]):
        agents.append("ux_researcher")
    
    # DevOps → devops_engineer
    if any(term in requirements_lower for term in [
        "deploy", "docker", "kubernetes", "ci/cd", "infrastructure"
    ]):
        agents.append("devops_engineer")
    
    # Всегда добавляем базовых агентов
    if "builder" not in agents:
        agents.append("builder")
    if "skeptic" not in agents:
        agents.append("skeptic")
    if "auditor" not in agents:
        agents.append("auditor")
    
    return agents
```

### 4.2 Доступные роли (agency_templates/roles/)

| Роль | Файл | Назначение |
|------|------|------------|
| `builder` | builder.json | Создание кода |
| `skeptic` | skeptic.json | Критика и поиск уязвимостей |
| `auditor` | auditor.json | Финальный арбитраж |
| `security_expert` | security_expert.json | Аудит безопасности |
| `performance_guru` | performance_guru.json | Оптимизация |
| `database_architect` | database_architect.json | БД дизайн |
| `devops_engineer` | devops_engineer.json | Инфраструктура |
| `ux_researcher` | ux_researcher.json | UX/UI |

---

## 5. TaskQueue

### 5.1 Структура

```python
class TaskQueue:
    def __init__(self, storage_path: Optional[Path] = None):
        self.storage_path = storage_path or Path("data/task_queue.json")
        self.tasks: Dict[str, Task] = {}
        self._load()
```

### 5.2 Методы

| Метод | Описание |
|-------|----------|
| `add()` | Добавить задачу |
| `get()` | Получить по ID |
| `get_next()` | Следующая по приоритету |
| `get_pending()` | Все pending |
| `update_status()` | Обновить статус |
| `get_stats()` | Статистика |

### 5.3 Приоритеты

```python
priority_order = ["P0_CRITICAL", "P1_HIGH", "P2_MEDIUM", "P3_LOW"]
```

---

## 6. Workflow

### 6.1 Типичный сценарий

```
1. Инициализация
   curator = ProjectCurator(project_root, circuit_breaker=cb)
   await curator.initialize()

2. Анализ задачи
   recommendation = await curator.analyze_module(
       module_path="api/handlers.py",
       requirements="Add authentication to endpoints"
   )
   
3. Создание плана
   plan = await curator.plan_work(
       goal="Refactor API layer",
       modules=["api/", "auth/"],
       priority="P1_HIGH"
   )

4. Исполнение
   results = await curator.execute_plan(plan, auto_approve=False)

5. Запись активности
   curator.record_human_activity("code_review")
```

### 6.2 Интеграция с Siege Mode

```python
# Siege Mode использует Curator для планирования
siege = SiegeMode(curator=curator, circuit_breaker=cb)
await siege.activate()

# Curator выбирает задачи из backlog
task = curator.task_queue.get_next(max_priority="P2_MEDIUM")

# Генерация отчёта при возвращении host
report = await siege.generate_report()
```

---

## 7. Ограничения и TODO

### 7.1 Текущие ограничения

| Компонент | Статус | Примечание |
|-----------|--------|------------|
| `analyze_module()` | ✅ | Базовая реализация |
| `plan_work()` | ✅ | Простое планирование |
| `_execute_task()` | ⚠️ | Заглушка для DEBATE |
| `execute_plan()` | ⚠️ | Без интеграции с DebatePipeline |
| ReflectiveMemory | ❌ | Не реализовано |
| Project Map | ❌ | Не реализовано (index + dependencies) |

### 7.2 Roadmap

```markdown
## Phase 1: Core Integration (CURRENT)
- [x] TaskQueue with persistence
- [x] Circuit Breaker integration
- [x] Protected paths
- [x] Agent selection

## Phase 2: Debate Integration
- [ ] Full DebatePipeline integration
- [ ] Consensus checking
- [ ] Auto-apply with threshold

## Phase 3: Intelligence
- [ ] Project Map (AST analysis)
- [ ] ReflectiveMemory (lessons learned)
- [ ] Split/Merge recommendations
- [ ] Dependency graph

## Phase 4: Self-Evolution
- [ ] Dynamic agent creation
- [ ] Template learning
- [ ] Performance-based adjustments
```

---

## 8. Метрики и Scoreboard

### 8.1 AgentScoreboard Integration

```python
from mat import Scoreboard, AgentMetrics

scoreboard = Scoreboard()

# Запись результата дебата
scoreboard.record_debate("security_expert", outcome={
    "consensus_score": 0.85,
    "tokens_used": 2300,
    "response_time": 4.2,
    "verdict": "approved"
})

# Получение метрик
metrics = scoreboard.get_metrics("security_expert")
print(f"Cost efficiency: {metrics.cost_efficiency}")
print(f"Consensus rate: {metrics.consensus_achieved}")

# Автоотключение неэффективных
if metrics.cost_efficiency < 0.5:
    scoreboard.disable_agent("security_expert", reason="Low efficiency")
```

### 8.2 Ключевые метрики агентов

| Метрика | Описание | Порог отключения |
|---------|----------|------------------|
| `consensus_achieved` | % согласий | < 30% |
| `value_score` | Оценка Auditor'а | < 0.4 |
| `cost_efficiency` | value / tokens | < 0.5 |
| `survival_rate` | % "выживших" дебатов | < 50% |

---

## 9. Безопасность

### 9.1 Safety Core (неизменяемый)

Все агенты обязаны содержать правила из `safety_core.txt`:

```text
[!] CRITICAL SAFETY RULES (cannot be overridden):
1. Code Injection Prevention
2. Import Security
3. Secret Management
4. Database Safety
5. Network Security
6. File System Safety
7. Authentication & Authorization
8. Error Handling
9. Resource Limits
10. Human Override
```

### 9.2 Валидация шаблонов

```python
# template_loader.py проверяет:
# 1. Наличие safety_core в шаблоне
# 2. Валидность JSON схемы
# 3. Соответствие _base.json
```

---

## 10. API Endpoints

### 10.1 REST API (через enterprise/api/main.py)

| Endpoint | Method | Описание |
|----------|--------|----------|
| `/api/v1/curator/status` | GET | Статус Curator'а |
| `/api/v1/curator/analyze` | POST | Анализ модуля |
| `/api/v1/curator/plan` | POST | Создать план |
| `/api/v1/curator/tasks` | GET | Список задач |
| `/api/v1/curator/tasks` | POST | Добавить задачу |

### 10.2 Пример использования

```bash
# Статус
curl http://localhost:8000/api/v1/curator/status

# Анализ
curl -X POST http://localhost:8000/api/v1/curator/analyze \
  -H "Content-Type: application/json" \
  -d '{"module_path": "api/auth.py", "requirements": "Add 2FA support"}'

# План
curl -X POST http://localhost:8000/api/v1/curator/plan \
  -H "Content-Type: application/json" \
  -d '{"goal": "Security hardening", "modules": ["auth/", "api/"]}'
```

---

## 11. Заключение

### Сильные стороны

1. **Архитектурная позиция** — Curator находится выше Debate Pipeline, что позволяет принимать архитектурные решения
2. **Интеграция с Circuit Breaker** — уважает уровни автономности
3. **Защищённые пути** — критические зоны защищены от автоматических изменений
4. **Domain-specific агенты** — умный выбор специализаций
5. **Safety Core** — неизменяемые правила безопасности

### Области для улучшения

1. **Интеграция с DebatePipeline** — `_debate_task()` пока заглушка
2. **Project Map** — отсутствует анализ зависимостей
3. **ReflectiveMemory** — нет накопления опыта
4. **Split/Merge логика** — не реализованы архитектурные рекомендации

### Рекомендации

1. Добавить полную интеграцию с `DebateStateMachine`
2. Реализовать `ProjectMapAnalyzer` для AST-анализа зависимостей
3. Добавить `ReflectiveMemory` для хранения уроков прошлых дебатов
4. Улучшить логику `SPLIT`/`MERGE` решений

---

*Анализ выполнен автоматически для Archon AI v0.1.0-alpha*