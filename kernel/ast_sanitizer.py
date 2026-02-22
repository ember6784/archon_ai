# archon/kernel/ast_sanitizer.py
"""
AST Sanitizer - Static analysis barrier for code safety.

Implements Barrier 3 (Static Analysis / AST Parsing) from the 5-barrier
security model. Parses Python source code and rejects any AST nodes that
could lead to privilege escalation or sandbox escape.

Blocked constructs:
- eval() / exec() / compile() calls
- __import__() direct calls
- os.system / subprocess with shell=True
- open() targeting protected paths
- Dangerous dunder attribute access (__class__, __mro__, __subclasses__)
- Import of blacklisted modules (os, sys, subprocess, importlib)
"""

import ast
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


BLACKLISTED_FUNCTIONS = {
    "eval",
    "exec",
    "compile",
    "__import__",
    "execfile",
    "input",
}

BLACKLISTED_MODULES = {
    "os",
    "sys",
    "subprocess",
    "importlib",
    "ctypes",
    "cffi",
    "socket",
    "pickle",
    "shelve",
    "marshal",
    "builtins",
    "pty",
    "termios",
}

BLACKLISTED_ATTRIBUTES = {
    "__class__",
    "__bases__",
    "__mro__",
    "__subclasses__",
    "__globals__",
    "__builtins__",
    "__code__",
    "__closure__",
    "__dict__",
}

PROTECTED_PATH_PREFIXES = (
    "/etc/",
    "/sys/",
    "/proc/",
    "/root/",
    "/boot/",
    "/dev/",
    "~/.ssh",
    ".env",
)


@dataclass
class SanitizationViolation:
    """A single AST-level violation found during sanitization."""
    rule: str
    message: str
    line: int | None = None
    col: int | None = None


@dataclass
class SanitizationResult:
    """Result returned by AstSanitizer.sanitize()."""
    safe: bool
    violations: list[SanitizationViolation] = field(default_factory=list)
    error: str | None = None

    def add_violation(self, rule: str, message: str, node: ast.AST | None = None) -> None:
        line = getattr(node, "lineno", None)
        col = getattr(node, "col_offset", None)
        self.violations.append(SanitizationViolation(rule=rule, message=message, line=line, col=col))
        self.safe = False


class _SafetyVisitor(ast.NodeVisitor):
    """AST visitor that collects safety violations."""

    def __init__(self, result: SanitizationResult) -> None:
        self._result = result

    # ------------------------------------------------------------------
    # Import checks
    # ------------------------------------------------------------------

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            root = alias.name.split(".")[0]
            if root in BLACKLISTED_MODULES:
                self._result.add_violation(
                    "blacklisted_import",
                    f"Import of blacklisted module '{alias.name}' is forbidden",
                    node,
                )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        root = module.split(".")[0]
        if root in BLACKLISTED_MODULES:
            self._result.add_violation(
                "blacklisted_import",
                f"Import from blacklisted module '{module}' is forbidden",
                node,
            )
        self.generic_visit(node)

    # ------------------------------------------------------------------
    # Call checks
    # ------------------------------------------------------------------

    def visit_Call(self, node: ast.Call) -> None:
        func_name = self._resolve_call_name(node.func)

        if func_name in BLACKLISTED_FUNCTIONS:
            self._result.add_violation(
                "blacklisted_call",
                f"Call to '{func_name}()' is forbidden",
                node,
            )

        # subprocess / os calls with shell=True
        if func_name in {
            "subprocess.call",
            "subprocess.run",
            "subprocess.Popen",
            "subprocess.check_output",
        }:
            for kw in node.keywords:
                if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value:
                    self._result.add_violation(
                        "shell_true",
                        f"'{func_name}(shell=True)' is forbidden - use explicit argument lists",
                        node,
                    )

        # open() targeting protected paths
        if func_name in {"open", "pathlib.Path"} and node.args:
            first_arg = node.args[0]
            if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
                path_str = first_arg.value
                if any(path_str.startswith(prefix) for prefix in PROTECTED_PATH_PREFIXES):
                    self._result.add_violation(
                        "protected_path",
                        f"Access to protected path '{path_str}' is forbidden",
                        node,
                    )

        self.generic_visit(node)

    # ------------------------------------------------------------------
    # Attribute checks
    # ------------------------------------------------------------------

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr in BLACKLISTED_ATTRIBUTES:
            self._result.add_violation(
                "blacklisted_attribute",
                f"Access to dunder attribute '{node.attr}' is forbidden",
                node,
            )
        self.generic_visit(node)

    # ------------------------------------------------------------------
    # Helper
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_call_name(func: ast.expr) -> str:
        """Return a dotted string representation of a call target."""
        if isinstance(func, ast.Name):
            return func.id
        if isinstance(func, ast.Attribute):
            parent = _SafetyVisitor._resolve_call_name(func.value)
            return f"{parent}.{func.attr}" if parent else func.attr
        return ""


class AstSanitizer:
    """
    Static code analysis sanitizer.

    Parses Python source code into an AST and walks it looking for
    constructs that violate the kernel's safety invariants.

    Usage::

        sanitizer = AstSanitizer()
        result = sanitizer.sanitize(code_string)
        if not result.safe:
            for v in result.violations:
                print(v.rule, v.message)
    """

    def __init__(self, extra_blacklisted_functions: set[str] | None = None) -> None:
        self._extra_functions = extra_blacklisted_functions or set()

    def sanitize(self, code: str, filename: str = "<agent_code>") -> SanitizationResult:
        """
        Parse and analyse Python source code for safety violations.

        Args:
            code: Python source code string to analyse.
            filename: Optional label used in error messages.

        Returns:
            SanitizationResult with safe=True if no violations were found.
        """
        result = SanitizationResult(safe=True)

        if not code or not code.strip():
            return result

        try:
            tree = ast.parse(code, filename=filename)
        except SyntaxError as exc:
            result.safe = False
            result.error = f"Syntax error at line {exc.lineno}: {exc.msg}"
            result.violations.append(
                SanitizationViolation(
                    rule="syntax_error",
                    message=result.error,
                    line=exc.lineno,
                )
            )
            return result

        if self._extra_functions:
            global BLACKLISTED_FUNCTIONS  # noqa: PLW0603
            BLACKLISTED_FUNCTIONS = BLACKLISTED_FUNCTIONS | self._extra_functions

        visitor = _SafetyVisitor(result)
        visitor.visit(tree)

        if not result.safe:
            logger.warning(
                f"[AST_SANITIZER] {len(result.violations)} violation(s) in '{filename}': "
                + "; ".join(v.rule for v in result.violations)
            )
        else:
            logger.debug(f"[AST_SANITIZER] '{filename}' passed all AST checks")

        return result

    def is_safe(self, code: str) -> bool:
        """Convenience method — returns True only when no violations are found."""
        return self.sanitize(code).safe


def sanitize_code(code: str) -> SanitizationResult:
    """Module-level helper for one-shot sanitization."""
    return AstSanitizer().sanitize(code)
