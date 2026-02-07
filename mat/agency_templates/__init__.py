"""
Agency Templates - Safe Role Library for Dynamic Agents

This module provides a library of pre-defined, safety-vaccinated role
templates for dynamic agent creation.

Usage:
    from mat.agency_templates import load_role, verify_vaccination

    # Load a role template
    template = load_role("security_expert")

    # Get full system prompt with Safety Core
    prompt = template.get_full_prompt(safety_core)

    # Verify an agent is vaccinated
    result = verify_vaccination(some_prompt)
"""

from .template_loader import (
    TemplateLoader,
    RoleTemplate,
    VaccinationSystem,
    get_template_loader,
    load_role,
    verify_vaccination
)

__version__ = "1.0.0"
__all__ = [
    "TemplateLoader",
    "RoleTemplate",
    "VaccinationSystem",
    "get_template_loader",
    "load_role",
    "verify_vaccination"
]
