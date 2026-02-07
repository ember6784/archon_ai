"""
Execution Contract - Bridge between Manifesto and Physical Isolation

The Execution Contract enforces security constraints at runtime by:
1. Validating environment before agent execution
2. Generating seccomp profiles
3. Enforcing resource limits
4. Providing audit trail for contract violations

This is the T0 → T3 boundary enforcement layer.
"""

from typing import Optional, List, Dict, Any, Set
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
import json
import hashlib
import logging

logger = logging.getLogger(__name__)


class SyscallRule(Enum):
    """Seccomp syscall rule types."""
    ALLOW = "SCMP_ACT_ALLOW"
    ERRNO = "SCMP_ACT_ERRNO"
    KILL = "SCMP_ACT_KILL"
    TRAP = "SCMP_ACT_TRAP"
    LOG = "SCMP_ACT_LOG"


@dataclass
class ResourceLimits:
    """Resource limits for execution."""
    max_memory_mb: int = 512
    max_cpu_time_seconds: int = 60
    max_open_files: int = 1024
    max_processes: int = 10
    max_file_size_mb: int = 100
    max_stack_size_kb: int = 8192

    def to_ulimit_args(self) -> List[str]:
        """Convert to ulimit command arguments."""
        return [
            f"-v {self.max_memory_mb * 1024 * 1024}",  # virtual memory
            f"-t {self.max_cpu_time_seconds}",        # CPU time
            f"-n {self.max_open_files}",              # open files
            f"-u {self.max_processes}",              # processes/threads
            f"-f {self.max_file_size_mb * 1024}",     # file size
            f"-s {self.max_stack_size_kb}",           # stack size
        ]


@dataclass
class NetworkPolicy:
    """Network access policy."""
    allow_network: bool = False
    allowed_domains: Set[str] = field(default_factory=set)
    allowed_ips: Set[str] = field(default_factory=set)
    allow_dns: bool = False
    allow_loopback: bool = True
    proxy_required: bool = False

    def to_seccomp_rules(self) -> List[Dict[str, Any]]:
        """Convert to seccomp filter rules."""
        rules = []

        if not self.allow_network:
            # Block network syscalls
            blocked_syscalls = [
                "socket", "socketpair", "connect", "bind", "listen",
                "accept", "sendto", "recvfrom", "sendmsg", "recvmsg",
                "shutdown", "getsockname", "getpeername"
            ]
            for syscall in blocked_syscalls:
                rules.append({
                    "names": [syscall],
                    "action": "SCMP_ACT_ERRNO",
                    "args": []
                })

        return rules


@dataclass
class FilesystemPolicy:
    """Filesystem access policy."""
    read_only_root: bool = True
    tmpfs_size_mb: int = 100
    read_only_paths: List[str] = field(default_factory=lambda: [
        "/app", "/usr", "/bin", "/lib", "/etc"
    ])
    writable_paths: List[str] = field(default_factory=lambda: [
        "/app/workspace", "/tmp", "/var/tmp"
    ])
    forbidden_paths: List[str] = field(default_factory=lambda: [
        "/proc", "/sys", "/etc/passwd", "/etc/shadow",
        "/root", "/home", "/var/secrets"
    ])

    def to_mount_options(self) -> Dict[str, str]:
        """Convert to Docker mount options."""
        mounts = {}

        for path in self.read_only_paths:
            mounts[path] = "ro"

        for path in self.writable_paths:
            mounts[path] = "rw"

        return mounts


@dataclass
class SecurityProfile:
    """Complete security profile for execution."""
    name: str
    version: str = "1.0"
    description: str = ""

    # Resource constraints
    resource_limits: ResourceLimits = field(default_factory=ResourceLimits)

    # Network policy
    network_policy: NetworkPolicy = field(default_factory=NetworkPolicy)

    # Filesystem policy
    filesystem_policy: FilesystemPolicy = field(default_factory=FilesystemPolicy)

    # Allowed/forbidden imports (from Manifesto)
    allowed_imports: Set[str] = field(default_factory=set)
    forbidden_imports: Dict[str, str] = field(default_factory=dict)

    # Security features
    enable_seccomp: bool = True
    enable_apparmor: bool = True
    enable_capabilities_dropping: bool = True
    no_new_privileges: bool = True

    # Atomic primitives requirement
    require_atomic_primitives: bool = False

    # Allowed syscalls (whitelist mode)
    allowed_syscalls: List[str] = field(default_factory=lambda: [
        # Basic I/O
        "read", "write", "open", "openat", "close", "stat", "fstat", "lstat",
        # Memory
        "mmap", "mprotect", "munmap", "brk",
        # Process
        "arch_prctl", "set_tid_address", "set_robust_list",
        # Time
        "clock_gettime", "gettimeofday",
        # Math
        "futex", "getrandom",
    ])

    def get_hash(self) -> str:
        """Get hash of this profile for integrity checking."""
        data = json.dumps(self.to_dict(), sort_keys=True)
        return hashlib.sha256(data.encode()).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "resource_limits": {
                "max_memory_mb": self.resource_limits.max_memory_mb,
                "max_cpu_time_seconds": self.resource_limits.max_cpu_time_seconds,
                "max_open_files": self.resource_limits.max_open_files,
                "max_processes": self.resource_limits.max_processes,
            },
            "network_policy": {
                "allow_network": self.network_policy.allow_network,
                "allowed_domains": list(self.network_policy.allowed_domains),
                "allow_dns": self.network_policy.allow_dns,
            },
            "filesystem_policy": {
                "read_only_root": self.filesystem_policy.read_only_root,
                "tmpfs_size_mb": self.filesystem_policy.tmpfs_size_mb,
                "writable_paths": self.filesystem_policy.writable_paths,
            },
            "allowed_imports": list(self.allowed_imports),
            "forbidden_imports": self.forbidden_imports,
            "security_features": {
                "enable_seccomp": self.enable_seccomp,
                "enable_apparmor": self.enable_apparmor,
                "no_new_privileges": self.no_new_privileges,
            },
            "allowed_syscalls": self.allowed_syscalls,
        }


class ExecutionContract:
    """
    Execution Contract - enforces security constraints.

    This is the bridge between Intent Manifesto (logical constraints)
    and physical isolation (seccomp, Docker, resource limits).

    The contract is validated BEFORE any agent execution.
    """

    # Predefined profiles for different autonomy levels
    PROFILES: Dict[str, SecurityProfile] = {}

    @classmethod
    def get_profile(cls, name: str) -> Optional[SecurityProfile]:
        """Get a predefined profile."""
        return cls.PROFILES.get(name)

    @classmethod
    def register_profile(cls, profile: SecurityProfile):
        """Register a new profile."""
        cls.PROFILES[profile.name] = profile

    def __init__(
        self,
        manifesto_path: str = "mat/agency_templates/safety_core.txt",
        profile: Optional[SecurityProfile] = None
    ):
        self.manifesto_path = Path(manifesto_path)
        self.profile = profile or self._default_profile()
        self._violations: List[Dict[str, Any]] = []

    def _default_profile(self) -> SecurityProfile:
        """Get default security profile."""
        return SecurityProfile(
            name="default",
            description="Default secure execution profile",
            resource_limits=ResourceLimits(
                max_memory_mb=512,
                max_cpu_time_seconds=60,
                max_open_files=256,
                max_processes=5
            ),
            network_policy=NetworkPolicy(
                allow_network=False,
                allow_loopback=True
            ),
            filesystem_policy=FilesystemPolicy(
                read_only_root=True,
                tmpfs_size_mb=100
            )
        )

    async def validate_execution(
        self,
        code: str,
        agent_id: str,
        autonomy_level: str = "GREEN"
    ) -> bool:
        """
        Validate execution against the contract.

        Args:
            code: Code to execute
            agent_id: Agent identifier
            autonomy_level: Current autonomy level

        Returns:
            True if execution is allowed
        """
        self._violations = []

        # Step 1: Check imports against manifesto
        await self._validate_imports(code, agent_id)

        # Step 2: Check for forbidden patterns
        await self._validate_patterns(code, agent_id)

        # Step 3: Check autonomy level constraints
        await self._validate_autonomy_level(autonomy_level)

        # Step 4: Check resource requirements
        await self._validate_resources(code)

        return len(self._violations) == 0

    async def _validate_imports(self, code: str, agent_id: str):
        """Validate imports against allowed/forbidden lists."""
        import re

        # Find all imports
        import_pattern = re.compile(r'^\s*(?:from\s+(\S+)\s+)?import\s+(.+)', re.MULTILINE)
        imports = []

        for match in import_pattern.finditer(code):
            module = match.group(1) or match.group(2).split('.')[0].strip()
            imports.append(module)

        # Check forbidden imports
        for imp in imports:
            if imp in self.profile.forbidden_imports:
                self._violations.append({
                    "severity": "CRITICAL",
                    "rule": "forbidden_import",
                    "agent_id": agent_id,
                    "import": imp,
                    "reason": self.profile.forbidden_imports[imp]
                })

        # Check allowed imports (if whitelist mode)
        if self.profile.allowed_imports:
            for imp in imports:
                if imp not in self.profile.allowed_imports:
                    self._violations.append({
                        "severity": "HIGH",
                        "rule": "unallowed_import",
                        "agent_id": agent_id,
                        "import": imp,
                        "reason": "Import not in allowed list"
                    })

    async def _validate_patterns(self, code: str, agent_id: str):
        """Validate against forbidden patterns."""
        import re

        forbidden_patterns = {
            "eval\\s*\\(": "Dynamic code execution via eval()",
            "exec\\s*\\(": "Dynamic code execution via exec()",
            "\\__import__\\s*\\(": "Dynamic imports",
            "compile\\s*\\(": "Code compilation",
            "open\\s*\\(['\"]\\/proc": "Access to /proc filesystem",
            "open\\s*\\(['\"]\\/sys": "Access to /sys filesystem",
        }

        for pattern, reason in forbidden_patterns.items():
            if re.search(pattern, code):
                self._violations.append({
                    "severity": "CRITICAL",
                    "rule": "forbidden_pattern",
                    "agent_id": agent_id,
                    "pattern": pattern,
                    "reason": reason
                })

    async def _validate_autonomy_level(self, autonomy_level: str):
        """Validate against autonomy level constraints."""
        # Different levels have different constraints
        if autonomy_level == "BLACK":
            # In BLACK mode, almost nothing is allowed
            self._violations.append({
                "severity": "CRITICAL",
                "rule": "autonomy_level",
                "level": autonomy_level,
                "reason": "Execution not allowed in BLACK mode"
            })

        elif autonomy_level in ["RED", "AMBER"]:
            # Check if execution is read-only
            if not self.profile.filesystem_policy.read_only_root:
                self._violations.append({
                    "severity": "HIGH",
                    "rule": "filesystem_not_readonly",
                    "level": autonomy_level,
                    "reason": f"Filesystem must be read-only in {autonomy_level} mode"
                })

    async def _validate_resources(self, code: str):
        """Validate resource requirements."""
        # Estimate memory usage (rough heuristic)
        code_size_kb = len(code.encode()) / 1024
        if code_size_kb > self.profile.resource_limits.max_memory_mb * 100:  # rough check
            self._violations.append({
                "severity": "MEDIUM",
                "rule": "code_too_large",
                "size_kb": code_size_kb,
                "reason": "Code size exceeds limits"
            })

    def get_violations(self) -> List[Dict[str, Any]]:
        """Get list of contract violations."""
        return self._violations.copy()

    def get_violations_summary(self) -> str:
        """Get human-readable summary of violations."""
        if not self._violations:
            return "✅ No contract violations"

        lines = ["❌ Contract Violations:"]
        for v in self._violations:
            lines.append(f"  [{v['severity']}] {v['rule']}: {v.get('reason', '')}")

        return "\n".join(lines)

    def generate_seccomp_profile(self) -> Dict[str, Any]:
        """
        Generate seccomp profile for Docker.

        Returns:
            seccomp profile JSON
        """
        default_action = "SCMP_ACT_ERRNO"
        if self.profile.network_policy.allow_network:
            default_action = "SCMP_ACT_ALLOW"

        # Build syscalls list
        syscalls = []
        for syscall in self.profile.allowed_syscalls:
            syscalls.append({
                "names": [syscall],
                "action": "SCMP_ACT_ALLOW",
                "args": []
            })

        # Add network policy rules
        syscalls.extend(self.profile.network_policy.to_seccomp_rules())

        return {
            "defaultAction": default_action,
            "architectures": ["SCMP_ARCH_X86_64", "SCMP_ARCH_X86"],
            "syscalls": syscalls
        }

    def generate_docker_security_opts(self) -> List[str]:
        """
        Generate Docker security options.

        Returns:
            List of security options for docker run
        """
        opts = []

        if self.profile.no_new_privileges:
            opts.append("no-new-privileges:true")

        if self.profile.enable_seccomp:
            # Would save seccomp profile to file and reference it
            opts.append("seccomp:/etc/agent-seccomp.json")

        if self.profile.enable_apparmor:
            opts.append("apparmor:agent-profile")

        return opts

    def generate_docker_mounts(self) -> List[str]:
        """
        Generate Docker mount options.

        Returns:
            List of mount specifications
        """
        mounts = []

        # Read-only root filesystem
        if self.profile.filesystem_policy.read_only_root:
            mounts.append("/app:ro")

        # Tmpfs for workspace
        tmpfs = f"/app/workspace:size={self.profile.filesystem_policy.tmpfs_size_mb}M"
        mounts.append(tmpfs)

        # Additional writable paths
        for path in self.profile.filesystem_policy.writable_paths:
            if path != "/app/workspace":
                mounts.append(f"{path}:rw")

        return mounts

    def generate_ulimit_script(self) -> str:
        """
        Generate shell script to set ulimits.

        Returns:
            Shell script content
        """
        limits = self.profile.resource_limits
        return f"""#!/bin/bash
# Set resource limits
ulimit -v {limits.max_memory_mb * 1024 * 1024}
ulimit -t {limits.max_cpu_time_seconds}
ulimit -n {limits.max_open_files}
ulimit -u {limits.max_processes}
ulimit -f {limits.max_file_size_mb * 1024}
ulimit -s {limits.max_stack_size_kb}
"""

    def save_seccomp_profile(self, path: str = "agent-seccomp.json"):
        """Save seccomp profile to file."""
        profile = self.generate_seccomp_profile()
        with open(path, 'w') as f:
            json.dump(profile, f, indent=2)
        logger.info(f"Seccomp profile saved to {path}")

    def save_to_file(self, path: str = "execution_contract.json"):
        """Save contract to file."""
        data = {
            "profile": self.profile.to_dict(),
            "seccomp_profile": self.generate_seccomp_profile(),
            "docker_security_opts": self.generate_docker_security_opts(),
            "docker_mounts": self.generate_docker_mounts(),
            "hash": self.profile.get_hash()
        }

        with open(path, 'w') as f:
            json.dump(data, f, indent=2)

        logger.info(f"Execution contract saved to {path}")


# Predefined profiles for different scenarios

# Profile for full autonomy (GREEN mode)
ExecutionContract.register_profile(SecurityProfile(
    name="full_autonomy",
    description="Full autonomy with all capabilities (GREEN mode only)",
    resource_limits=ResourceLimits(
        max_memory_mb=2048,
        max_cpu_time_seconds=300,
        max_open_files=1024,
        max_processes=20
    ),
    network_policy=NetworkPolicy(
        allow_network=True,
        allow_dns=True
    ),
    filesystem_policy=FilesystemPolicy(
        read_only_root=False,
        tmpfs_size_mb=500
    )
))

# Profile for restricted autonomy (AMBER mode)
ExecutionContract.register_profile(SecurityProfile(
    name="restricted_autonomy",
    description="Restricted autonomy - no core/production changes",
    resource_limits=ResourceLimits(
        max_memory_mb=1024,
        max_cpu_time_seconds=120,
        max_open_files=512,
        max_processes=10
    ),
    network_policy=NetworkPolicy(
        allow_network=False,
        allow_loopback=True
    ),
    filesystem_policy=FilesystemPolicy(
        read_only_root=True,
        tmpfs_size_mb=100
    ),
    forbidden_imports={
        "subprocess": "Process execution not allowed in AMBER mode",
        "multiprocessing": "Process spawning not allowed"
    }
))

# Profile for minimal autonomy (RED mode)
ExecutionContract.register_profile(SecurityProfile(
    name="minimal_autonomy",
    description="Minimal autonomy - read-only + canary only",
    resource_limits=ResourceLimits(
        max_memory_mb=512,
        max_cpu_time_seconds=60,
        max_open_files=256,
        max_processes=5
    ),
    network_policy=NetworkPolicy(
        allow_network=False
    ),
    filesystem_policy=FilesystemPolicy(
        read_only_root=True,
        tmpfs_size_mb=50
    ),
    forbidden_imports={
        "subprocess": "Process execution not allowed",
        "multiprocessing": "Process spawning not allowed",
        "socket": "Network access not allowed",
        "requests": "Network access not allowed",
        "httpx": "Network access not allowed",
        "aiohttp": "Network access not allowed"
    }
))

# Profile for monitoring only (BLACK mode)
ExecutionContract.register_profile(SecurityProfile(
    name="monitoring_only",
    description="Monitoring only - no execution allowed",
    resource_limits=ResourceLimits(
        max_memory_mb=256,
        max_cpu_time_seconds=30,
        max_open_files=64,
        max_processes=1
    ),
    network_policy=NetworkPolicy(
        allow_network=False
    ),
    filesystem_policy=FilesystemPolicy(
        read_only_root=True,
        tmpfs_size_mb=10
    ),
    # Block all execution
    forbidden_imports={
        "subprocess": "No execution allowed",
        "multiprocessing": "No execution allowed",
        "socket": "No network allowed",
        "requests": "No network allowed",
        "open": "No file access allowed",
        "write": "No file access allowed"
    }
))


def get_contract_for_autonomy(autonomy_level: str) -> ExecutionContract:
    """
    Get appropriate execution contract for autonomy level.

    Args:
        autonomy_level: GREEN, AMBER, RED, or BLACK

    Returns:
        ExecutionContract with appropriate profile
    """
    profiles = {
        "GREEN": "full_autonomy",
        "AMBER": "restricted_autonomy",
        "RED": "minimal_autonomy",
        "BLACK": "monitoring_only"
    }

    profile_name = profiles.get(autonomy_level, "monitoring_only")
    profile = ExecutionContract.get_profile(profile_name)

    if not profile:
        profile = ExecutionContract._default_profile()

    return ExecutionContract(profile=profile)
