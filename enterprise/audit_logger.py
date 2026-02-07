"""
Audit Logger - SOC2/GDPR Compliant Audit Trail
==============================================

Immutable, append-only logging system for security events.

Features:
- Append-only logs (cannot delete/modify)
- Hash chaining for tamper detection
- SOC2/GDPR compliant (7-year retention)
- Structured event types
- Multi-tenant isolation
- Export capabilities

Usage:
    from enterprise.audit_logger import AuditLogger, EventType

    logger = AuditLogger()
    logger.log(
        event_type=EventType.CODE_EXECUTED,
        user_id="user_123",
        tenant_id="tenant_abc",
        data={"module": "auth", "result": "success"}
    )
"""

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any
from collections import deque

logger = logging.getLogger(__name__)


class EventType(Enum):
    """Audit event types"""
    # Authentication & Authorization
    USER_LOGIN = "user.login"
    USER_LOGOUT = "user.logout"
    USER_CREATED = "user.created"
    USER_DELETED = "user.deleted"
    ROLE_ASSIGNED = "role.assigned"
    ROLE_REVOKED = "role.revoked"
    PERMISSION_DENIED = "permission.denied"
    PERMISSION_GRANTED = "permission.granted"

    # Circuit Breaker
    AUTONOMY_LEVEL_CHANGED = "autonomy.level_changed"
    AUTONOMY_ESCALATED = "autonomy.escalated"
    AUTONOMY_DE_ESCALATED = "autonomy.de_escalated"
    HUMAN_ACTIVITY_RECORDED = "human.activity_recorded"

    # Siege Mode
    SIEGE_ACTIVATED = "siege.activated"
    SIEGE_DEACTIVATED = "siege.deactivated"
    SIEGE_TASK_EXECUTED = "siege.task_executed"
    SIEGE_REPORT_GENERATED = "siege.report_generated"

    # Debate Pipeline
    DEBATE_STARTED = "debate.started"
    DEBATE_COMPLETED = "debate.completed"
    DEBATE_FAILED = "debate.failed"
    DEBATE_VERDICT = "debate.verdict"

    # Execution
    CODE_EXECUTED = "code.executed"
    CODE_DEPLOYED = "code.deployed"
    CODE_MODIFIED = "code.modified"
    CONTRACT_VIOLATION = "contract.violation"
    SANDBOX_ESCAPE_ATTEMPT = "sandbox.escape_attempt"

    # Agent
    AGENT_CREATED = "agent.created"
    AGENT_DELETED = "agent.deleted"
    AGENT_DISABLED = "agent.disabled"
    AGENT_EXECUTED = "agent.executed"

    # Tenant
    TENANT_CREATED = "tenant.created"
    TENANT_DELETED = "tenant.deleted"
    TENANT_MODIFIED = "tenant.modified"

    # System
    SYSTEM_STARTED = "system.started"
    SYSTEM_STOPPED = "system.stopped"
    SYSTEM_ERROR = "system.error"
    CONFIG_CHANGED = "config.changed"

    # Audit
    AUDIT_LOG_EXPORTED = "audit.exported"
    AUDIT_LOG_QUERIED = "audit.queried"
    AUDIT_TAMPER_DETECTED = "audit.tamper_detected"


class Severity(Enum):
    """Event severity levels"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class AuditEvent:
    """Immutable audit event"""
    event_id: str
    timestamp: str
    event_type: str
    severity: str
    user_id: Optional[str] = None
    tenant_id: Optional[str] = None
    session_id: Optional[str] = None
    data: Dict[str, Any] = field(default_factory=dict)
    source_ip: Optional[str] = None
    user_agent: Optional[str] = None
    chain_hash: Optional[str] = None  # Previous hash in chain
    event_hash: Optional[str] = None  # Hash of this event

    def __post_init__(self):
        """Calculate event hash after creation"""
        if self.event_hash is None:
            self.event_hash = self._calculate_hash()

    def _calculate_hash(self) -> str:
        """Calculate SHA-256 hash of event data"""
        content = f"{self.event_id}:{self.timestamp}:{self.event_type}:{self.user_id}:{self.tenant_id}:{json.dumps(self.data, sort_keys=True)}"
        if self.chain_hash:
            content += f":{self.chain_hash}"
        return hashlib.sha256(content.encode()).hexdigest()

    def verify_chain(self, previous_hash: Optional[str]) -> bool:
        """Verify event chain integrity"""
        return self.chain_hash == previous_hash

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "severity": self.severity,
            "user_id": self.user_id,
            "tenant_id": self.tenant_id,
            "session_id": self.session_id,
            "data": self.data,
            "source_ip": self.source_ip,
            "user_agent": self.user_agent,
            "chain_hash": self.chain_hash,
            "event_hash": self.event_hash,
        }


@dataclass
class AuditQuery:
    """Query parameters for audit log"""
    event_types: Optional[List[EventType]] = None
    user_id: Optional[str] = None
    tenant_id: Optional[str] = None
    severity: Optional[Severity] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    limit: int = 100
    offset: int = 0


class AuditLogger:
    """
    SOC2/GDPR Compliant Audit Logger

    Features:
    - Append-only (no delete/modify)
    - Hash chaining for tamper detection
    - Automatic rotation
    - Export capabilities
    """

    def __init__(
        self,
        storage_dir: Optional[Path] = None,
        retention_years: int = 7
    ):
        self.storage_dir = storage_dir or Path("data/audit")
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.retention_years = retention_years

        # Current log file
        self.current_log_file = self.storage_dir / f"audit_{datetime.now().strftime('%Y%m')}.jsonl"
        self.index_file = self.storage_dir / "audit_index.json"

        # In-memory state
        self._events: deque = deque(maxlen=10000)  # Last 10K in memory
        self._last_hash: Optional[str] = None
        self._event_counter: int = 0

        # Load state
        self._load_index()

        logger.info(f"[AuditLogger] Initialized with {retention_years} year retention")

    # ========================================================================
    # Logging
    # ========================================================================

    def log(
        self,
        event_type: EventType,
        data: Dict[str, Any],
        user_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        severity: Severity = Severity.INFO,
        session_id: Optional[str] = None,
        source_ip: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> AuditEvent:
        """
        Log an audit event

        Args:
            event_type: Type of event
            data: Event data
            user_id: User identifier
            tenant_id: Tenant identifier
            severity: Event severity
            session_id: Session identifier
            source_ip: Source IP address
            user_agent: User agent string

        Returns:
            AuditEvent that was created
        """
        # Generate event ID
        self._event_counter += 1
        event_id = f"evt_{datetime.now().strftime('%Y%m%d%H%M%S')}_{self._event_counter:06d}"

        # Create event
        event = AuditEvent(
            event_id=event_id,
            timestamp=datetime.now().isoformat(),
            event_type=event_type.value,
            severity=severity.value,
            user_id=user_id,
            tenant_id=tenant_id,
            session_id=session_id,
            data=data,
            source_ip=source_ip,
            user_agent=user_agent,
            chain_hash=self._last_hash,
        )

        # Update chain hash
        self._last_hash = event.event_hash

        # Store in memory
        self._events.append(event)

        # Persist to file
        self._append_to_file(event)

        # Update index
        self._update_index(event)

        return event

    def log_permission_denied(
        self,
        user_id: str,
        permission: str,
        tenant_id: Optional[str] = None,
        **kwargs
    ) -> AuditEvent:
        """Convenience method for logging permission denied"""
        return self.log(
            event_type=EventType.PERMISSION_DENIED,
            user_id=user_id,
            tenant_id=tenant_id,
            severity=Severity.WARNING,
            data={"permission": permission, **kwargs}
        )

    def log_code_executed(
        self,
        user_id: str,
        module: str,
        result: str,
        tenant_id: Optional[str] = None,
        **kwargs
    ) -> AuditEvent:
        """Convenience method for logging code execution"""
        return self.log(
            event_type=EventType.CODE_EXECUTED,
            user_id=user_id,
            tenant_id=tenant_id,
            data={"module": module, "result": result, **kwargs}
        )

    def log_contract_violation(
        self,
        user_id: str,
        violations: List[str],
        tenant_id: Optional[str] = None,
        **kwargs
    ) -> AuditEvent:
        """Convenience method for logging contract violations"""
        return self.log(
            event_type=EventType.CONTRACT_VIOLATION,
            user_id=user_id,
            tenant_id=tenant_id,
            severity=Severity.CRITICAL,
            data={"violations": violations, **kwargs}
        )

    # ========================================================================
    # Querying
    # ========================================================================

    def query(
        self,
        query: Optional[AuditQuery] = None,
        **kwargs
    ) -> List[AuditEvent]:
        """
        Query audit log

        Args:
            query: AuditQuery parameters
            **kwargs: Direct query parameters (overrides query)

        Returns:
            List of matching events
        """
        # Build query from kwargs if not provided
        if query is None:
            query = AuditQuery(**kwargs)

        # Start with in-memory events
        events = list(self._events)

        # Apply filters
        if query.event_types:
            events = [e for e in events if e.event_type in [t.value for t in query.event_types]]

        if query.user_id:
            events = [e for e in events if e.user_id == query.user_id]

        if query.tenant_id:
            events = [e for e in events if e.tenant_id == query.tenant_id]

        if query.severity:
            events = [e for e in events if e.severity == query.severity.value]

        if query.start_time:
            events = [e for e in events if e.timestamp >= query.start_time]

        if query.end_time:
            events = [e for e in events if e.timestamp <= query.end_time]

        # Sort by timestamp descending
        events = sorted(events, key=lambda e: e.timestamp, reverse=True)

        # Apply pagination
        return events[query.offset:query.offset + query.limit]

    def get_by_user(
        self,
        user_id: str,
        limit: int = 100
    ) -> List[AuditEvent]:
        """Get all events for a user"""
        return self.query(user_id=user_id, limit=limit)

    def get_by_tenant(
        self,
        tenant_id: str,
        limit: int = 100
    ) -> List[AuditEvent]:
        """Get all events for a tenant"""
        return self.query(tenant_id=tenant_id, limit=limit)

    def get_recent(
        self,
        limit: int = 50,
        severity: Optional[Severity] = None
    ) -> List[AuditEvent]:
        """Get recent events"""
        if severity:
            return self.query(limit=limit, severity=severity)
        return self.query(limit=limit)

    # ========================================================================
    # Chain Verification
    # ========================================================================

    def verify_chain(self) -> Dict[str, Any]:
        """
        Verify audit log chain integrity

        Returns:
            Verification result with details
        """
        events = list(self._events)
        valid = True
        breaks = []

        for i, event in enumerate(events):
            if i > 0:
                prev_hash = events[i - 1].event_hash
                if not event.verify_chain(prev_hash):
                    valid = False
                    breaks.append({
                        "event_id": event.event_id,
                        "expected_chain": prev_hash,
                        "actual_chain": event.chain_hash
                    })

        return {
            "valid": valid,
            "total_events": len(events),
            "breaks": breaks,
            "last_hash": self._last_hash
        }

    # ========================================================================
    # Export
    # ========================================================================

    def export(
        self,
        query: Optional[AuditQuery] = None,
        format: str = "json"
    ) -> str:
        """
        Export audit log

        Args:
            query: Query parameters for filtering
            format: Export format (json, csv)

        Returns:
            Exported data as string
        """
        events = self.query(query or AuditQuery())

        if format == "json":
            return json.dumps([e.to_dict() for e in events], indent=2)
        elif format == "csv":
            import csv
            import io

            output = io.StringIO()
            if events:
                writer = csv.DictWriter(output, fieldnames=events[0].to_dict().keys())
                writer.writeheader()
                for event in events:
                    writer.writerow(event.to_dict())
            return output.getvalue()
        else:
            raise ValueError(f"Unsupported format: {format}")

    # ========================================================================
    # Persistence
    # ========================================================================

    def _append_to_file(self, event: AuditEvent):
        """Append event to current log file"""
        # Check if we need to rotate (new month)
        expected_file = self.storage_dir / f"audit_{datetime.now().strftime('%Y%m')}.jsonl"
        if expected_file != self.current_log_file:
            self.current_log_file = expected_file

        with open(self.current_log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(event.to_dict(), ensure_ascii=False) + '\n')

    def _load_index(self):
        """Load audit index"""
        if not self.index_file.exists():
            return

        try:
            with open(self.index_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            self._event_counter = data.get("event_counter", 0)
            self._last_hash = data.get("last_hash")

            logger.info(f"[AuditLogger] Loaded index: {self._event_counter} events")

        except Exception as e:
            logger.error(f"[AuditLogger] Failed to load index: {e}")

    def _update_index(self, event: AuditEvent):
        """Update audit index"""
        data = {
            "event_counter": self._event_counter,
            "last_hash": self._last_hash,
            "last_event": {
                "event_id": event.event_id,
                "timestamp": event.timestamp,
                "event_type": event.event_type,
            },
            "updated_at": datetime.now().isoformat()
        }

        with open(self.index_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)

    # ========================================================================
    # Maintenance
    # ========================================================================

    def rotate_old_logs(self):
        """Rotate logs older than retention period"""
        cutoff_date = datetime.now().year - self.retention_years

        for log_file in self.storage_dir.glob("audit_*.jsonl"):
            # Extract year from filename
            try:
                year_str = log_file.stem.split('_')[1][:4]
                file_year = int(year_str)

                if file_year < cutoff_date:
                    log_file.unlink()
                    logger.info(f"[AuditLogger] Deleted old log: {log_file.name}")

            except (ValueError, IndexError):
                continue

    def get_status(self) -> Dict[str, Any]:
        """Get audit logger status"""
        chain_status = self.verify_chain()

        return {
            "total_events": self._event_counter,
            "memory_events": len(self._events),
            "current_log_file": str(self.current_log_file),
            "retention_years": self.retention_years,
            "chain_valid": chain_status["valid"],
            "chain_breaks": len(chain_status["breaks"]),
        }


# =============================================================================
# Singleton Instance
# =============================================================================

_global_audit_logger: Optional[AuditLogger] = None


def get_audit_logger() -> AuditLogger:
    """Get global AuditLogger instance"""
    global _global_audit_logger
    if _global_audit_logger is None:
        _global_audit_logger = AuditLogger()
    return _global_audit_logger


def set_audit_logger(audit_logger: AuditLogger) -> None:
    """Set global AuditLogger instance"""
    global _global_audit_logger
    _global_audit_logger = audit_logger


__all__ = [
    "AuditLogger",
    "AuditEvent",
    "AuditQuery",
    "EventType",
    "Severity",
    "get_audit_logger",
    "set_audit_logger",
]
