# Archon AI - Next Session Plan

**Last Updated:** 2026-02-07
**Project Status:** MAT Integration Complete

---

## Completed Tasks

### Phase 1: MAT Integration (COMPLETED)

The following components have been successfully copied and adapted from `E:/multi_agent_team/` to `E:/archon_ai/mat/`:

1. **Circuit Breaker** (`mat/circuit_breaker.py`) ✅
   - 4-level autonomy system (GREEN/AMBER/RED/BLACK)
   - `OperationType` for permission checking
   - `require_autonomy_level` decorator
   - State persistence to JSON

2. **Siege Mode** (`mat/siege_mode.py`) ✅
   - Full autonomy when host is offline
   - `VirtualCTOReport` for debriefing
   - Background task execution
   - Integration with Circuit Breaker

3. **Project Curator** (`mat/project_curator.py`) ✅
   - Simplified version without heavy dependencies
   - `TaskQueue` for managing work
   - `WorkPlan` generation
   - Agent selection from templates

4. **Debate Pipeline** (`mat/debate_pipeline.py`) ✅
   - Simplified implementation
   - Phases: DRAFT -> SIEGE -> FORTIFY -> JUDGMENT
   - Integration with agency_templates
   - Stub for LLM integration (to be completed)

5. **Agent Scoreboard** (`mat/agent_scoreboard.py`) ✅
   - Performance metrics tracking
   - Auto-disable for low performers
   - History persistence to JSONL

6. **Agency Templates** (`mat/agency_templates/`) ✅
   - `safety_core.txt` - Immutable genetic code
   - `template_loader.py` - Load and validate roles
   - `roles/` - 6 role templates (base, security_expert, performance_guru, database_architect, ux_researcher, devops_engineer)
   - `index.json` - Template registry
   - Vaccination system for agent safety

7. **Package Exports** (`mat/__init__.py`) ✅
   - All components properly exported
   - Clean API for importing

---

## Pending Tasks

### Phase 2: RBAC System (PRIORITY: P0)

Create `enterprise/rbac.py`:

```python
class Role(Enum):
    SUPER_ADMIN = "super_admin"      # Full access
    TENANT_ADMIN = "tenant_admin"    # Tenant management
    DEVELOPER = "developer"           # Code execution
    ANALYST = "analyst"              # Read-only
    EXTERNAL = "external"             # Limited access

class Permission(Enum):
    AGENT_EXECUTE = "agent.execute"
    AGENT_MONITOR = "agent.monitor"
    CODE_READ = "code.read"
    CODE_WRITE = "code.write"
    CODE_DEPLOY = "code.deploy"

def check_permission(user_id: str, permission: Permission) -> bool
def assign_role(user_id: str, role: Role)
```

### Phase 3: Audit Logger (PRIORITY: P1)

Create `enterprise/audit_logger.py`:

- Append-only logs with hash chaining
- SOC2/GDPR compliant (7-year retention)
- Subscribe to all EventBus events
- Immutable log records

### Phase 4: FastAPI Server (PRIORITY: P0)

Create `enterprise/api/main.py`:

**Endpoints:**
- `GET /health` - Health check
- `GET /api/v1/circuit_breaker/status` - Get autonomy level
- `POST /api/v1/circuit_breaker/record_activity` - Record human activity
- `POST /api/v1/siege/activate` - Activate Siege Mode
- `POST /api/v1/siege/deactivate` - Deactivate Siege Mode
- `GET /api/v1/siege/report` - Get Virtual CTO report
- `GET /api/v1/curator/status` - Get Curator status
- `POST /api/v1/debate/start` - Start a debate
- `GET /api/v1/scoreboard/stats` - Get agent metrics

### Phase 5: LLM Integration (PRIORITY: P1)

Enhance `mat/debate_pipeline.py`:
- Connect to LLM router (14 models across 7 providers)
- Implement actual Builder/Skeptic/Auditor prompts
- Integrate with agency_templates for role selection

### Phase 6: Integration Testing (PRIORITY: P1)

Create `tests/integration/test_mat_integration.py`:
- Test message flow: RBAC → Contract → Debate → Execution → Audit
- Test Siege Mode activation
- Test contract violations blocking
- Test multi-tenant isolation

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    CHANNELS (OpenClaw)                      │
│  WhatsApp │ Telegram │ Slack │ Discord │ Signal │ Teams    │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                     ENTERPRISE LAYER                        │
│  RBAC │ Audit │ Multi-tenancy │ SSO │ Compliance            │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                    MAT LAYER (NEW!)                         │
│  CircuitBreaker │ SiegeMode │ ProjectCurator │ DebatePipeline│
│  AgentScoreboard │ AgencyTemplates (safety_core.txt)        │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                 EXECUTION LAYER (Enterprise)                │
│  Execution Contract │ Event Bus │ Gateway Bridge            │
└─────────────────────────────────────────────────────────────┘
```

---

## Quick Start Commands

```bash
# Install dependencies
cd E:/archon_ai
pip install -e .

# Test imports
python -c "from mat import CircuitBreaker, SiegeMode, ProjectCurator, DebatePipeline; print('OK')"

# Run main service
python -m enterprise.main

# Run tests
pytest tests/ -v
```

---

## Next Session Priorities

1. **RBAC System** - Create `enterprise/rbac.py`
2. **Audit Logger** - Create `enterprise/audit_logger.py`
3. **FastAPI Server** - Create `enterprise/api/main.py`
4. **LLM Integration** - Connect DebatePipeline to LLM router
5. **Integration Tests** - Test full stack

---

## Notes

- All MAT components are now in `E:/archon_ai/mat/`
- Agency templates include Safety Core vaccination
- Circuit Breaker state persists to `data/circuit_breaker_state.json`
- Siege Mode generates Virtual CTO reports
- Debate Pipeline is simplified - needs LLM integration
