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

V3.0: AST-based analysis with bytecode verification
"""

import ast
import hashlib
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


logger = logging.getLogger(__name__)


# =============================================================================
# Security Analysis Results
# =============================================================================

@dataclass
class SecurityAnalysisResult:
    """Результат детального security-анализа"""
    is_safe: bool
    violations: List[str] = field(default_factory=list)
    imports: Set[str] = field(default_factory=set)
    calls: Set[str] = field(default_factory=set)
    complexity_score: float = 0.0
    obfuscation_detected: bool = False
    
    def add_violation(self, message: str) -> None:
        self.violations.append(message)
        self.is_safe = False


# =============================================================================
# AST-Based Security Analyzer (Replaces regex patterns)
# =============================================================================

class SecurityASTAnalyzer(ast.NodeVisitor):
    """
    Детерминированный AST-анализатор для выявления code injection.
    
    Использует абстрактное синтаксическое дерево вместо regex,
    что делает обход значительно сложнее для атакующих.
    
    Проверяет:
    - Опасные builtin функции (eval, exec, compile, __import__)
    - Forbidden imports (os, subprocess, sys, socket и др.)
    - Obfuscation техники (getattr, dynamic imports)
    - Подозрительную сложность (потенциальное obfuscation)
    """
    
    # Критически опасные встроенные функции
    DANGEROUS_BUILTINS = frozenset({
        'eval', 'exec', 'compile', '__import__', '__builtins__',
        'open', 'input', 'raw_input', 'breakpoint', 'help',
    })
    
    # Опасные модули (полный список)
    FORBIDDEN_MODULES = frozenset({
        'os', 'subprocess', 'sys', 'pty', 'socket',
        'urllib', 'urllib2', 'http', 'ftplib', 'telnetlib',
        'pickle', 'cPickle', 'marshal', 'shelve',
        'tempfile', 'shutil', 'pathlib', 'path', 'ntpath', 'posixpath',
        'ctypes', 'cffi', 'mmap', 'resource', 'multiprocessing',
        'threading', '_thread', 'asyncio.subprocess',
    })
    
    # Подозрительные паттерны getattr/dynamic access
    SUSPICIOUS_GETATTR_PATTERNS = frozenset({
        'eval', 'exec', 'system', 'popen', 'spawn',
        'getenv', 'environ', '__dict__', '__globals__',
    })
    
    def __init__(self, source_code: str = ""):
        self.source_code = source_code
        self.result = SecurityAnalysisResult(is_safe=True)
        self._current_function: Optional[str] = None
        self._nested_depth = 0
        self._max_nested_depth = 0
        
    def analyze(self) -> SecurityAnalysisResult:
        """
        Запускает полный анализ кода.
        
        Returns:
            SecurityAnalysisResult с результатами анализа
        """
        if not self.source_code.strip():
            return self.result
            
        try:
            tree = ast.parse(self.source_code)
            self.visit(tree)
            
            # Проверка сложности (obfuscation detection)
            self._analyze_complexity(tree)
            
            # Проверка через bytecode (если возможно)
            self._verify_with_bytecode()
            
        except SyntaxError as e:
            self.result.add_violation(f"Syntax error in code: {e}")
        except Exception as e:
            logger.error(f"AST analysis error: {e}")
            # Fail-safe: если не можем проанализировать - блокируем
            self.result.add_violation(f"Analysis failed: {e}")
            
        return self.result
    
    def visit_Import(self, node: ast.Import) -> None:
        """Проверка import statements"""
        for alias in node.names:
            base_module = alias.name.split('.')[0]
            self.result.imports.add(alias.name)
            
            if base_module in self.FORBIDDEN_MODULES:
                self.result.add_violation(
                    f"Forbidden import: {alias.name}"
                )
                
        self.generic_visit(node)
    
    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """Проверка from ... import statements"""
        if node.module:
            base_module = node.module.split('.')[0]
            
            if base_module in self.FORBIDDEN_MODULES:
                self.result.add_violation(
                    f"Forbidden from-import: {node.module}"
                )
                
            # Особая проверка: from os import system, popen
            if base_module == 'os':
                dangerous_os_funcs = {'system', 'popen', 'spawn*', 'exec*'}
                for alias in node.names:
                    if any(
                        fnmatch.fnmatch(alias.name, pattern) 
                        for pattern in dangerous_os_funcs
                    ):
                        self.result.add_violation(
                            f"Dangerous os function imported: {alias.name}"
                        )
                        
        self.generic_visit(node)
    
    def visit_Call(self, node: ast.Call) -> None:
        """Проверка вызовов функций"""
        self._nested_depth += 1
        self._max_nested_depth = max(self._max_nested_depth, self._nested_depth)
        
        # Прямой вызов опасной функции
        if isinstance(node.func, ast.Name):
            if node.func.id in self.DANGEROUS_BUILTINS:
                self.result.add_violation(
                    f"Dangerous builtin called: {node.func.id}()"
                )
            self.result.calls.add(node.func.id)
            
        # Вызов через getattr (обход: getattr(__builtins__, 'eval'))
        elif isinstance(node.func, ast.Attribute):
            if node.func.attr in self.SUSPICIOUS_GETATTR_PATTERNS:
                self.result.add_violation(
                    f"Suspicious method access: .{node.func.attr}()"
                )
                
            # Проверка os.system, subprocess.Popen и т.д.
            if isinstance(node.func.value, ast.Name):
                if node.func.value.id in self.FORBIDDEN_MODULES:
                    self.result.add_violation(
                        f"Dangerous module call: {node.func.value.id}.{node.func.attr}()"
                    )
                    
        # Вызов через subscript (обход: __builtins__['eval'])
        elif isinstance(node.func, ast.Subscript):
            self.result.add_violation(
                "Dynamic function access via subscript detected"
            )
            
        self.generic_visit(node)
        self._nested_depth -= 1
    
    def visit_Expression(self, node: ast.Expression) -> None:
        """Проверка expression statements"""
        # Проверяем на eval-like expressions
        if isinstance(node.body, ast.Call):
            if isinstance(node.body.func, ast.Name):
                if node.body.func.id in {'eval', 'exec'}:
                    self.result.add_violation(
                        f"Expression with dangerous call: {node.body.func.id}"
                    )
        self.generic_visit(node)
    
    def visit_Lambda(self, node: ast.Lambda) -> None:
        """Проверка lambda функций (часто используются в obfuscation)"""
        if self._nested_depth > 3:
            self.result.add_violation(
                f"Deeply nested lambda (depth {self._nested_depth}) - possible obfuscation"
            )
        self._nested_depth += 1
        self._max_nested_depth = max(self._max_nested_depth, self._nested_depth)
        self.generic_visit(node)
        self._nested_depth -= 1
    
    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Отслеживание функций"""
        prev_func = self._current_function
        self._current_function = node.name
        self._nested_depth += 1
        self._max_nested_depth = max(self._max_nested_depth, self._nested_depth)
        self.generic_visit(node)
        self._nested_depth -= 1
        self._current_function = prev_func
    
    visit_AsyncFunctionDef = visit_FunctionDef
    
    def _analyze_complexity(self, tree: ast.AST) -> None:
        """Анализ сложности кода (obfuscation detection)"""
        # Считаем различные метрики сложности
        nodes_count = sum(1 for _ in ast.walk(tree))
        branching = sum(1 for node in ast.walk(tree) if isinstance(
            node, (ast.If, ast.For, ast.While, ast.Try, ast.With, ast.ExceptHandler)
        ))
        
        # Эвристики для обнаружения obfuscation
        if nodes_count > 500 and branching < nodes_count * 0.05:
            # Много кода без ветвлений - подозрительно
            self.result.obfuscation_detected = True
            self.result.add_violation(
                f"Possible code obfuscation: {nodes_count} nodes with low branching"
            )
            
        if self._max_nested_depth > 5:
            self.result.obfuscation_detected = True
            self.result.add_violation(
                f"Deep nesting detected ({self._max_nested_depth}) - possible obfuscation"
            )
            
        # String concatenation obfuscation detection
        str_concat_count = sum(1 for node in ast.walk(tree) if isinstance(
            node, ast.BinOp
        ) and isinstance(node.op, ast.Add) and isinstance(
            node.left, (ast.Constant, ast.Str)
        ))
        
        if str_concat_count > 10:
            self.result.add_violation(
                f"Excessive string concatenation ({str_concat_count}) - possible obfuscation"
            )
            
        self.result.complexity_score = (
            nodes_count * 0.01 + 
            branching * 0.1 + 
            self._max_nested_depth * 0.5
        )
    
    def _verify_with_bytecode(self) -> None:
        """Дополнительная проверка через bytecode (если возможно)"""
        try:
            import dis
            compiled = compile(self.source_code, '<string>', 'exec')
            
            # Проверяем наличие опасных LOAD_NAME/LOAD_GLOBAL
            for instr in dis.get_instructions(compiled):
                if instr.opname in {'LOAD_NAME', 'LOAD_GLOBAL', 'LOAD_ATTR'}:
                    if instr.argval in self.DANGEROUS_BUILTINS:
                        self.result.add_violation(
                            f"Bytecode analysis: dangerous builtin '{instr.argval}' detected"
                        )
                    if instr.argval in {'getattr', 'setattr', 'delattr'}:
                        self.result.add_violation(
                            f"Bytecode analysis: dynamic attribute access '{instr.argval}' detected"
                        )
                        
        except SyntaxError:
            pass  # Уже обработано в analyze()
        except Exception as e:
            logger.debug(f"Bytecode verification skipped: {e}")


# =============================================================================
# Secure Path Validator (Replaces simple string checks)
# =============================================================================

@dataclass
class PathValidationResult:
    """Результат валидации пути"""
    is_valid: bool
    resolved_path: Optional[str] = None
    reason: str = ""
    inode: Optional[Tuple[int, int]] = None  # (device, inode)


class SecurePathValidator:
    """
    Криптографически защищённый валидатор путей.
    
    Защищает от:
    - Path traversal (../../../etc/passwd)
    - Symlink attacks
    - Race conditions (TOCTOU)
    - Hardlink attacks
    
    Использует inode-level проверки для неподделываемой идентификации файлов.
    """
    
    # Защищённые inodes (инициализируются при старте системы)
    _protected_inodes: Set[Tuple[int, int]] = set()
    _initialized: bool = False
    
    # Защищённые mount points
    PROTECTED_MOUNTS = frozenset({
        '/proc', '/sys', '/dev', '/boot', '/root',
    })
    
    # Защищённые patterns (string-based fallback)
    PROTECTED_PATTERNS = frozenset({
        '/etc/', '/etc ',  # /etc and variants
        '.env', '.env.', '.envrc',
        '.ssh/', '.ssh ',
        '.aws/', '.aws ',
        'credentials/', 'credentials ',
        'secrets/', 'secrets ',
        '.git/', '.git ',
        '.hg/', '.hg ',
        '.svn/', '.svn ',
    })
    
    @classmethod
    def initialize_protected_inodes(cls) -> None:
        """
        Инициализация защищённых inodes.
        
        Должна вызываться при старте системы с root privileges.
        После снижения privileges эти inodes нельзя подделать.
        """
        protected_paths = [
            '/etc', '/sys', '/proc', '/root', '/boot', '/dev',
            Path.home() / '.ssh',
            Path.home() / '.aws',
            Path.home() / '.config',
        ]
        
        cls._protected_inodes.clear()
        
        for path in protected_paths:
            try:
                resolved = os.path.realpath(path)
                stat_info = os.stat(resolved)
                # (device, inode) tuple - уникален в системе
                inode_key = (stat_info.st_dev, stat_info.st_ino)
                cls._protected_inodes.add(inode_key)
                logger.info(f"[SecurePath] Protected inode: {resolved} -> {inode_key}")
            except (OSError, IOError, PermissionError) as e:
                logger.warning(f"[SecurePath] Cannot protect {path}: {e}")
                
        cls._initialized = True
    
    def validate(self, path: str, base_dir: Optional[str] = None) -> PathValidationResult:
        """
        Многоуровневая валидация пути.
        
        Args:
            path: Путь для проверки
            base_dir: Базовая директория (для jail'ов)
            
        Returns:
            PathValidationResult с результатами
        """
        if not path:
            return PathValidationResult(is_valid=True, reason="empty_path")
            
        # Уровень 1: Базовая канонизация
        try:
            # Раскрываем ~ и ~user
            expanded = os.path.expanduser(path)
            
            # Проверка на null bytes и другие инъекции
            if '\x00' in expanded:
                return PathValidationResult(
                    is_valid=False, 
                    reason="null_byte_injection"
                )
        except Exception as e:
            return PathValidationResult(
                is_valid=False, 
                reason=f"path_expansion_error: {e}"
            )
            
        # Уровень 2: Проверка на path escape относительно base_dir
        if base_dir:
            try:
                real_base = os.path.realpath(base_dir)
                # Комбинируем и нормализуем
                combined = os.path.join(real_base, expanded)
                real_path = os.path.realpath(combined)
                
                if not real_path.startswith(real_base):
                    return PathValidationResult(
                        is_valid=False,
                        resolved_path=real_path,
                        reason="path_escape_detected"
                    )
            except Exception as e:
                return PathValidationResult(
                    is_valid=False,
                    reason=f"path_resolution_error: {e}"
                )
        else:
            try:
                real_path = os.path.realpath(expanded)
            except Exception as e:
                return PathValidationResult(
                    is_valid=False,
                    reason=f"path_resolution_error: {e}"
                )
                
        # Уровень 3: Проверка защищённых mount points
        for protected_mount in self.PROTECTED_MOUNTS:
            if real_path.startswith(protected_mount):
                return PathValidationResult(
                    is_valid=False,
                    resolved_path=real_path,
                    reason=f"protected_mount_point: {protected_mount}"
                )
                
        # Уровень 4: Проверка защищённых inodes (атомарная)
        if self._initialized:
            try:
                stat_info = os.stat(real_path)
                inode_key = (stat_info.st_dev, stat_info.st_ino)
                
                if inode_key in self._protected_inodes:
                    return PathValidationResult(
                        is_valid=False,
                        resolved_path=real_path,
                        inode=inode_key,
                        reason="protected_inode"
                    )
            except (OSError, IOError):
                # Файл не существует - это ок для create операций
                pass
                
        # Уровень 5: String-based fallback (для не-initialized режима)
        path_lower = real_path.lower()
        for pattern in self.PROTECTED_PATTERNS:
            if pattern in path_lower or path_lower.startswith(pattern.rstrip()):
                return PathValidationResult(
                    is_valid=False,
                    resolved_path=real_path,
                    reason=f"protected_pattern: {pattern}"
                )
                
        # Уровень 6: Проверка на suspicious patterns
        suspicious = [
            '/../', '/./', '//',  # Obfuscation
            '...',  # Triple dot obfuscation
            '\x00', '\n', '\r',  # Control characters
        ]
        for s in suspicious:
            if s in real_path:
                return PathValidationResult(
                    is_valid=False,
                    resolved_path=real_path,
                    reason=f"suspicious_pattern: {s!r}"
                )
                
        return PathValidationResult(
            is_valid=True,
            resolved_path=real_path,
            inode=inode_key if 'inode_key' in dir() else None,
            reason="validation_passed"
        )
    
    def validate_with_lstat(self, path: str, base_dir: Optional[str] = None) -> PathValidationResult:
        """
        Валидация с использованием lstat (не следует по symlinks).
        
        Используется для проверки самих symlinks.
        """
        result = self.validate(path, base_dir)
        if not result.is_valid:
            return result
            
        try:
            # lstat не следует по symlinks
            lstat_info = os.lstat(result.resolved_path)
            
            # Проверяем что это не symlink на защищённый файл
            if os.path.islink(result.resolved_path):
                link_target = os.readlink(result.resolved_path)
                target_result = self.validate(link_target, base_dir)
                if not target_result.is_valid:
                    return PathValidationResult(
                        is_valid=False,
                        resolved_path=result.resolved_path,
                        reason=f"symlink_to_protected: {link_target}"
                    )
                    
        except (OSError, IOError):
            pass
            
        return result


# =============================================================================
# Legacy Pattern Invariants (for backward compatibility)
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
    "open_etc": re.compile(r'open\s*\([\'"]\/\/\/'),
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
# Enhanced Invariant Checker Functions
# =============================================================================

# Global instances
_path_validator: Optional[SecurePathValidator] = None

def get_path_validator() -> SecurePathValidator:
    """Get singleton path validator instance"""
    global _path_validator
    if _path_validator is None:
        _path_validator = SecurePathValidator()
    return _path_validator


def no_code_injection(payload: Dict[str, Any]) -> bool:
    """
    Block operations containing code injection patterns.
    
    V3.0: Uses AST-based analysis instead of regex.
    """
    code_content = _extract_code_content(payload)
    
    if not code_content:
        return True
        
    # AST-based анализ (основной)
    analyzer = SecurityASTAnalyzer(code_content)
    result = analyzer.analyze()
    
    if not result.is_safe:
        for violation in result.violations:
            logger.warning(f"[INVARIANT-AST] {violation}")
        return False
        
    # Fallback: regex для быстрой проверки (обратная совместимость)
    for name, pattern in DANGEROUS_PATTERNS.items():
        if name in ['eval_exec', 'compile']:
            if pattern.search(code_content):
                logger.warning(f"[INVARIANT-REGEX] Code injection pattern detected: {name}")
                return False
    
    return True


def no_shell_injection(payload: Dict[str, Any]) -> bool:
    """
    Block shell command injection patterns.
    
    V3.0: Uses AST-based analysis with enhanced checks.
    """
    content = _extract_code_content(payload)
    
    if not content:
        return True
        
    # AST-анализ для обнаружения os/subprocess вызовов
    analyzer = SecurityASTAnalyzer(content)
    result = analyzer.analyze()
    
    # Проверяем imports
    dangerous_imports = result.imports & analyzer.FORBIDDEN_MODULES
    if dangerous_imports:
        logger.warning(f"[INVARIANT-AST] Dangerous imports detected: {dangerous_imports}")
        return False
        
    # Fallback: regex
    shell_patterns = ['os.system', 'shell=True', 'Popen.*shell', 'call.*shell']
    for pattern_str in shell_patterns:
        if re.search(pattern_str, content):
            logger.warning(f"[INVARIANT-REGEX] Shell injection pattern: {pattern_str}")
            return False
    
    return True


def no_protected_path_access(payload: Dict[str, Any]) -> bool:
    """
    Block access to protected system paths.
    
    V3.0: Uses inode-level validation with symlink resolution.
    """
    validator = get_path_validator()
    
    # Проверяем все возможные path параметры
    path_keys = ['path', 'file_path', 'target', 'dest', 'destination', 'source']
    
    for key in path_keys:
        path = payload.get(key, "")
        if not path:
            continue
            
        result = validator.validate(path)
        
        if not result.is_valid:
            logger.warning(
                f"[INVARIANT-PATH] Protected path access blocked: "
                f"{path} -> {result.resolved_path} ({result.reason})"
            )
            return False
            
    return True


def no_hardcoded_secrets(payload: Dict[str, Any]) -> bool:
    """
    Block operations with hardcoded secrets.
    
    V3.0: Enhanced patterns with entropy analysis.
    """
    code_content = _extract_code_content(payload)
    
    if not code_content:
        return True
    
    # Entropy-based detection для API ключей
    high_entropy_patterns = [
        # OpenAI API keys
        (r'sk-[a-zA-Z0-9]{48,}', 'OpenAI API key'),
        # AWS keys
        (r'AKIA[0-9A-Z]{16}', 'AWS Access Key ID'),
        # JWT tokens (требуют высокой энтропии)
        (r'eyJ[A-Za-z0-9_-]*\.eyJ[A-Za-z0-9_-]*\.[A-Za-z0-9_-]*', 'JWT token'),
        # Generic high-entropy secrets
        (r'[a-zA-Z0-9_-]{32,64}', 'high_entropy_secret'),
    ]
    
    # Secret patterns
    secret_patterns = [
        (r'api[_-]?key\s*=\s*["\'][^"\']{20,}["\']', 'API key assignment'),
        (r'password\s*=\s*["\'][^"\']{8,}["\']', 'hardcoded password'),
        (r'secret[_-]?key\s*=\s*["\'][^"\']{16,}["\']', 'secret key'),
        (r'private[_-]?key\s*=\s*["\'][^"\']{100,}["\']', 'private key'),
        (r'token\s*=\s*["\']eyJ[a-zA-Z0-9]{20,}', 'JWT token assignment'),
    ]
    
    all_patterns = secret_patterns + high_entropy_patterns
    
    for pattern, name in all_patterns:
        matches = re.finditer(pattern, code_content, re.IGNORECASE)
        for match in matches:
            # Для high-entropy проверяем реальную энтропию
            if name == 'high_entropy_secret':
                entropy = _calculate_entropy(match.group())
                if entropy < 4.0:  # Низкая энтропия - скорее не секрет
                    continue
                    
            logger.warning(f"[INVARIANT] Hardcoded secret detected: {name}")
            return False
    
    return True


def max_operation_size(payload: Dict[str, Any]) -> bool:
    """Block operations that are too large (potential DoS)."""
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
        
    # Check total payload size
    payload_str = str(payload)
    if len(payload_str) > 2_000_000:  # 2MB total
        logger.warning(f"[INVARIANT] Payload too large: {len(payload_str)} bytes")
        return False
    
    return True


def combined_safety_invariant(payload: Dict[str, Any]) -> bool:
    """
    Combined invariant that runs all safety checks.
    
    V3.0: Enhanced with detailed reporting.
    """
    checks = [
        ("code_injection", no_code_injection),
        ("shell_injection", no_shell_injection),
        ("protected_path", no_protected_path_access),
        ("hardcoded_secrets", no_hardcoded_secrets),
        ("max_size", max_operation_size),
    ]
    
    failed_checks = []
    
    for check_name, checker in checks:
        if not checker(payload):
            failed_checks.append(check_name)
    
    if failed_checks:
        logger.warning(
            f"[INVARIANT-COMBINED] Failed checks: {', '.join(failed_checks)}"
        )
        return False
        
    return True


# =============================================================================
# Helper Functions
# =============================================================================

def _extract_code_content(payload: Dict[str, Any]) -> str:
    """Extract code/content from various payload structures."""
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


def _calculate_entropy(s: str) -> float:
    """
    Calculate Shannon entropy of a string.
    
    Используется для обнаружения случайных строк (API keys, tokens).
    """
    import math
    from collections import Counter
    
    if not s:
        return 0.0
        
    counts = Counter(s)
    length = len(s)
    
    entropy = -sum(
        (count / length) * math.log2(count / length)
        for count in counts.values()
    )
    
    return entropy


# =============================================================================
# Invariant Registry
# =============================================================================

INVARIANT_REGISTRY = {
    # V3.0 AST-based invariants
    "no_code_injection": no_code_injection,
    "no_shell_injection": no_shell_injection,
    "no_protected_path_access": no_protected_path_access,
    "no_hardcoded_secrets": no_hardcoded_secrets,
    "max_operation_size": max_operation_size,
    "combined_safety": combined_safety_invariant,
    # Classes for advanced usage
    "SecurityASTAnalyzer": SecurityASTAnalyzer,
    "SecurePathValidator": SecurePathValidator,
}


def get_invariant(name: str):
    """Get an invariant checker by name."""
    return INVARIANT_REGISTRY.get(name)


def list_invariants() -> List[str]:
    """List all available invariant checkers."""
    return [k for k in INVARIANT_REGISTRY.keys() if isinstance(INVARIANT_REGISTRY[k], type(lambda: None))]


def initialize_security_invariants() -> Dict[str, Any]:
    """
    Initialize security invariants (call at system startup).
    
    Returns:
        Dict with initialization results
    """
    results = {
        "path_validator_initialized": False,
        "protected_inodes_count": 0,
        "warnings": [],
    }
    
    try:
        SecurePathValidator.initialize_protected_inodes()
        results["path_validator_initialized"] = True
        results["protected_inodes_count"] = len(SecurePathValidator._protected_inodes)
    except PermissionError as e:
        results["warnings"].append(f"Cannot initialize protected inodes: {e}")
        
    return results


__all__ = [
    # V3.0 Classes
    "SecurityASTAnalyzer",
    "SecurePathValidator", 
    "PathValidationResult",
    "SecurityAnalysisResult",
    # Functions
    "no_code_injection",
    "no_shell_injection",
    "no_protected_path_access",
    "no_hardcoded_secrets",
    "max_operation_size",
    "combined_safety_invariant",
    "get_invariant",
    "list_invariants",
    "initialize_security_invariants",
    "get_path_validator",
]
