import pytest
import ast
from kernel.ast_sanitizer import (
    AstSanitizer,
    SanitizationResult,
    SanitizationViolation,
    sanitize_code,
    BLACKLISTED_FUNCTIONS,
    BLACKLISTED_MODULES
)

def test_sanitization_result_add_violation():
    result = SanitizationResult(safe=True)
    node = ast.Name(id="test", lineno=1, col_offset=2)
    result.add_violation("test_rule", "test message", node)
    
    assert result.safe is False
    assert len(result.violations) == 1
    assert result.violations[0].rule == "test_rule"
    assert result.violations[0].line == 1
    assert result.violations[0].col == 2

def test_ast_sanitizer_safe_code():
    code = """
def add(a, b):
    return a + b

result = add(10, 20)
print(result)
"""
    sanitizer = AstSanitizer()
    result = sanitizer.sanitize(code)
    assert result.safe is True
    assert len(result.violations) == 0

def test_ast_sanitizer_blacklisted_functions():
    sanitizer = AstSanitizer()
    
    for func in ["eval('1+1')", "exec('import os')", "compile('1+1', '', 'eval')", "__import__('os')"]:
        result = sanitizer.sanitize(func)
        assert result.safe is False
        assert any(v.rule == "blacklisted_call" for v in result.violations)

def test_ast_sanitizer_blacklisted_modules():
    sanitizer = AstSanitizer()
    
    codes = [
        "import os",
        "import sys",
        "from subprocess import Popen",
        "import importlib.util"
    ]
    
    for code in codes:
        result = sanitizer.sanitize(code)
        assert result.safe is False
        assert any(v.rule == "blacklisted_import" for v in result.violations)

def test_ast_sanitizer_shell_true():
    sanitizer = AstSanitizer()
    
    code = "import subprocess_mock; subprocess.run('ls', shell=True)"
    # Note: the sanitizer resolves subprocess.run even if subprocess is not actually imported 
    # as long as the AST shows the call to subprocess.run.
    result = sanitizer.sanitize(code)
    assert result.safe is False
    assert any(v.rule == "shell_true" for v in result.violations)

def test_ast_sanitizer_protected_paths():
    sanitizer = AstSanitizer()
    
    bad_paths = [
        "open('/etc/passwd')",
        "open('/root/secret')",
        "open('.env')",
        "import pathlib; pathlib.Path('/etc/shadow')"
    ]
    
    for code in bad_paths:
        result = sanitizer.sanitize(code)
        assert result.safe is False
        assert any(v.rule == "protected_path" for v in result.violations)

def test_ast_sanitizer_dunder_attributes():
    sanitizer = AstSanitizer()
    
    code = "obj.__class__.__mro__"
    result = sanitizer.sanitize(code)
    assert result.safe is False
    # Should find 2 violations: __class__ and __mro__
    assert len(result.violations) >= 2
    assert all(v.rule == "blacklisted_attribute" for v in result.violations)

def test_ast_sanitizer_syntax_error():
    sanitizer = AstSanitizer()
    code = "if True" # Missing colon
    result = sanitizer.sanitize(code)
    assert result.safe is False
    assert result.error is not None
    assert any(v.rule == "syntax_error" for v in result.violations)

def test_ast_sanitizer_extra_functions():
    sanitizer = AstSanitizer(extra_blacklisted_functions={"custom_bad_func"})
    code = "custom_bad_func()"
    result = sanitizer.sanitize(code)
    assert result.safe is False
    assert any(v.rule == "blacklisted_call" and "custom_bad_func" in v.message for v in result.violations)

def test_ast_sanitizer_is_safe():
    sanitizer = AstSanitizer()
    assert sanitizer.is_safe("x = 1") is True
    assert sanitizer.is_safe("eval('1')") is False

def test_sanitize_code_helper():
    result = sanitize_code("x = 1")
    assert result.safe is True
    
    result = sanitize_code("import os")
    assert result.safe is False

def test_ast_sanitizer_empty_code():
    sanitizer = AstSanitizer()
    assert sanitizer.sanitize("").safe is True
    assert sanitizer.sanitize("  \n  ").safe is True
