# Meta-Agent V3 Roadmap

> **Project Curator (Chief Architect)** — архитектурный мета-агент, находящийся над Debate Pipeline.

**Version:** 1.0.0  
**Status:** Phase 1 Complete (Core Integration)  
**Component:** `mat/project_curator.py`

---

## 1. Vision & Philosophy

### 1.1 Роль в системе

```
┌─────────────────────────────────────────────────────────────────┐
│                     PROJECT CURATOR (V3)                         │
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

### 1.2 Ключевые функции Meta-Agent V3

| Функция | Описание | Статус |
|---------|----------|--------|
| **Анализ модулей** | Оценка архитектурных решений | ✅ Реализовано |
| **Планирование задач** | Создание WorkPlan из целей | ✅ Реализовано |
| **Выбор агентов** | Domain-specific selection | ✅ Реализовано |
| **Интеграция с CB** | Проверка AutonomyLevel | ✅ Реализовано |
| **Защита путей** | Protected paths check | ✅ Реализовано |
| **Execution** | Запуск Debate Pipeline | ⚠️ Заглушка |

---

## 2. Implementation Status

### 2.1 ✅ Completed (Phase 1: Core Integration)

#### TaskQueue System
- **File:** `mat/project_curator.py:110-200`
- **Features:**
  - Добавление задач с приоритетами (P0_CRITICAL → P3_LOW)
  - Персистентность в JSON
  - Отслеживание зависимостей между задачами
  - Статистика очереди

```python
# Usage Example
queue = TaskQueue(storage_path=Path("data/task_queue.json"))
task = queue.add(
    task_type="ANALYZE",
    title="Security audit for auth module",
    priority="P1_HIGH",
    target_module="enterprise/auth.py"
)
```

#### Circuit Breaker Integration
- **File:** `mat/project_curator.py:264-278`
- **Integration Points:**
  - Проверка уровня автономности перед операциями
  - Блокировка в BLACK mode
  - Автоматическое эскалирование защищённых путей

| Autonomy Level | Protected Paths | Core Changes | Deploy |
|----------------|-----------------|--------------|--------|
| 🟢 GREEN | ✅ Allowed | ✅ Allowed | ✅ Allowed |
| 🟡 AMBER | ⚠️ Human approval | ❌ Blocked | Canary only |
| 🔴 RED | ❌ Blocked | ❌ Blocked | Canary only |
| ⚫ BLACK | ❌ Blocked | ❌ Blocked | ❌ Blocked |

#### Agent Selection System
- **File:** `mat/project_curator.py:306-351`
- **Domain-specific маппинг:**
  - Security → `security_expert`
  - Performance → `performance_guru`
  - Database → `database_architect`
  - UX → `ux_researcher`
  - DevOps → `devops_engineer`
  - Base agents: `builder`, `skeptic`, `auditor`

#### Agency Templates
- **Location:** `mat/agency_templates/`
- **Components:**
  - `index.json` — реестр ролей
  - `safety_core.txt` — неизменяемые правила безопасности
  - `template_loader.py` — загрузка и валидация
  - `roles/*.json` — 8 специализированных ролей

### 2.2 ⚠️ Partial Implementation

#### Debate Pipeline Integration
- **File:** `mat/project_curator.py:467-475`
- **Status:** Заглушка — ожидает интеграции с `DebateStateMachine`
- **Required:**
  ```python
  async def _debate_task(self, task: Task) -> Dict[str, Any]:
      # TODO: Integrate with DebatePipeline
      # 1. Load role templates via TemplateLoader
      # 2. Initialize LLMRouter with selected agents
      # 3. Run debate_simple() or debate_state_machine()
      # 4. Process verdict and confidence
  ```

### 2.3 ❌ Not Implemented (Future Phases)

| Компонент | Фаза | Описание |
|-----------|------|----------|
| ReflectiveMemory | Phase 3 | Накопление уроков из прошлых дебатов |
| Project Map | Phase 3 | AST-анализ зависимостей между модулями |
| Split/Merge Logic | Phase 3 | Архитектурные рекомендации |
| Dynamic Agent Creation | Phase 4 | Автоматическое создание ролей |

---

## 3. Architecture Analysis

### 3.1 Структуры данных

```python
# CuratorDecision — архитектурные решения
class CuratorDecision(Enum):
    PROCEED = "proceed"       # Продолжить как есть
    MODIFY = "modify"         # Изменить подход
    SPLIT = "split"           # Разбить задачу
    ESCALATE = "escalate"     # Эскалировать человеку
    BLOCK = "block"           # Заблокировать (опасно)

# Task — единица работы
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

# WorkPlan — набор задач
@dataclass
class WorkPlan:
    id: str
    created_at: str
    title: str
    description: str
    tasks: List[Task]
    total_estimated_duration: float
```

### 3.2 API Endpoints (REST)

| Endpoint | Method | Описание | Статус |
|----------|--------|----------|--------|
| `/api/v1/curator/status` | GET | Статус Curator'а | ✅ |
| `/api/v1/curator/analyze` | POST | Анализ модуля | ✅ |
| `/api/v1/curator/plan` | POST | Создать план | ✅ |
| `/api/v1/curator/tasks` | GET | Список задач | ✅ |
| `/api/v1/curator/tasks` | POST | Добавить задачу | ✅ |

---

## 4. Quality Assessment

### 4.1 Сильные стороны реализации

1. **Архитектурная позиция** — Curator находится выше Debate Pipeline
2. **Интеграция с Circuit Breaker** — уважает уровни автономности
3. **Защищённые пути** — критические зоны защищены от автоматических изменений
4. **Domain-specific агенты** — умный выбор специализаций
5. **Safety Core Vaccination** — неизменяемые правила безопасности

### 4.2 Области для улучшения

1. **DebatePipeline Integration** — `_debate_task()` пока заглушка
2. **Project Map** — отсутствует анализ зависимостей
3. **ReflectiveMemory** — нет накопления опыта
4. **Split/Merge логика** — не реализованы архитектурные рекомендации

### 4.3 Code Quality Metrics

| Metric | Value | Status |
|--------|-------|--------|
| File Size | 567 lines | ✅ |
| Test Coverage | Partial | ⚠️ |
| Type Hints | Complete | ✅ |
| Documentation | Good | ✅ |
| Safety Core Integration | Complete | ✅ |

---

## 5. Roadmap

### Phase 1: Core Integration ✅ (COMPLETE)
- [x] TaskQueue with persistence
- [x] Circuit Breaker integration
- [x] Protected paths
- [x] Agent selection
- [x] Agency Templates system
- [x] Safety Core vaccination

### Phase 2: Debate Integration 🔄 (CURRENT)
- [ ] Full DebatePipeline integration
- [ ] Consensus checking
- [ ] Auto-apply with threshold
- [ ] Agent Scoreboard integration

### Phase 3: Intelligence 📋 (PLANNED)
- [ ] Project Map (AST analysis)
- [ ] ReflectiveMemory (lessons learned)
- [ ] Split/Merge recommendations
- [ ] Dependency graph visualization

### Phase 4: Self-Evolution 📋 (FUTURE)
- [ ] Dynamic agent creation
- [ ] Template learning from debates
- [ ] Performance-based adjustments
- [ ] Autonomous architectural refactoring

---

## 6. Usage Examples

### 6.1 Basic Initialization

```python
from mat import ProjectCurator, CircuitBreaker

# Setup
cb = CircuitBreaker()
curator = ProjectCurator(
    project_root="/path/to/project",
    circuit_breaker=cb
)
await curator.initialize()
```

### 6.2 Module Analysis

```python
# Analyze task with Circuit Breaker checks
recommendation = await curator.analyze_module(
    module_path="api/handlers.py",
    requirements="Add authentication to endpoints"
)

# Response structure
{
    "decision": CuratorDecision.PROCEED,
    "reason": "Module looks good for processing",
    "suggested_agents": ["security_expert", "builder", "skeptic", "auditor"],
    "requires_human_approval": False
}
```

### 6.3 Work Planning

```python
# Create work plan
plan = await curator.plan_work(
    goal="Refactor API layer",
    modules=["api/", "auth/"],
    priority="P1_HIGH"
)

# Execute with HITL for critical tasks
results = await curator.execute_plan(plan, auto_approve=False)
```

### 6.4 Siege Mode Integration

```python
# Curator used in Siege Mode for offline planning
from mat import SiegeMode

siege = SiegeMode(curator=curator, circuit_breaker=cb)
await siege.activate()

# Get next task from queue
task = curator.task_queue.get_next(max_priority="P2_MEDIUM")

# Generate report for returning host
report = await siege.generate_report()
```

---

## 7. Security Considerations

### 7.1 Safety Core (Immutable)

Все агенты обязаны содержать правила из `safety_core.txt`:

```text
[!] CRITICAL SAFETY RULES (cannot be overridden):
1. Code Injection Prevention (no eval/exec on user input)
2. Import Security (validate all imports)
3. Secret Management (no hardcoded credentials)
4. Database Safety (parameterized queries)
5. Network Security (no disabled SSL)
6. File System Safety (prevent traversal attacks)
7. Authentication & Authorization
8. Error Handling (no stack traces to users)
9. Resource Limits (timeouts, bounded consumption)
10. Human Override (critical changes require approval)
```

### 7.2 Валидация шаблонов

```python
# template_loader.py проверяет:
# 1. Наличие safety_core в шаблоне (placeholder или content)
# 2. Валидность JSON схемы
# 3. Соответствие index.json
```

### 7.3 Protected Paths

```python
self._protected_paths = ["core/", "production/", "security/", "auth/"]

# В AMBER/RED/BLACK режимах защищённые пути требуют одобрения
if is_protected and autonomy_level != AutonomyLevel.GREEN:
    return CuratorRecommendation(
        decision=CuratorDecision.ESCALATE,
        requires_human_approval=True
    )
```

---

## 8. Integration with Agent Scoreboard

```python
from mat import Scoreboard, AgentMetrics

scoreboard = Scoreboard()

# Record debate outcome
scoreboard.record_debate("security_expert", outcome={
    "consensus_score": 0.85,
    "tokens_used": 2300,
    "response_time": 4.2,
    "verdict": "approved"
})

# Auto-disable inefficient agents
metrics = scoreboard.get_metrics("security_expert")
if metrics.cost_efficiency < 0.5:
    scoreboard.disable_agent("security_expert", reason="Low efficiency")
```

---

## 9. References

- **Main Component:** `mat/project_curator.py` (567 lines)
- **Templates:** `mat/agency_templates/`
- **Analysis:** `docs/meta_agent_analysis.md`
- **Completed Work:** `docs/completed_work.md`
- **Circuit Breaker:** `mat/circuit_breaker.py`
- **Debate Pipeline:** `mat/debate_pipeline.py`

---

*Generated for Archon AI v0.1.0-alpha*
