from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.enums import ActionState, CapabilityRoute, GoalStatus
from app.models import Goal, Task


GOOD_GOAL_UUID = "11111111-1111-1111-1111-111111111111"


def test_create_goal_success(client: TestClient, auth_headers: dict, sample_goal_payload: dict) -> None:
    resp = client.post("/api/v1/goals", json=sample_goal_payload, headers=auth_headers)
    assert resp.status_code == 201
    body = resp.json()
    assert UUID(body["id"])
    assert body["status"] == GoalStatus.ACTIVE.value
    assert body["created_at"]


def test_create_goal_validation_error_missing_title_uses_standard_envelope(
    client: TestClient, auth_headers: dict
) -> None:
    resp = client.post("/api/v1/goals", json={}, headers=auth_headers)
    assert resp.status_code == 422
    body = resp.json()

    assert "error" in body
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert isinstance(body["error"]["message"], str) and body["error"]["message"]
    assert isinstance(body["error"]["details"], dict)
    assert body["error"]["request_id"]

    field_errors = body["error"]["details"]["field_errors"]
    assert len(field_errors) >= 1
    missing_title = next((e for e in field_errors if e["field"] == "title"), None)
    assert missing_title is not None
    assert missing_title["type"] == "missing"
    assert "title" in missing_title["message"].lower() or "required" in missing_title["message"].lower()


def test_create_goal_validation_error_wrong_priority_and_long_title(
    client: TestClient, auth_headers: dict
) -> None:
    payload = {
        "title": "x" * 500,
        "priority": "not_a_valid_priority",
    }
    resp = client.post("/api/v1/goals", json=payload, headers=auth_headers)
    assert resp.status_code == 422
    body = resp.json()

    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["request_id"]
    assert isinstance(body["error"]["details"]["field_errors"], list)
    assert len(body["error"]["details"]["field_errors"]) >= 2

    fields_present = {e["field"] for e in body["error"]["details"]["field_errors"]}
    assert "title" in fields_present
    assert "priority" in fields_present


def test_create_goal_validation_error_no_stack_trace_in_body(
    client: TestClient, auth_headers: dict
) -> None:
    import json

    resp = client.post("/api/v1/goals", json={"title": 12345, "priority": "bogus"}, headers=auth_headers)
    raw = resp.content.decode("utf-8")
    parsed = json.loads(raw)

    assert "traceback" not in raw.lower()
    assert "stack" not in raw.lower()
    assert "line " not in raw.lower()
    assert resp.status_code == 422
    assert parsed["error"]["code"] == "VALIDATION_ERROR"


def test_get_goal_success(
    client: TestClient, auth_headers: dict, db_session: Session, sample_goal_payload: dict
) -> None:
    goal = Goal(
        id=UUID(GOOD_GOAL_UUID),
        user_id=UUID("00000000-0000-0000-0000-000000000001"),
        title=sample_goal_payload["title"],
        description=sample_goal_payload["description"],
        objective=sample_goal_payload["objective"],
        priority=sample_goal_payload["priority"],
        category=sample_goal_payload["category"],
        constraints=sample_goal_payload["constraints"],
        status=GoalStatus.ACTIVE,
    )
    db_session.add(goal)
    db_session.commit()

    resp = client.get(f"/api/v1/goals/{GOOD_GOAL_UUID}", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == GOOD_GOAL_UUID
    assert body["title"] == sample_goal_payload["title"]
    assert body["status"] == GoalStatus.ACTIVE.value
    assert body["category"] == "academic"


def test_get_goal_not_found(client: TestClient, auth_headers: dict) -> None:
    missing = uuid4()
    resp = client.get(f"/api/v1/goals/{missing}", headers=auth_headers)
    assert resp.status_code == 404
    body = resp.json()
    assert body["error"]["code"] == "GOAL_NOT_FOUND"
    assert body["error"]["request_id"]


def test_get_goal_forbidden_wrong_user(
    client: TestClient, auth_headers: dict, db_session: Session
) -> None:
    goal = Goal(
        id=uuid4(),
        user_id=UUID("00000000-0000-0000-0000-000000000002"),
        title="Someone else's goal",
        description="desc",
        objective="obj",
        status=GoalStatus.ACTIVE,
    )
    db_session.add(goal)
    db_session.commit()

    resp = client.get(f"/api/v1/goals/{goal.id}", headers=auth_headers)
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN_RESOURCE"


def test_list_goal_tasks_empty(
    client: TestClient, auth_headers: dict, db_session: Session
) -> None:
    goal = Goal(
        id=uuid4(),
        user_id=UUID("00000000-0000-0000-0000-000000000001"),
        title="T",
        description="",
        objective="",
        status=GoalStatus.ACTIVE,
    )
    db_session.add(goal)
    db_session.commit()

    resp = client.get(f"/api/v1/goals/{goal.id}/tasks", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_goal_tasks_ordered(
    client: TestClient, auth_headers: dict, db_session: Session
) -> None:
    goal = Goal(
        id=uuid4(),
        user_id=UUID("00000000-0000-0000-0000-000000000001"),
        title="T",
        description="",
        objective="",
        status=GoalStatus.ACTIVE,
    )
    db_session.add(goal)
    db_session.flush()

    t2 = Task(
        id=uuid4(),
        goal_id=goal.id,
        title="Second",
        order_index=2,
        status=ActionState.PENDING,
        capability_route=CapabilityRoute.LOCAL,
    )
    t1 = Task(
        id=uuid4(),
        goal_id=goal.id,
        title="First",
        order_index=1,
        status=ActionState.PENDING,
        capability_route=CapabilityRoute.LOCAL,
    )
    db_session.add_all([t1, t2])
    db_session.commit()

    resp = client.get(f"/api/v1/goals/{goal.id}/tasks", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert [t["title"] for t in body] == ["First", "Second"]
    for t in body:
        assert t["capability_route"] == CapabilityRoute.LOCAL.value


def test_list_goal_tasks_not_found(
    client: TestClient, auth_headers: dict
) -> None:
    resp = client.get(f"/api/v1/goals/{uuid4()}/tasks", headers=auth_headers)
    assert resp.status_code == 404


def _intent_goal_payload(intent_keyword: str) -> dict:
    return {
        "title": f"{intent_keyword} about my research paper",
        "description": f"Please {intent_keyword} the draft research paper attached.",
        "objective": f"Completed {intent_keyword} output saved.",
        "priority": "medium",
        "category": "academic",
        "constraints": [],
    }


def test_plan_goal_success(
    client: TestClient, auth_headers: dict, db_session: Session
) -> None:
    create_resp = client.post(
        "/api/v1/goals",
        json=_intent_goal_payload("remind me tomorrow to review"),
        headers=auth_headers,
    )
    assert create_resp.status_code == 201
    goal_id = create_resp.json()["id"]

    plan_resp = client.post(f"/api/v1/goals/{goal_id}/plan", headers=auth_headers)
    assert plan_resp.status_code == 200, plan_resp.content.decode("utf-8")
    body = plan_resp.json()

    assert UUID(body["plan_id"])
    assert isinstance(body["tasks"], list) and len(body["tasks"]) >= 1
    assert body["permission_level"] in {
        "AUTOMATIC",
        "CONFIRMATION_REQUIRED",
        "BLOCKED",
    }

    seen_order: set[int] = set()
    for task in body["tasks"]:
        assert UUID(task["id"])
        assert isinstance(task["title"], str) and len(task["title"]) > 0
        assert isinstance(task["order_index"], int) and task["order_index"] >= 0
        assert task["capability_route"] in {"local", "online", "partial"}
        seen_order.add(task["order_index"])
    assert len(seen_order) == len(body["tasks"])

    tasks_after = db_session.query(Task).filter(Task.goal_id == UUID(goal_id)).all()
    assert len(tasks_after) == len(body["tasks"])


def test_plan_goal_already_exists_409(
    client: TestClient, auth_headers: dict
) -> None:
    create_resp = client.post(
        "/api/v1/goals",
        json=_intent_goal_payload("create task to summarize the report"),
        headers=auth_headers,
    )
    assert create_resp.status_code == 201
    goal_id = create_resp.json()["id"]

    first = client.post(f"/api/v1/goals/{goal_id}/plan", headers=auth_headers)
    assert first.status_code == 200

    second = client.post(f"/api/v1/goals/{goal_id}/plan", headers=auth_headers)
    assert second.status_code == 409
    body = second.json()
    assert body["error"]["code"] == "PLAN_ALREADY_EXISTS"
    assert body["error"]["request_id"]
    assert "force=true" in body["error"]["message"]


def test_plan_goal_force_replace(
    client: TestClient, auth_headers: dict, db_session: Session
) -> None:
    create_resp = client.post(
        "/api/v1/goals",
        json=_intent_goal_payload("list tasks for my upcoming calendar"),
        headers=auth_headers,
    )
    assert create_resp.status_code == 201
    goal_id = create_resp.json()["id"]

    first = client.post(f"/api/v1/goals/{goal_id}/plan", headers=auth_headers)
    assert first.status_code == 200
    first_task_ids = {t["id"] for t in first.json()["tasks"]}
    assert len(first_task_ids) >= 1

    second = client.post(
        f"/api/v1/goals/{goal_id}/plan?force=true",
        headers=auth_headers,
    )
    assert second.status_code == 200
    second_body = second.json()
    assert len(second_body["tasks"]) >= 1
    second_task_ids = {t["id"] for t in second_body["tasks"]}

    remaining = (
        db_session.query(Task)
        .filter(Task.goal_id == UUID(goal_id))
        .all()
    )
    remaining_ids = {str(t.id) for t in remaining}
    assert remaining_ids == second_task_ids


def test_plan_goal_not_found(
    client: TestClient, auth_headers: dict
) -> None:
    resp = client.post(f"/api/v1/goals/{uuid4()}/plan", headers=auth_headers)
    assert resp.status_code == 404
    body = resp.json()
    assert body["error"]["code"] == "GOAL_NOT_FOUND"
    assert body["error"]["request_id"]


def test_plan_goal_forbidden_wrong_user(
    client: TestClient, auth_headers: dict, db_session: Session
) -> None:
    other_goal = Goal(
        id=uuid4(),
        user_id=UUID("00000000-0000-0000-0000-000000000002"),
        title="Summarize document — another user's goal",
        description="desc",
        objective="obj",
        status=GoalStatus.ACTIVE,
    )
    db_session.add(other_goal)
    db_session.commit()

    resp = client.post(
        f"/api/v1/goals/{other_goal.id}/plan",
        headers=auth_headers,
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN_RESOURCE"
