"""
RBAC (Role-Based Access Control) System
========================================

Enterprise-grade access control for Archon AI.

Features:
- 5-tier role hierarchy
- Fine-grained permissions
- Multi-tenant isolation
- JWT integration ready
- Audit logging integration

Usage:
    from enterprise.rbac import RBAC, Role, Permission

    rbac = RBAC()

    # Check permission
    if rbac.check_permission("user_123", Permission.CODE_EXECUTE):
        # Execute code
        pass

    # Assign role
    rbac.assign_role("user_123", Role.DEVELOPER, tenant_id="tenant_abc")
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Set, Any
from collections import defaultdict

logger = logging.getLogger(__name__)


class Role(Enum):
    """User roles with hierarchical permissions"""
    SUPER_ADMIN = "super_admin"      # Full access to all tenants
    TENANT_ADMIN = "tenant_admin"    # Full access within tenant
    DEVELOPER = "developer"           # Code execution, read/write
    ANALYST = "analyst"              # Read-only access
    EXTERNAL = "external"             # Limited external access


class Permission(Enum):
    """Granular permissions"""
    # Agent permissions
    AGENT_EXECUTE = "agent.execute"
    AGENT_MONITOR = "agent.monitor"
    AGENT_CREATE = "agent.create"
    AGENT_DELETE = "agent.delete"

    # Code permissions
    CODE_READ = "code.read"
    CODE_WRITE = "code.write"
    CODE_EXECUTE = "code.execute"
    CODE_DEPLOY = "code.deploy"
    CODE_DELETE = "code.delete"

    # Infrastructure permissions
    INFRASTRUCTURE_MANAGE = "infrastructure.manage"
    INFRASTRUCTURE_VIEW = "infrastructure.view"

    # Tenant permissions
    TENANT_CREATE = "tenant.create"
    TENANT_MANAGE = "tenant.manage"
    TENANT_VIEW = "tenant.view"

    # System permissions
    SYSTEM_ADMIN = "system.admin"
    SYSTEM_AUDIT = "system.audit"
    USER_MANAGE = "user.manage"


# Role-Permission Matrix
ROLE_PERMISSIONS: Dict[Role, Set[Permission]] = {
    Role.SUPER_ADMIN: {
        # All permissions
        Permission.AGENT_EXECUTE, Permission.AGENT_MONITOR, Permission.AGENT_CREATE, Permission.AGENT_DELETE,
        Permission.CODE_READ, Permission.CODE_WRITE, Permission.CODE_EXECUTE, Permission.CODE_DEPLOY, Permission.CODE_DELETE,
        Permission.INFRASTRUCTURE_MANAGE, Permission.INFRASTRUCTURE_VIEW,
        Permission.TENANT_CREATE, Permission.TENANT_MANAGE, Permission.TENANT_VIEW,
        Permission.SYSTEM_ADMIN, Permission.SYSTEM_AUDIT, Permission.USER_MANAGE,
    },
    Role.TENANT_ADMIN: {
        # Tenant-level admin
        Permission.AGENT_EXECUTE, Permission.AGENT_MONITOR, Permission.AGENT_CREATE, Permission.AGENT_DELETE,
        Permission.CODE_READ, Permission.CODE_WRITE, Permission.CODE_EXECUTE, Permission.CODE_DEPLOY,
        Permission.INFRASTRUCTURE_VIEW,
        Permission.TENANT_VIEW,
        Permission.SYSTEM_AUDIT, Permission.USER_MANAGE,
    },
    Role.DEVELOPER: {
        # Code execution and modification
        Permission.AGENT_EXECUTE, Permission.AGENT_MONITOR,
        Permission.CODE_READ, Permission.CODE_WRITE, Permission.CODE_EXECUTE,
        Permission.INFRASTRUCTURE_VIEW,
        Permission.TENANT_VIEW,
    },
    Role.ANALYST: {
        # Read-only access
        Permission.AGENT_MONITOR,
        Permission.CODE_READ,
        Permission.INFRASTRUCTURE_VIEW,
        Permission.TENANT_VIEW,
    },
    Role.EXTERNAL: {
        # Limited external access
        Permission.AGENT_MONITOR,
        Permission.CODE_READ,
        Permission.TENANT_VIEW,
    },
}


@dataclass
class UserRole:
    """User role assignment with tenant context"""
    user_id: str
    role: Role
    tenant_id: Optional[str] = None
    assigned_at: str = field(default_factory=lambda: datetime.now().isoformat())
    assigned_by: Optional[str] = None
    expires_at: Optional[str] = None

    def is_valid(self) -> bool:
        """Check if role assignment is still valid"""
        if self.expires_at:
            return datetime.fromisoformat(self.expires_at) > datetime.now()
        return True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "role": self.role.value,
            "tenant_id": self.tenant_id,
            "assigned_at": self.assigned_at,
            "assigned_by": self.assigned_by,
            "expires_at": self.expires_at,
        }


@dataclass
class AuditRecord:
    """Audit record for RBAC actions"""
    timestamp: str
    action: str
    user_id: str
    role: Optional[Role] = None
    permission: Optional[Permission] = None
    tenant_id: Optional[str] = None
    result: str = "allowed"  # allowed | denied
    reason: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "action": self.action,
            "user_id": self.user_id,
            "role": self.role.value if self.role else None,
            "permission": self.permission.value if self.permission else None,
            "tenant_id": self.tenant_id,
            "result": self.result,
            "reason": self.reason,
            "metadata": self.metadata,
        }


class RBAC:
    """
    Role-Based Access Control System

    Features:
    - Multi-tenant role assignments
    - Permission checking
    - Role hierarchy resolution
    - Audit trail generation
    - Persistent storage
    """

    def __init__(self, storage_path: Optional[Path] = None):
        self.storage_path = storage_path or Path("data/rbac_state.json")
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)

        # State
        self._user_roles: Dict[str, List[UserRole]] = defaultdict(list)
        self._tenant_users: Dict[str, Set[str]] = defaultdict(set)
        self._audit_log: List[AuditRecord] = []

        # Load state
        self._load()

        logger.info("[RBAC] System initialized")

    # ========================================================================
    # Role Management
    # ========================================================================

    def assign_role(
        self,
        user_id: str,
        role: Role,
        tenant_id: Optional[str] = None,
        assigned_by: Optional[str] = None,
        expires_at: Optional[str] = None
    ) -> UserRole:
        """
        Assign a role to a user

        Args:
            user_id: User identifier
            role: Role to assign
            tenant_id: Optional tenant ID for multi-tenancy
            assigned_by: User who made this assignment
            expires_at: Optional expiration timestamp

        Returns:
            UserRole assignment
        """
        # Check if user already has this role for the tenant
        existing = self.get_user_roles(user_id, tenant_id)
        if any(r.role == role and r.tenant_id == tenant_id for r in existing):
            logger.warning(f"[RBAC] User {user_id} already has role {role.value} for tenant {tenant_id}")
            return next(r for r in existing if r.role == role and r.tenant_id == tenant_id)

        user_role = UserRole(
            user_id=user_id,
            role=role,
            tenant_id=tenant_id,
            assigned_by=assigned_by,
            expires_at=expires_at
        )

        self._user_roles[user_id].append(user_role)

        if tenant_id:
            self._tenant_users[tenant_id].add(user_id)

        # Audit
        self._audit(
            action="role.assign",
            user_id=user_id,
            role=role,
            tenant_id=tenant_id,
            result="allowed",
            metadata={"assigned_by": assigned_by}
        )

        self._save()
        logger.info(f"[RBAC] Assigned role {role.value} to user {user_id}")

        return user_role

    def revoke_role(
        self,
        user_id: str,
        role: Role,
        tenant_id: Optional[str] = None,
        revoked_by: Optional[str] = None
    ) -> bool:
        """
        Revoke a role from a user

        Args:
            user_id: User identifier
            role: Role to revoke
            tenant_id: Optional tenant ID
            revoked_by: User who made this revocation

        Returns:
            True if role was revoked
        """
        roles = self._user_roles.get(user_id, [])
        original_count = len(roles)

        # Filter out the role to revoke
        self._user_roles[user_id] = [
            r for r in roles
            if not (r.role == role and (tenant_id is None or r.tenant_id == tenant_id))
        ]

        removed = len(roles) - len(self._user_roles[user_id])

        if removed > 0:
            # Audit
            self._audit(
                action="role.revoke",
                user_id=user_id,
                role=role,
                tenant_id=tenant_id,
                result="allowed",
                metadata={"revoked_by": revoked_by}
            )

            self._save()
            logger.info(f"[RBAC] Revoked role {role.value} from user {user_id}")
            return True

        logger.warning(f"[RBAC] Role {role.value} not found for user {user_id}")
        return False

    def get_user_roles(
        self,
        user_id: str,
        tenant_id: Optional[str] = None,
        include_expired: bool = False
    ) -> List[UserRole]:
        """
        Get user's roles

        Args:
            user_id: User identifier
            tenant_id: Optional tenant filter
            include_expired: Include expired roles

        Returns:
            List of user roles
        """
        roles = self._user_roles.get(user_id, [])

        # Filter by tenant
        if tenant_id is not None:
            roles = [r for r in roles if r.tenant_id == tenant_id or r.tenant_id is None]

        # Filter expired
        if not include_expired:
            roles = [r for r in roles if r.is_valid()]

        return roles

    # ========================================================================
    # Permission Checking
    # ========================================================================

    def check_permission(
        self,
        user_id: str,
        permission: Permission,
        tenant_id: Optional[str] = None
    ) -> bool:
        """
        Check if user has permission

        Args:
            user_id: User identifier
            permission: Permission to check
            tenant_id: Optional tenant context

        Returns:
            True if user has permission
        """
        roles = self.get_user_roles(user_id, tenant_id)

        if not roles:
            # No roles = no access
            self._audit(
                action="permission.check",
                user_id=user_id,
                permission=permission,
                tenant_id=tenant_id,
                result="denied",
                reason="no_role"
            )
            return False

        # Check all user roles
        for user_role in roles:
            if permission in ROLE_PERMISSIONS.get(user_role.role, set()):
                self._audit(
                    action="permission.check",
                    user_id=user_id,
                    role=user_role.role,
                    permission=permission,
                    tenant_id=tenant_id,
                    result="allowed",
                    reason=f"granted_via_{user_role.role.value}"
                )
                return True

        # Permission not found in any role
        self._audit(
            action="permission.check",
            user_id=user_id,
            permission=permission,
            tenant_id=tenant_id,
            result="denied",
            reason="permission_not_in_roles"
        )
        return False

    def check_any_permission(
        self,
        user_id: str,
        permissions: List[Permission],
        tenant_id: Optional[str] = None
    ) -> bool:
        """
        Check if user has ANY of the given permissions

        Args:
            user_id: User identifier
            permissions: List of permissions to check
            tenant_id: Optional tenant context

        Returns:
            True if user has at least one permission
        """
        return any(
            self.check_permission(user_id, perm, tenant_id)
            for perm in permissions
        )

    def check_all_permissions(
        self,
        user_id: str,
        permissions: List[Permission],
        tenant_id: Optional[str] = None
    ) -> bool:
        """
        Check if user has ALL of the given permissions

        Args:
            user_id: User identifier
            permissions: List of permissions to check
            tenant_id: Optional tenant context

        Returns:
            True if user has all permissions
        """
        return all(
            self.check_permission(user_id, perm, tenant_id)
            for perm in permissions
        )

    def require_permission(self, user_id: str, permission: Permission, tenant_id: Optional[str] = None):
        """
        Decorator/function to require permission or raise exception

        Raises:
            PermissionError: If user lacks permission
        """
        if not self.check_permission(user_id, permission, tenant_id):
            raise PermissionError(
                f"User {user_id} lacks permission {permission.value}"
                f" (tenant: {tenant_id})"
            )

    # ========================================================================
    # Tenant Management
    # ========================================================================

    def get_tenant_users(self, tenant_id: str) -> List[str]:
        """Get all users in a tenant"""
        return list(self._tenant_users.get(tenant_id, set()))

    def get_tenants_for_user(self, user_id: str) -> Set[str]:
        """Get all tenants a user belongs to"""
        roles = self.get_user_roles(user_id)
        return {r.tenant_id for r in roles if r.tenant_id}

    # ========================================================================
    # Audit
    # ========================================================================

    def get_audit_log(
        self,
        user_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        limit: int = 100
    ) -> List[AuditRecord]:
        """
        Get audit log

        Args:
            user_id: Filter by user
            tenant_id: Filter by tenant
            limit: Max records

        Returns:
            List of audit records
        """
        records = self._audit_log

        if user_id:
            records = [r for r in records if r.user_id == user_id]

        if tenant_id:
            records = [r for r in records if r.tenant_id == tenant_id]

        return records[-limit:]

    def _audit(
        self,
        action: str,
        user_id: str,
        role: Optional[Role] = None,
        permission: Optional[Permission] = None,
        tenant_id: Optional[str] = None,
        result: str = "allowed",
        reason: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Record audit event"""
        record = AuditRecord(
            timestamp=datetime.now().isoformat(),
            action=action,
            user_id=user_id,
            role=role,
            permission=permission,
            tenant_id=tenant_id,
            result=result,
            reason=reason,
            metadata=metadata or {}
        )
        self._audit_log.append(record)

        # Keep only last 10,000 records
        if len(self._audit_log) > 10000:
            self._audit_log = self._audit_log[-10000:]

    # ========================================================================
    # Persistence
    # ========================================================================

    def _save(self):
        """Save state to file"""
        data = {
            "user_roles": {
                user_id: [r.to_dict() for r in roles]
                for user_id, roles in self._user_roles.items()
            },
            "tenant_users": {
                tenant_id: list(users)
                for tenant_id, users in self._tenant_users.items()
            },
            "audit_log": [r.to_dict() for r in self._audit_log[-1000:]],  # Last 1000
        }

        with open(self.storage_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _load(self):
        """Load state from file"""
        if not self.storage_path.exists():
            # Create default admin user
            self.assign_role(
                user_id="admin",
                role=Role.SUPER_ADMIN,
                assigned_by="system"
            )
            return

        try:
            with open(self.storage_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Load user roles
            for user_id, roles_data in data.get("user_roles", {}).items():
                for role_data in roles_data:
                    role = Role(role_data["role"])
                    user_role = UserRole(
                        user_id=role_data["user_id"],
                        role=role,
                        tenant_id=role_data.get("tenant_id"),
                        assigned_at=role_data.get("assigned_at", datetime.now().isoformat()),
                        assigned_by=role_data.get("assigned_by"),
                        expires_at=role_data.get("expires_at")
                    )
                    self._user_roles[user_id].append(user_role)

                    if user_role.tenant_id:
                        self._tenant_users[user_role.tenant_id].add(user_id)

            # Load audit log
            for record_data in data.get("audit_log", []):
                role = Role(record_data["role"]) if record_data.get("role") else None
                permission = Permission(record_data["permission"]) if record_data.get("permission") else None

                self._audit_log.append(AuditRecord(
                    timestamp=record_data["timestamp"],
                    action=record_data["action"],
                    user_id=record_data["user_id"],
                    role=role,
                    permission=permission,
                    tenant_id=record_data.get("tenant_id"),
                    result=record_data.get("result", "allowed"),
                    reason=record_data.get("reason"),
                    metadata=record_data.get("metadata", {})
                ))

            logger.info(f"[RBAC] Loaded state: {len(self._user_roles)} users, {len(self._audit_log)} audit records")

        except Exception as e:
            logger.error(f"[RBAC] Failed to load state: {e}")
            # Create default admin user
            self.assign_role(
                user_id="admin",
                role=Role.SUPER_ADMIN,
                assigned_by="system"
            )

    # ========================================================================
    # Status
    # ========================================================================

    def get_status(self) -> Dict[str, Any]:
        """Get system status"""
        return {
            "total_users": len(self._user_roles),
            "total_tenants": len(self._tenant_users),
            "total_audit_records": len(self._audit_log),
            "roles": {
                role.value: len([
                    u for roles in self._user_roles.values()
                    for r in roles if r.role == role
                ])
                for role in Role
            }
        }


# =============================================================================
# Singleton Instance
# =============================================================================

_global_rbac: Optional[RBAC] = None


def get_rbac() -> RBAC:
    """Get global RBAC instance"""
    global _global_rbac
    if _global_rbac is None:
        _global_rbac = RBAC()
    return _global_rbac


def set_rbac(rbac: RBAC) -> None:
    """Set global RBAC instance"""
    global _global_rbac
    _global_rbac = rbac


__all__ = [
    "RBAC",
    "Role",
    "Permission",
    "UserRole",
    "AuditRecord",
    "get_rbac",
    "set_rbac",
]
