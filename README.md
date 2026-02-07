# Archon AI 🏛️

> **Enterprise AI Operating System** with T0-T3 security architecture, autonomous operations, and multi-channel support.

**Status:** 🚧 Under Development | **Version:** 0.1.0

---

## Overview

Archon AI is an enterprise-grade AI operating system that combines multi-channel communication infrastructure with advanced security governance and autonomous decision-making capabilities.

```
CHANNELS (12+) → ENTERPRISE (RBAC/Audit) → SECURITY (CB/Curator/Siege) → EXECUTION
```

### What You Get

| Feature | Description |
|---------|-------------|
| **12+ Communication Channels** | WhatsApp, Telegram, Slack, Discord, Signal, Teams, and more |
| **4 Autonomy Levels** | GREEN → AMBER → RED → BLACK (Circuit Breaker) |
| **Multi-Agent Decisions** | Debate Pipeline for collective decision-making |
| **Full Autonomy** | Siege Mode when host is offline |
| **Enterprise Security** | RBAC, Audit Trail, SOC2/GDPR compliance |
| **Multi-Tenant** | Complete tenant isolation |
| **SSO Integration** | Okta, Azure AD, Google Workspace |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        CHANNELS (OpenClaw)                              │
│  WhatsApp │ Telegram │ Slack │ Discord │ Signal │ Teams │ WebChat      │
└──────────────────────────────────────┬──────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        ENTERPRISE LAYER                                 │
│  RBAC │ Audit │ Compliance │ Multi-tenancy │ SSO                       │
└──────────────────────────────────────┬──────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     SECURITY LAYER (MAT Logic)                          │
│  Circuit Breaker │ Project Curator │ Debate Pipeline │ Siege Mode      │
└──────────────────────────────────────┬──────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      EXECUTION LAYER (OpenClaw)                         │
│  WebSocket Gateway │ Docker Sandbox │ Canvas A2UI │ Tailscale          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Quick Start

### Prerequisites

- Python 3.11+
- Docker & Docker Compose
- Redis (for state management)
- PostgreSQL (for persistence)

### Installation

```bash
# Clone repository
git clone https://github.com/ember6784/openclaw-enterprise.git
cd openclaw-enterprise

# Install dependencies
poetry install

# Copy environment template
cp .env.example .env

# Start services
docker-compose up -d

# Run migrations
poetry run alembic upgrade head

# Start the application
poetry run python -m enterprise.main
```

### Configuration

Edit `.env`:

```env
# Database
DATABASE_URL=postgresql://user:pass@localhost:5432/openclaw_enterprise

# Redis
REDIS_URL=redis://localhost:6379/0

# OpenClaw Gateway
OPENCLAW_GATEWAY_URL=ws://localhost:18789

# LLM Providers
ANTHROPIC_API_KEY=your_key_here
OPENAI_API_KEY=your_key_here

# Security
CIRCUIT_BREAKER_ENABLED=true
SIEGE_MODE_ENABLED=true
AUDIT_RETENTION_DAYS=2555

# SSO (optional)
SSO_PROVIDER=okta
SSO_CLIENT_ID=your_client_id
SSO_CLIENT_SECRET=your_client_secret
```

---

## Project Structure

```
openclaw-enterprise/
├── enterprise/              # Enterprise Layer (RBAC, Audit, Multi-tenant)
│   ├── gateway_bridge.py    # Bridge to OpenClaw Gateway
│   ├── event_bus.py         # Async event system
│   ├── state_manager.py     # Distributed state
│   ├── rbac.py              # Role-Based Access Control
│   ├── audit_logger.py      # SOC2/GDPR audit trail
│   ├── multi_tenant.py      # Tenant isolation
│   ├── sso.py               # SSO integration
│   └── compliance.py        # Compliance reporting
│
├── mat/                     # Multi-Agent Team components
│   ├── circuit_breaker.py   # 4-level autonomy system
│   ├── project_curator.py   # Meta-agent for project management
│   ├── siege_mode.py        # Full autonomy when offline
│   ├── debate_pipeline.py   # Multi-agent decision making
│   ├── agent_scoreboard.py  # Performance metrics
│   └── agency_templates/    # Agent role templates
│
├── openclaw/                # OpenClaw integration
│   ├── gateway.py           # WebSocket Gateway client
│   ├── channels.py          # Channel managers
│   └── sandbox.py           # Docker sandbox wrapper
│
├── deploy/                  # Infrastructure
│   ├── kubernetes/          # K8s manifests
│   ├── terraform/           # IaC
│   └── docker/              # Dockerfiles
│
├── tests/                   # Tests
│   ├── unit/
│   ├── integration/
│   └── load/
│
└── docs/                    # Documentation
```

---

## Usage

### Starting the Enterprise Service

```bash
poetry run python -m enterprise.main
```

### Sending a Message

```python
from enterprise.gateway_bridge import GatewayBridge

bridge = GatewayBridge(
    ws_url="ws://localhost:18789",
    rbac=rbac_system,
    circuit_breaker=circuit_breaker
)

await bridge.start()
```

### Checking Circuit Breaker Status

```bash
curl http://localhost:8000/api/v1/circuit_breaker/status
```

### Activating Siege Mode

```bash
curl -X POST http://localhost:8000/api/v1/siege/activate
```

---

## Security Model

### Defense in Depth (6 Layers)

1. **Network** — TLS 1.3, Tailscale private networking
2. **Auth** — SSO + MFA, JWT tokens
3. **RBAC** — Role-based permissions, least privilege
4. **Circuit Breaker** — 4 autonomy levels
5. **Sandbox** — Docker container isolation
6. **Safety Core** — Vaccinated agents, prompt injection protection

### Autonomy Levels

| Level | Trigger | Allowed |
|-------|---------|----------|
| 🟢 GREEN | Host online | All operations |
| 🟡 AMBER | No activity 2h+ | Except core/production |
| 🔴 RED | No activity 6h+ | Canary only |
| ⚫ BLACK | 2+ critical | Monitor only |

### Compliance

- **SOC2 Type II** — Access control, change management, incident response
- **GDPR** — Data processing records, DSR handling
- **HIPAA** — PHI handling, breach notifications (optional)
- **PCI DSS** — Card data protection (optional)

---

## Development

### Running Tests

```bash
# Unit tests
poetry run pytest tests/unit

# Integration tests
poetry run pytest tests/integration

# Load tests
poetry run locust tests/load/locustfile.py

# With coverage
poetry run pytest --cov=enterprise --cov=mat
```

### Code Quality

```bash
# Linting
poetry run ruff check .

# Formatting
poetry run ruff format .

# Type checking
poetry run mypy .
```

### Local Development

```bash
# Start all services
docker-compose up -d

# Run with hot reload
poetry run python -m enterprise.main --reload
```

---

## Deployment

### Kubernetes

```bash
kubectl apply -k deploy/kubernetes/overlays/production
```

### Docker Compose

```bash
docker-compose -f deploy/docker/docker-compose.prod.yml up -d
```

### Terraform

```bash
cd deploy/terraform
terraform init
terraform apply
```

---

## Roadmap

### Phase 1: Foundation (Weeks 1-2) ✅ Design Complete
- [ ] Gateway Bridge implementation
- [ ] Event Bus
- [ ] State Manager
- [ ] Configuration system

### Phase 2: Security Integration (Weeks 3-4)
- [ ] RBAC system
- [ ] Circuit Breaker integration
- [ ] Audit Logger

### Phase 3: Enterprise Features (Weeks 5-6)
- [ ] Multi-tenancy
- [ ] SSO integration
- [ ] Compliance reporting

### Phase 4: Orchestration (Weeks 7-8)
- [ ] Project Curator integration
- [ ] Debate Pipeline integration
- [ ] Siege Mode integration

### Phase 5: Deployment (Weeks 9-10)
- [ ] Kubernetes manifests
- [ ] Terraform modules
- [ ] Monitoring

### Phase 6: Testing & Docs (Weeks 11-12)
- [ ] Integration tests
- [ ] Load tests
- [ ] Complete documentation

---

## Contributing

Contributions are welcome! Please read `docs/CONTRIBUTING.md` for details.

## License

MIT License — see `LICENSE` for details.

---

## Acknowledgments

- [OpenClaw](https://github.com/openclaw/openclaw) — Communication infrastructure
- [Multi-Agent Team](https://github.com/ember6784/multi_agent_team) — Security and autonomy
- Anthropic — Claude AI models
- OpenAI — GPT models

---

**Author:** ember6784 + Claude Code
**Status:** 🚧 Under Development
**Version:** 0.1.0
