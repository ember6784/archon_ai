"""
Agency Templates Loader

Loads and validates role templates for dynamic agent creation.
Implements Vaccination System to ensure Safety Core is present.
"""

import json
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass


@dataclass
class RoleTemplate:
    """Loaded and validated role template"""
    role_id: str
    name: str
    version: str
    description: str
    category: str
    parent_role: Optional[str]
    system_prompt: str
    max_tokens_per_debate: int
    temperature: float
    allowed_tools: List[str]
    forbidden_patterns: List[str]
    constraints: Dict[str, Any]
    metadata: Dict[str, Any]
    safety_vaccinated: bool
    safety_hash: str

    def get_full_prompt(self, safety_core_content: str) -> str:
        """Get system prompt with Safety Core injected"""
        return self.system_prompt.replace("{SAFETY_CORE}", safety_core_content)


class TemplateLoader:
    """
    Load and validate agency templates

    Usage:
        loader = TemplateLoader()
        template = loader.load_role("security_expert")
        prompt = template.get_full_prompt(loader.get_safety_core())
    """

    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = base_dir or Path(__file__).parent
        self.safety_core_file = self.base_dir / "safety_core.txt"
        self.index_file = self.base_dir / "index.json"
        self.roles_dir = self.base_dir / "roles"

        # Cache
        self._safety_core: Optional[str] = None
        self._safety_hash: Optional[str] = None
        self._index: Optional[Dict] = None

    def get_safety_core(self) -> str:
        """Load Safety Core content"""
        if self._safety_core is None:
            if not self.safety_core_file.exists():
                raise FileNotFoundError(f"Safety Core not found: {self.safety_core_file}")

            self._safety_core = self.safety_core_file.read_text(encoding='utf-8')

        return self._safety_core

    def get_safety_hash(self) -> str:
        """Get SHA-256 hash of Safety Core"""
        if self._safety_hash is None:
            content = self.get_safety_core()
            self._safety_hash = hashlib.sha256(content.encode()).hexdigest()

        return self._safety_hash

    def get_index(self) -> Dict:
        """Load template index"""
        if self._index is None:
            if not self.index_file.exists():
                raise FileNotFoundError(f"Index not found: {self.index_file}")

            self._index = json.loads(self.index_file.read_text(encoding='utf-8'))

        return self._index

    def verify_safety_core(self, system_prompt: str) -> bool:
        """
        Verify that Safety Core is present in system prompt

        Vaccination check - ensures all agents have safety rules

        Accepts either:
        1. {SAFETY_CORE} placeholder (will be injected at runtime)
        2. Direct Safety Core content with critical rules
        """
        # Check for placeholder (will be injected later)
        if "{SAFETY_CORE}" in system_prompt:
            return True

        # Check for actual Safety Core content
        # At least 2 critical markers must be present
        safety_markers = [
            "SAFETY CORE",
            "CRITICAL SAFETY RULES",
            "NEVER use eval(",
            "ALWAYS use parameterized",
            "NEVER expose secrets"
        ]

        prompt_lower = system_prompt.lower()
        markers_found = sum(1 for m in safety_markers if m.lower() in prompt_lower)

        return markers_found >= 2  # Need at least 2 markers

    def load_role(self, role_id: str) -> RoleTemplate:
        """
        Load a role template by ID

        Args:
            role_id: Role identifier (e.g., "security_expert")

        Returns:
            RoleTemplate with validated content

        Raises:
            FileNotFoundError: If template file doesn't exist
            ValueError: If template fails validation
        """
        index = self.get_index()

        # Find role in index
        role_info = None
        for key, info in index.get("templates", {}).items():
            if info.get("role_id") == role_id or key == role_id:
                role_info = info
                break

        if not role_info:
            raise ValueError(f"Role not found in index: {role_id}")

        # Load template file
        template_file = self.base_dir / role_info["file"]
        if not template_file.exists():
            raise FileNotFoundError(f"Template file not found: {template_file}")

        data = json.loads(template_file.read_text(encoding='utf-8'))

        # Verify Safety Core vaccination
        system_prompt = data.get("system_prompt", "")
        is_vaccinated = self.verify_safety_core(system_prompt)

        if not is_vaccinated:
            raise ValueError(f"Role {role_id} is not vaccinated! Missing Safety Core.")

        return RoleTemplate(
            role_id=data["role_id"],
            name=data["name"],
            version=data["version"],
            description=data.get("description", ""),
            category=data.get("category", "general"),
            parent_role=data.get("parent_role"),
            system_prompt=system_prompt,
            max_tokens_per_debate=data.get("max_tokens_per_debate", 2000),
            temperature=data.get("temperature", 0.3),
            allowed_tools=data.get("allowed_tools", []),
            forbidden_patterns=data.get("forbidden_patterns", []),
            constraints=data.get("constraints", {}),
            metadata=data.get("metadata", {}),
            safety_vaccinated=is_vaccinated,
            safety_hash=self.get_safety_hash()
        )

    def mix_templates(self, base_role: str, mixins: List[str]) -> RoleTemplate:
        """
        Combine base role with mixin templates

        Args:
            base_role: Base role ID
            mixins: List of mixin role IDs to overlay

        Returns:
            Combined RoleTemplate
        """
        # Load base template
        base = self.load_role(base_role)

        # For now, just return base - mixin composition can be extended later
        # Future: overlay prompts, merge allowed_tools, combine constraints
        return base

    def list_roles(self, category: Optional[str] = None) -> List[Dict]:
        """
        List available roles

        Args:
            category: Filter by category (optional)

        Returns:
            List of role info dictionaries
        """
        index = self.get_index()
        templates = index.get("templates", {})

        if category:
            templates = {
                k: v for k, v in templates.items()
                if v.get("category") == category
            }

        return list(templates.values())

    def get_all_categories(self) -> List[str]:
        """Get all available categories"""
        index = self.get_index()
        return list(index.get("categories", {}).keys())


class VaccinationSystem:
    """
    Vaccination System for agent safety

    Ensures all agents contain Safety Core rules
    """

    def __init__(self, loader: TemplateLoader):
        self.loader = loader

    def verify_agent(self, system_prompt: str) -> Dict[str, Any]:
        """
        Verify an agent is vaccinated

        Returns:
            {
                "vaccinated": bool,
                "safety_hash": str,
                "missing_rules": List[str],
                "recommendation": str
            }
        """
        safety_core = self.loader.get_safety_core()
        safety_hash = self.loader.get_safety_hash()

        # Check for critical safety rules
        required_rules = [
            "NEVER use eval(",
            "ALWAYS use parameterized",
            "NEVER expose secrets",
            "NEVER disable SSL"
        ]

        missing_rules = []
        for rule in required_rules:
            if rule.lower() not in system_prompt.lower():
                missing_rules.append(rule)

        # Require at least 3 out of 4 critical rules for vaccination
        vaccinated = len(missing_rules) <= 1

        recommendation = (
            "Agent is properly vaccinated" if vaccinated
            else f"Agent missing {len(missing_rules)} critical safety rules"
        )

        return {
            "vaccinated": vaccinated,
            "safety_hash": safety_hash,
            "missing_rules": missing_rules,
            "recommendation": recommendation
        }

    def vaccinate_agent(self, base_prompt: str) -> str:
        """
        Add Safety Core to an agent prompt

        Returns:
            Vaccinated prompt with Safety Core injected
        """
        safety_core = self.loader.get_safety_core()

        # If prompt has placeholder, replace it
        if "{SAFETY_CORE}" in base_prompt:
            return base_prompt.replace("{SAFETY_CORE}", safety_core)

        # Otherwise, prepend Safety Core
        vaccinated = f"# SAFETY CORE\n{safety_core}\n\n# Original Prompt\n{base_prompt}"
        return vaccinated


# Convenience functions
def get_template_loader() -> TemplateLoader:
    """Get singleton TemplateLoader instance"""
    return TemplateLoader()


def load_role(role_id: str) -> RoleTemplate:
    """Convenience function to load a role"""
    loader = get_template_loader()
    return loader.load_role(role_id)


def verify_vaccination(system_prompt: str) -> Dict[str, Any]:
    """Convenience function to verify agent vaccination"""
    loader = get_template_loader()
    vaccination = VaccinationSystem(loader)
    return vaccination.verify_agent(system_prompt)


__all__ = [
    "TemplateLoader",
    "RoleTemplate",
    "VaccinationSystem",
    "get_template_loader",
    "load_role",
    "verify_vaccination"
]
