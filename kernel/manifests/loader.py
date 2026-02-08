# archon/kernel/manifests/loader.py
"""
Manifest Loader with inheritance, environment overrides, and fallback support.

Loads manifests from multiple sources:
1. Base manifests (~/manifests/)
2. Project manifests (multi_agent_team/manifests/)
3. Archon manifests (archon/manifests/)
4. Environment overrides (archon/manifests/environments/)

Supports:
- "extends" for inheritance
- Environment-specific overrides
- Fallback to defaults
- Domain enable/disable
- Priority-based merging
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime


class ManifestLoadError(Exception):
    """Raised when manifest cannot be loaded or parsed."""
    def __init__(self, path: str, reason: str):
        self.path = path
        self.reason = reason
        super().__init__(f"Failed to load manifest '{path}': {reason}")


class ManifestLoader:
    """
    Load manifests from multiple sources with priority-based merging.

    Priority order (later = higher priority):
    1. Base manifests (~/manifests/base.json)
    2. Domain manifests (multi_agent_team/manifests/*.json)
    3. Operation manifests (archon/manifests/operations.json)
    4. Environment overrides (archon/manifests/environments/{env}.json)
    """

    DEFAULT_PATHS = {
        "base": "~/manifests",
        "project": "../multi_agent_team/manifests",
        "archon": "manifests",
    }

    def __init__(
        self,
        base_path: Optional[str] = None,
        project_path: Optional[str] = None,
        archon_path: Optional[str] = None,
        environment: str = "prod"
    ):
        """
        Initialize manifest loader.

        Args:
            base_path: Path to base manifests (default: ~/manifests)
            project_path: Path to project-specific manifests
            archon_path: Path to archon/control-layer manifests
            environment: Environment name (dev/prod/test)
        """
        self.environment = environment
        self.paths = self._resolve_paths(base_path, project_path, archon_path)
        self._cache: Dict[str, Dict] = {}
        self._load_time: Dict[str, datetime] = {}

    def _resolve_paths(
        self,
        base_path: Optional[str],
        project_path: Optional[str],
        archon_path: Optional[str]
    ) -> Dict[str, Path]:
        """Resolve all paths to absolute Path objects."""
        base = Path(base_path or self.DEFAULT_PATHS["base"]).expanduser()
        project = Path(project_path or self.DEFAULT_PATHS["project"]).expanduser()
        archon = Path(archon_path or self.DEFAULT_PATHS["archon"]).expanduser()

        return {
            "base": base,
            "project": project,
            "archon": archon,
        }

    def load(self, name: str, use_cache: bool = True) -> Dict[str, Any]:
        """
        Load manifest with inheritance and environment overrides.

        Args:
            name: Manifest name (without .json extension)
            use_cache: Use cached version if available

        Returns:
            Merged manifest dictionary

        Raises:
            ManifestLoadError: If manifest cannot be loaded
        """
        # Cache key includes environment to avoid cross-environment contamination
        cache_key = f"{self.environment}:{name}"
        if use_cache and cache_key in self._cache:
            return self._cache[cache_key]

        # 1. Load base manifest with priority
        manifest = self._load_from_sources(name)

        if not manifest:
            raise ManifestLoadError(name, "Manifest not found in any source")

        # 2. Resolve extends (inheritance)
        if "extends" in manifest:
            manifest = self._resolve_extends(manifest)

        # 3. Apply environment overrides
        env_override = self._load_env_override(name)
        if env_override:
            manifest = self._deep_merge(manifest, env_override)

        # 4. Validate manifest structure
        self._validate_manifest(manifest)

        # 5. Cache and return (with environment in key)
        self._cache[cache_key] = manifest
        self._load_time[cache_key] = datetime.now()

        return manifest

    def _load_from_sources(self, name: str) -> Dict[str, Any]:
        """
        Load manifest from all sources with priority (later = higher priority).

        Priority: base < project < archon
        """
        result = {}

        # Priority 1: Base manifests
        base_file = self.paths["base"] / f"{name}.json"
        if base_file.exists():
            try:
                result.update(json.loads(base_file.read_text()))
            except json.JSONDecodeError as e:
                raise ManifestLoadError(str(base_file), f"Invalid JSON: {e}")

        # Priority 2: Project manifests
        project_file = self.paths["project"] / f"{name}.json"
        if project_file.exists():
            try:
                data = json.loads(project_file.read_text())
                result.update(data)
            except json.JSONDecodeError as e:
                raise ManifestLoadError(str(project_file), f"Invalid JSON: {e}")

        # Priority 3: Archon/control-layer manifests
        archon_file = self.paths["archon"] / f"{name}.json"
        if archon_file.exists():
            try:
                data = json.loads(archon_file.read_text())
                result.update(data)
            except json.JSONDecodeError as e:
                raise ManifestLoadError(str(archon_file), f"Invalid JSON: {e}")

        return result

    def _resolve_extends(self, manifest: Dict[str, Any]) -> Dict[str, Any]:
        """
        Resolve 'extends' field with deep merge.

        Example:
            {
                "extends": ["base", "trading"],
                "domain_constraints": {
                    "trading": {
                        "critical_thresholds": {
                            "min_sharpe_ratio": 1.8  # override base
                        }
                    }
                }
            }
        """
        if "extends" not in manifest:
            return manifest

        result = {}
        extends_list = manifest["extends"]

        for base_name in extends_list:
            # Load base manifest WITHOUT environment overrides
            # Environment should only apply to the final manifest, not base parents
            base_manifest = self._load_base_for_extends(base_name)
            result = self._deep_merge(result, base_manifest)

        # Merge current manifest on top (has highest priority)
        result = self._deep_merge(result, manifest)

        # Remove 'extends' from result to avoid cycles
        result.pop("extends", None)

        return result

    def _deep_merge(self, base: Dict, override: Dict) -> Dict:
        """Deep merge two dictionaries (override takes precedence)."""
        result = base.copy()

        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                # Recursively merge nested dictionaries
                result[key] = self._deep_merge(result[key], value)
            else:
                # Override with new value
                result[key] = value

        return result

    def _load_base_for_extends(self, name: str) -> Dict[str, Any]:
        """
        Load a base manifest for extends resolution WITHOUT environment overrides.

        This ensures that parent manifests in an extends chain are not
        polluted with environment-specific settings.
        """
        # Check cache for base manifests (without environment)
        base_cache_key = f"_base:{name}"
        if base_cache_key in self._cache:
            return self._cache[base_cache_key]

        # Load from sources
        manifest = self._load_from_sources(name)
        if not manifest:
            raise ManifestLoadError(name, "Base manifest not found in any source")

        # Recursively resolve extends (without env overrides)
        if "extends" in manifest:
            manifest = self._resolve_extends(manifest)

        # Validate base manifest
        self._validate_manifest(manifest)

        # Cache base manifest
        self._cache[base_cache_key] = manifest
        self._load_time[base_cache_key] = datetime.now()

        return manifest

    def _load_env_override(self, name: str) -> Optional[Dict[str, Any]]:
        """Load environment-specific override for given manifest name.

        Returns the full env data if name matches, allowing deep merge of all keys.
        """
        env_file = self.paths["archon"] / "environments" / f"{self.environment}.json"

        if not env_file.exists():
            return None

        try:
            env_data = json.loads(env_file.read_text())
        except json.JSONDecodeError as e:
            raise ManifestLoadError(str(env_file), f"Invalid JSON: {e}")

        # Return full env data for deep merge
        # This allows merging operations, domains, and other top-level keys
        return env_data

    def _validate_manifest(self, manifest: Dict[str, Any]) -> None:
        """Validate manifest has required structure."""
        if "version" not in manifest:
            raise ManifestLoadError("unknown", "Missing 'version' field")

        # Validate operations if present (skip wildcards like "*")
        if "operations" in manifest:
            for op_name, op_config in manifest["operations"].items():
                # Skip wildcards and meta-operations
                if op_name.startswith("*") or op_name.startswith("_"):
                    continue
                # Only require risk_level for concrete operations
                if "risk_level" not in op_config and "fallback_contract" not in op_config:
                    raise ManifestLoadError(
                        f"operation:{op_name}",
                        "Missing 'risk_level' or 'fallback_contract'"
                    )

    # ==========================================================================
    # Domain and Operation Access
    # ==========================================================================

    def get_domain_contract(self, domain: str) -> Dict[str, Any]:
        """
        Get domain contract with fallback to defaults.

        Fallback chain:
        1. Exact domain match in domain_constraints
        2. default_constraints in manifest
        3. Safe defaults (empty but secure)
        """
        # Load main manifest (usually operations.json or base)
        manifest = self.load("operations")

        # 1. Try exact domain match
        if "domains" in manifest and domain in manifest["domains"]:
            return manifest["domains"][domain]

        # 2. Try default_constraints
        if "default_constraints" in manifest:
            return manifest["default_constraints"]

        # 3. Safe defaults
        return self._safe_defaults()

    def _safe_defaults(self) -> Dict[str, Any]:
        """Fallback defaults when no default_constraints defined."""
        return {
            "enabled": True,
            "priority": 50,
            "critical_thresholds": {
                "max_risk_level": 0.5,
                "require_audit": True,
                "require_rbac": True
            },
            "forbidden_patterns": {},
            "required_checks": ["rbac", "audit"],
            "debate_required": False,
            "human_approval_required": False
        }

    def get_operation_contract(
        self,
        operation: str,
        manifest_name: str = "operations"
    ) -> Optional[Dict[str, Any]]:
        """
        Get operation contract from manifest.

        Returns None if operation not found (no wildcard).
        """
        manifest = self.load(manifest_name)

        if "operations" not in manifest:
            return None

        # Try exact match
        if operation in manifest["operations"]:
            return manifest["operations"][operation]

        # Try wildcard fallback
        if "*" in manifest["operations"]:
            wildcard = manifest["operations"]["*"]
            if wildcard.get("fallback_contract"):
                return wildcard

        return None

    def get_domains(self) -> Dict[str, Dict[str, Any]]:
        """Get all domains with their status."""
        manifest = self.load("operations")
        return manifest.get("domains", {})

    def is_domain_enabled(self, domain: str) -> bool:
        """Check if domain is currently enabled."""
        contract = self.get_domain_contract(domain)
        return contract.get("enabled", True)

    def get_risk_level(self, operation: str, default: float = 0.5) -> float:
        """Get risk level for operation."""
        contract = self.get_operation_contract(operation)
        if contract:
            return contract.get("risk_level", default)
        return default

    def is_fast_path_available(self, operation: str) -> bool:
        """Check if operation can use fast path (skip most checks)."""
        contract = self.get_operation_contract(operation)
        if contract:
            return contract.get("fast_path_available", False)

        # Use risk threshold for decision
        risk = self.get_risk_level(operation)
        return risk <= 0.1

    # ==========================================================================
    # Cache Management
    # ==========================================================================

    def clear_cache(self, name: Optional[str] = None) -> None:
        """Clear cached manifests.

        Args:
            name: Manifest name to clear. If None, clears all cache for current environment.
                  Use '*' to clear all environments.
        """
        if name:
            # Clear specific manifest for current environment
            cache_key = f"{self.environment}:{name}"
            self._cache.pop(cache_key, None)
            self._load_time.pop(cache_key, None)
        else:
            # Clear all cache for current environment only
            prefix = f"{self.environment}:"
            keys_to_remove = [k for k in self._cache.keys() if k.startswith(prefix)]
            for key in keys_to_remove:
                self._cache.pop(key, None)
                self._load_time.pop(key, None)

    def get_cache_info(self) -> Dict[str, datetime]:
        """Get cache load times."""
        return self._load_time.copy()

    def reload(self, name: str) -> Dict[str, Any]:
        """Force reload of manifest (bypass cache)."""
        self.clear_cache(name)
        return self.load(name, use_cache=False)


# =============================================================================
# Global Loader Instance (Singleton pattern)
# =============================================================================

_global_loader: Optional[ManifestLoader] = None


def get_loader(
    environment: str = "prod",
    reload: bool = False
) -> ManifestLoader:
    """
    Get global manifest loader instance.

    Args:
        environment: Environment name (dev/prod/test)
        reload: Force reload of manifests

    Returns:
        ManifestLoader instance
    """
    global _global_loader

    if _global_loader is None or reload:
        _global_loader = ManifestLoader(environment=environment)

    return _global_loader


def load_manifest(name: str, environment: str = "prod") -> Dict[str, Any]:
    """
    Convenience function to load a manifest.

    Args:
        name: Manifest name
        environment: Environment name

    Returns:
        Merged manifest dictionary
    """
    loader = get_loader(environment=environment)
    return loader.load(name)


# =============================================================================
# Utility Functions
# =============================================================================

def get_operation_manifest(operation: str, environment: str = "prod") -> Optional[Dict]:
    """Get operation contract for given operation."""
    loader = get_loader(environment=environment)
    return loader.get_operation_contract(operation)


def is_domain_enabled(domain: str, environment: str = "prod") -> bool:
    """Check if domain is enabled in given environment."""
    loader = get_loader(environment=environment)
    return loader.is_domain_enabled(domain)


def get_risk_level(operation: str, environment: str = "prod") -> float:
    """Get risk level for operation."""
    loader = get_loader(environment=environment)
    return loader.get_risk_level(operation)
