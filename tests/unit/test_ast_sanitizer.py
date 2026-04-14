import pytest
import ast
from kernel.ast_sanitizer import (
    AstSanitizer,
    SanitizationResult,
    SanitizationViolation,
    sanitize_code,
    BLACKLISTED_FUNCTIONS,
    BLACKLISTED_MODULES,
    BLACKLISTED_ATTRIBUTES
)

def test_sanitization_result_add_violation():
    result = SanitizationResult(safe=True)
    node = ast.Name(id="test", lineno=1, col_offset=2)
    result.add_violation("test_rule", "test message", node)
    
    assert result.safe is False
    assert len(result.violations) == 1
    v = result.violations[0]
    assert v.rule == "test_rule"
    assert v.message == "test message"
    assert v.line == 1
    assert v.col == 2

def test_ast_sanitizer_safe_code():
    code = """
def factorial(n):
    if n == 0:
        return 1
    else:
        return n * factorial(n-1)

results = [factorial(i) for i in range(5)]
print(f"Factorials: {results}")
"""
    sanitizer = AstSanitizer()
    result = sanitizer.sanitize(code)
    assert result.safe is True
    assert len(result.violations) == 0

def test_ast_sanitizer_blacklisted_functions():
    sanitizer = AstSanitizer()
    for func in BLACKLISTED_FUNCTIONS:
        code = f"{func}('something')"
        result = sanitizer.sanitize(code)
        assert result.safe is False
        assert any(v.rule == "blacklisted_call" for v in result.violations)

def test_ast_sanitizer_blacklisted_modules_simple():
    sanitizer = AstSanitizer()
    for mod in BLACKLISTED_MODULES:
        result = sanitizer.sanitize(f"import {mod}")
        assert result.safe is False
        assert any(v.rule == "blacklisted_import" for v in result.violations)

def test_ast_sanitizer_import_from():
    sanitizer = AstSanitizer()
    # Direct import from blacklisted
    assert sanitizer.sanitize("from os import path").safe is False
    # Nested import from blacklisted
    assert sanitizer.sanitize("from importlib.util import find_spec").safe is False
    # Safe import
    assert sanitizer.sanitize("from math import sqrt").safe is True

def test_ast_sanitizer_import_alias():
    sanitizer = AstSanitizer()
    assert sanitizer.sanitize("import os as compromised").safe is False
    assert sanitizer.sanitize("from subprocess import Popen as Run").safe is False

def test_ast_sanitizer_shell_true():
    sanitizer = AstSanitizer()
    bad_calls = [
        "subprocess.run('ls', shell=True)",
        "subprocess.Popen(['ls'], shell=True)",
        "subprocess.call('ls', shell=1)", # Truthy value
        "subprocess.check_output('ls', shell=True)"
    ]
    for code in bad_calls:
        result = sanitizer.sanitize(code)
        assert result.safe is False
        assert any(v.rule == "shell_true" for v in result.violations)
    
    # False is OK
    assert sanitizer.sanitize("subprocess.run('ls', shell=False)").safe is True

def test_ast_sanitizer_protected_paths():
    sanitizer = AstSanitizer()
    bad_paths = [
        "open('/etc/passwd')",
        "open('/root/.bashrc')",
        "open('.env')",
        "pathlib.Path('/sys/kernel')",
        "open('~/.ssh/id_rsa')"
    ]
    for code in bad_paths:
        result = sanitizer.sanitize(code)
        assert result.safe is False
        assert any(v.rule == "protected_path" for v in result.violations)
    
    # Safe path
    assert sanitizer.sanitize("open('/tmp/data.txt')").safe is True

def test_ast_sanitizer_dunder_attributes():
    sanitizer = AstSanitizer()
    for attr in BLACKLISTED_ATTRIBUTES:
        code = f"x.{attr}"
        result = sanitizer.sanitize(code)
        assert result.safe is False
        assert any(v.rule == "blacklisted_attribute" for v in result.violations)

def test_ast_sanitizer_nested_dunder():
    sanitizer = AstSanitizer()
    code = "obj.__class__.__subclasses__()"
    result = sanitizer.sanitize(code)
    assert result.safe is False
    # Should catch both __class__ and __subclasses__
    violations = [v.message for v in result.violations]
    assert any("__class__" in m for m in violations)
    assert any("__subclasses__" in m for m in violations)

def test_ast_sanitizer_syntax_error():
    sanitizer = AstSanitizer()
    code = "def invalid_syntax(" # Missing closing paren and body
    result = sanitizer.sanitize(code)
    assert result.safe is False
    assert result.error is not None
    assert any(v.rule == "syntax_error" for v in result.violations)

def test_ast_sanitizer_extra_functions():
    sanitizer = AstSanitizer(extra_blacklisted_functions={"hack_me", "delete_world"})
    assert sanitizer.sanitize("hack_me()").safe is False
    assert sanitizer.sanitize("delete_world()").safe is False

def test_ast_sanitizer_empty_and_whitespace():
    sanitizer = AstSanitizer()
    assert sanitizer.sanitize("").safe is True
    assert sanitizer.sanitize("   \n\t   ").safe is True

def test_helper_functions():
    assert sanitize_code("print('hello')").safe is True
    assert sanitize_code("eval('1+1')").safe is False
    
    sanitizer = AstSanitizer()
    assert sanitizer.is_safe("x = 1") is True
    assert sanitizer.is_safe("import os") is False

def test_complex_attribute_resolution():
    sanitizer = AstSanitizer()
    # Test _resolve_call_name for deep attributes
    code = "a.b.c.d()"
    # This shouldn't be blocked, but we want to ensure it doesn't crash
    assert sanitizer.sanitize(code).safe is True
    
    # Blocking a nested call if the base is blacklisted
    # (Actually BLACKLISTED_FUNCTIONS are mostly top-level)
    code = "builtins.eval('1')"
    assert sanitizer.sanitize(code).safe is False
