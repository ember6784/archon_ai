# Execution Chokepoint RFC

## Concept

The Execution Chokepoint is the single mandatory validation boundary through which all state-changing operations must pass. No agent, LLM, or external channel can modify environment state without going through the Execution Kernel.

```
Agent → Protocol Layer → Execution Kernel → Environment
```

Agents have NO direct access to filesystem, network, tools, or LLM APIs.

---

## Security Invariant

```
∀ state_change ∈ Environment :
  origin(state_change) ∈ KernelApprovedOperations
```

Every environment state change must originate from a Kernel-approved operation ID. This is the primary security guarantee of the system.

---

## Threat Model

**Agent capabilities assumed hostile-by-complexity:**
- Can chain allowed operations to produce forbidden effects
- Can generate code that spawns subprocesses
- Can exploit tool responses
- Can induce humans via output manipulation
- Can exploit LLM hallucinated tool specifications

**Security goal:**
No action can affect environment state unless validated by Execution Kernel.

**Non-goals:**
- Semantic alignment
- Intent understanding
- Agent "morality"
- Protection against a compromised Kernel itself

---

## Kernel Trust Boundary

The Execution Kernel is the highest-trust component in the system.

**Mitigations for SPOF risk:**
- Minimal code surface (target: <500 lines)
- No LLM inside Kernel — deterministic logic only
- No agent-generated code is ever executed by Kernel — only predefined registered operations are triggered
- External audit required for Kernel changes

**Fail-closed policy:**
All validation failures default to DENY. If audit logging fails, the operation is blocked.

---

## Validation Order (fail-fast, cheapest first)

1. **RBAC** — Can this agent perform this operation? (in-memory, no I/O)
2. **Circuit Breaker** — Is the autonomy level sufficient?
3. **Whitelist check** — Is the operation registered?
4. **Resource limits** — Is the agent within quota?
5. **Intent Contract pre-conditions** — Rules-based pre-check
6. **Debate Pipeline** — For high-risk operations only (async, expensive)
7. **Execution Contract** — Final structural validation
8. **Execute** — Trigger predefined operation
9. **Post-condition invariants** — Verify state after execution

Rejection at any step triggers an audit log entry and returns DENY.

---

## OS-Level Isolation

| Mechanism | Status | Purpose |
|-----------|--------|---------|
| Docker user namespaces | Implemented | Process isolation |
| seccomp whitelist profile | Planned | Syscall restriction |
| `no-new-privileges` flag | Implemented | Privilege escalation prevention |
| Network namespace isolation | Implemented | Network access control |
| Read-only root FS + overlay | Planned | Filesystem protection |

---

## What This System Does NOT Protect Against

- A compromised Execution Kernel
- Supply chain attacks on Kernel dependencies
- Hardware-level vulnerabilities
- Semantic misalignment (an agent doing the "right" operation for the "wrong" reason)
- Operations explicitly whitelisted but used in unexpected chains (compositional bypass — mitigated by Intent Contracts)

---

## Debate Layer Clarification

The Heterogeneous Debate (Barrier 2) is a **confidence enhancer**, not a security enforcement layer.

| Barrier | Type | Purpose |
|---------|------|---------|
| 1 — Intent Contract | Logical contract check | Formal pre/post validation |
| 2 — Debate | Cognitive redundancy | Reduce reasoning error correlation |
| 3 — AST Analysis | Static safety | Detect forbidden code patterns |
| 4 — Execution Kernel | **Actual enforcement** | The only true security boundary |
| 5 — Resource Cage | Runtime containment | Docker, seccomp, resource limits |

The debate layer reduces correlated reasoning errors across different LLM providers. It does NOT protect against malicious behavior — that is the Kernel's job.

---

## Incentive System Note

Trust Score, rewards, and penalties in the Agent Scoreboard are **behavior shaping tools**, not security guarantees. LLMs do not have agency and do not respond to incentives. The incentive system improves task quality and orchestration, but provides zero security guarantees.
