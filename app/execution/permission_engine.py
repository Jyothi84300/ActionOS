"""Permission Engine per §14 of the Master Specification.

Evaluates each proposed action against both:
  * ActionOS Permission Policy (§14.2): AUTOMATIC / CONFIRMATION_REQUIRED / BLOCKED
  * User's stored grants (user_id → tool_id scope) in the `permissions` table.

Platform permission checks (Android runtime, etc.) are the responsibility
of the device-local Android layer.  In the Cloud Agent Core we simply
assume platform permissions are already satisfied when a tool has
`ToolCapability.LOCAL` and the user has granted it; for cloud-only
integrations the permission decision here is the only gate.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID

from app.enums import PermissionLevel
from app.logging_config import get_logger
from app.models import Permission
from app.skills.contracts import ToolContract
from app.skills.registry import ToolRegistry, default_tool_registry

logger = get_logger(__name__)


class PermissionOutcome(str, enum.Enum):
    AUTOMATIC = "AUTOMATIC"
    """§14.2 — executes without per-instance user confirmation."""
    CONFIRMATION_REQUIRED = "CONFIRMATION_REQUIRED"
    """§14.2 — action moves to WAITING_CONFIRMATION before execution."""
    BLOCKED = "BLOCKED"
    """§14.2 — action moves to BLOCKED; never executed."""


@dataclass
class PermissionDecision:
    outcome: PermissionOutcome
    permission_level: PermissionLevel
    tool_id: UUID
    user_id: UUID
    scope: str | None = None
    permission_id: UUID | None = None
    reasons: list[str] = field(default_factory=list)
    """Human-readable, auditable reasons for this decision."""


class PermissionStore(Protocol):
    """Thin accessor over user permissions — swappable for tests."""

    def get_permission_for_tool(
        self, user_id: UUID, tool_id: UUID, scope: str | None
    ) -> Permission | None: ...


class _DbPermissionStore:
    """Default PermissionStore reading from the SQLAlchemy session."""

    def __init__(self, db_session) -> None:
        self._db = db_session

    def get_permission_for_tool(
        self, user_id: UUID, tool_id: UUID, scope: str | None
    ) -> Permission | None:
        q = self._db.query(Permission).filter(
            Permission.user_id == user_id,
            Permission.tool_id == tool_id,
        )
        results = q.all()
        # Narrow by scope when a caller-provided scope exists.
        if scope is not None:
            scoped = [r for r in results if r.scope == scope]
            if scoped:
                return scoped[0]
        return results[0] if results else None


class PermissionEngine:
    """§14 — evaluates tool-level permission for each proposed action."""

    def __init__(self, tool_registry: ToolRegistry | None = None) -> None:
        self._registry = tool_registry or default_tool_registry()

    def evaluate(
        self,
        *,
        user_id: UUID,
        tool_id: UUID,
        permission_store: PermissionStore,
        scope: str | None = None,
    ) -> PermissionDecision:
        tool: ToolContract | None = self._registry.get(tool_id)
        if tool is None:
            # Unknown tools are BLOCKED by default (safety-first).
            return PermissionDecision(
                outcome=PermissionOutcome.BLOCKED,
                permission_level=PermissionLevel.BLOCKED,
                tool_id=tool_id,
                user_id=user_id,
                scope=scope,
                reasons=[
                    f"Tool {tool_id!s} is not registered in the ToolRegistry.",
                    "Unknown tool_ids are blocked per §13 of the Master Specification.",
                ],
            )

        tier = tool.permission_level

        if tier == PermissionLevel.BLOCKED:
            # §14.2 — the Blocked tier can never be overridden by a grant.
            return PermissionDecision(
                outcome=PermissionOutcome.BLOCKED,
                permission_level=tier,
                tool_id=tool_id,
                user_id=user_id,
                scope=scope,
                reasons=[
                    "Tool is declared BLOCKED in its ToolContract manifest.",
                    "§14.2: Blocked-tier operations are never executed.",
                ],
            )

        stored = permission_store.get_permission_for_tool(user_id, tool_id, scope)
        grant_status = "UNKNOWN"
        if stored is not None:
            if stored.revoked_at is not None:
                grant_status = "REVOKED"
            elif stored.granted:
                grant_status = "GRANTED"
            else:
                grant_status = "NOT_GRANTED"

        if tier == PermissionLevel.AUTOMATIC:
            # §14.2 — execute immediately unless the user revoked the tool.
            if grant_status == "REVOKED":
                return PermissionDecision(
                    outcome=PermissionOutcome.BLOCKED,
                    permission_level=tier,
                    tool_id=tool_id,
                    user_id=user_id,
                    scope=scope,
                    permission_id=stored.id if stored else None,
                    reasons=["User revoked this tool permission."],
                )
            return PermissionDecision(
                outcome=PermissionOutcome.AUTOMATIC,
                permission_level=tier,
                tool_id=tool_id,
                user_id=user_id,
                scope=scope,
                permission_id=stored.id if stored else None,
                reasons=[
                    "Tool's registered permission_level is AUTOMATIC.",
                    (
                        "Implicit grant: user has not explicitly revoked the permission."
                        if grant_status != "GRANTED"
                        else "Explicit grant present in permissions table."
                    ),
                ],
            )

        # CONFIRMATION_REQUIRED tier:
        if grant_status == "GRANTED":
            # User pre-granted — treat as AUTOMATIC path (§14.3 lifecycle).
            return PermissionDecision(
                outcome=PermissionOutcome.AUTOMATIC,
                permission_level=tier,
                tool_id=tool_id,
                user_id=user_id,
                scope=scope,
                permission_id=stored.id if stored else None,
                reasons=[
                    "Tool requires CONFIRMATION per manifest but user has a stored grant.",
                ],
            )
        if grant_status == "REVOKED":
            return PermissionDecision(
                outcome=PermissionOutcome.BLOCKED,
                permission_level=tier,
                tool_id=tool_id,
                user_id=user_id,
                scope=scope,
                permission_id=stored.id if stored else None,
                reasons=["User revoked this tool permission."],
            )
        # Default — requires per-instance confirmation UI.
        return PermissionDecision(
            outcome=PermissionOutcome.CONFIRMATION_REQUIRED,
            permission_level=tier,
            tool_id=tool_id,
            user_id=user_id,
            scope=scope,
            permission_id=stored.id if stored else None,
            reasons=[
                "Tool requires CONFIRMATION_REQUIRED per its ToolContract manifest.",
                "No pre-existing grant found — user must confirm per-instance.",
            ],
        )


def default_permission_engine() -> PermissionEngine:
    return PermissionEngine()
