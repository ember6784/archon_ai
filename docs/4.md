# Archon AI over OpenClaw: Integration Design

## Overview

Archon AI acts as a security and governance overlay on top of OpenClaw. OpenClaw handles the lower layer (tool calling, channels, sandbox), while the Archon Execution Kernel enforces strict control, invariants, audit, and adversarial protection at the upper layer.

This is classical **defense in depth** without code duplication.

---

## Integration Options

### Option A: Kernel as Middleware (Recommended)

All OpenClaw tool calls are routed through an `ArchonKernelProxy`. OpenClaw internals are not modified — only the execution entry point is wrapped.

**Pros:**
- Minimal changes to OpenClaw codebase
- Easy to test and roll back
- Acceptable overhead (5–20% latency increase)
- Clean separation of concerns

**Cons:**
- Double-stack overhead in high-load scenarios
- Requires monitoring OpenClaw updates to detect breaking changes

### Option B: Full Kernel Replacement
Replace OpenClaw execution engine entirely with Kernel. Maximum control, but duplicates OpenClaw logic and creates a maintenance burden.

### Option C: Native Patch
Patch OpenClaw source directly. Efficient, but breaks on upstream updates. Not recommended for open-source dependencies.

---

## Kernel Proxy Implementation

```python
# archon/kernel_proxy.py
from typing import Any, Dict, Optional
from enterprise.rbac import RBACSystem
from enterprise.audit_logger import AuditLogger
from enterprise.event_bus import EventBus
from mat.circuit_breaker import CircuitBreaker
from mat.debate_pipeline import DebatePipeline

class ArchonKernelProxy:
    """
    Proxy layer that controls all OpenClaw operation execution.
    All tool calls, file ops, and code execution pass through here.
    """

    def __init__(
        self,
        debate_pipeline: DebatePipeline,
        rbac: RBACSystem,
        event_bus: EventBus,
        circuit_breaker: CircuitBreaker,
        fast_path_threshold: float = 0.25
    ):
        self.debate_pipeline = debate_pipeline
        self.rbac = rbac
        self.event_bus = event_bus
        self.circuit_breaker = circuit_breaker
        self.fast_path_threshold = fast_path_threshold

    async def execute(
        self,
        operation: str,
        payload: Dict[str, Any],
        context: Dict[str, Any],
        agent_id: str,
        risk_score: Optional[float] = None
    ) -> Any:
        # 0. Circuit Breaker
        if not self.circuit_breaker.is_allowed(operation):
            raise RuntimeError("Circuit breaker open — operation blocked")

        # 1. RBAC check
        if not self.rbac.has_permission(agent_id, operation, payload):
            raise PermissionError(f"Agent {agent_id} has no permission for {operation}")

        # 2. Risk estimation
        if risk_score is None:
            risk_score = self._estimate_risk(operation, payload)

        # 3. Fast path for low risk
        if risk_score <= self.fast_path_threshold:
            result = await self._execute_direct(operation, payload, context)
            await self._log_success(operation, payload, result)
            return result

        # 4. Debate for medium/high risk
        debate_result = await self.debate_pipeline.run_debate(
            operation=operation,
            payload=payload,
            context=context,
            agent_id=agent_id
        )

        if debate_result["verdict"] != "APPROVED":
            await self._log_rejection(operation, payload, debate_result["reason"])
            raise PermissionError(f"Debate rejected: {debate_result['reason']}")

        # 5. Execute
        try:
            result = await self._execute_direct(operation, payload, context)
            await self._log_success(operation, payload, result)
            return result
        except Exception as e:
            await self._log_failure(operation, payload, str(e))
            self.circuit_breaker.record_failure(operation)
            raise

    def _estimate_risk(self, operation: str, payload: Dict) -> float:
        if "exec" in operation.lower() or "eval" in str(payload):
            return 0.95
        if "write" in operation.lower() or "delete" in operation.lower():
            return 0.75
        if "network" in operation.lower():
            return 0.60
        return 0.20
```

---

## AST Sanitizer

All code passed to execution must be sanitized before reaching the Kernel:

```python
# archon/ast_sanitizer.py
import ast
from typing import Any

class AstSanitizer(ast.NodeTransformer):
    FORBIDDEN = (ast.Eval, ast.Exec, ast.Lambda)

    def generic_visit(self, node: ast.AST) -> Any:
        if isinstance(node, self.FORBIDDEN):
            raise ValueError(f"Forbidden AST node: {type(node).__name__}")
        return super().generic_visit(node)

def sanitize_code(code: str) -> str:
    tree = ast.parse(code)
    sanitizer = AstSanitizer()
    new_tree = sanitizer.visit(tree)
    ast.fix_missing_locations(new_tree)
    return ast.unparse(new_tree)
```

---

## Intent Contract Structure

Contracts are defined declaratively in JSON and evaluated imperatively in Python:

```json
{
  "operation": "modify_file",
  "pre_conditions": ["file_exists", "not_in_core_path"],
  "post_conditions": ["file_valid", "tests_pass"],
  "invariants": ["no_secrets_in_content"],
  "fast_path": false
}
```

---

## Integration Checklist

1. Identify all execution entry points in OpenClaw (tool calls, file ops, code exec)
2. Route all of them through `ArchonKernelProxy.execute()`
3. Pass required components into the proxy at initialization
4. Configure `event_bus` to record all events (success / rejection / failure)
5. Write tests:
   - Low-risk operation → fast path (no debate)
   - High-risk operation → full debate + approval
   - Rejected operation → audit log entry created

---

## Known Integration Gap

`enterprise/main.py` currently uses the base `GatewayBridge` without RBAC or Circuit Breaker:

```python
# Current (insecure):
self.gateway_bridge = GatewayBridge(
    ws_url=settings.openclaw_gateway_url,
    event_bus=self.event_bus
)

# Required (secure):
from enterprise.openclaw_integration import create_secure_bridge
self.gateway_bridge = create_secure_bridge(event_bus=self.event_bus)
```

`enterprise/openclaw_integration.py` already contains `SecureGatewayBridge` with full Kernel integration. It needs to be wired into `ArchonService`.
