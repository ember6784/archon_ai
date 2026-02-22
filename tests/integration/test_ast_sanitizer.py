"""
Tests for AstSanitizer - Barrier 3 (Static Analysis / AST Parsing).

Covers:
- Clean code passes sanitization
- Blocked function calls (eval, exec, compile, __import__)
- Blocked imports (os, subprocess, sys, ctypes, etc.)
- Blocked dunder attribute access (__class__, __subclasses__, etc.)
- subprocess with shell=True blocked
- Protected path access blocked
- Syntax errors handled gracefully
- Empty / whitespace code handled
- Convenience helpers (is_safe, sanitize_code)
"""

from kernel.ast_sanitizer import AstSanitizer, SanitizationResult, sanitize_code

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sanitize(code: str) -> SanitizationResult:
    return AstSanitizer().sanitize(code)


def _assert_violation(result: SanitizationResult, rule: str) -> None:
    rules = {v.rule for v in result.violations}
    assert rule in rules, f"Expected rule '{rule}' but got {rules}"


# ---------------------------------------------------------------------------
# Safe code
# ---------------------------------------------------------------------------

class TestSafeCode:
    def test_simple_function_is_safe(self) -> None:
        code = "def add(a, b):\n    return a + b\n"
        result = _sanitize(code)
        assert result.safe is True
        assert result.violations == []

    def test_list_comprehension_is_safe(self) -> None:
        code = "result = [x * 2 for x in range(10)]"
        result = _sanitize(code)
        assert result.safe is True

    def test_class_definition_is_safe(self) -> None:
        code = """
class Calculator:
    def __init__(self, value: int) -> None:
        self.value = value

    def add(self, n: int) -> int:
        return self.value + n
"""
        result = _sanitize(code)
        assert result.safe is True

    def test_standard_open_in_safe_path_is_ok(self) -> None:
        code = "with open('/tmp/safe.txt', 'r') as f:\n    data = f.read()\n"
        result = _sanitize(code)
        assert result.safe is True

    def test_empty_string_is_safe(self) -> None:
        result = _sanitize("")
        assert result.safe is True

    def test_whitespace_only_is_safe(self) -> None:
        result = _sanitize("   \n  \t  ")
        assert result.safe is True

    def test_comments_only_is_safe(self) -> None:
        result = _sanitize("# This is just a comment\n")
        assert result.safe is True


# ---------------------------------------------------------------------------
# Blocked function calls
# ---------------------------------------------------------------------------

class TestBlockedCalls:
    def test_eval_is_blocked(self) -> None:
        result = _sanitize("result = eval('1 + 1')")
        assert result.safe is False
        _assert_violation(result, "blacklisted_call")

    def test_exec_is_blocked(self) -> None:
        result = _sanitize("exec('print(\"hello\")')")
        assert result.safe is False
        _assert_violation(result, "blacklisted_call")

    def test_compile_is_blocked(self) -> None:
        result = _sanitize("code = compile('1+1', '<string>', 'eval')")
        assert result.safe is False
        _assert_violation(result, "blacklisted_call")

    def test_dunder_import_is_blocked(self) -> None:
        result = _sanitize("mod = __import__('os')")
        assert result.safe is False
        _assert_violation(result, "blacklisted_call")

    def test_multiple_violations_reported(self) -> None:
        code = "eval('x')\nexec('y')"
        result = _sanitize(code)
        assert result.safe is False
        assert len(result.violations) >= 2


# ---------------------------------------------------------------------------
# Blocked imports
# ---------------------------------------------------------------------------

class TestBlockedImports:
    def test_import_os_is_blocked(self) -> None:
        result = _sanitize("import os")
        assert result.safe is False
        _assert_violation(result, "blacklisted_import")

    def test_import_subprocess_is_blocked(self) -> None:
        result = _sanitize("import subprocess")
        assert result.safe is False
        _assert_violation(result, "blacklisted_import")

    def test_from_os_import_is_blocked(self) -> None:
        result = _sanitize("from os import path")
        assert result.safe is False
        _assert_violation(result, "blacklisted_import")

    def test_import_sys_is_blocked(self) -> None:
        result = _sanitize("import sys")
        assert result.safe is False
        _assert_violation(result, "blacklisted_import")

    def test_import_ctypes_is_blocked(self) -> None:
        result = _sanitize("import ctypes")
        assert result.safe is False
        _assert_violation(result, "blacklisted_import")

    def test_import_pickle_is_blocked(self) -> None:
        result = _sanitize("import pickle")
        assert result.safe is False
        _assert_violation(result, "blacklisted_import")

    def test_import_importlib_is_blocked(self) -> None:
        result = _sanitize("import importlib")
        assert result.safe is False
        _assert_violation(result, "blacklisted_import")

    def test_safe_import_allowed(self) -> None:
        result = _sanitize("import math\nimport json\nimport re")
        assert result.safe is True


# ---------------------------------------------------------------------------
# Blocked dunder attributes
# ---------------------------------------------------------------------------

class TestBlockedDunderAttributes:
    def test_dunder_class_is_blocked(self) -> None:
        result = _sanitize("x = obj.__class__")
        assert result.safe is False
        _assert_violation(result, "blacklisted_attribute")

    def test_subclasses_is_blocked(self) -> None:
        result = _sanitize("subs = object.__subclasses__()")
        assert result.safe is False
        _assert_violation(result, "blacklisted_attribute")

    def test_mro_is_blocked(self) -> None:
        result = _sanitize("mro = MyClass.__mro__")
        assert result.safe is False
        _assert_violation(result, "blacklisted_attribute")

    def test_globals_is_blocked(self) -> None:
        result = _sanitize("g = func.__globals__")
        assert result.safe is False
        _assert_violation(result, "blacklisted_attribute")

    def test_builtins_is_blocked(self) -> None:
        result = _sanitize("b = func.__builtins__")
        assert result.safe is False
        _assert_violation(result, "blacklisted_attribute")


# ---------------------------------------------------------------------------
# Shell injection patterns
# ---------------------------------------------------------------------------

class TestShellInjection:
    def test_subprocess_call_shell_true_blocked(self) -> None:
        code = "import subprocess\nsubprocess.call(['ls'], shell=True)"
        result = _sanitize(code)
        assert result.safe is False

    def test_subprocess_run_shell_true_blocked(self) -> None:
        code = "subprocess.run('ls -la', shell=True)"
        result = _sanitize(code)
        assert result.safe is False

    def test_subprocess_popen_shell_true_blocked(self) -> None:
        code = "subprocess.Popen('echo hi', shell=True)"
        result = _sanitize(code)
        assert result.safe is False

    def test_subprocess_call_without_shell_not_flagged(self) -> None:
        code = "subprocess.call(['ls', '-la'])"
        result = _sanitize(code)
        violations = [v for v in result.violations if v.rule == "shell_true"]
        assert violations == []


# ---------------------------------------------------------------------------
# Protected path access
# ---------------------------------------------------------------------------

class TestProtectedPathAccess:
    def test_open_etc_blocked(self) -> None:
        result = _sanitize("open('/etc/passwd', 'r')")
        assert result.safe is False
        _assert_violation(result, "protected_path")

    def test_open_sys_blocked(self) -> None:
        result = _sanitize("open('/sys/kernel/ksyms', 'r')")
        assert result.safe is False
        _assert_violation(result, "protected_path")

    def test_open_proc_blocked(self) -> None:
        result = _sanitize("open('/proc/self/mem', 'rb')")
        assert result.safe is False
        _assert_violation(result, "protected_path")

    def test_open_safe_path_allowed(self) -> None:
        result = _sanitize("open('/tmp/data.txt', 'r')")
        assert result.safe is True


# ---------------------------------------------------------------------------
# Syntax error handling
# ---------------------------------------------------------------------------

class TestSyntaxErrors:
    def test_syntax_error_returns_not_safe(self) -> None:
        result = _sanitize("def broken(:\n    pass")
        assert result.safe is False
        assert result.error is not None
        _assert_violation(result, "syntax_error")

    def test_syntax_error_does_not_raise(self) -> None:
        result = _sanitize("this is not valid python !!!@#")
        assert result.safe is False


# ---------------------------------------------------------------------------
# Convenience helpers
# ---------------------------------------------------------------------------

class TestConvenienceHelpers:
    def test_is_safe_returns_true_for_clean_code(self) -> None:
        sanitizer = AstSanitizer()
        assert sanitizer.is_safe("x = 1 + 2") is True

    def test_is_safe_returns_false_for_eval(self) -> None:
        sanitizer = AstSanitizer()
        assert sanitizer.is_safe("eval('1')") is False

    def test_module_level_sanitize_code(self) -> None:
        result = sanitize_code("import os")
        assert result.safe is False

    def test_module_level_sanitize_code_clean(self) -> None:
        result = sanitize_code("def f(x): return x + 1")
        assert result.safe is True


# ---------------------------------------------------------------------------
# Violation metadata
# ---------------------------------------------------------------------------

class TestViolationMetadata:
    def test_violation_includes_line_number(self) -> None:
        code = "x = 1\neval('bad')\ny = 3"
        result = _sanitize(code)
        assert result.safe is False
        assert any(v.line == 2 for v in result.violations)

    def test_violation_has_rule_and_message(self) -> None:
        result = _sanitize("exec('code')")
        assert result.safe is False
        v = result.violations[0]
        assert v.rule == "blacklisted_call"
        assert "exec" in v.message
