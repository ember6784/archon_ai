# archon/kernel/manifests/__init__.py
"""
Manifest system for Intent Contract validation.

Supports:
- Multi-source loading (base, project, archon)
- Inheritance with "extends"
- Environment overrides (dev/prod/test)
- Fallback to defaults
- Domain enable/disable
"""

from .loader import ManifestLoader, ManifestLoadError, get_loader

__all__ = [
    "ManifestLoader",
    "ManifestLoadError",
    "get_loader",
]
