"""Goal-centric structured Memory Manager per §17 of the Master Specification.

Memory stores useful persistent state (decisions, approvals, deadlines,
history entries) without vector/semantic databases.  Retrieval uses direct
structured lookup by (user_id, goal_id, type) as mandated by ADR-006.

Policies implemented here:
  * User + goal isolation on every read/write path (§17.2 Privacy).
  * Cascade deletion when a goal is removed (§17.2 Deletion).
  * No raw sensitive content beyond what is needed to resume/audit (§17.2).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy.orm import Session

from app.enums import MemoryType
from app.logging_config import get_logger
from app.models import Memory

logger = get_logger(__name__)


@dataclass
class MemoryWriteResult:
    memory_id: UUID
    user_id: UUID
    goal_id: UUID | None
    memory_type: MemoryType


class MemoryStore(Protocol):
    """Narrow storage surface — swappable for unit tests."""

    def create(
        self,
        *,
        user_id: UUID,
        goal_id: UUID | None,
        memory_type: MemoryType,
        payload: dict[str, Any],
    ) -> Memory: ...

    def list_for_goal(
        self,
        *,
        user_id: UUID,
        goal_id: UUID,
    ) -> list[Memory]: ...

    def list_for_user(
        self,
        *,
        user_id: UUID,
        memory_type: MemoryType | None,
    ) -> list[Memory]: ...


class _DbMemoryStore:
    """Default store backed by the SQLAlchemy session and app.crud helpers."""

    def __init__(self, db_session: Session) -> None:
        self._db = db_session

    def create(
        self,
        *,
        user_id: UUID,
        goal_id: UUID | None,
        memory_type: MemoryType,
        payload: dict[str, Any],
    ) -> Memory:
        import app.crud as crud

        return crud.create_memory(
            self._db,
            user_id=user_id,
            goal_id=goal_id,
            memory_type=memory_type,
            payload=payload,
        )

    def list_for_goal(
        self,
        *,
        user_id: UUID,
        goal_id: UUID,
    ) -> list[Memory]:
        import app.crud as crud

        return crud.list_memory_for_goal(
            self._db,
            user_id=user_id,
            goal_id=goal_id,
        )

    def list_for_user(
        self,
        *,
        user_id: UUID,
        memory_type: MemoryType | None,
    ) -> list[Memory]:
        import app.crud as crud

        return crud.list_memory_for_user(
            self._db,
            user_id=user_id,
            memory_type=memory_type,
        )


class MemoryManager:
    """Structured memory persistence and retrieval (§17).

    This is the integration layer used by the Executor → Memory step of
    the Agent Workflow (§8).  It does NOT perform embeddings or vector
    lookup; all queries are relational structured lookups.
    """

    def __init__(self, store: MemoryStore | None = None) -> None:
        self._store = store

    def _resolve_store(self, db_session: Session | None) -> MemoryStore:
        if self._store is not None:
            return self._store
        if db_session is None:
            raise RuntimeError(
                "MemoryManager requires a MemoryStore at construction or a "
                "db_session passed to each call."
            )
        return _DbMemoryStore(db_session)

    def record_decision(
        self,
        *,
        user_id: UUID,
        goal_id: UUID | None,
        decision: str,
        context: dict[str, Any] | None = None,
        actor: str = "user",
        db_session: Session | None = None,
    ) -> MemoryWriteResult:
        """Record a user/system decision (§17.1 — Decisions)."""
        store = self._resolve_store(db_session)
        payload = {
            "decision": decision,
            "actor": actor,
            "context": context or {},
        }
        mem = store.create(
            user_id=user_id,
            goal_id=goal_id,
            memory_type=MemoryType.DECISION,
            payload=payload,
        )
        return MemoryWriteResult(
            memory_id=mem.id,
            user_id=mem.user_id,
            goal_id=mem.goal_id,
            memory_type=mem.type,
        )

    def record_approval(
        self,
        *,
        user_id: UUID,
        goal_id: UUID | None,
        permission_id: UUID | None,
        tool_id: UUID | None,
        granted: bool,
        scope: str | None = None,
        db_session: Session | None = None,
    ) -> MemoryWriteResult:
        """Record a permission approval/revocation event (§17.1 — Approvals)."""
        store = self._resolve_store(db_session)
        payload = {
            "permission_id": str(permission_id) if permission_id else None,
            "tool_id": str(tool_id) if tool_id else None,
            "granted": granted,
            "scope": scope,
        }
        mem = store.create(
            user_id=user_id,
            goal_id=goal_id,
            memory_type=MemoryType.APPROVAL,
            payload=payload,
        )
        return MemoryWriteResult(
            memory_id=mem.id,
            user_id=mem.user_id,
            goal_id=mem.goal_id,
            memory_type=mem.type,
        )

    def record_deadline(
        self,
        *,
        user_id: UUID,
        goal_id: UUID | None,
        deadline_iso: str,
        description: str,
        db_session: Session | None = None,
    ) -> MemoryWriteResult:
        """Record a deadline reference (§17.1 — Deadlines)."""
        store = self._resolve_store(db_session)
        payload = {
            "deadline": deadline_iso,
            "description": description,
        }
        mem = store.create(
            user_id=user_id,
            goal_id=goal_id,
            memory_type=MemoryType.DEADLINE,
            payload=payload,
        )
        return MemoryWriteResult(
            memory_id=mem.id,
            user_id=mem.user_id,
            goal_id=mem.goal_id,
            memory_type=mem.type,
        )

    def record_history_entry(
        self,
        *,
        user_id: UUID,
        goal_id: UUID | None,
        action_id: UUID | None,
        task_id: UUID | None,
        event: str,
        details: dict[str, Any] | None = None,
        db_session: Session | None = None,
    ) -> MemoryWriteResult:
        """Append an auditable action-history entry (§17.1 — Action history)."""
        store = self._resolve_store(db_session)
        payload = {
            "action_id": str(action_id) if action_id else None,
            "task_id": str(task_id) if task_id else None,
            "event": event,
            "details": details or {},
        }
        mem = store.create(
            user_id=user_id,
            goal_id=goal_id,
            memory_type=MemoryType.HISTORY_ENTRY,
            payload=payload,
        )
        return MemoryWriteResult(
            memory_id=mem.id,
            user_id=mem.user_id,
            goal_id=mem.goal_id,
            memory_type=mem.type,
        )

    def retrieve_goal_context(
        self,
        *,
        user_id: UUID,
        goal_id: UUID,
        db_session: Session | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        """Return all goal-scoped memories grouped by type (§17 structured lookup).

        Used by the Context Engine to rehydrate prior decisions, approvals
        and history when resuming an interrupted workflow (§8 — Memory /
        State Update stage).
        """
        store = self._resolve_store(db_session)
        rows = store.list_for_goal(user_id=user_id, goal_id=goal_id)
        grouped: dict[str, list[dict[str, Any]]] = {
            MemoryType.DECISION.value: [],
            MemoryType.APPROVAL.value: [],
            MemoryType.DEADLINE.value: [],
            MemoryType.HISTORY_ENTRY.value: [],
        }
        for m in rows:
            grouped[m.type.value].append(
                {
                    "id": str(m.id),
                    "created_at": m.created_at.isoformat() if m.created_at else None,
                    "payload": m.payload,
                }
            )
        return grouped


def default_memory_manager() -> MemoryManager:
    return MemoryManager()


__all__ = [
    "MemoryManager",
    "MemoryStore",
    "MemoryWriteResult",
    "default_memory_manager",
]
