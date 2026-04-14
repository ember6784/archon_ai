import pytest
import json
from pathlib import Path
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
    DraftOutput,
    StagnationReport,
    GroundingResult,
    FreshEyeResult,
    SeniorAuditorDecision
)

def test_artifact_creation():
    content = "print('hello')"
    artifact = Artifact.create(content, "code", author="test")
    assert artifact.content == content
    assert artifact.content_type == "code"
    assert artifact.metadata["author"] == "test"
    assert artifact.hash is not None
    assert len(artifact.hash) == 64 # SHA-256

def test_structural_fingerprint():
    code = """
import os
from sys import path

class MyClass(Base):
    async def my_async_func(self):
        pass

def my_func():
    pass
"""
    sf = StructuralFingerprint(module_name="test_mod")
    symbols = sf.extract_fingerprint(code)
    
    assert "test_mod::import:os" in symbols
    assert "test_mod::from_import:sys.path" in symbols
    assert "test_mod::class:MyClass" in symbols
    assert "test_mod::inherits:Base" in symbols
    assert "test_mod::async_func:my_async_func" in symbols
    assert "test_mod::func:my_func" in symbols

def test_calculate_jaccard():
    set_a = {"a", "b", "c"}
    set_b = {"b", "c", "d"}
    # intersection: {b, c} (size 2)
    # union: {a, b, c, d} (size 4)
    assert calculate_jaccard(set_a, set_b) == 0.5
    
    assert calculate_jaccard(set(), set()) == 1.0
    assert calculate_jaccard({"a"}, set()) == 0.0

def test_consensus_calculator():
    sol_a = "def add(a, b): return a + b"
    sol_b = "def add(x, y): return x + y"
    f_a = {"func:add"}
    f_b = {"func:add"}
    risks = []
    
    consensus, breakdown = ConsensusCalculatorV3.calculate_consensus(sol_a, sol_b, f_a, f_b, risks)
    assert 0 <= consensus <= 1.0
    assert breakdown["jaccard_similarity"] == 1.0
    assert breakdown["penalty_applied"] is False

def test_consensus_calculator_penalty():
    sol_a = "x = 1"
    sol_b = "x = 1"
    f_a = {"var:x"}
    f_b = {"var:x"}
    risks = ["security_risk"] # There are risks but no changes
    
    consensus, breakdown = ConsensusCalculatorV3.calculate_consensus(sol_a, sol_b, f_a, f_b, risks)
    assert breakdown["penalty_applied"] is True
    assert breakdown["final_consensus"] < 1.0

def test_entropy_marker():
    marker = EntropyMarker(
        model_version="gpt-4",
        model_family="openai",
        temperature=0.0,
        seed=123,
        confidence_score=0.9
    )
    assert marker.is_deterministic is True
    assert marker.fragility_index < 0.1
    assert marker.to_dict()["model_version"] == "gpt-4"

def test_decision_trace_drift():
    m1 = EntropyMarker("v1", "f1", 0.0, seed=1)
    m2 = EntropyMarker("v2", "f1", 0.0, seed=1)
    
    trace1 = DecisionTrace(path=["A"], metrics={}, signals={})
    trace1.add_entropy_marker("state1", m1)
    
    trace2 = DecisionTrace(path=["A"], metrics={}, signals={})
    trace2.add_entropy_marker("state1", m2)
    
    warnings = trace1.check_entropy_drift(trace2)
    assert any("Model version changed" in w for w in warnings)

def test_state_contracts():
    # Test valid draft input
    di = DraftInput(task="do something", task_type="code", context={})
    assert StateContracts.validate_draft_input(di) is True
    assert StateContracts.validate_draft_input({}) is False
    
    # Test draft output validation
    art = Artifact.create("code", "code", rationale="because")
    assert StateContracts.validate_draft_output(art) is True
    
    # Test fortify output validation (should fail if new symbols added)
    art_bad = Artifact.create("code", "code", new_symbols_added=["new_func"])
    assert StateContracts.validate_fortify_output(art_bad) is False

@pytest.fixture
def mock_artifact():
    return Artifact.create("content", "code")

def test_debate_state_machine(tmp_path):
    workspace = tmp_path / "workspace"
    sm = DebateStateMachine(debate_id="test_debate", workspace=workspace)
    
    art = Artifact.create("proposed code", "code")
    sm._log_transition(DebateState.DRAFT, art, model_version="gpt-4", model_family="openai")
    
    assert sm.current_state == DebateState.DRAFT
    assert sm.get_artifact(DebateState.DRAFT) == art
    assert len(sm.history) == 1
    
    # Check if history file was created
    assert sm.history_file.exists()
    
    # Test replay
    sm2 = DebateStateMachine(debate_id="test_debate", workspace=workspace)
    assert sm2.replay_to_state(DebateState.DRAFT) is True
    assert sm2.current_state == DebateState.DRAFT

def test_debate_participant_activity(tmp_path):
    sm = DebateStateMachine(debate_id="test", workspace=tmp_path)
    sm.register_participant("agent1", "builder")
    sm.track_participant_activity("agent1", tokens_used=100)
    
    assert "agent1" in sm._participants
    assert sm._participants["agent1"]["tokens_used"] == 100
    assert sm._participants["agent1"]["responses"] == 1
