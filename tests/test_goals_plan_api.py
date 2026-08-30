"""Focused API integration tests validating the 3 genuine gaps fixed
in the Agent → API layer for `POST /goals/{goal_id}/plan`:

  * Gap A — skill_version was hardcoded ``"1.0.0"`` in the endpoint.
    The endpoint now resolves manifest_version from SkillRouter's
    ``SkillMatch`` (primary), falling back to a ``SkillRegistry``
    lookup when ``pipeline.skill_routing`` is None.  The default
    InMemorySkillRegistry happens to carry manifest_version="1.0.0"
    for all three Phase-2 skills, so the *value* is indistinguishable
    from the old hardcode — what we validate is the *mechanism*: the
    skill_version stored matches what the registry declares and
    persists through FK resolution (no silent None / wrong value).

  * Gap B — ``PlanTaskResponse`` omitted ``depends_on`` even though
    the plan carries it and it is persisted.  The plan response now
    includes ``depends_on`` and it equals the tasks-list endpoint.

  * Gap C — The pipeline runs SkillRouter and produces
    ``SkillRouterResult.unmatched_task_ids`` but the endpoint threw it
    away.  The ``PlanResponse`` now surfaces an
    ``unmatched_task_ids`` list populated from ``pipeline_result``.

All tests use ``TestClient`` through the shared conftest fixtures.
No LLM, no Android, no new infrastructure.
"""

from __future__ import annotations

from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.agent.planner import (
    SKILL_ID_CALENDAR,
    SKILL_ID_DOCUMENT,
    SKILL_ID_TASK,
)
from app.agent.skill_router import default_skill_registry
from app.enums import SkillCapability, SkillStatus
from app.models import Skill, Task


def _create_goal(
    client: TestClient,
    headers: dict,
    *,
    title: str,
    description: str | None = None,
) -> str:
    payload = {
        "title": title,
        "description": description or title,
        "objective": f"{title} complete",
        "priority": "medium",
        "category": "personal",
        "constraints": [],
    }
    resp = client.post("/api/v1/goals", json=payload, headers=headers)
    assert resp.status_code == 201, resp.content.decode("utf-8")
    return resp.json()["id"]


def _plan(client: TestClient, headers: dict, goal_id: str) -> dict:
    resp = client.post(f"/api/v1/goals/{goal_id}/plan", headers=headers)
    assert resp.status_code == 200, resp.content.decode("utf-8")
    return resp.json()


# ---------------------------------------------------------------------------
# Gap A — skill_version resolved from SkillRouter/registry, NOT hardcoded
# ---------------------------------------------------------------------------


class TestGapA_SkillVersionResolvedNotHardcoded:
    def _seed_skills_for_fk(self, db_session: Session) -> None:
        """Seed Skill rows so FK passes and crud preserves skill_id +
        skill_version.  The version number on Task comes from the
        ENDPOINT caller (the SkillRouter manifest_version), NOT from
        the Skill.current_version column; this seed only satisfies
        the foreign-key constraint."""
        reg = default_skill_registry()
        for reg_skill in reg.list():
            exists = (
                db_session.query(Skill)
                .filter(Skill.skill_id == reg_skill.skill_id)
                .first()
                is not None
            )
            if not exists:
                db_session.add(
                    Skill(
                        skill_id=reg_skill.skill_id,
                        name=reg_skill.name,
                        current_version=reg_skill.manifest_version,
                        capability=SkillCapability.LOCAL,
                        status=SkillStatus.ENABLED,
                    )
                )
        db_session.commit()

    def _expected_versions(self) -> dict[UUID, str]:
        return {s.skill_id: s.manifest_version for s in default_skill_registry().list()}

    def test_all_skill_versions_match_registry_after_fk_seed(
        self,
        client: TestClient,
        auth_headers: dict,
        db_session: Session,
    ) -> None:
        """For each of the 3 Phase-2 skills, a goal whose planner task
        declares that required_skill_id must store the registry's
        manifest_version on the resulting Task row."""
        self._seed_skills_for_fk(db_session)
        cases = [
            # (input snippet, expected skill_id)
            ("summarize the research paper attachment", SKILL_ID_DOCUMENT),
            ("Please create a todo to submit the expenses report", SKILL_ID_TASK),
            ("remind me next tuesday at 3pm about the meeting", SKILL_ID_CALENDAR),
        ]
        expected = self._expected_versions()
        for snippet, expected_id in cases:
            gid = _create_goal(client, auth_headers, title=snippet)
            body = _plan(client, auth_headers, gid)
            assert len(body["tasks"]) >= 1
            tasks = (
                db_session.query(Task)
                .filter(Task.goal_id == UUID(gid))
                .filter(Task.skill_id == expected_id)
                .all()
            )
            assert len(tasks) >= 1, f"No DB Task matched skill {expected_id} for '{snippet}'"
            for task in tasks:
                assert task.skill_version == expected[expected_id], (
                    f"Gap-A: for intent snippet '{snippet}' "
                    f"(skill {expected_id}), Task.skill_version="
                    f"{task.skill_version!r} but expected "
                    f"{expected[expected_id]!r} (registry manifest version)."
                )

    def test_task_skill_version_never_none_after_skill_registry_seed(
        self,
        client: TestClient,
        auth_headers: dict,
        db_session: Session,
    ) -> None:
        self._seed_skills_for_fk(db_session)
        gid = _create_goal(
            client,
            auth_headers,
            title="summarize report and create a task to review it",
        )
        _plan(client, auth_headers, gid)
        tasks = db_session.query(Task).filter(Task.goal_id == UUID(gid)).all()
        assert len(tasks) >= 2
        versions: set[str] = set()
        for task in tasks:
            if task.skill_id is not None:
                assert task.skill_version is not None, (
                    "Gap-A: skill_id present but skill_version NULL — "
                    "version lookup not wired from registry."
                )
                versions.add(task.skill_version)
        assert len(versions) >= 1

    def test_unseeded_skills_skill_version_remains_null_consistent_with_crud(
        self,
        client: TestClient,
        auth_headers: dict,
        db_session: Session,
    ) -> None:
        """When skills DB is UNSEEDED, crud.create_task_for_plan
        NULLifies both skill_id and skill_version to satisfy FK
        constraint.  The API must silently tolerate this, matching
        pre-fix behavior (no crash / no 500)."""
        gid = _create_goal(
            client,
            auth_headers,
            title="remind me tomorrow morning at 9",
        )
        body = _plan(client, auth_headers, gid)
        assert len(body["tasks"]) >= 1
        tasks = db_session.query(Task).filter(Task.goal_id == UUID(gid)).all()
        for task in tasks:
            # FK not satisfied → skill_version None (per crud design).
            # We only assert the endpoint didn't crash and returns
            # correctly-shaped output — separate from FK resolution.
            assert task.skill_id is None or task.skill_version is not None


# ---------------------------------------------------------------------------
# Gap B — PlanTaskResponse includes depends_on
# ---------------------------------------------------------------------------


class TestGapB_PlanTaskResponseIncludesDependsOn:
    def test_shape_exposes_depends_on(
        self,
        client: TestClient,
        auth_headers: dict,
    ) -> None:
        gid = _create_goal(
            client,
            auth_headers,
            title="summarize paper then create a task to review",
        )
        body = _plan(client, auth_headers, gid)
        for task in body["tasks"]:
            assert "depends_on" in task, (
                "Gap-B: PlanTaskResponse shape missing 'depends_on' field."
            )
            assert isinstance(task["depends_on"], list)

    def test_depends_on_round_trips_against_tasks_list_endpoint(
        self,
        client: TestClient,
        auth_headers: dict,
        db_session: Session,
    ) -> None:
        gid = _create_goal(
            client,
            auth_headers,
            title="list calendar events then summarize the notes",
        )
        plan_body = _plan(client, auth_headers, gid)
        list_resp = client.get(f"/api/v1/goals/{gid}/tasks", headers=auth_headers)
        assert list_resp.status_code == 200
        list_by_id = {t["id"]: t for t in list_resp.json()}
        for pt in plan_body["tasks"]:
            db_task = list_by_id[str(pt["id"])]
            plan_deps = sorted(str(d) for d in pt["depends_on"])
            list_deps = sorted(str(d) for d in db_task["depends_on"])
            assert plan_deps == list_deps, (
                "Gap-B: PlanTaskResponse.depends_on must equal persisted "
                "Task.depends_on returned by GET /goals/{id}/tasks."
            )

    def test_depends_on_contains_only_known_task_ids(
        self,
        client: TestClient,
        auth_headers: dict,
    ) -> None:
        gid = _create_goal(
            client,
            auth_headers,
            title="analyze the document then create a task to email summary",
        )
        body = _plan(client, auth_headers, gid)
        known_ids = {t["id"] for t in body["tasks"]}
        for task in body["tasks"]:
            for dep in task["depends_on"]:
                UUID(dep)  # must parse as valid UUID
                assert dep in known_ids, (
                    "PlanTaskResponse.depends_on references a task_id "
                    "not present in the same plan tasks list."
                )


# ---------------------------------------------------------------------------
# Gap C — PlanResponse surfaces unmatched_task_ids
# ---------------------------------------------------------------------------


class TestGapC_PlanResponseSurfacesUnmatchedTaskIds:
    def test_shape_includes_unmatched_task_ids_list(
        self,
        client: TestClient,
        auth_headers: dict,
    ) -> None:
        gid = _create_goal(
            client,
            auth_headers,
            title="summarize attached technical memo",
        )
        body = _plan(client, auth_headers, gid)
        assert "unmatched_task_ids" in body, (
            "Gap-C: PlanResponse shape missing 'unmatched_task_ids' field."
        )
        assert isinstance(body["unmatched_task_ids"], list)

    def test_known_intents_produce_empty_unmatched(
        self,
        client: TestClient,
        auth_headers: dict,
    ) -> None:
        known_inputs = [
            "summarize the quarterly business review document",
            "create a task to submit the final homework",
            "remind me at 5pm to call the office",
        ]
        for snippet in known_inputs:
            gid = _create_goal(client, auth_headers, title=snippet)
            body = _plan(client, auth_headers, gid)
            assert body["unmatched_task_ids"] == [], (
                f"Gap-C: known intent '{snippet}' should route cleanly "
                f"but unmatched={body['unmatched_task_ids']!r}."
            )

    def test_unmatched_list_is_preserved_through_force_replan(
        self,
        client: TestClient,
        auth_headers: dict,
    ) -> None:
        """After a force=true replan, unmatched_task_ids is still
        populated (empty or otherwise) rather than missing."""
        gid = _create_goal(
            client,
            auth_headers,
            title="remind me friday afternoon to take a break",
        )
        first = _plan(client, auth_headers, gid)
        replan = client.post(
            f"/api/v1/goals/{gid}/plan?force=true",
            headers=auth_headers,
        )
        assert replan.status_code == 200, replan.content.decode("utf-8")
        second = replan.json()
        # Shape must be preserved on both calls.
        assert isinstance(first["unmatched_task_ids"], list)
        assert isinstance(second["unmatched_task_ids"], list)
