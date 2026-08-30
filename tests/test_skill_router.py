"""Dedicated unit and integration tests for the Skill Router module
and the Planner → Skill Router integration contract (§12 of the Master
Specification).

Tests cover:
  * Skill registry lookup by stable skill_id constants used by Planner.
  * Safe rejection of unknown / unregistered skill IDs.
  * Permission boundaries enforced via available_skill_ids filter.
  * Structured routing result shape (SkillRouterResult, SkillMatch).
  * Direct Planner output → Skill Router resolution for every intent
    blueprint registered in app.agent.planner.
  * Scoring rules: explicit required_skill_id yields score 1.0 when the
    declared intent is supported by the matched skill manifest.

No LLM, no DB, no Android, no real integrations. Uses the default MVP
rule-based Planner + InMemorySkillRegistry + IntentScoringSkillRouter.
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.agent.planner import (
    INTENT_TASK_BLUEPRINT,
    SKILL_ID_CALENDAR,
    SKILL_ID_DOCUMENT,
    SKILL_ID_TASK,
    IntentDrivenPlanner,
    PlannerInput,
    default_planner,
)
from app.agent.schemas import (
    AgentStage,
    ContextRetrievalResult,
    ParsedGoal,
    PlanTask,
    SkillMatch,
    SkillRouterInput,
    SkillRouterResult,
    StructuredPlan,
)
from app.agent.skill_router import (
    InMemorySkillRegistry,
    IntentScoringSkillRouter,
    RegisteredSkill,
    default_skill_registry,
    default_skill_router,
)
from app.enums import CapabilityRoute, Priority

TEST_UID = UUID("00000000-0000-0000-0000-000000000001")
_UNKNOWN_SKILL_ID = UUID("deadbeef-dead-beef-dead-beef00000001")


def _run_async(fn, *args, **kwargs):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(fn(*args, **kwargs))
    finally:
        loop.close()


def _empty_ctx() -> ContextRetrievalResult:
    return ContextRetrievalResult(user_id=TEST_UID, references=[])


def _plan_for_intents(intents: list[str], *, title: str = "Test") -> StructuredPlan:
    """Run the default planner with a single ParsedGoal carrying intents."""
    parsed = ParsedGoal(title=title, description="d", intents=intents, priority=Priority.MEDIUM)
    plan_input = PlannerInput(
        user_id=TEST_UID,
        parsed_goal=parsed,
        context=_empty_ctx(),
        capability_route=CapabilityRoute.LOCAL,
    )
    result = _run_async(default_planner().plan, plan_input)
    return result.plan


class TestInMemorySkillRegistry:
    def test_default_registry_contains_three_stable_skills(self) -> None:
        reg = default_skill_registry()
        all_skills = list(reg.list())
        ids = {s.skill_id for s in all_skills}
        assert SKILL_ID_DOCUMENT in ids
        assert SKILL_ID_TASK in ids
        assert SKILL_ID_CALENDAR in ids

    def test_registry_get_returns_none_for_unknown_id(self) -> None:
        reg = default_skill_registry()
        assert reg.get(_UNKNOWN_SKILL_ID) is None

    def test_document_skill_registers_summarize_and_analyze_intents(self) -> None:
        reg = default_skill_registry()
        doc = reg.get(SKILL_ID_DOCUMENT)
        assert doc is not None
        assert "document.summarize" in doc.supported_intents
        assert "document.analyze" in doc.supported_intents

    def test_task_skill_registers_create_and_list_intents(self) -> None:
        reg = default_skill_registry()
        task = reg.get(SKILL_ID_TASK)
        assert task is not None
        assert "task.create" in task.supported_intents
        assert "task.list" in task.supported_intents

    def test_calendar_skill_registers_read_and_reminder_intents(self) -> None:
        reg = default_skill_registry()
        cal = reg.get(SKILL_ID_CALENDAR)
        assert cal is not None
        assert "calendar.read" in cal.supported_intents
        assert "calendar.create_reminder" in cal.supported_intents

    def test_custom_registry_respects_supplied_skills_only(self) -> None:
        custom_id = uuid4()
        custom = RegisteredSkill(
            skill_id=custom_id,
            name="Custom",
            manifest_version="0.1.0",
            supported_intents=("custom.op",),
            tool_ids=(),
        )
        reg = InMemorySkillRegistry(skills=[custom])
        assert reg.get(custom_id) is not None
        assert reg.get(SKILL_ID_DOCUMENT) is None
        assert len(list(reg.list())) == 1


class TestSkillRouterStructuredResult:
    def _route_plan(self, plan: StructuredPlan, **kwargs: Any) -> SkillRouterResult:
        router_input = SkillRouterInput(
            user_id=TEST_UID,
            plan=plan,
            **kwargs,
        )
        return _run_async(default_skill_router().route, router_input)

    def test_result_stage_marker_is_skill_routing(self) -> None:
        plan = _plan_for_intents(["document.summarize"])
        result = self._route_plan(plan)
        assert result.stage == AgentStage.SKILL_ROUTING

    def test_result_preserves_user_id_and_plan_id(self) -> None:
        plan = _plan_for_intents(["document.summarize"], title="PID check")
        result = self._route_plan(plan)
        assert result.user_id == TEST_UID
        assert result.plan_id == plan.plan_id

    def test_task_matches_keys_match_plan_task_ids(self) -> None:
        plan = _plan_for_intents(["document.summarize", "task.list"])
        result = self._route_plan(plan)
        plan_task_ids = {t.task_id for t in plan.tasks}
        assert set(result.task_matches.keys()) == plan_task_ids
        assert len(result.unmatched_task_ids) == 0

    def test_skill_match_shape_contains_required_fields(self) -> None:
        plan = _plan_for_intents(["document.summarize"])
        result = self._route_plan(plan)
        task_id = plan.tasks[0].task_id
        matches = result.task_matches[task_id]
        assert len(matches) >= 1
        top = matches[0]
        assert isinstance(top, SkillMatch)
        assert isinstance(top.skill_id, UUID)
        assert isinstance(top.skill_name, str) and top.skill_name
        assert isinstance(top.manifest_version, str) and top.manifest_version
        assert isinstance(top.score, float) and 0.0 <= top.score <= 1.0
        assert isinstance(top.matched_intents, list)
        assert isinstance(top.tool_ids, list)

    def test_candidates_sorted_descending_by_score(self) -> None:
        reg = default_skill_registry()
        custom_id = uuid4()
        extra = RegisteredSkill(
            skill_id=custom_id,
            name="Overlap",
            manifest_version="0.0.1",
            supported_intents=("document.summarize", "document.analyze", "other.op"),
            tool_ids=(),
        )
        merged_reg = InMemorySkillRegistry(skills=list(reg.list()) + [extra])
        router = IntentScoringSkillRouter(registry=merged_reg)
        plan = _plan_for_intents(["document.summarize"])
        inp = SkillRouterInput(user_id=TEST_UID, plan=plan)
        result = _run_async(router.route, inp)
        task_id = plan.tasks[0].task_id
        scores = [m.score for m in result.task_matches[task_id]]
        assert scores == sorted(scores, reverse=True)


class TestSkillRouterUnknownSkillRejection:
    def test_task_with_unregistered_required_skill_id_is_unmatched(self) -> None:
        task_id = uuid4()
        bad_task = PlanTask(
            task_id=task_id,
            title="Unknown skill task",
            description="references bogus skill",
            order_index=0,
            depends_on=[],
            required_skill_id=_UNKNOWN_SKILL_ID,
            required_skill_intent="anything.op",
        )
        plan = StructuredPlan(
            plan_id=uuid4(),
            tasks=[bad_task],
            required_skills=[_UNKNOWN_SKILL_ID],
            capability_route=CapabilityRoute.LOCAL,
        )
        inp = SkillRouterInput(user_id=TEST_UID, plan=plan)
        result = _run_async(default_skill_router().route, inp)
        assert task_id in result.unmatched_task_ids
        assert task_id not in result.task_matches

    def test_task_with_unregistered_skill_and_null_intent_stays_unmatched(self) -> None:
        task_id = uuid4()
        bad_task = PlanTask(
            task_id=task_id,
            title="Fully unknown",
            description="no intent either",
            order_index=0,
            depends_on=[],
            required_skill_id=_UNKNOWN_SKILL_ID,
            required_skill_intent=None,
        )
        plan = StructuredPlan(
            plan_id=uuid4(),
            tasks=[bad_task],
            required_skills=[_UNKNOWN_SKILL_ID],
            capability_route=CapabilityRoute.LOCAL,
        )
        inp = SkillRouterInput(user_id=TEST_UID, plan=plan)
        result = _run_async(default_skill_router().route, inp)
        assert task_id in result.unmatched_task_ids
        assert len(result.task_matches) == 0

    def test_unknown_skill_does_not_raise_exceptions(self) -> None:
        bad_task = PlanTask(
            task_id=uuid4(),
            title="Bogus",
            order_index=0,
            required_skill_id=_UNKNOWN_SKILL_ID,
        )
        plan = StructuredPlan(
            plan_id=uuid4(),
            tasks=[bad_task],
            required_skills=[_UNKNOWN_SKILL_ID],
            capability_route=CapabilityRoute.LOCAL,
        )
        inp = SkillRouterInput(user_id=TEST_UID, plan=plan)
        try:
            result = _run_async(default_skill_router().route, inp)
        except Exception as exc:  # noqa: BLE001
            pytest.fail(f"Routing unknown skill must not raise, got: {exc!r}")
        assert isinstance(result, SkillRouterResult)

    def test_mixed_known_and_unknown_tasks_partitioned_correctly(self) -> None:
        known_plan = _plan_for_intents(["document.summarize"])
        known_task = known_plan.tasks[0]
        unknown_task_id = uuid4()
        unknown_task = PlanTask(
            task_id=unknown_task_id,
            title="Unknown skill task",
            order_index=1,
            required_skill_id=_UNKNOWN_SKILL_ID,
            required_skill_intent="nope.op",
            depends_on=[known_task.task_id],
        )
        mixed_plan = StructuredPlan(
            plan_id=known_plan.plan_id,
            tasks=[known_task, unknown_task],
            required_skills=[SKILL_ID_DOCUMENT, _UNKNOWN_SKILL_ID],
            capability_route=CapabilityRoute.LOCAL,
        )
        inp = SkillRouterInput(user_id=TEST_UID, plan=mixed_plan)
        result = _run_async(default_skill_router().route, inp)
        assert known_task.task_id in result.task_matches
        assert unknown_task_id in result.unmatched_task_ids
        assert len(result.task_matches) == 1
        assert len(result.unmatched_task_ids) == 1


class TestSkillRouterPermissionBoundaries:
    def test_available_skill_ids_empty_means_all_registered_are_eligible(self) -> None:
        plan = _plan_for_intents(["document.summarize", "task.create", "calendar.read"])
        inp = SkillRouterInput(user_id=TEST_UID, plan=plan, available_skill_ids=[])
        result = _run_async(default_skill_router().route, inp)
        assert len(result.unmatched_task_ids) == 0
        assert len(result.task_matches) == 3

    def test_restricting_available_skill_ids_excludes_others(self) -> None:
        plan = _plan_for_intents(["document.summarize", "task.create", "calendar.read"])
        inp = SkillRouterInput(
            user_id=TEST_UID,
            plan=plan,
            available_skill_ids=[SKILL_ID_DOCUMENT],
        )
        result = _run_async(default_skill_router().route, inp)
        doc_task_id = next(t.task_id for t in plan.tasks if t.required_skill_id == SKILL_ID_DOCUMENT)
        task_ids = [t.task_id for t in plan.tasks if t.required_skill_id == SKILL_ID_TASK]
        cal_ids = [t.task_id for t in plan.tasks if t.required_skill_id == SKILL_ID_CALENDAR]
        assert doc_task_id in result.task_matches
        for tid in task_ids + cal_ids:
            assert tid in result.unmatched_task_ids
        assert len(result.unmatched_task_ids) == 2

    def test_available_skill_ids_unknown_ids_are_silently_ignored(self) -> None:
        plan = _plan_for_intents(["document.summarize"])
        inp = SkillRouterInput(
            user_id=TEST_UID,
            plan=plan,
            available_skill_ids=[SKILL_ID_DOCUMENT, _UNKNOWN_SKILL_ID],
        )
        result = _run_async(default_skill_router().route, inp)
        assert len(result.unmatched_task_ids) == 0
        task_id = plan.tasks[0].task_id
        matches = result.task_matches[task_id]
        assert all(m.skill_id == SKILL_ID_DOCUMENT for m in matches)

    def test_no_overlap_between_available_and_required_produces_unmatched(self) -> None:
        plan = _plan_for_intents(["task.create"])
        inp = SkillRouterInput(
            user_id=TEST_UID,
            plan=plan,
            available_skill_ids=[SKILL_ID_CALENDAR],
        )
        result = _run_async(default_skill_router().route, inp)
        assert plan.tasks[0].task_id in result.unmatched_task_ids


class TestPlannerToSkillRouterIntegration:
    def test_every_planner_intent_blueprint_resolves_against_registry(self) -> None:
        for intent in INTENT_TASK_BLUEPRINT:
            plan = _plan_for_intents([intent], title=f"intent::{intent}")
            inp = SkillRouterInput(user_id=TEST_UID, plan=plan)
            result = _run_async(default_skill_router().route, inp)
            assert len(result.unmatched_task_ids) == 0, (
                f"Intent '{intent}' from INTENT_TASK_BLUEPRINT did not resolve "
                f"against the skill registry (unmatched={result.unmatched_task_ids})"
            )
            assert len(result.task_matches) == len(plan.tasks)

    def test_planner_stable_skill_ids_are_registry_matches(self) -> None:
        cases = {
            "document.summarize": SKILL_ID_DOCUMENT,
            "document.analyze": SKILL_ID_DOCUMENT,
            "task.create": SKILL_ID_TASK,
            "task.list": SKILL_ID_TASK,
            "calendar.read": SKILL_ID_CALENDAR,
            "calendar.create_reminder": SKILL_ID_CALENDAR,
        }
        for intent, expected_id in cases.items():
            plan = _plan_for_intents([intent])
            inp = SkillRouterInput(user_id=TEST_UID, plan=plan)
            result = _run_async(default_skill_router().route, inp)
            task_id = plan.tasks[0].task_id
            matches = result.task_matches[task_id]
            top_skill = matches[0].skill_id
            assert top_skill == expected_id, (
                f"Intent '{intent}' expected top skill={expected_id} got {top_skill}"
            )

    def test_intent_scoring_exact_match_gets_full_score(self) -> None:
        plan = _plan_for_intents(["document.summarize"])
        inp = SkillRouterInput(user_id=TEST_UID, plan=plan)
        result = _run_async(default_skill_router().route, inp)
        task_id = plan.tasks[0].task_id
        top = result.task_matches[task_id][0]
        assert top.score == 1.0
        assert "document.summarize" in top.matched_intents

    def test_multi_intent_plan_routes_all_tasks_with_no_unmatched(self) -> None:
        intents = ["document.analyze", "task.list", "calendar.create_reminder"]
        plan = _plan_for_intents(intents)
        inp = SkillRouterInput(user_id=TEST_UID, plan=plan)
        result = _run_async(default_skill_router().route, inp)
        assert len(plan.tasks) == len(intents)
        assert len(result.unmatched_task_ids) == 0
        assert len(result.task_matches) == len(intents)
        expected_ids = {SKILL_ID_DOCUMENT, SKILL_ID_TASK, SKILL_ID_CALENDAR}
        actual_ids = {matches[0].skill_id for matches in result.task_matches.values()}
        assert actual_ids == expected_ids

    def test_planner_required_skills_list_matches_router_input(self) -> None:
        """The StructuredPlan.required_skills produced by Planner must be
        exactly the set the Skill Router is expected to resolve."""
        plan = _plan_for_intents(["document.summarize", "calendar.read"])
        required = set(plan.required_skills)
        assert required == {SKILL_ID_DOCUMENT, SKILL_ID_CALENDAR}
        inp = SkillRouterInput(user_id=TEST_UID, plan=plan)
        result = _run_async(default_skill_router().route, inp)
        matched = {matches[0].skill_id for matches in result.task_matches.values()}
        assert matched == required

    def test_unsupported_planner_intent_task_is_unmatched_by_router(self) -> None:
        """When Planner emits a task with no required_skill_id it is
        treated as unsupported — the Skill Router must not fabricate a
        match and should report it as unmatched."""
        parsed = ParsedGoal(
            title="Unsupported blueprint",
            description="xyzzy",
            intents=["this.intent.does.not.exist"],
            priority=Priority.MEDIUM,
        )
        plan_input = PlannerInput(
            user_id=TEST_UID,
            parsed_goal=parsed,
            context=_empty_ctx(),
            capability_route=CapabilityRoute.LOCAL,
        )
        planner_result = _run_async(default_planner().plan, plan_input)
        plan = planner_result.plan
        task = plan.tasks[0]
        assert task.required_skill_id is None
        inp = SkillRouterInput(user_id=TEST_UID, plan=plan)
        result = _run_async(default_skill_router().route, inp)
        assert task.task_id in result.unmatched_task_ids

    def test_planner_task_dependency_order_preserved_through_router(self) -> None:
        plan = _plan_for_intents(["document.summarize", "task.create"])
        first, second = plan.tasks[0], plan.tasks[1]
        assert second.depends_on == [first.task_id]
        inp = SkillRouterInput(user_id=TEST_UID, plan=plan)
        result = _run_async(default_skill_router().route, inp)
        assert first.task_id in result.task_matches
        assert second.task_id in result.task_matches
        matched_ids = list(result.task_matches.keys())
        assert matched_ids.index(first.task_id) < matched_ids.index(second.task_id)

    def test_default_router_and_default_registry_are_stable_factories(self) -> None:
        r1 = default_skill_router()
        r2 = default_skill_router()
        assert r1 is not r2
        plan = _plan_for_intents(["task.list"])
        inp = SkillRouterInput(user_id=TEST_UID, plan=plan)
        out1 = _run_async(r1.route, inp)
        out2 = _run_async(r2.route, inp)
        assert len(out1.task_matches) == len(out2.task_matches) == 1
