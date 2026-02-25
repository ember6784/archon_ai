# Archon AI Documentation

> **Constraint-Oriented Adaptive System (COAS)** — операционная среда для мультиагентных интеллектов с гарантиями безопасности через архитектурные ограничения.

---

## Navigation

### Getting Started

| Document | Description |
|----------|-------------|
| [Quick Start](getting-started/quick-start.md) | Запуск за 5 минут |
| [Telegram Bot](getting-started/telegram-bot.md) | Настройка @quant_dev_ai_bot |
| [Environment Setup](getting-started/environment.md) | Переменные окружения |

### Architecture

| Document | Description |
|----------|-------------|
| [Vision & Philosophy](vision.md) | Архитектурная философия |
| [5 Barriers](1.md) | Многоуровневая защита |
| [Execution Chokepoint](2.md) | RFC по ядру исполнения |
| [Security Review](3.md) | Анализ безопасности |
| [Integration Patterns](4.md) | Паттерны интеграции |
| [Kernel RFC](5.md) | RFC Execution Kernel |
| [Debate Pipeline](6.md) | Multi-LLM дебаты |
| [Implementation Priorities](7.md) | Приоритеты разработки |
| [Analysis & Recommendations](8.md) | Анализ и рекомендации |

### Development

| Document | Description |
|----------|-------------|
| [Testing Guide](testing.md) | Тестирование и бенчмарки |
| [Security Improvements](development/security-improvements.md) | V3.0 улучшения безопасности |
| [Completed Work](completed_work.md) | История выполненных задач |

### Reference

| Document | Description |
|----------|-------------|
| [Commands Reference](reference/commands.md) | Справочник команд |
| [API Endpoints](reference/api.md) | REST API документация |

### Integration

| Document | Description |
|----------|-------------|
| [OpenClaw Gateway](integration/gateway.md) | Интеграция с Gateway |
| [Integration Status](integration/status.md) | Текущий статус интеграции |

---

## Quick Links

- **GitHub README**: [../README.md](../README.md) — Основная документация проекта
- **Agent Guide**: [../AGENTS.md](../AGENTS.md) — Гид для AI-ассистентов
- **Makefile**: [../Makefile](../Makefile) — Команды сборки

---

## Project Structure

```
archon_ai/
├── enterprise/              # Security & Governance Layer
│   ├── api/main.py          # FastAPI server
│   ├── rbac.py              # Role-based access control
│   ├── audit_logger.py      # Tamper-evident logging
│   └── event_bus.py         # Async pub/sub
│
├── kernel/                  # Execution Kernel
│   ├── execution_kernel.py  # Core validation logic
│   ├── intent_contract.py   # Pre/post conditions
│   ├── invariants.py        # Safety invariants
│   ├── dynamic_circuit_breaker.py
│   └── openclaw_integration.py
│
├── mat/                     # Multi-Agent Team
│   ├── llm_router.py        # Multi-provider LLM
│   ├── debate_pipeline.py   # State machine for debates
│   ├── circuit_breaker.py   # 4-level autonomy
│   └── agency_templates/    # Role definitions
│
├── openclaw/                # Gateway client
│   └── gateway_v3.py        # WebSocket Protocol v3
│
├── tests/                   # Test suites
│   ├── unit/
│   └── integration/
│
└── docs/                    # This documentation
```

---

## Security Model: 5 Barriers

```
┌─────────────────────────────────────────────────────────┐
│  BARRIER 1: Intent Contract Validation (JSON schemas)   │
├─────────────────────────────────────────────────────────┤
│  BARRIER 2: Heterogeneous Debate (Multiple LLMs)        │
├─────────────────────────────────────────────────────────┤
│  BARRIER 3: Static Analysis (AST parsing)               │
├─────────────────────────────────────────────────────────┤
│  BARRIER 4: Execution Chokepoint (Kernel)               │
├─────────────────────────────────────────────────────────┤
│  BARRIER 5: Resource Cage (Docker, seccomp, readonly)   │
└─────────────────────────────────────────────────────────┘
```

---

## Key Concepts

### Circuit Breaker (4-Level Autonomy)

| Level | Trigger | Permissions |
|-------|---------|-------------|
| GREEN | Human online | Full access |
| AMBER | No contact 2h+ | No core/, canary only |
| RED | No contact 6h+ | Read-only + canary |
| BLACK | 2+ critical failures | Monitoring only |

### Trust Boundary

```
Agent → Protocol Layer → Execution Kernel → Environment
```

Agent has NO direct access to filesystem, network, tools, or LLM APIs.

### Fail-Closed Policy

All validation failures default to DENY. No LLM inside kernel — deterministic logic only.

---

## License

- **Code:** MIT
- **Documentation:** CC-BY-SA

**Author:** ember6784
