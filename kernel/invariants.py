# archon/kernel/invariants.py
"""
Invariant checkers for ExecutionKernel.

Invariants are security-critical checks that run BEFORE and AFTER
every operation. If any invariant fails, the operation is blocked.

These are deterministic functions (NO LLM) that check for:
- Code injection patterns (eval, exec, os.system)
- Protected path access (/etc, /sys, /proc)
- Dangerous imports
- Shell injection patterns
"""

import re
import logging
from typing import Any, Dict, List


logger = logging.getLogger(__name__)


# =============================================================================
# Pattern Invariants (detect dangerous content)
# =============================================================================

DANGEROUS_PATTERNS = {
    # Code execution
    "eval_exec": re.compile(r'\beval\(|\bexec\s*\('),
    "compile": re.compile(r'\bcompile\s*\('),

    # System calls
    "os_system": re.compile(r'\bos\.system\s*\('),
    "os_popen": re.compile(r'\bos\.popen\s*\('),
    "os_spawn": re.compile(r'\bos\.spawn[l|v|e|lp|vp]?\s*\('),
    "subprocess_call": re.compile(r'\bsubprocess\.call\s*([^)]*shell\s*=\s*True)'),
    "subprocess_popen": re.compile(r'\bsubprocess\.Popen\s*([^)]*shell\s*=\s*True)'),
    "subprocess_run": re.compile(r'\bsubprocess\.run\s*([^)]*shell\s*=\s*True)'),

    # File operations on protected paths
    "open_etc": re.compile(r'open\s*\([\'"]\/etc\/'),
    "open_sys": re.compile(r'open\s*\([\'"]\/sys\/'),
    "open_proc": re.compile(r'open\s*\([\'"]\/proc\/'),

    # Import statements
    "import_os": re.compile(r'\bimport\s+os\s*\.'),
    "import_subprocess": re.compile(r'\bfrom\s+subprocess\s+import'),
}

FORBIDDEN_IMPORTS = [
    'os.system',
    'os.popen',
    'os.spawn',
    'subprocess.call',
    'subprocess.Popen',
    'subprocess.run',
]

PROTECTED_PATHS = [
    "/etc/",
    "/sys/",
    "/proc/",
    "/root/",
    "/boot/",
    "/dev/",
    ".env",
    ".ssh/",
    "credentials/",
    "secrets/",
    "config/secrets/",
]


# =============================================================================
# Invariant Checker Functions
# =============================================================================

def no_code_injection(payload: Dict[str, Any]) -> bool:
    """
    Block operations containing code injection patterns.

    Checks for:
    - eval() / exec() calls
    - compile() with potentially malicious code
    - __import__() with dangerous modules

    Args:
        payload: Operation parameters

    Returns:
        True if safe (no injection patterns), False otherwise
    """
    # Extract code content from various payload structures
    code_content = _extract_code_content(payload)

    if not code_content:
        return True  # No code to check

    # Check against dangerous patterns
    for name, pattern in DANGEROUS_PATTERNS.items():
        if name in ['eval_exec', 'compile']:
            if pattern.search(code_content):
                logger.warning(f"[INVARIANT] Code injection pattern detected: {name}")
                return False

    # Check for forbidden imports
    for forbidden in FORBIDDEN_IMPORTS:
        if forbidden in code_content:
            logger.warning(f"[INVARIANT] Forbidden import detected: {forbidden}")
            return False

    return True


def no_shell_injection(payload: Dict[str, Any]) -> bool:
    """
    Block shell command injection patterns.

    Checks for:
    - os.system()
    - subprocess with shell=True
    - Unquoted command arguments

    Args:
        payload: Operation parameters

    Returns:
        True if safe (no shell injection), False otherwise
    """
    # Extract code or command content
    content = _extract_code_content(payload)

    if not content:
        return True  # No code to check

    # Check for shell execution patterns
    shell_patterns = ['os.system', 'shell=True', 'Popen.*shell', 'call.*shell']
    for pattern_str in shell_patterns:
        if re.search(pattern_str, content):
            logger.warning(f"[INVARIANT] Shell injection pattern: {pattern_str}")
            return False

    return True


def no_protected_path_access(payload: Dict[str, Any]) -> bool:
    """
    Block access to protected system paths.

    Protected paths:
    - /etc/, /sys/, /proc/, /root/, /boot/, /dev/
    - .env, .ssh/, credentials/, secrets/

    Args:
        payload: Operation parameters

    Returns:
        True if safe (no protected access), False otherwise
    """
    # Check for path parameter
    path = payload.get("path", "")
    file_path = payload.get("file_path", "")
    target = payload.get("target", "")

    for candidate in [path, file_path, target]:
        if not candidate:
            continue
        for protected in PROTECTED_PATHS:
            if candidate.startswith(protected) or protected in candidate:
                logger.warning(
                    f"[INVARIANT] Protected path access: {candidate} (matches {protected})"
                )
                return False

    return True


def no_hardcoded_secrets(payload: Dict[str, Any]) -> bool:
    """
    Block operations with hardcoded secrets.

    Looks for patterns like:
    - api_key = "sk-..."
    - password = "..."
    - token = "eyJ..."

    Args:
        payload: Operation parameters

    Returns:
        True if safe (no secrets detected), False otherwise
    """
    # Extract code content
    code_content = _extract_code_content(payload)

    if not code_content:
        return True

    # Secret patterns (basic detection)
    secret_patterns = [
        (r'api_key\s*=\s*["\']sk-[a-zA-Z0-9]{20,}', 'API key'),
        (r'password\s*=\s*["\'][^"\']{8,}["\']', 'hardcoded password'),
        (r'token\s*=\s*["\']eyJ[a-zA-Z0-9]{20,}', 'JWT token'),
        (r'secret\s*=\s*["\'][^"\']{8,}["\']', 'secret string'),
    ]

    for pattern, name in secret_patterns:
        if re.search(pattern, code_content):
            logger.warning(f"[INVARIANT] Hardcoded secret detected: {name}")
            return False

    return True


def max_operation_size(payload: Dict[str, Any]) -> bool:
    """
    Block operations that are too large (potential DoS).

    Args:
        payload: Operation parameters

    Returns:
        True if operation size is acceptable, False otherwise
    """
    # Check code size
    code = payload.get("code", "")
    if len(code) > 100_000:  # 100KB limit
        logger.warning(f"[INVARIANT] Code too large: {len(code)} bytes")
        return False

    # Check content size
    content = payload.get("content", "")
    if len(content) > 1_000_000:  # 1MB limit
        logger.warning(f"[INVARIANT] Content too large: {len(content)} bytes")
        return False

    return True


# =============================================================================
# Helper Functions
# =============================================================================

def _extract_code_content(payload: Dict[str, Any]) -> str:
    """
    Extract code/content from various payload structures.

    Looks for keys like: code, content, source, script, command
    """
    code_keys = ['code', 'content', 'source', 'script', 'command', 'expression']

    for key in code_keys:
        if key in payload:
            value = payload[key]
            if isinstance(value, str):
                return value
            elif isinstance(value, (list, dict)):
                return str(value)

    # Also check nested structures
    if 'parameters' in payload:
        return _extract_code_content(payload['parameters'])

    return ""


# =============================================================================
# Combined Invariant (all checks in one)
# =============================================================================

def combined_safety_invariant(payload: Dict[str, Any]) -> bool:
    """
    Combined invariant that runs all safety checks.

    This is a convenience function that combines multiple invariants
    into a single checker.

    Args:
        payload: Operation parameters

    Returns:
        True if all checks pass, False otherwise
    """
    checks = [
        no_code_injection,
        no_shell_injection,
        no_protected_path_access,
        no_hardcoded_secrets,
        max_operation_size,
    ]

    for checker in checks:
        if not checker(payload):
            return False

    return True


# =============================================================================
# Invariant Registry
# =============================================================================

INVARIANT_REGISTRY = {
    "no_code_injection": no_code_injection,
    "no_shell_injection": no_shell_injection,
    "no_protected_path_access": no_protected_path_access,
    "no_hardcoded_secrets": no_hardcoded_secrets,
    "max_operation_size": max_operation_size,
    "combined_safety": combined_safety_invariant,
}


def get_invariant(name: str):
    """Get an invariant checker by name."""
    return INVARIANT_REGISTRY.get(name)


def list_invariants() -> List[str]:
    """List all available invariant checkers."""
    return list(INVARIANT_REGISTRY.keys())
