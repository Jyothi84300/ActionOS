from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.enums import (
    PermissionLevel,
    SkillCapability,
    SkillStatus,
    ToolCapability,
)
from app.models import Permission, Skill, Tool


USER_ID = UUID("00000000-0000-0000-0000-000000000001")
OTHER_USER_ID = UUID("00000000-0000-0000-0000-000000000002")


def _seed_skill_and_tool(db: Session) -> Tool:
    skill = Skill(
        skill_id=uuid4(),
        name="Task Skill",
        current_version="1.0.0",
        description="Task management",
        status=SkillStatus.ENABLED,
        capability=SkillCapability.LOCAL,
    )
    db.add(skill)
    db.flush()
    tool = Tool(
        id=uuid4(),
        skill_id=skill.skill_id,
        name="create_task",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        permission_level=PermissionLevel.AUTOMATIC,
        capability=ToolCapability.LOCAL,
        enabled=True,
    )
    db.add(tool)
    db.commit()
    return tool


def test_list_permissions_empty(client: TestClient, auth_headers: dict) -> None:
    resp = client.get("/api/v1/permissions", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_permissions_scoped_to_user(
    client: TestClient, auth_headers: dict, db_session: Session
) -> None:
    tool = _seed_skill_and_tool(db_session)
    p1 = Permission(
        id=uuid4(),
        user_id=USER_ID,
        tool_id=tool.id,
        scope=None,
        granted=True,
    )
    p2 = Permission(
        id=uuid4(),
        user_id=OTHER_USER_ID,
        tool_id=tool.id,
        scope=None,
        granted=False,
    )
    db_session.add_all([p1, p2])
    db_session.commit()

    resp = client.get("/api/v1/permissions", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["granted"] is True
    assert body[0]["user_id"] == str(USER_ID)


def test_update_permission_revoke(
    client: TestClient, auth_headers: dict, db_session: Session
) -> None:
    tool = _seed_skill_and_tool(db_session)
    perm_id = uuid4()
    perm = Permission(
        id=perm_id,
        user_id=USER_ID,
        tool_id=tool.id,
        scope=None,
        granted=True,
    )
    db_session.add(perm)
    db_session.commit()

    resp = client.put(
        f"/api/v1/permissions/{perm_id}",
        json={"granted": False},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == str(perm_id)
    assert body["granted"] is False
    assert body["revoked_at"] is not None
    assert body["granted_at"] is None


def test_update_permission_grant(
    client: TestClient, auth_headers: dict, db_session: Session
) -> None:
    tool = _seed_skill_and_tool(db_session)
    perm_id = uuid4()
    perm = Permission(
        id=perm_id,
        user_id=USER_ID,
        tool_id=tool.id,
        scope=None,
        granted=False,
    )
    db_session.add(perm)
    db_session.commit()

    resp = client.put(
        f"/api/v1/permissions/{perm_id}",
        json={"granted": True},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["granted"] is True
    assert body["granted_at"] is not None
    assert body["revoked_at"] is None


def test_update_permission_not_found(client: TestClient, auth_headers: dict) -> None:
    resp = client.put(
        f"/api/v1/permissions/{uuid4()}",
        json={"granted": True},
        headers=auth_headers,
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "PERMISSION_NOT_FOUND"


def test_update_permission_forbidden_other_user(
    client: TestClient, auth_headers: dict, db_session: Session
) -> None:
    tool = _seed_skill_and_tool(db_session)
    perm_id = uuid4()
    perm = Permission(
        id=perm_id,
        user_id=OTHER_USER_ID,
        tool_id=tool.id,
        granted=False,
    )
    db_session.add(perm)
    db_session.commit()

    resp = client.put(
        f"/api/v1/permissions/{perm_id}",
        json={"granted": True},
        headers=auth_headers,
    )
    assert resp.status_code == 403
