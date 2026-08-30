"""Tests for the Memory Architecture (§17 of the Master Specification).

Covers:
  * CRUD operations with strict user + goal isolation.
  * MemoryManager convenience writers (decision/approval/deadline/history).
  * Structured retrieval grouped by type for goal context rehydration.
  * Cascade deletion for goal-scoped entries.
  * API endpoint GET /api/v1/memory/{goal_id} including 403/404 cases.
"""

from __future__ import annotations

import datetime
from collections.abc import Generator
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

import app.crud as crud
from app.enums import MemoryType
from app.memory import MemoryManager, MemoryStore, MemoryWriteResult
from app.models import Memory
from tests.conftest import OTHER_USER_ID, TEST_USER_ID


def _goal_kwargs(payload: dict) -> dict:
    """Copy a JSON goal payload, converting deadline ISO string → datetime for direct CRUD use."""
    kwargs = dict(payload)
    dl = kwargs.get("deadline")
    if isinstance(dl, str):
        kwargs["deadline"] = datetime.datetime.fromisoformat(
            dl.replace("Z", "+00:00")
        )
    return kwargs


# ---------------------------------------------------------------------------
# In-memory MemoryStore fixture — allows testing MemoryManager without DB
# ---------------------------------------------------------------------------


class _InMemoryStore(MemoryStore):
    def __init__(self) -> None:
        self.rows: list[Memory] = []

    def create(
        self,
        *,
        user_id: UUID,
        goal_id: UUID | None,
        memory_type: MemoryType,
        payload: dict,
    ) -> Memory:
        import datetime

        mem = Memory(
            id=uuid4(),
            user_id=user_id,
            goal_id=goal_id,
            type=memory_type,
            payload=payload,
            created_at=datetime.datetime.now(datetime.timezone.utc),
        )
        self.rows.append(mem)
        return mem

    def list_for_goal(
        self,
        *,
        user_id: UUID,
        goal_id: UUID,
    ) -> list[Memory]:
        return [
            r
            for r in self.rows
            if r.user_id == user_id and r.goal_id == goal_id
        ]

    def list_for_user(
        self,
        *,
        user_id: UUID,
        memory_type: MemoryType | None,
    ) -> list[Memory]:
        out = [r for r in self.rows if r.user_id == user_id]
        if memory_type is not None:
            out = [r for r in out if r.type == memory_type]
        return out


@pytest.fixture()
def mem_store() -> _InMemoryStore:
    return _InMemoryStore()


@pytest.fixture()
def mem_manager(mem_store: _InMemoryStore) -> MemoryManager:
    return MemoryManager(store=mem_store)


# ---------------------------------------------------------------------------
# CRUD layer — user / goal isolation
# ---------------------------------------------------------------------------


class TestMemoryCrudIsolation:
    def test_create_and_list_memory_for_goal_isolated_by_user(
        self, db_session: Session, sample_goal_payload: dict
    ) -> None:
        goal_a = crud.create_goal(
            db_session, user_id=TEST_USER_ID, **_goal_kwargs(sample_goal_payload)
        )
        goal_b = crud.create_goal(
            db_session, user_id=OTHER_USER_ID, **_goal_kwargs(sample_goal_payload)
        )

        crud.create_memory(
            db_session,
            user_id=TEST_USER_ID,
            goal_id=goal_a.id,
            memory_type=MemoryType.DECISION,
            payload={"decision": "use calendar skill"},
        )
        crud.create_memory(
            db_session,
            user_id=OTHER_USER_ID,
            goal_id=goal_b.id,
            memory_type=MemoryType.DECISION,
            payload={"decision": "other user decision"},
        )

        ours = crud.list_memory_for_goal(
            db_session, user_id=TEST_USER_ID, goal_id=goal_a.id
        )
        assert len(ours) == 1
        assert ours[0].payload["decision"] == "use calendar skill"
        assert ours[0].user_id == TEST_USER_ID

        theirs = crud.list_memory_for_goal(
            db_session, user_id=OTHER_USER_ID, goal_id=goal_b.id
        )
        assert len(theirs) == 1
        assert theirs[0].payload["decision"] == "other user decision"

        cross = crud.list_memory_for_goal(
            db_session, user_id=TEST_USER_ID, goal_id=goal_b.id
        )
        assert cross == []

    def test_list_memory_for_user_filters_by_type(
        self, db_session: Session, sample_goal_payload: dict
    ) -> None:
        goal = crud.create_goal(
            db_session, user_id=TEST_USER_ID, **sample_goal_payload
        )
        for mt in (MemoryType.DECISION, MemoryType.APPROVAL, MemoryType.DEADLINE):
            crud.create_memory(
                db_session,
                user_id=TEST_USER_ID,
                goal_id=goal.id,
                memory_type=mt,
                payload={"kind": mt.value},
            )

        all_rows = crud.list_memory_for_user(db_session, user_id=TEST_USER_ID)
        assert len(all_rows) == 3

        only_decisions = crud.list_memory_for_user(
            db_session, user_id=TEST_USER_ID, memory_type=MemoryType.DECISION
        )
        assert len(only_decisions) == 1
        assert only_decisions[0].type == MemoryType.DECISION

    def test_cascade_delete_memories_for_goal_is_scoped(
        self, db_session: Session, sample_goal_payload: dict
    ) -> None:
        goal_a = crud.create_goal(
            db_session, user_id=TEST_USER_ID, **sample_goal_payload
        )
        goal_b = crud.create_goal(
            db_session, user_id=TEST_USER_ID, **sample_goal_payload
        )
        for _ in range(2):
            crud.create_memory(
                db_session,
                user_id=TEST_USER_ID,
                goal_id=goal_a.id,
                memory_type=MemoryType.HISTORY_ENTRY,
                payload={"g": "a"},
            )
            crud.create_memory(
                db_session,
                user_id=TEST_USER_ID,
                goal_id=goal_b.id,
                memory_type=MemoryType.HISTORY_ENTRY,
                payload={"g": "b"},
            )

        removed = crud.cascade_delete_memories_for_goal(
            db_session, user_id=TEST_USER_ID, goal_id=goal_a.id
        )
        assert removed == 2

        remaining_a = crud.list_memory_for_goal(
            db_session, user_id=TEST_USER_ID, goal_id=goal_a.id
        )
        remaining_b = crud.list_memory_for_goal(
            db_session, user_id=TEST_USER_ID, goal_id=goal_b.id
        )
        assert remaining_a == []
        assert len(remaining_b) == 2

    def test_delete_single_memory(self, db_session: Session, sample_goal_payload: dict) -> None:
        goal = crud.create_goal(
            db_session, user_id=TEST_USER_ID, **sample_goal_payload
        )
        mem = crud.create_memory(
            db_session,
            user_id=TEST_USER_ID,
            goal_id=goal.id,
            memory_type=MemoryType.DECISION,
            payload={"x": 1},
        )
        crud.delete_memory(db_session, mem)
        assert crud.get_memory(db_session, mem.id) is None


# ---------------------------------------------------------------------------
# MemoryManager convenience writers
# ---------------------------------------------------------------------------


class TestMemoryManagerWriters:
    def test_record_decision_structures_payload(
        self, mem_manager: MemoryManager, mem_store: _InMemoryStore
    ) -> None:
        goal_id = uuid4()
        result = mem_manager.record_decision(
            user_id=TEST_USER_ID,
            goal_id=goal_id,
            decision="schedule reminder",
            context={"reason": "deadline approaching"},
        )
        assert isinstance(result, MemoryWriteResult)
        assert result.memory_type == MemoryType.DECISION
        assert result.goal_id == goal_id

        stored = mem_store.rows[0]
        assert stored.payload["decision"] == "schedule reminder"
        assert stored.payload["actor"] == "user"
        assert stored.payload["context"]["reason"] == "deadline approaching"

    def test_record_approval_captures_grant_state(
        self, mem_manager: MemoryManager, mem_store: _InMemoryStore
    ) -> None:
        pid, tid = uuid4(), uuid4()
        result = mem_manager.record_approval(
            user_id=TEST_USER_ID,
            goal_id=None,
            permission_id=pid,
            tool_id=tid,
            granted=True,
            scope="calendar:primary",
        )
        assert result.memory_type == MemoryType.APPROVAL
        stored = mem_store.rows[0]
        assert stored.payload["granted"] is True
        assert stored.payload["scope"] == "calendar:primary"
        assert stored.payload["permission_id"] == str(pid)
        assert stored.goal_id is None

    def test_record_deadline_and_history(
        self, mem_manager: MemoryManager, mem_store: _InMemoryStore
    ) -> None:
        goal_id = uuid4()
        mem_manager.record_deadline(
            user_id=TEST_USER_ID,
            goal_id=goal_id,
            deadline_iso="2026-09-04T23:59:00+00:00",
            description="paper draft due",
        )
        action_id = uuid4()
        mem_manager.record_history_entry(
            user_id=TEST_USER_ID,
            goal_id=goal_id,
            action_id=action_id,
            task_id=uuid4(),
            event="action.completed",
            details={"verified": True},
        )

        types = [r.type for r in mem_store.rows]
        assert types == [MemoryType.DEADLINE, MemoryType.HISTORY_ENTRY]

        history = mem_store.rows[1]
        assert history.payload["event"] == "action.completed"
        assert history.payload["details"]["verified"] is True
        assert history.payload["action_id"] == str(action_id)

    def test_retrieve_goal_context_groups_by_type(
        self, mem_manager: MemoryManager, mem_store: _InMemoryStore
    ) -> None:
        goal_id = uuid4()
        mem_manager.record_decision(
            user_id=TEST_USER_ID, goal_id=goal_id, decision="d1"
        )
        mem_manager.record_decision(
            user_id=TEST_USER_ID, goal_id=goal_id, decision="d2"
        )
        mem_manager.record_history_entry(
            user_id=TEST_USER_ID,
            goal_id=goal_id,
            action_id=None,
            task_id=None,
            event="created",
        )

        ctx = mem_manager.retrieve_goal_context(
            user_id=TEST_USER_ID, goal_id=goal_id
        )
        assert len(ctx[MemoryType.DECISION.value]) == 2
        assert len(ctx[MemoryType.HISTORY_ENTRY.value]) == 1
        assert ctx[MemoryType.APPROVAL.value] == []
        assert ctx[MemoryType.DEADLINE.value] == []

    def test_retrieve_goal_context_isolates_users(
        self, mem_manager: MemoryManager, mem_store: _InMemoryStore
    ) -> None:
        goal_id = uuid4()
        mem_manager.record_decision(
            user_id=TEST_USER_ID, goal_id=goal_id, decision="mine"
        )
        mem_manager.record_decision(
            user_id=OTHER_USER_ID, goal_id=goal_id, decision="theirs"
        )

        ctx = mem_manager.retrieve_goal_context(
            user_id=TEST_USER_ID, goal_id=goal_id
        )
        decisions = ctx[MemoryType.DECISION.value]
        assert len(decisions) == 1
        assert decisions[0]["payload"]["decision"] == "mine"

    def test_db_memory_store_roundtrip(
        self, db_session: Session, sample_goal_payload: dict
    ) -> None:
        goal = crud.create_goal(
            db_session, user_id=TEST_USER_ID, **sample_goal_payload
        )
        mm = MemoryManager()
        result = mm.record_decision(
            user_id=TEST_USER_ID,
            goal_id=goal.id,
            decision="db-backed",
            db_session=db_session,
        )
        stored = crud.get_memory(db_session, result.memory_id)
        assert stored is not None
        assert stored.payload["decision"] == "db-backed"

        ctx = mm.retrieve_goal_context(
            user_id=TEST_USER_ID, goal_id=goal.id, db_session=db_session
        )
        assert len(ctx[MemoryType.DECISION.value]) == 1


# ---------------------------------------------------------------------------
# API endpoint GET /api/v1/memory/{goal_id}
# ---------------------------------------------------------------------------


class TestMemoryApi:
    def _create_goal_with_memories(
        self, client: TestClient, sample_goal_payload: dict
    ) -> UUID:
        resp = client.post("/api/v1/goals", json=sample_goal_payload)
        goal_id = UUID(resp.json()["id"])
        for mt in (MemoryType.DECISION, MemoryType.HISTORY_ENTRY):
            resp2 = client.post("/api/v1/goals", json=sample_goal_payload)
            # ensure the 2nd goal doesn't cause cross-contamination later
            _ = resp2
        return goal_id

    def test_list_memory_empty(self, client: TestClient, sample_goal_payload: dict, db_session: Session) -> None:
        resp = client.post("/api/v1/goals", json=sample_goal_payload)
        goal_id = resp.json()["id"]
        resp = client.get(f"/api/v1/memory/{goal_id}")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_memory_returns_entries_ordered_created_asc(
        self, client: TestClient, sample_goal_payload: dict, db_session: Session
    ) -> None:
        resp = client.post("/api/v1/goals", json=sample_goal_payload)
        goal_id = UUID(resp.json()["id"])
        crud.create_memory(
            db_session,
            user_id=TEST_USER_ID,
            goal_id=goal_id,
            memory_type=MemoryType.DECISION,
            payload={"order": 1},
        )
        crud.create_memory(
            db_session,
            user_id=TEST_USER_ID,
            goal_id=goal_id,
            memory_type=MemoryType.HISTORY_ENTRY,
            payload={"order": 2},
        )
        resp = client.get(f"/api/v1/memory/{goal_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["type"] == MemoryType.DECISION.value
        assert data[1]["type"] == MemoryType.HISTORY_ENTRY.value
        for row in data:
            assert UUID(row["user_id"]) == TEST_USER_ID
            assert UUID(row["goal_id"]) == goal_id

    def test_list_memory_404_goal_not_found(self, client: TestClient) -> None:
        resp = client.get(f"/api/v1/memory/{uuid4()}")
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "GOAL_NOT_FOUND"

    def test_list_memory_403_forbidden_other_user(
        self,
        client: TestClient,
        sample_goal_payload: dict,
        db_session: Session,
        auth_headers: dict,
    ) -> None:
        # Create goal owned by OTHER_USER_ID directly via crud
        other_goal = crud.create_goal(
            db_session, user_id=OTHER_USER_ID, **sample_goal_payload
        )
        crud.create_memory(
            db_session,
            user_id=OTHER_USER_ID,
            goal_id=other_goal.id,
            memory_type=MemoryType.DECISION,
            payload={"secret": "other-user-data"},
        )
        resp = client.get(f"/api/v1/memory/{other_goal.id}")
        assert resp.status_code == 403
        body = resp.json()
        assert body["error"]["code"] == "FORBIDDEN_RESOURCE"
        # No data leakage in the error body
        assert "other-user-data" not in str(body)

    def test_list_memory_no_cross_leakage(
        self, client: TestClient, sample_goal_payload: dict, db_session: Session
    ) -> None:
        resp = client.post("/api/v1/goals", json=sample_goal_payload)
        our_goal = UUID(resp.json()["id"])
        other_goal = crud.create_goal(
            db_session, user_id=OTHER_USER_ID, **sample_goal_payload
        )
        crud.create_memory(
            db_session,
            user_id=OTHER_USER_ID,
            goal_id=other_goal.id,
            memory_type=MemoryType.DECISION,
            payload={"leak": "never"},
        )
        crud.create_memory(
            db_session,
            user_id=TEST_USER_ID,
            goal_id=our_goal,
            memory_type=MemoryType.DECISION,
            payload={"ok": True},
        )
        data = client.get(f"/api/v1/memory/{our_goal}").json()
        assert len(data) == 1
        assert data[0]["payload"] == {"ok": True}
