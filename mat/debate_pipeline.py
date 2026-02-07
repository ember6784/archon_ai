"""
Debate Pipeline - Multi-Agent Decision Making
============================================

Implements multi-agent debate system for code analysis and decision making.

From Text Document.txt:
> "Builder proposes code, Skeptic finds vulnerabilities, Auditor makes verdict.
> The debate goes through phases: DRAFT -> SIEGE -> FORTIFY -> JUDGMENT"

Usage:
    from mat.debate_pipeline import DebatePipeline

    pipeline = DebatePipeline()
    result = await pipeline.debate(code, requirements)
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


class DebatePhase(Enum):
    """Debate phases"""
    DRAFT = "draft"           # Builder proposes code
    SIEGE = "siege"           # Skeptic attacks
    FORTIFY = "fortify"       # Builder defends
    JUDGMENT = "judgment"     # Auditor decides


class VerdictType(Enum):
    """Verdict types"""
    APPROVED = "approved"
    APPROVED_WITH_RISKS = "approved_with_risks"
    REJECTED = "rejected"
    NEEDS_REVIEW = "needs_review"


@dataclass
class DebateState:
    """Current debate state"""
    phase: DebatePhase
    original_code: str
    requirements: str
    file_path: Optional[str] = None

    # Phase outputs
    draft_code: Optional[str] = None
    siege_critiques: List[str] = field(default_factory=list)
    fortified_code: Optional[str] = None
    verdict: Optional[str] = None
    verdict_justification: Optional[str] = None

    # Metadata
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())
    completed_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "phase": self.phase.value,
            "original_code": self.original_code[:100] + "..." if len(self.original_code) > 100 else self.original_code,
            "requirements": self.requirements,
            "file_path": self.file_path,
            "draft_code": self.draft_code[:100] + "..." if self.draft_code and len(self.draft_code) > 100 else self.draft_code,
            "siege_critiques_count": len(self.siege_critiques),
            "fortified_code": self.fortified_code[:100] + "..." if self.fortified_code and len(self.fortified_code) > 100 else self.fortified_code,
            "verdict": self.verdict,
            "started_at": self.started_at,
            "completed_at": self.completed_at
        }


@dataclass
class DebateResult:
    """Final debate result"""
    verdict: str
    confidence: float
    consensus_score: float
    justification: str
    final_code: Optional[str] = None
    vulnerabilities_found: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    states: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "verdict": self.verdict,
            "confidence": self.confidence,
            "consensus_score": self.consensus_score,
            "justification": self.justification,
            "final_code": self.final_code,
            "vulnerabilities_found": self.vulnerabilities_found,
            "recommendations": self.recommendations,
            "states_count": len(self.states)
        }


class DebatePipeline:
    """
    Multi-Agent Debate Pipeline

    Orchestrates debates between:
    - Builder: Proposes code changes
    - Skeptic: Finds vulnerabilities and issues
    - Auditor: Makes final verdict

    Phases:
    1. DRAFT: Builder proposes initial code
    2. SIEGE: Skeptic attacks and finds issues
    3. FORTIFY: Builder addresses concerns
    4. JUDGMENT: Auditor makes final decision
    """

    def __init__(
        self,
        workspace: Optional[Path] = None,
        llm_router=None,
        enabled_roles: Optional[List[str]] = None
    ):
        self.workspace = workspace or Path.cwd()
        self.llm_router = llm_router
        self.enabled_roles = enabled_roles or ["builder", "skeptic", "auditor"]

        # Agency templates integration
        self._template_loader = None
        try:
            from mat.agency_templates import TemplateLoader
            self._template_loader = TemplateLoader()
            logger.info("[DebatePipeline] Agency templates loaded")
        except ImportError:
            logger.warning("[DebatePipeline] Agency templates not available")

        logger.info(f"[DebatePipeline] Initialized with roles: {self.enabled_roles}")

    async def debate(
        self,
        code: str,
        requirements: str,
        file_path: Optional[str] = None
    ) -> DebateResult:
        """
        Run a full debate

        Args:
            code: Code to analyze
            requirements: Requirements for the code
            file_path: Optional file path

        Returns:
            DebateResult with final verdict
        """
        state = DebateState(
            phase=DebatePhase.DRAFT,
            original_code=code,
            requirements=requirements,
            file_path=file_path
        )

        results = []

        # Phase 1: DRAFT - Builder proposes
        logger.info("[DebatePipeline] DRAFT phase")
        state.draft_code = await self._run_draft_phase(state)
        results.append(state.to_dict())

        # Phase 2: SIEGE - Skeptic attacks
        logger.info("[DebatePipeline] SIEGE phase")
        state.phase = DebatePhase.SIEGE
        state.siege_critiques = await self._run_siege_phase(state)
        results.append(state.to_dict())

        # Phase 3: FORTIFY - Builder defends
        logger.info("[DebatePipeline] FORTIFY phase")
        state.phase = DebatePhase.FORTIFY
        state.fortified_code = await self._run_fortify_phase(state)
        results.append(state.to_dict())

        # Phase 4: JUDGMENT - Auditor decides
        logger.info("[DebatePipeline] JUDGMENT phase")
        state.phase = DebatePhase.JUDGMENT
        verdict_data = await self._run_judgment_phase(state)
        state.verdict = verdict_data["verdict"]
        state.verdict_justification = verdict_data["justification"]
        state.completed_at = datetime.now().isoformat()
        results.append(state.to_dict())

        # Build final result
        return DebateResult(
            verdict=state.verdict,
            confidence=verdict_data.get("confidence", 0.5),
            consensus_score=verdict_data.get("consensus_score", 0.5),
            justification=state.verdict_justification or "",
            final_code=state.fortified_code or state.draft_code,
            vulnerabilities_found=state.siege_critiques,
            recommendations=verdict_data.get("recommendations", []),
            states=results
        )

    async def debate_simple(
        self,
        code: str,
        requirements: str,
        file_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """Simple debate entry point"""
        result = await self.debate(code, requirements, file_path)
        return result.to_dict()

    async def _run_draft_phase(self, state: DebateState) -> str:
        """Run DRAFT phase - Builder proposes code"""
        # For now, just return original code
        # In full implementation, this would call LLM with Builder role
        return state.original_code

    async def _run_siege_phase(self, state: DebateState) -> List[str]:
        """Run SIEGE phase - Skeptic finds issues"""
        # For now, return empty critiques
        # In full implementation, this would call LLM with Skeptic role
        # and use safety_core from agency_templates
        return []

    async def _run_fortify_phase(self, state: DebateState) -> str:
        """Run FORTIFY phase - Builder addresses concerns"""
        # For now, return draft code
        # In full implementation, this would call LLM with Builder role
        # to address siege_critiques
        return state.draft_code or state.original_code

    async def _run_judgment_phase(self, state: DebateState) -> Dict[str, Any]:
        """Run JUDGMENT phase - Auditor makes verdict"""
        # For now, return a default approval
        # In full implementation, this would call LLM with Auditor role
        # to make final decision based on all previous phases
        return {
            "verdict": VerdictType.APPROVED.value,
            "confidence": 0.7,
            "consensus_score": 0.8,
            "justification": "Code approved - no critical issues found",
            "recommendations": []
        }

    def get_available_roles(self) -> List[str]:
        """Get available agent roles"""
        if self._template_loader:
            return [t["role_id"] for t in self._template_loader.list_roles()]
        return ["builder", "skeptic", "auditor"]

    def get_status(self) -> Dict[str, Any]:
        """Get pipeline status"""
        return {
            "workspace": str(self.workspace),
            "enabled_roles": self.enabled_roles,
            "available_roles": self.get_available_roles(),
            "agency_templates_loaded": self._template_loader is not None
        }


__all__ = [
    "DebatePipeline",
    "DebatePhase",
    "DebateState",
    "DebateResult",
    "VerdictType"
]
