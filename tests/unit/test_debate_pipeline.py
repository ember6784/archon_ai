import pytest
import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
from mat.debate_pipeline import (
    DebateState,
    DebateStateMachine,
    StructuralFingerprint,
    calculate_jaccard,
    ConsensusCalculatorV3,
    StateContracts,
    DecisionTrace,
    EntropyMarker,
    Artifact,
    DraftInput,
    StagnationReport,
    GroundingResult,
    FreshEyeResult,
    SeniorAuditorDecision
)

def test_artifact_creation():
    content = "def hello(): pass"
    artifact = Artifact.create(content, "code", author="test_agent", phase="initial")
    assert artifact.content == content
    assert artifact.content_type == "code"
    assert artifact.metadata["author"] == "test_agent"
    assert artifact.metadata["phase"] == "initial"
    assert artifact.hash is not None
    assert len(artifact.hash) == 64 # SHA-256

def test_structural_fingerprint_complex():
    code = """
import sys
from os import path as os_path

class Base:
    pass

class Derived(Base, Mixin):
    def __init__(self):
        super().__init__()
        
    async def process_data(self, data):
        def nested():
            pass
        return data

def top_level_func():
    pass
"""
    sf = StructuralFingerprint(module_name="test_mod")
    symbols = sf.extract_fingerprint(code)
    
    assert "test_mod::import:sys" in symbols
    assert "test_mod::from_import:os.path" in symbols
    assert "test_mod::class:Base" in symbols
    assert "test_mod::class:Derived" in symbols
    assert "test_mod::inherits:Base" in symbols
    assert "test_mod::inherits:Mixin" in symbols
    assert "test_mod::func:__init__" in symbols
    assert "test_mod::async_func:process_data" in symbols
    assert "test_mod::func:nested" in symbols
    assert "test_mod::func:top_level_func" in symbols

def test_calculate_jaccard():
    # Identical
    assert calculate_jaccard({"a", "b"}, {"a", "b"}) == 1.0
    # Completely different
    assert calculate_jaccard({"a", "b"}, {"c", "d"}) == 0.0
    # Partial overlap
    assert calculate_jaccard({"a", "b", "c"}, {"b", "c", "d"}) == 2/4 # intersection {b,c}, union {a,b,c,d}
    # Empty
    assert calculate_jaccard(set(), set()) == 1.0
    assert calculate_jaccard({"a"}, set()) == 0.0

def test_consensus_calculator_no_sklearn():
    # Force sklearn import failure for fallback testing
    with patch("builtins.__import__", side_effect=lambda name, *args, **kwargs: 
               MagicMock() if name == "sklearn" else __import__(name, *args, **kwargs)):
        sol_a = "x = 1"
        sol_b = "x = 2"
        f_a = {"var:x"}
        f_b = {"var:x"}
        
        consensus, breakdown = ConsensusCalculatorV3.calculate_consensus(sol_a, sol_b, f_a, f_b, [])
        assert 0 <= consensus <= 1.0

def test_consensus_calculator_penalty():
    sol_a = "data = 1"
    sol_b = "data = 1" # No change
    f_a = {"data"}
    f_b = {"data"}
    risks = ["security_vulnerability"]
    
    consensus, breakdown = ConsensusCalculatorV3.calculate_consensus(sol_a, sol_b, f_a, f_b, risks)
    assert breakdown["penalty_applied"] is True
    assert consensus < 1.0

def test_entropy_marker_fragility():
    # Low fragility
    m1 = EntropyMarker("gpt-4", "openai", 0.0, seed=123, confidence_score=0.95, system_fingerprint="fp1")
    assert m1.is_deterministic is True
    assert m1.fragility_index < 0.1
    assert m1.get_warning() is None
    
    # High fragility
    m2 = EntropyMarker("gpt-4", "openai", 0.8, seed=None, confidence_score=0.4)
    assert m2.is_deterministic is False
    assert m2.fragility_index > 0.3
    assert "High fragility" in m2.get_warning()

def test_decision_trace_drift():
    m1 = EntropyMarker("v1", "openai", 0.0, system_fingerprint="fp1")
    m2 = EntropyMarker("v1", "openai", 0.0, system_fingerprint="fp2") # Changed fingerprint
    
    trace1 = DecisionTrace(path=["state1"], metrics={}, signals={})
    trace1.add_entropy_marker("state1", m1)
    
    trace2 = DecisionTrace(path=["state1"], metrics={}, signals={})
    trace2.add_entropy_marker("state1", m2)
    
    warnings = trace1.check_entropy_drift(trace2)
    assert any("System fingerprint changed" in w for w in warnings)

def test_state_contracts_validation():
    # Stagnation Report
    sr = StagnationReport(has_changes=True, is_no_op=False, jaccard_similarity=0.5, cfg_difference=1, stagnation_count=0, recommendation="continue")
    assert StateContracts.validate_stagnation_report(sr) is True
    assert StateContracts.validate_stagnation_report({}) is False
    
    # Grounding Result
    gr = GroundingResult(tests_executed=True, tests_passed=5, tests_failed=0, test_errors=[], real_errors_found=False, should_fix=False, error_summary="")
    assert StateContracts.validate_grounding_result(gr) is True
    assert StateContracts.validate_grounding_result(GroundingResult(True, -1, 0, [], False, False, "")) is False
    
    # Senior Auditor
    sa = SeniorAuditorDecision(status="approved", confidence=0.9, rationale="Good", constitutional_violations=[], respects_grounding=True, respects_reflection=True, final_code="...", veto_active=False)
    assert StateContracts.validate_senior_auditor_decision(sa) is True

def test_debate_state_machine_flow(tmp_path):
    sm = DebateStateMachine(debate_id="test_123", workspace=tmp_path)
    sm.register_participant("builder_agent", "builder")
    
    # Transition 1
    art1 = Artifact.create("code v1", "code")
    sm._log_transition(DebateState.DRAFT, art1, model_version="gpt-4", model_family="openai")
    
    assert sm.current_state == DebateState.DRAFT
    assert sm.get_artifact(DebateState.DRAFT) == art1
    
    # Transition 2
    art2 = Artifact.create("code v1 normalized", "canonical_code", normalization_stats={})
    sm._log_transition(DebateState.NORMALIZE_SEMANTIC, art2)
    
    assert sm.current_state == DebateState.NORMALIZE_SEMANTIC
    assert len(sm.history) == 2
    
    # History persistence check
    assert sm.history_file.exists()
    
    # Replay
    sm_new = DebateStateMachine(debate_id="test_123", workspace=tmp_path)
    assert sm_new.replay_to_state(DebateState.DRAFT) is True
    assert sm_new.current_state == DebateState.DRAFT

def test_debate_participant_tracking(tmp_path):
    sm = DebateStateMachine(debate_id="test_tracking", workspace=tmp_path)
    sm.register_participant("p1", "skeptic")
    sm.track_participant_activity("p1", tokens_used=500)
    
    assert sm._participants["p1"]["tokens_used"] == 500
    assert sm._participants["p1"]["responses"] == 1
    
    # Test finalize with scoreboard (mocked)
    mock_sb = MagicMock()
    # Mock record_debate
    mock_sb.record_debate.return_value = MagicMock(value_score=0.8, cost_efficiency=0.9)
    sm.set_scoreboard(mock_sb)
    
    # Mock the whole agent_scoreboard module to avoid import issues
    mock_metrics = MagicMock()
    with patch.dict(sys.modules, {'agent_scoreboard': MagicMock(AgentMetrics=mock_metrics)}):
         sm.finalize_debate("approved", 0.85)
    
    assert mock_sb.record_debate.called
