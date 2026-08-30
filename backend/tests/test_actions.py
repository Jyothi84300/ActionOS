from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.enums import ActionState, CapabilityRoute, GoalStatus, VerificationResult
from app.models import Action, Goal, Skill, Task, Verification


def _make_action(db: Session, *, user_id: UUID, state: ActionState = ActionState.COMPLETED) -> Action:
    goal = Goal(
        id=uuid4(),
        user_id=user_id,
        title="Goal",
        description="",
        objective="",
        status=GoalStatus.ACTIVE,
    )
    db.add(goal)
    db.flush()
    task = Task(
        id=uuid4(),
        goal_id=goal.id,
        title="Task",
        order_index=0,
        capability_route=CapabilityRoute.LOCAL,
        status=state,
    )
    db.add(task)
    db.flush()
    action = Action(
        id=uuid4(),
        task_id=task.id,
        input_payload={},
        state=state,
    )
    db.add(action)
    db.commit()
    return action


def test_get_action_pending_no_verification(
    client: TestClient, auth_headers: dict, db_session: Session
) -> None:
    user_id = UUID("00000000-0000-0000-0000-000000000001")
    action = _make_action(db_session, user_id=user_id, state=ActionState.PENDING)

    resp = client.get(f"/api/v1/actions/{action.id}", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == str(action.id)
    assert body["state"] == ActionState.PENDING.value
    assert body["verification"] is None


def test_get_action_with_verification(
    client: TestClient, auth_headers: dict, db_session: Session
) -> None:
    user_id = UUID("00000000-0000-0000-0000-000000000001")
    action = _make_action(db_session, user_id=user_id, state=ActionState.COMPLETED)
    verified_at = datetime(2026, 8, 28, 10, 5, 0, tzinfo=timezone.utc)
    verification = Verification(
        id=uuid4(),
        action_id=action.id,
        method="independent_read",
        result=VerificationResult.VERIFIED,
        observed_state={"status": "exists"},
        verified_at=verified_at,
    )
    db_session.add(verification)
    db_session.commit()

    resp = client.get(f"/api/v1/actions/{action.id}", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["state"] == ActionState.COMPLETED.value
    assert body["verification"] is not None
    assert body["verification"]["result"] == VerificationResult.VERIFIED.value
    assert "verified_at" in body["verification"]


def test_get_action_unverified(
    client: TestClient, auth_headers: dict, db_session: Session
) -> None:
    user_id = UUID("00000000-0000-0000-0000-000000000001")
    action = _make_action(db_session, user_id=user_id, state=ActionState.UNVERIFIED)
    verification = Verification(
        id=uuid4(),
        action_id=action.id,
        method=None,
        result=VerificationResult.UNVERIFIED,
        observed_state=None,
    )
    db_session.add(verification)
    db_session.commit()

    resp = client.get(f"/api/v1/actions/{action.id}", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["state"] == ActionState.UNVERIFIED.value
    assert body["verification"]["result"] == VerificationResult.UNVERIFIED.value


def test_get_action_not_found(client: TestClient, auth_headers: dict) -> None:
    resp = client.get(f"/api/v1/actions/{uuid4()}", headers=auth_headers)
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "ACTION_NOT_FOUND"


def test_get_action_forbidden_other_user(
    client: TestClient, auth_headers: dict, db_session: Session
) -> None:
    other_user = UUID("00000000-0000-0000-0000-000000000002")
    action = _make_action(db_session, user_id=other_user)
    resp = client.get(f"/api/v1/actions/{action.id}", headers=auth_headers)
    assert resp.status_code == 403


def _make_task(
    db: Session,
    *,
    user_id: UUID,
    task_status: ActionState = ActionState.PENDING,
) -> Task:
    goal = Goal(
        id=uuid4(),
        user_id=user_id,
        title="Execute test goal",
        description="",
        objective="",
        status=GoalStatus.ACTIVE,
    )
    db.add(goal)
    db.flush()
    task = Task(
        id=uuid4(),
        goal_id=goal.id,
        title="Execute test task",
        order_index=0,
        capability_route=CapabilityRoute.LOCAL,
        status=task_status,
    )
    db.add(task)
    db.commit()
    return task


def test_execute_task_success(
    client: TestClient, auth_headers: dict, db_session: Session
) -> None:
    user_id = UUID("00000000-0000-0000-0000-000000000001")
    task = _make_task(db_session, user_id=user_id, task_status=ActionState.PENDING)

    resp = client.post(f"/api/v1/tasks/{task.id}/execute", headers=auth_headers)
    assert resp.status_code == 202
    body = resp.json()
    assert UUID(body["action_id"])
    assert body["state"] == ActionState.PENDING.value

    db_session.refresh(task)
    assert task.status == ActionState.RUNNING

    action_resp = client.get(f"/api/v1/actions/{body['action_id']}", headers=auth_headers)
    assert action_resp.status_code == 200
    assert action_resp.json()["state"] == ActionState.PENDING.value


def test_execute_task_409_running(
    client: TestClient, auth_headers: dict, db_session: Session
) -> None:
    user_id = UUID("00000000-0000-0000-0000-000000000001")
    task = _make_task(db_session, user_id=user_id, task_status=ActionState.RUNNING)

    resp = client.post(f"/api/v1/tasks/{task.id}/execute", headers=auth_headers)
    assert resp.status_code == 409
    err = resp.json()["error"]
    assert err["code"] == "TASK_NOT_ELIGIBLE"
    assert err["details"]["current_state"] == ActionState.RUNNING.value


def test_execute_task_409_completed(
    client: TestClient, auth_headers: dict, db_session: Session
) -> None:
    user_id = UUID("00000000-0000-0000-0000-000000000001")
    task = _make_task(db_session, user_id=user_id, task_status=ActionState.COMPLETED)

    resp = client.post(f"/api/v1/tasks/{task.id}/execute", headers=auth_headers)
    assert resp.status_code == 409
    err = resp.json()["error"]
    assert err["code"] == "TASK_NOT_ELIGIBLE"
    assert err["details"]["current_state"] == ActionState.COMPLETED.value


def test_execute_task_404(
    client: TestClient, auth_headers: dict
) -> None:
    missing = uuid4()
    resp = client.post(f"/api/v1/tasks/{missing}/execute", headers=auth_headers)
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "TASK_NOT_FOUND"


def test_execute_task_403_wrong_user(
    client: TestClient, auth_headers: dict, db_session: Session
) -> None:
    other_user = UUID("00000000-0000-0000-0000-000000000002")
    task = _make_task(db_session, user_id=other_user, task_status=ActionState.PENDING)

    resp = client.post(f"/api/v1/tasks/{task.id}/execute", headers=auth_headers)
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN_RESOURCE"
