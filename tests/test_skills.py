from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.enums import SkillCapability, SkillStatus
from app.models import Skill, SkillVersion


def test_list_skills_empty(client: TestClient, auth_headers: dict) -> None:
    resp = client.get("/api/v1/skills", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_skills_returns_summaries(
    client: TestClient, auth_headers: dict, db_session: Session
) -> None:
    s1_id, s2_id = uuid4(), uuid4()
    s1 = Skill(
        skill_id=s1_id,
        name="Document Skill",
        current_version="1.0.0",
        description="Read and analyze documents",
        status=SkillStatus.ENABLED,
        capability=SkillCapability.BOTH,
    )
    s2 = Skill(
        skill_id=s2_id,
        name="Calendar Skill",
        current_version="0.2.1",
        description="Calendar access",
        status=SkillStatus.ENABLED,
        capability=SkillCapability.LOCAL,
    )
    v1 = SkillVersion(
        id=uuid4(),
        skill_id=s1_id,
        version="1.0.0",
        manifest={"tools": []},
    )
    db_session.add_all([s1, s2, v1])
    db_session.commit()

    resp = client.get("/api/v1/skills", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    assert body[0]["name"] == "Calendar Skill"
    assert body[0]["skill_id"] == str(s2_id)
    assert body[0]["current_version"] == "0.2.1"
    assert body[0]["capability"] == SkillCapability.LOCAL.value
    assert body[1]["name"] == "Document Skill"
    assert body[1]["capability"] == SkillCapability.BOTH.value
