"""Phase 5 — Permissions + Execution + Verification.

Implements the controlled execution system per §14-16 of the Master
Specification.

Architecture:

    Proposed Action
        ↓
    Permission Engine  →  AUTOMATIC / CONFIRMATION_REQUIRED / BLOCKED
        ↓ (AUTOMATIC path, or CONFIRMATION after user approves)
    Executor (ToolRegistry-lookup only, NEVER arbitrary code)
        ↓
    Tool Handler → provider adapters
        ↓
    Verifier (independent verification of resulting state)
        ↓
    AuditEvent + persisted Action state

Action state machine (§15.1):
    PENDING → WAITING_CONFIRMATION → RUNNING → COMPLETED
                                              ↘ FAILED
    PENDING → BLOCKED
    RUNNING → CANCELLED
    COMPLETED → UNVERIFIED  (if verification fails)
"""

from app.execution.permission_engine import (
    PermissionDecision,
    PermissionEngine,
    PermissionOutcome,
    default_permission_engine,
)
from app.execution.executor import (
    ActionExecutor,
    ExecutorResult,
    default_action_executor,
    UnknownToolError,
)
from app.execution.verifier import (
    ActionVerifier,
    VerificationOutcome,
    default_action_verifier,
)
from app.execution.engine import (
    ControlledExecutionEngine,
    ExecutionRequest,
    ExecutionOutcome,
    default_execution_engine,
    execute_task,
)
from app.execution.audit import (
    AuditLogger,
    NoopAuditLogger,
    DatabaseAuditLogger,
    default_audit_logger,
)

__all__ = [
    # permission
    "PermissionDecision",
    "PermissionOutcome",
    "PermissionEngine",
    "default_permission_engine",
    # executor
    "ActionExecutor",
    "ExecutorResult",
    "UnknownToolError",
    "default_action_executor",
    # verifier
    "ActionVerifier",
    "VerificationOutcome",
    "default_action_verifier",
    # top-level engine
    "ControlledExecutionEngine",
    "ExecutionRequest",
    "ExecutionOutcome",
    "execute_task",
    "default_execution_engine",
    # audit
    "AuditLogger",
    "NoopAuditLogger",
    "DatabaseAuditLogger",
    "default_audit_logger",
]
