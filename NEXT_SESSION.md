# Archon AI - Development Plan

**Last Updated:** 2026-02-07
**Project Status:** Phase 3 Complete - LLM Integration + Production Code from multi_agent_team
**Current Focus:** Phase 4 - Execution Kernel + OpenClaw Integration

---

## Completed Tasks

### Phase 0: Foundation ✅ (from previous sessions)

| Component | File | Lines |
|-----------|------|-------|
| Execution Contract | `enterprise/execution_contract.py` | ~629 |
| Event Bus | `enterprise/event_bus.py` | ~331 |
| Gateway Bridge | `enterprise/gateway_bridge.py` | ~405 |
| Config | `enterprise/config.py` | ~194 |
| **Total Phase 0** | | **~1,560** |

### Phase 1: MAT Integration ✅ (UPDATED with production code from multi_agent_team)

| Component | File | Lines | Source |
|-----------|------|-------|--------|
| LLM Router | `mat/llm_router.py` | ~997 | Created |
| DebateStateMachine | `mat/debate_pipeline.py` | ~1147 | Copied from multi_agent_team |
| Siege Mode | `mat/siege_mode.py` | ~740 | Existing |
| Project Curator | `mat/project_curator.py` | ~567 | Existing |
| Circuit Breaker | `mat/circuit_breaker.py` | ~1084 | Copied from multi_agent_team |
| Agent Scoreboard | `mat/agent_scoreboard.py` | ~853 | Copied from multi_agent_team |
| Chaos Engine | `mat/chaos_engine.py` | ~280 | Existing |
| Agency Templates | `mat/agency_templates/` | ~467 | Existing |
| Package Exports | `mat/__init__.py` | ~237 | Updated |
| **Total Phase 1** | | **~6,370** |

### Phase 2: Enterprise Layer ✅

| Component | File | Lines |
|-----------|------|-------|
| RBAC System | `enterprise/rbac.py` | ~656 |
| Audit Logger | `enterprise/audit_logger.py` | ~575 |
| FastAPI Server | `enterprise/api/main.py` | ~778 |
| API Init | `enterprise/api/__init__.py` | ~20 |
| Enterprise Init | `enterprise/__init__.py` | ~30 |
| Main Entry | `enterprise/main.py` | ~231 |
| **Total Phase 2** | | **~2,290** |

### Phase 3: LLM Integration ✅ (COMPLETED 2026-02-07)

| Component | File | Lines |
|-----------|------|-------|
| Role Templates (Debate) | `mat/agency_templates/roles/` | ~160 |
| Integration Tests | `tests/integration/test_full_flow.py` | ~425 |
| Unit Tests | `tests/unit/test_event_bus.py` | ~224 |
| **Deployment Files** | | |
| Dockerfile | `Dockerfile` | ~50 |
| Dockerfile.dev | `Dockerfile.dev` | ~40 |
| docker-compose.yml | `docker-compose.yml` | ~120 |
| docker-compose.dev.yml | `docker-compose.dev.yml` | ~90 |
| Makefile | `Makefile` | ~80 |
| .env.example | `.env.example` | ~130 |
| **Total Phase 3** | | **~1,320** |

**Phase 3 Summary:**
- ✅ DebateStateMachine (1147 lines) - Full state machine from multi_agent_team
- ✅ AgentScoreboard (853 lines) - Performance metrics from multi_agent_team
- ✅ CircuitBreaker (1084 lines) - 4-level autonomy from multi_agent_team
- ✅ All 17 integration tests passing
- ✅ LLM Router with 14+ models across 8 providers
- ✅ Role templates for Builder, Skeptic, Auditor with Safety Core vaccination
- ✅ OpenAPI specifications with examples
- ✅ Docker deployment configuration

---

## Total Project Status

```
Python Files:     26
Total Lines:       ~10,500 (updated with production code)
Phases:            0, 1, 2, 3 Complete
Docker:            ✅ Configured
Tests:             ✅ 17/17 Integration tests passing
OpenAPI:           ✅ With examples
```

---

## Pending Tasks

### Phase 4: Execution Kernel + OpenClaw Integration (PRIORITY: P0)

**Architecture Decision: Variant A (Middleware Pattern)**

```
OpenClaw Agent → Tool Call → ArchonMiddleware → Validation → OpenClaw Execution → Result
                      ↓
              ┌─────────────────────────────────┐
              │     ExecutionKernel             │
              │  1. RBAC check                  │
              │  2. Circuit Breaker check       │
              │  3. Resource limits check       │
              │  4. Intent Contract pre-check   │
              │  5. Debate (if risk > 0.5)      │
              │  6. Execution Contract validate │
              │  7. Execute + post-conditions   │
              └─────────────────────────────────┘
```

#### Components to Create:

| Priority | Component | File | Description |
|----------|-----------|------|-------------|
| P0 | ExecutionKernel | `archon/kernel/execution_kernel.py` | Core validation logic (fail-fast) |
| P0 | ArchonMiddleware | `archon/kernel/middleware.py` | OpenClaw integration wrapper |
| P0 | ValidationResult | `archon/kernel/validation.py` | Result type for kernel decisions |
| P1 | IntentContract | `archon/kernel/intent_contract.py` | Pre/post/invariants validation |
| P1 | AstSanitizer | `archon/kernel/ast_sanitizer.py` | Remove dangerous AST nodes |
| P1 | RiskEstimator | `archon/kernel/risk.py` | Operation risk scoring |
| P2 | ResourceLimits | `archon/kernel/limits.py` | Token/time/memory tracking |
| P2 | Z3 Integration | `archon/kernel/formal.py` | Formal verification (future) |

#### Risk Levels for Operations:

| Operation | Risk | Path |
|-----------|------|------|
| read_file | 0.0 | Fast path (no checks) |
| write_file | 0.3 | RBAC + Contract |
| exec_code | 0.9 | Full debate |
| delete_file | 0.8 | Full debate |
| network_request | 0.6 | RBAC + Contract + Audit |
| git_commit | 0.5 | RBAC + Contract |
| trade_execute | 0.9 | Full debate + human approval? |

#### Intent Contract Rules (Base Set):

```python
BASE_RULES = [
    "file_exists",
    "file_not_in_protected_path",
    "agent_has_permission",
    "core_files_unchanged",
    "system_integrity_maintained",
    "risk_level_acceptable"
]
```

#### Trust Boundary:

```
┌─────────────────────────────────────────────────────────────┐
│  UNTRUSTED LAYER                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Agent LLM (GPT/Claude/Llama) — hostile-by-complexity│   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                              ↓
                    ═══════════╧══════════
                    TRUST BOUNDARY
                    ═══════════╧══════════
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  TRUSTED LAYER (Kernel)                                     │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  - Deterministic logic ONLY                         │   │
│  │  - NO LLM inside                                    │   │
│  │  - Minimal code surface                            │   │
│  │  - Fail-closed policy                               │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  SEMI-TRUSTED LAYER (Execution Environment)                 │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  - Docker + seccomp whitelist                       │   │
│  │  - read-only rootfs                                │   │
│  │  - capability dropping                             │   │
│  │  - AST sanitization                                │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

#### Testing Strategy:

```
Unit Tests:
- ExecutionKernel.validate() с различными сценариями
- IntentContract.check_pre() с mock context
- AstSanitizer с malicious code
- RiskEstimator с different operations

Integration Tests:
- OpenClaw + Archon (end-to-end)
- Debate pipeline rejection
- Circuit breaker escalation

Adversarial Tests:
- Agent attempts to bypass restrictions
- Compositional bypass (chain of allowed operations)
- AST injection attacks
```

---

### Phase 5: Testing & Validation (PRIORITY: P1)

- [x] Run full test suite with pytest - ✅ 17/17 passing
- [ ] Contract violations blocking tests
- [ ] Load testing with Locust
- [ ] Adversarial penetration tests

---

### Phase 6: Production (PRIORITY: P2)

- [ ] Production deployment
- [ ] Monitoring (Prometheus/Grafana)
- [ ] Alerting setup
- [ ] Security hardening
- [ ] External security audit

---

## Session 4 Summary (2026-02-07) - Production Code Integration

### Completed
- ✅ Copied DebateStateMachine (1147 lines) from multi_agent_team
- ✅ Copied AgentScoreboard (853 lines) from multi_agent_team
- ✅ Copied CircuitBreaker (1084 lines) from multi_agent_team
- ✅ Updated mat/__init__.py with all exports (237 lines)
- ✅ Fixed all 17 integration tests to work with production code
- ✅ All tests passing (17/17)

### Files Updated (Session 4)
| File | Change | Lines |
|------|--------|-------|
| `mat/debate_pipeline.py` | Replaced with full state machine | 1147 |
| `mat/agent_scoreboard.py` | Replaced with full implementation | 853 |
| `mat/circuit_breaker.py` | Replaced with full implementation | 1084 |
| `mat/__init__.py` | Updated exports | 237 |
| `tests/integration/test_full_flow.py` | Fixed tests for production code | ~430 |

### Key Changes from multi_agent_team Integration:
- `DebateStateMachine` replaces simplified `DebatePipeline`
- Full event sourcing with JSONL history
- AST fingerprinting for code analysis
- Entropy markers for reproducibility
- ConsensusCalculatorV3 for verdict analysis
- StateContracts for validation
- ScoreboardIntegration for metrics

---

## Next Session Goals

1. **Create archon/kernel/ package** - ExecutionKernel, Middleware, ValidationResult
2. **Implement IntentContract** - Base rules (file_exists, agent_has_permission, etc.)
3. **Write AstSanitizer** - Remove dangerous AST nodes (eval, exec, etc.)
4. **Integration tests** - Mock OpenClaw, test rejection paths
5. **OpenClaw integration** - Monkey-patch or wrapper pattern decision

---

## Session 5 Summary (2026-02-07) - Architecture Discussion

### Completed
- ✅ Read all documentation (docs/vision.md, 1.md, 2.md, 3.md, 4.md, 5.md, 6.md)
- ✅ Discussed integration architecture with OpenClaw
- ✅ Defined Trust Boundary (Untrusted → Kernel → Semi-trusted)
- ✅ Chose Variant A (Middleware Pattern) for integration
- ✅ Defined validation order (fail-fast: RBAC → CB → Limits → Contract → Debate → Execute)

### Architectural Decisions Made:

| Decision | Value | Rationale |
|----------|-------|-----------|
| Integration Point | Variant A (Middleware) | Minimal changes, easy rollback |
| Validation Order | Fail-fast | Cheap checks first, minimize overhead |
| Trust Boundary | At Kernel | Deterministic logic only, NO LLM inside |
| Intent Contract Format | Hybrid (JSON → Python) | Configurable rules + dynamic checks |
| Risk Threshold | 0.5 | Below = fast path, above = full debate |

### Key Insights from Documentation:

**From 1.md (Security Review):**
- "Intent Verification" → **Intent Contract Consistency Check**
- Kernel is SPOF — needs mitigation (minimal code, no LLM)
- Heterogeneous Debate = confidence layer, NOT security barrier

**From 2.md (OS-level isolation):**
- Need: seccomp whitelist, no_new_privileges, read-only rootfs
- Kernel must NEVER execute agent code (predefined ops only)

**From 3.md (OpenClaw Integration):**
- Middleware pattern with risk-based fast path
- Proxy pattern for tool wrapping
- Hybrid contract format (JSON + Python)

**From 4.md/5.md (Philosophy):**
- System architecture → observers and control layers
- "Who controls the evolution of rules?" — core question

### Files Referenced (for implementation):

```
archon/kernel/
├── __init__.py
├── execution_kernel.py    # Core validation logic
├── middleware.py           # OpenClaw integration wrapper
├── validation.py           # ValidationResult type
├── intent_contract.py      # Pre/post/invariants
├── ast_sanitizer.py        # AST manipulation
├── risk.py                 # Risk estimation
├── limits.py               # Resource tracking
└── formal.py               # Z3 integration (future)
```

### Open Questions:

1. **OpenClaw API stability** — Will execution_engine.execute() change?
2. **Trade operations** — What risk level for trading? Human approval needed?
3. **Fallback behavior** — If Kernel down, deny all or direct execution?
4. **Protected paths** — Which paths are "core_files_unchanged"?


---

## Session 6 Summary (2026-02-07) - Manifest System Complete

### Completed
- ✅ Created base manifest at ~/manifests/base.json with forbidden patterns
- ✅ Created operations manifest at archon/manifests/operations.json with operation contracts
- ✅ Created environment overrides (dev/prod/test) at archon/manifests/environments/
- ✅ Implemented ManifestLoader with:
  - Multi-source loading (base/project/archon priority)
  - Inheritance via extends field with deep merge
  - Environment-specific overrides
  - Fallback chain (exact match → default_constraints → safe_defaults)
  - Cache isolation between environments
- ✅ All tests passing - manifests load correctly with environment overrides

### Files Created (Session 6):
| File | Lines | Description |
|------|-------|-------------|
| ~/manifests/base.json | ~105 | Base safety manifest with forbidden patterns |
| archon/manifests/operations.json | ~250 | Operation contracts with pre/post-conditions |
| archon/manifests/environments/dev.json | ~80 | Development overrides |
| archon/manifests/environments/prod.json | ~70 | Production overrides |
| archon/manifests/environments/test.json | ~70 | Testing overrides (mock mode) |
| archon/kernel/__init__.py | ~18 | Kernel package exports |
| archon/kernel/manifests/__init__.py | ~20 | Manifests package exports |
| archon/kernel/manifests/loader.py | ~445 | ManifestLoader with inheritance & overrides |

### Key Features Implemented:
1. Inheritance: extends field with recursive resolution
2. Environment Overrides: Per-environment configuration (dev/prod/test)
3. Priority Merging: base < project < archon < environment
4. Domain Management: Dynamic enable/disable with fallback
5. Post-Conditions: Operators (>=, <=, ==, etc.) for validation
6. Cache Isolation: Environment-aware cache keys prevent cross-contamination

### Test Results:
dev   : exec_code risk=0.5, mock=N/A
prod  : exec_code risk=0.95, mock=N/A
test  : exec_code risk=0.1, mock=True  ✓ Environment override working
Base forbidden_patterns inherited: True ✓

---

## Next Session Goals

1. Create archon/kernel/execution_kernel.py - Core validation logic with fail-fast checks
2. Create archon/kernel/validation.py - ValidationResult type-safe result class
3. Create archon/kernel/intent_contract.py - Pre/post-condition validator
4. Create archon/kernel/dynamic_circuit_breaker.py - DynamicCircuitBreaker with ChaosMonkey integration
5. Create archon/kernel/middleware.py - OpenClaw integration wrapper
6. Integration tests - Mock OpenClaw, test rejection paths



---

## Session 6 Final Summary (2026-02-07) - Kernel System Complete

### All Tasks Completed ✅

| Component | File | Lines | Status |
|-----------|------|-------|--------|
| Base Manifest |  | ~105 | ✅ |
| Operations Manifest |  | ~250 | ✅ |
| Environment Overrides |  | ~220 | ✅ |
| ManifestLoader |  | ~445 | ✅ |
| ExecutionKernel |  | ~380 | ✅ |
| ValidationResult |  | ~260 | ✅ |
| DynamicCircuitBreaker |  | ~500 | ✅ |
| Package Exports |  | ~70 | ✅ |

### Total Session 6: ~2,250 lines of code

### Key Features:
1. **Manifest System**: Multi-source loading with inheritance, environment overrides, cache isolation
2. **Execution Kernel**: Fail-fast validation (domain → RBAC → risk → contract → CB → audit)
3. **ValidationResult**: Type-safe results with DecisionReason enum
4. **DynamicCircuitBreaker** (with improvements):
   - Panic cooldown (3 cycles minimum) - prevents ping-pong
   - Agent-specific thresholds: 
   - Panic mode (Siege Mode) for sudden spikes

### Test Results:


### Next Session Goals:
1. Create archon/kernel/middleware.py - OpenClaw integration wrapper
2. Create archon/kernel/intent_contract.py - Pre/post-condition validator
3. Integration tests - Mock OpenClaw, test rejection paths
4. Connect ExecutionKernel with DynamicCircuitBreaker in production flow


---

## Session 7 (2026-02-08) - Minimal Working Kernel

### Guidance from docs/7.md
**Focus:** Python kernel first, Rust later.

### Tasks:
1. **Update execution_kernel.py** with minimal working example:
   - Operation registration (whitelist)
   - RBAC check
   - Invariant checkers (pre/post)
   - Actual execution (not just validation)
   
2. **Add invariants**:
   -  - block os.system calls
   -  - block protected paths
   -  - block eval/exec patterns

3. **OpenClaw middleware** - proxy all tool calls through kernel

### Progress will be tracked here.

---

## Session 7 Complete ✅ (2026-02-08)

### All Tasks Completed:

| Component | File | Lines | Status |
|-----------|------|-------|--------|
| ExecutionKernel (updated) | kernel/execution_kernel.py | ~500 | ✅ |
| Invariants | kernel/invariants.py | ~240 | ✅ |
| Middleware | kernel/middleware.py | ~320 | ✅ |
| OpenClaw Integration | kernel/openclaw_integration.py | ~450 | ✅ |
| Integration Tests | tests/integration/test_kernel_integration.py | ~370 | ✅ |

### Test Results: 20/20 PASSED ✅

TestSecureHandler:              4/4 PASSED
TestSecureGatewayBridge:        4/4 PASSED
TestFactoryFunctions:           2/2 PASSED
TestAutonomyLevels:            10/10 PASSED

### Total Session 7: ~1,880 lines of code

---

## Session 8 Goals (2026-02-08)

Priority: P0 - Intent Contract Validator

1. Create kernel/intent_contract.py
2. Extend validation.py with PostConditionResult
3. Integration tests for intent contracts
4. Connect IntentContract ↔ ExecutionKernel

