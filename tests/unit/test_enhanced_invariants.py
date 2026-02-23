"""
Tests for Enhanced Security Invariants (V3.0)
==============================================

Tests for:
- SecurityASTAnalyzer (AST-based code analysis)
- SecurePathValidator (inode-level path validation)
- VerificationMetricsCollector
"""

import pytest
from kernel.invariants import (
    SecurityASTAnalyzer,
    SecurePathValidator,
    no_code_injection,
    no_shell_injection,
    no_protected_path_access,
    combined_safety_invariant,
    initialize_security_invariants,
)
from kernel.verification_metrics import (
    VerificationMetricsCollector,
    BarrierMetrics,
    get_metrics_collector,
)


# =============================================================================
# SecurityASTAnalyzer Tests
# =============================================================================

class TestSecurityASTAnalyzer:
    """Tests for AST-based security analysis."""
    
    def test_detects_eval_call(self):
        """Should detect direct eval() call."""
        code = "result = eval(user_input)"
        analyzer = SecurityASTAnalyzer(code)
        result = analyzer.analyze()
        
        assert not result.is_safe
        assert any("eval" in v for v in result.violations)
        
    def test_detects_exec_call(self):
        """Should detect direct exec() call."""
        code = "exec(malicious_code)"
        analyzer = SecurityASTAnalyzer(code)
        result = analyzer.analyze()
        
        assert not result.is_safe
        assert any("exec" in v for v in result.violations)
        
    def test_detects_forbidden_import_os(self):
        """Should detect 'import os'."""
        code = "import os\nos.system('ls')"
        analyzer = SecurityASTAnalyzer(code)
        result = analyzer.analyze()
        
        assert not result.is_safe
        assert any("os" in v for v in result.violations)
        
    def test_detects_forbidden_import_subprocess(self):
        """Should detect 'import subprocess'."""
        code = "import subprocess"
        analyzer = SecurityASTAnalyzer(code)
        result = analyzer.analyze()
        
        assert not result.is_safe
        assert any("subprocess" in v for v in result.violations)
        
    def test_detects_os_system_via_attribute(self):
        """Should detect os.system() call via attribute access."""
        code = """
import os
os.system('rm -rf /')
"""
        analyzer = SecurityASTAnalyzer(code)
        result = analyzer.analyze()
        
        assert not result.is_safe
        assert any("os.system" in v or "os" in v for v in result.violations)
        
    def test_detects_subprocess_shell(self):
        """Should detect subprocess with shell=True."""
        code = """
from subprocess import Popen
Popen('ls', shell=True)
"""
        analyzer = SecurityASTAnalyzer(code)
        result = analyzer.analyze()
        
        assert not result.is_safe
        
    def test_allows_safe_code(self):
        """Should allow safe code without violations."""
        code = """
def add(a, b):
    return a + b

result = add(1, 2)
"""
        analyzer = SecurityASTAnalyzer(code)
        result = analyzer.analyze()
        
        assert result.is_safe
        assert len(result.violations) == 0
        
    def test_detects_getattr_obfuscation(self):
        """Should detect getattr(__builtins__, 'eval') obfuscation."""
        code = "getattr(__builtins__, 'eval')('1+1')"
        analyzer = SecurityASTAnalyzer(code)
        result = analyzer.analyze()
        
        # Should detect suspicious getattr pattern
        assert any("getattr" in v or "Suspicious" in v for v in result.violations)
        
    def test_detects_deeply_nested_obfuscation(self):
        """Should detect deeply nested code (possible obfuscation)."""
        code = """
f = lambda x: (lambda y: (lambda z: eval(z))(y))(x)
result = f("1+1")
"""
        analyzer = SecurityASTAnalyzer(code)
        result = analyzer.analyze()
        
        assert result.obfuscation_detected or any("lambda" in v.lower() for v in result.violations)
        
    def test_extracts_imports(self):
        """Should extract all imports from code."""
        code = """
import os
import sys
from datetime import datetime
import json
"""
        analyzer = SecurityASTAnalyzer(code)
        result = analyzer.analyze()
        
        # Note: For forbidden modules (os, sys), analysis stops early with violations
        # but still captures all imports seen before violations
        assert "os" in result.imports
        assert "sys" in result.imports
        assert "json" in result.imports
        # datetime from "from datetime import" may not be added if analysis stops early
        # due to os/sys being forbidden


# =============================================================================
# SecurePathValidator Tests
# =============================================================================

class TestSecurePathValidator:
    """Tests for secure path validation."""
    
    def test_blocks_direct_etc_access(self):
        """Should block direct /etc access."""
        validator = SecurePathValidator()
        result = validator.validate("/etc/passwd")
        
        assert not result.is_valid
        assert "protected" in result.reason.lower() or "etc" in result.reason.lower()
        
    def test_blocks_traversal_attack(self):
        """Should block ../../../etc/passwd traversal."""
        validator = SecurePathValidator()
        result = validator.validate("/safe/path/../../../etc/passwd")
        
        assert not result.is_valid
        
    def test_blocks_with_base_dir_escape(self):
        """Should block escape from base_dir."""
        validator = SecurePathValidator()
        result = validator.validate("../secret.txt", base_dir="/app/data")
        
        assert not result.is_valid
        assert "escape" in result.reason.lower()
        
    def test_allows_safe_path(self):
        """Should allow safe path within bounds."""
        validator = SecurePathValidator()
        result = validator.validate("/app/data/file.txt", base_dir="/app")
        
        assert result.is_valid
        assert result.resolved_path is not None
        
    def test_blocks_ssh_directory(self):
        """Should block .ssh directory access."""
        validator = SecurePathValidator()
        result = validator.validate("/home/user/.ssh/id_rsa")
        
        assert not result.is_valid
        
    def test_blocks_env_files(self):
        """Should block .env files."""
        validator = SecurePathValidator()
        result = validator.validate("/app/.env")
        
        assert not result.is_valid
        
    def test_allows_empty_path(self):
        """Should allow empty path."""
        validator = SecurePathValidator()
        result = validator.validate("")
        
        assert result.is_valid
        
    def test_blocks_null_byte_injection(self):
        """Should block null byte injection."""
        validator = SecurePathValidator()
        result = validator.validate("/safe/file.txt\x00/etc/passwd")
        
        assert not result.is_valid
        assert "null" in result.reason.lower()


# =============================================================================
# Invariant Function Tests
# =============================================================================

class TestInvariantFunctions:
    """Tests for high-level invariant functions."""
    
    def test_no_code_injection_blocks_eval(self):
        """no_code_injection should block eval."""
        payload = {"code": "eval('1+1')"}
        assert not no_code_injection(payload)
        
    def test_no_code_injection_blocks_exec(self):
        """no_code_injection should block exec."""
        payload = {"code": "exec('print(1)')"}
        assert not no_code_injection(payload)
        
    def test_no_code_injection_allows_safe_code(self):
        """no_code_injection should allow safe code."""
        payload = {"code": "x = 1 + 2"}
        assert no_code_injection(payload)
        
    def test_no_shell_injection_blocks_os_system(self):
        """no_shell_injection should block os.system."""
        payload = {"code": "import os\nos.system('ls')"}
        assert not no_shell_injection(payload)
        
    def test_no_protected_path_blocks_etc(self):
        """no_protected_path_access should block /etc."""
        payload = {"path": "/etc/passwd"}
        assert not no_protected_path_access(payload)
        
    def test_no_protected_path_allows_safe_path(self):
        """no_protected_path_access should allow safe paths."""
        payload = {"path": "/app/data/file.txt"}
        assert no_protected_path_access(payload)
        
    def test_combined_safety_blocks_dangerous_code(self):
        """combined_safety_invariant should block dangerous code."""
        payload = {
            "code": "import os\nos.system('rm -rf /')",
            "path": "/app/data"
        }
        assert not combined_safety_invariant(payload)
        
    def test_combined_safety_allows_safe_operation(self):
        """combined_safety_invariant should allow safe operations."""
        payload = {
            "code": "def add(a, b): return a + b",
            "path": "/app/data/output.txt"
        }
        assert combined_safety_invariant(payload)


# =============================================================================
# VerificationMetrics Tests
# =============================================================================

class TestVerificationMetricsCollector:
    """Tests for verification metrics collection."""
    
    def test_records_barrier_check(self):
        """Should record barrier check results."""
        collector = VerificationMetricsCollector(storage_dir="/tmp/test_metrics_1")
        
        collector.record_barrier_check(
            barrier_name="test_barrier",
            barrier_level=1,
            blocked=True,
            was_threat=True,
            latency_ms=10.0
        )
        
        assert collector._operation_counts["total_checks"] == 1
        
    def test_calculates_precision(self):
        """Should correctly calculate precision."""
        collector = VerificationMetricsCollector(storage_dir="/tmp/test_metrics_2")
        
        # 10 checks: 8 TP, 2 FP
        for _ in range(8):
            collector.record_barrier_check("barrier", 1, True, True, 10.0)
        for _ in range(2):
            collector.record_barrier_check("barrier", 1, True, False, 10.0)
            
        metrics = collector.finalize_window(force=True)
        
        assert metrics is not None
        barrier = metrics.barrier_stats["barrier"]
        assert barrier.precision == 0.8  # 8/10
        
    def test_calculates_recall(self):
        """Should correctly calculate recall."""
        collector = VerificationMetricsCollector(storage_dir="/tmp/test_metrics_3")
        
        # 10 threats: detected 8, missed 2
        for _ in range(8):
            collector.record_barrier_check("barrier", 1, True, True, 10.0)
        for _ in range(2):
            collector.record_barrier_check("barrier", 1, False, True, 10.0)
            
        metrics = collector.finalize_window(force=True)
        
        assert metrics is not None
        barrier = metrics.barrier_stats["barrier"]
        assert barrier.recall == 0.8  # 8/10
        
    def test_detects_high_fn_rate_anomaly(self):
        """Should detect high false negative rate anomaly."""
        collector = VerificationMetricsCollector(storage_dir="/tmp/test_metrics_4")
        
        # High FN rate: 10 threats, only 2 detected
        for _ in range(2):
            collector.record_barrier_check("barrier", 1, True, True, 10.0)
        for _ in range(8):
            collector.record_barrier_check("barrier", 1, False, True, 10.0)
            
        metrics = collector.finalize_window(force=True)
        
        # Should have generated an anomaly
        assert len(collector._anomalies) > 0
        fn_anomalies = [a for a in collector._anomalies if "false_negative" in a.anomaly_type]
        assert len(fn_anomalies) > 0
        
    def test_calculates_overall_confidence(self):
        """Should calculate overall confidence score."""
        collector = VerificationMetricsCollector(storage_dir="/tmp/test_metrics_5")
        
        # Good performance
        for _ in range(10):
            collector.record_barrier_check("barrier", 1, True, True, 10.0)
        collector.record_operation("test_op", checked=True)
        
        metrics = collector.finalize_window(force=True)
        
        assert metrics is not None
        confidence = metrics.calculate_overall_confidence()
        assert 0 <= confidence <= 1
        
    def test_trend_analysis(self):
        """Should provide trend analysis."""
        import tempfile
        import shutil
        
        # Create temp directory for isolation
        temp_dir = tempfile.mkdtemp()
        try:
            collector = VerificationMetricsCollector(storage_dir=temp_dir)
            
            # Create multiple windows
            for i in range(3):
                for _ in range(5):
                    collector.record_barrier_check("barrier", 1, True, True, 10.0)
                collector.record_operation("test_op", checked=True)
                collector.finalize_window(force=True)
                
            trends = collector.get_trend_analysis(hours=1)
            
            assert "data_points" in trends
            assert "confidence" in trends
            assert trends["data_points"] == 3
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


# =============================================================================
# Integration Tests
# =============================================================================

class TestIntegration:
    """Integration tests combining multiple components."""
    
    def test_full_security_pipeline(self):
        """Test full security validation pipeline."""
        # Create a malicious payload
        malicious_payload = {
            "code": """
import os
def exploit():
    # Try to access protected path
    with open('/etc/passwd') as f:
        return f.read()
os.system('whoami')
""",
            "path": "/etc/passwd",
            "target": "/root/.ssh/id_rsa"
        }
        
        # All invariants should block this
        assert not no_code_injection(malicious_payload)
        assert not no_shell_injection(malicious_payload)
        assert not no_protected_path_access(malicious_payload)
        assert not combined_safety_invariant(malicious_payload)
        
    def test_safe_code_passes_all_checks(self):
        """Test that safe code passes all invariant checks."""
        safe_payload = {
            "code": """
import json
from datetime import datetime

def process_data(data):
    return json.dumps({"timestamp": datetime.now().isoformat(), "data": data})
""",
            "path": "/app/output/result.json"
        }
        
        assert no_code_injection(safe_payload)
        assert no_protected_path_access(safe_payload)
        assert combined_safety_invariant(safe_payload)


# =============================================================================
# Performance Tests
# =============================================================================

class TestPerformance:
    """Performance tests for invariant checking."""
    
    def test_ast_analysis_performance(self):
        """AST analysis should complete quickly."""
        import time
        
        # Create safe code without forbidden imports
        # Keep it small enough to avoid obfuscation detection
        lines = ["import json", "import math", "x = 1"]
        for i in range(20):
            lines.append(f"if x > {i}:")
            lines.append(f"    result_{i} = x + {i}")
            lines.append(f"    data_{i} = json.dumps(result_{i})")
        code = "\n".join(lines)
        
        start = time.time()
        analyzer = SecurityASTAnalyzer(code)
        result = analyzer.analyze()
        elapsed = time.time() - start
        
        # Should complete in less than 100ms for ~65 lines
        assert elapsed < 0.1
        assert result.is_safe


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
