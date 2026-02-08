"""
Archon AI FastAPI Server - Main Application
============================================

REST API for managing Archon AI components.

Usage:
    uvicorn enterprise.api.main:app --reload --host 0.0.0.0 --port 8000
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Dict, List, Optional, Any

from fastapi import FastAPI, HTTPException, Depends, Header, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

# Import Archon components
from mat import CircuitBreaker, SiegeMode, ProjectCurator, DebatePipeline, Scoreboard, LLMRouter
from mat.circuit_breaker import AutonomyLevel, OperationType
from mat.siege_mode import SiegeState, SiegeTrigger
from enterprise.rbac import RBAC, Role, Permission, get_rbac
from enterprise.audit_logger import AuditLogger, EventType, Severity, get_audit_logger

logger = logging.getLogger(__name__)


# =============================================================================
# Global State
# =============================================================================

# Global instances
_circuit_breaker: Optional[CircuitBreaker] = None
_siege_mode: Optional[SiegeMode] = None
_project_curator: Optional[ProjectCurator] = None
_debate_pipeline: Optional[DebatePipeline] = None
_scoreboard: Optional[Scoreboard] = None
_rbac: Optional[RBAC] = None
_audit_logger: Optional[AuditLogger] = None


def get_components() -> Dict[str, Any]:
    """Get all initialized components"""
    return {
        "circuit_breaker": _circuit_breaker,
        "siege_mode": _siege_mode,
        "project_curator": _project_curator,
        "debate_pipeline": _debate_pipeline,
        "scoreboard": _scoreboard,
        "rbac": _rbac,
        "audit_logger": _audit_logger,
    }


# =============================================================================
# Lifecycle
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    global _circuit_breaker, _siege_mode, _project_curator
    global _debate_pipeline, _scoreboard, _rbac, _audit_logger

    logger.info("[ArchonAI] Starting API server...")

    # Initialize components
    try:
        _circuit_breaker = CircuitBreaker()
        logger.info("[ArchonAI] CircuitBreaker initialized")

        _audit_logger = AuditLogger()
        logger.info("[ArchonAI] AuditLogger initialized")

        _rbac = get_rbac()
        logger.info("[ArchonAI] RBAC initialized")

        _project_curator = ProjectCurator(project_root=".")
        await _project_curator.initialize()
        logger.info("[ArchonAI] ProjectCurator initialized")

        _siege_mode = SiegeMode(circuit_breaker=_circuit_breaker, curator=_project_curator)
        logger.info("[ArchonAI] SiegeMode initialized")

        # Initialize LLM Router for DebatePipeline
        llm_router = None
        try:
            llm_router = LLMRouter(quality_preference="balanced")
            logger.info("[ArchonAI] LLMRouter initialized with balanced quality preference")
        except Exception as e:
            logger.warning(f"[ArchonAI] LLMRouter initialization failed: {e}")
            logger.info("[ArchonAI] DebatePipeline will run in fallback mode")

        _debate_pipeline = DebatePipeline(llm_router=llm_router)
        logger.info("[ArchonAI] DebatePipeline initialized")

        _scoreboard = Scoreboard()
        logger.info("[ArchonAI] Scoreboard initialized")

        # Log startup
        _audit_logger.log(
            event_type=EventType.SYSTEM_STARTED,
            data={"component": "api_server"},
            severity=Severity.INFO
        )

        logger.info("[ArchonAI] All components initialized")

    except Exception as e:
        logger.error(f"[ArchonAI] Failed to initialize components: {e}")
        raise

    yield

    # Shutdown
    logger.info("[ArchonAI] Shutting down API server...")
    if _siege_mode and _siege_mode.is_active():
        await _siege_mode.deactivate("shutdown")


# =============================================================================
# FastAPI App
# =============================================================================

app = FastAPI(
    title="Archon AI API",
    description="""
    ## Enterprise AI Operating System with T0-T3 Security Architecture

    Archon AI is a Constraint-Oriented Adaptive System (COAS) for multi-agent intelligence
    with architectural safety guarantees.

    ### Features
    - **Circuit Breaker**: 4-level autonomy system (GREEN/AMBER/RED/BLACK)
    - **Siege Mode**: Full autonomy when host is offline
    - **Debate Pipeline**: Multi-agent code review with LLM integration
    - **RBAC**: Role-based access control with multi-tenant support
    - **Audit Logger**: Tamper-evident logging with hash chaining

    ### LLM Integration
    - 14+ models across 7 providers (OpenAI, Anthropic, Google, Groq, xAI, GLM, HuggingFace, Cerebras)
    - Automatic model selection by task type
    - Fallback logic for reliability

    ### Quick Start
    1. Set API keys in environment variables (see .env.example)
    2. Start a debate: POST /api/v1/debate/start
    3. Check autonomy level: GET /api/v1/circuit_breaker/status
    """,
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_tags=[
        {
            "name": "health",
            "description": "Health check and system status"
        },
        {
            "name": "circuit_breaker",
            "description": "Autonomy level management and human activity tracking"
        },
        {
            "name": "siege_mode",
            "description": "Offline autonomy mode activation and management"
        },
        {
            "name": "debate",
            "description": "Multi-agent code review with LLM integration"
        },
        {
            "name": "rbac",
            "description": "Role-based access control"
        },
        {
            "name": "audit",
            "description": "Audit log querying and verification"
        }
    ]
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# Pydantic Models
# =============================================================================

class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    version: str
    timestamp: str
    components: Dict[str, str]


class CircuitBreakerStatusResponse(BaseModel):
    """Circuit breaker status response"""
    current_level: str
    level_emoji: str
    human_minutes_away: Optional[float]
    system_state: Dict[str, Any]
    permissions: Dict[str, bool]
    history: List[Dict[str, Any]]


class RecordActivityRequest(BaseModel):
    """Record human activity request"""
    action: str = "api_activity"
    user_id: Optional[str] = None


class SiegeActivateRequest(BaseModel):
    """Siege mode activation request"""
    trigger: str = "manual"


class SiegeStatusResponse(BaseModel):
    """Siege mode status response"""
    state: str
    is_active: bool
    current_session: Optional[Dict[str, Any]]


class DebateStartRequest(BaseModel):
    """Start debate request"""
    code: str = Field(
        ...,
        description="Code to review",
        examples=["def add(a, b): return a + b"]
    )
    requirements: str = Field(
        ...,
        description="Requirements for the code",
        examples=["Create a function that adds two numbers"]
    )
    file_path: Optional[str] = Field(
        None,
        description="Optional file path for context",
        examples=["src/math.py"]
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "code": "def add(a, b): return a + b",
                    "requirements": "Create a function that adds two numbers",
                    "file_path": "src/math.py"
                },
                {
                    "code": "def process_user_input(user_input):\n    query = f\"SELECT * FROM users WHERE name = '{user_input}'\"\n    return execute_query(query)",
                    "requirements": "Create a function to query users by name",
                    "file_path": "src/users.py"
                }
            ]
        }
    }


class RoleAssignRequest(BaseModel):
    """Assign role request"""
    user_id: str
    role: str
    tenant_id: Optional[str] = None


# =============================================================================
# Dependencies
# =============================================================================

async def get_current_user(
    x_user_id: Optional[str] = Header(None),
    x_tenant_id: Optional[str] = Header(None)
) -> Optional[str]:
    """Get current user from headers"""
    return x_user_id


# =============================================================================
# Health & Status Routes
# =============================================================================

@app.get(
    "/",
    response_model=Dict[str, str],
    tags=["health"],
    summary="Root endpoint",
    description="Returns API information and documentation links"
)
async def root():
    """Root endpoint"""
    return {
        "name": "Archon AI API",
        "version": "0.1.0",
        "status": "running",
        "docs": "/docs"
    }


@app.get(
    "/health",
    response_model=HealthResponse,
    tags=["health"],
    summary="Health check",
    description="Check the health status of all Archon AI components",
    responses={
        200: {
            "description": "All components healthy",
            "content": {
                "application/json": {
                    "example": {
                        "status": "healthy",
                        "version": "0.1.0",
                        "timestamp": "2026-02-07T12:00:00",
                        "components": {
                            "circuit_breaker": "ready",
                            "siege_mode": "ready",
                            "debate_pipeline": "ready",
                            "llm_router": "ready"
                        }
                    }
                }
            }
        }
    }
)
async def health_check():
    """Health check endpoint"""
    components = {}
    for name, component in get_components().items():
        if component is not None:
            components[name] = "ready"
        else:
            components[name] = "not_initialized"

    return HealthResponse(
        status="healthy" if all(c == "ready" for c in components.values()) else "degraded",
        version="0.1.0",
        timestamp=datetime.now().isoformat(),
        components=components
    )


# =============================================================================
# Circuit Breaker Routes
# =============================================================================

@app.get(
    "/api/v1/circuit_breaker/status",
    tags=["circuit_breaker"],
    summary="Get circuit breaker status",
    description="Returns current autonomy level, permissions, and system state",
    responses={
        200: {
            "description": "Circuit breaker status",
            "content": {
                "application/json": {
                    "example": {
                        "current_level": "GREEN",
                        "level_emoji": "🟢",
                        "human_minutes_away": 0.0,
                        "system_state": {
                            "last_human_activity": "2026-02-07T12:00:00",
                            "minutes_since_contact": 0.0
                        },
                        "permissions": {
                            "can_execute_code": True,
                            "can_modify_system": True
                        },
                        "history": []
                    }
                }
            }
        }
    }
)
async def get_circuit_breaker_status():
    """Get current circuit breaker status"""
    if _circuit_breaker is None:
        raise HTTPException(status_code=503, detail="CircuitBreaker not initialized")

    status = _circuit_breaker.get_status()

    # Log access
    if _audit_logger:
        _audit_logger.log(
            event_type=EventType.AUDIT_LOG_QUERIED,
            data={"endpoint": "/circuit_breaker/status"}
        )

    return status


@app.post(
    "/api/v1/circuit_breaker/record_activity",
    tags=["circuit_breaker"],
    summary="Record human activity",
    description="Records human activity and resets autonomy countdown to GREEN",
    responses={
        200: {
            "description": "Activity recorded successfully",
            "content": {
                "application/json": {
                    "example": {
                        "status": "recorded",
                        "action": "manual_review"
                    }
                }
            }
        }
    }
)
async def record_human_activity(request: RecordActivityRequest):
    """Record human activity (resets autonomy countdown)"""
    if _circuit_breaker is None:
        raise HTTPException(status_code=503, detail="CircuitBreaker not initialized")

    _circuit_breaker.record_human_activity(request.action)

    # Log activity
    if _audit_logger:
        _audit_logger.log(
            event_type=EventType.HUMAN_ACTIVITY_RECORDED,
            user_id=request.user_id,
            data={"action": request.action}
        )

    return {"status": "recorded", "action": request.action}


@app.get(
    "/api/v1/circuit_breaker/history",
    tags=["circuit_breaker"],
    summary="Get circuit breaker history",
    description="Returns the history of autonomy level transitions"
)
async def get_circuit_breaker_history():
    """Get circuit breaker level transition history"""
    if _circuit_breaker is None:
        raise HTTPException(status_code=503, detail="CircuitBreaker not initialized")

    return {"history": list(_circuit_breaker._level_history)}


# =============================================================================
# Siege Mode Routes
# =============================================================================

@app.get("/api/v1/siege/status", response_model=SiegeStatusResponse)
async def get_siege_status():
    """Get Siege Mode status"""
    if _siege_mode is None:
        raise HTTPException(status_code=503, detail="SiegeMode not initialized")

    return SiegeStatusResponse(
        state=_siege_mode.get_state().value,
        is_active=_siege_mode.is_active(),
        current_session=_siege_mode.current_session.to_dict() if _siege_mode.current_session else None
    )


@app.post("/api/v1/siege/activate")
async def activate_siege_mode(request: SiegeActivateRequest):
    """Activate Siege Mode"""
    if _siege_mode is None:
        raise HTTPException(status_code=503, detail="SiegeMode not initialized")

    trigger = SiegeTrigger.TIMEOUT if request.trigger == "timeout" else SiegeTrigger.MANUAL

    success = await _siege_mode.activate(trigger)

    if not success:
        raise HTTPException(status_code=400, detail="Failed to activate Siege Mode")

    # Log activation
    if _audit_logger:
        _audit_logger.log(
            event_type=EventType.SIEGE_ACTIVATED,
            data={"trigger": trigger.value}
        )

    return {"status": "activated", "trigger": trigger.value}


@app.post("/api/v1/siege/deactivate")
async def deactivate_siege_mode():
    """Deactivate Siege Mode"""
    if _siege_mode is None:
        raise HTTPException(status_code=503, detail="SiegeMode not initialized")

    success = await _siege_mode.deactivate("api_request")

    if not success:
        raise HTTPException(status_code=400, detail="Failed to deactivate Siege Mode")

    # Log deactivation
    if _audit_logger:
        _audit_logger.log(
            event_type=EventType.SIEGE_DEACTIVATED,
            data={"reason": "api_request"}
        )

    return {"status": "deactivated"}


@app.get("/api/v1/siege/report")
async def get_siege_report():
    """Get Virtual CTO report from Siege Mode"""
    if _siege_mode is None:
        raise HTTPException(status_code=503, detail="SiegeMode not initialized")

    report = await _siege_mode.generate_report()
    return report.to_dict()


# =============================================================================
# Project Curator Routes
# =============================================================================

@app.get("/api/v1/curator/status")
async def get_curator_status():
    """Get Project Curator status"""
    if _project_curator is None:
        raise HTTPException(status_code=503, detail="ProjectCurator not initialized")

    return _project_curator.get_status_report()


# =============================================================================
# Debate Pipeline Routes
# =============================================================================

@app.post(
    "/api/v1/debate/start",
    tags=["debate"],
    summary="Start a code review debate",
    description="""
    Starts a multi-agent debate to review code using LLM integration.

    **Debate Phases:**
    1. DRAFT - Builder proposes/improves code
    2. SIEGE - Skeptic finds vulnerabilities
    3. FORTIFY - Builder addresses concerns
    4. JUDGMENT - Auditor makes final verdict

    **Verdicts:**
    - `approved` - Code is safe and functional
    - `approved_with_risks` - Code works but has documented issues
    - `needs_review` - Code needs changes
    - `rejected` - Code is unsafe or doesn't meet requirements
    """,
    responses={
        200: {
            "description": "Debate completed successfully",
            "content": {
                "application/json": {
                    "example": {
                        "verdict": "approved",
                        "confidence": 0.85,
                        "consensus_score": 0.78,
                        "justification": "Code is safe, well-structured, and meets requirements. No security vulnerabilities found.",
                        "final_code": "def add(a: int, b: int) -> int:\n    return a + b",
                        "vulnerabilities_found": [],
                        "recommendations": ["Consider adding type hints for better clarity"],
                        "states_count": 4
                    }
                }
            }
        },
        503: {
            "description": "DebatePipeline not initialized or LLM unavailable"
        }
    }
)
async def start_debate(request: DebateStartRequest):
    """Start a new debate"""
    if _debate_pipeline is None:
        raise HTTPException(status_code=503, detail="DebatePipeline not initialized")

    # Log debate start
    if _audit_logger:
        _audit_logger.log(
            event_type=EventType.DEBATE_STARTED,
            data={
                "code_length": len(request.code),
                "requirements": request.requirements,
                "file_path": request.file_path
            }
        )

    result = await _debate_pipeline.debate_simple(
        code=request.code,
        requirements=request.requirements,
        file_path=request.file_path
    )

    # Log debate completion
    if _audit_logger:
        _audit_logger.log(
            event_type=EventType.DEBATE_COMPLETED,
            data={"verdict": result.get("verdict")}
        )

    return result


# =============================================================================
# Scoreboard Routes
# =============================================================================

@app.get("/api/v1/scoreboard/stats")
async def get_scoreboard_stats():
    """Get agent scoreboard statistics"""
    if _scoreboard is None:
        raise HTTPException(status_code=503, detail="Scoreboard not initialized")

    return _scoreboard.get_statistics()


@app.get("/api/v1/scoreboard/agents/{agent_id}")
async def get_agent_metrics(agent_id: str):
    """Get metrics for a specific agent"""
    if _scoreboard is None:
        raise HTTPException(status_code=503, detail="Scoreboard not initialized")

    metrics = _scoreboard.get_metrics(agent_id)
    if metrics is None:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")

    return metrics.to_dict()


# =============================================================================
# RBAC Routes
# =============================================================================

@app.get("/api/v1/rbac/roles")
async def list_roles():
    """List all available roles"""
    return {
        "roles": [role.value for role in Role],
        "permissions": [perm.value for perm in Permission]
    }


@app.post("/api/v1/rbac/assign")
async def assign_role(request: RoleAssignRequest):
    """Assign a role to a user"""
    if _rbac is None:
        raise HTTPException(status_code=503, detail="RBAC not initialized")

    try:
        role = Role(request.role)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid role: {request.role}")

    user_role = _rbac.assign_role(
        user_id=request.user_id,
        role=role,
        tenant_id=request.tenant_id
    )

    # Log role assignment
    if _audit_logger:
        _audit_logger.log(
            event_type=EventType.ROLE_ASSIGNED,
            user_id=request.user_id,
            tenant_id=request.tenant_id,
            data={"role": role.value}
        )

    return user_role.to_dict()


@app.get("/api/v1/rbac/users/{user_id}")
async def get_user_roles(user_id: str, tenant_id: Optional[str] = None):
    """Get roles for a user"""
    if _rbac is None:
        raise HTTPException(status_code=503, detail="RBAC not initialized")

    roles = _rbac.get_user_roles(user_id, tenant_id)
    return {
        "user_id": user_id,
        "tenant_id": tenant_id,
        "roles": [r.to_dict() for r in roles]
    }


# =============================================================================
# Audit Routes
# =============================================================================

@app.get("/api/v1/audit/events")
async def get_audit_events(
    user_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    limit: int = 100
):
    """Query audit log"""
    if _audit_logger is None:
        raise HTTPException(status_code=503, detail="AuditLogger not initialized")

    from enterprise.audit_logger import AuditQuery

    query = AuditQuery(user_id=user_id, tenant_id=tenant_id, limit=limit)
    events = _audit_logger.query(query)

    return {
        "events": [e.to_dict() for e in events],
        "count": len(events)
    }


@app.get("/api/v1/audit/verify")
async def verify_audit_chain():
    """Verify audit log chain integrity"""
    if _audit_logger is None:
        raise HTTPException(status_code=503, detail="AuditLogger not initialized")

    return _audit_logger.verify_chain()


# =============================================================================
# Error Handlers
# =============================================================================

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler"""
    logger.error(f"[ArchonAI] Unhandled exception: {exc}")

    # Log error
    if _audit_logger:
        _audit_logger.log(
            event_type=EventType.SYSTEM_ERROR,
            severity=Severity.ERROR,
            data={"error": str(exc), "path": str(request.url.path)}
        )

    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "detail": str(exc)}
    )


# =============================================================================
# Main
# =============================================================================

if __name__ == "__main__":
    import uvicorn

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    uvicorn.run(
        "enterprise.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )


__all__ = ["app", "lifespan"]
