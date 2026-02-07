"""
OpenClaw Enterprise - Enterprise Layer

This package provides the enterprise-grade features on top of OpenClaw
and Multi-Agent Team:

- RBAC (Role-Based Access Control)
- Audit Logger (SOC2/GDPR compliant)
- Multi-tenancy
- SSO Integration
- Compliance Reporting
"""

__version__ = "0.1.0"

from enterprise.config import settings
from enterprise.event_bus import EventBus, EventType, Event

__all__ = [
    "settings",
    "EventBus",
    "EventType",
    "Event",
]
