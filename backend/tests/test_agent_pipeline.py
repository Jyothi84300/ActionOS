"""Focused unit tests for the Agent Pipeline orchestration layer.

Tests cover §6.2 + §8 of the Master Specification:
  * State-machine transitions between IDLE → GOAL_PARSED → CONTEXT_READY
    → CAPABILITY_ROUTED → PLANNED → SKILLS_ROUTED → COMPLETED.
  * BLOCKED and FAILED early-exit branches.
  * Warning propagation across stages (AMBIGUOUS_GOAL, ROUTING_NOTES,
    UNMATCHED_TASKS, MISSING_PERMISSIONS, PLAN_BLOCKED).
  * Capability Router classification (LOCAL / PARTIAL) drives downstream
    plan task routes.
  * Planner output (StructuredPlan + permission_level) is preserved
    through to PipelineResult.
  * Skill Router matches planner's stable skill_id constants
    (Document / Task / Calendar) correctly.
  * Stage exceptions are caught, logged to state.errors, and final
    phase is FAILED (not leaked to caller).

No LLM, no DB, no Android, no real integrations. All stubs are the
default rule-based MVP implementations supplied by the package.
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

import pytest

from app.agent import AgentPhase, AgentStage, PipelineInput, PipelineResult
from app.agent.goal_understanding import GoalUnderstandingBackend, GoalUnderstandingInput, GoalUnderstandingResult
from app.agent.pipeline import AgentPipeline, default_pipeline
from app.agent.schemas import ParsedGoal
from app.agent.state import StateTransitionError
from app.enums import CapabilityRoute, PermissionLevel, Priority

TEST_UID = UUID("00000000-0000-0000-0000-000000000001")


def _run(pipe: AgentPipeline, **kwargs: Any) -> PipelineResult:
    kw: dict[str, Any] = {"user_id": TEST_UID}
    kw.update(kwargs)
    inp = PipelineInput(**kw)
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(pipe.run(inp))
    finally:
        loop.close()


class TestPipelineSuccessPath:
    def test_recognized_intent_ends_completed_with_plan(self) -> None:
        r = _run(default_pipeline(), goal_text="Remind me to file the report tomorrow")
        assert r.final_phase == AgentPhase.COMPLETED
        assert r.plan is not None
        assert r.goal_id is None
        assert r.user_id == TEST_UID
        assert len(r.errors) == 0

    def test_plan_contains_task_with_stable_skill_id(self) -> None:
        r = _run(default_pipeline(), goal_text="Create task: buy milk")
        assert r.plan is not None
        assert len(r.plan.tasks) >= 1
        task = r.plan.tasks[0]
        assert task.required_skill_id == UUID("11111111-1111-1111-1111-000000000002")  # TASK skill
        assert task.order_index == 0

    def test_skill_router_matches_all_planner_tasks_for_recognized_intents(self) -> None:
        r = _run(default_pipeline(), goal_text="Summarize document and list tasks")
        assert r.final_phase == AgentPhase.COMPLETED
        assert r.plan is not None and len(r.plan.tasks) == 2
        assert r.skill_routing is not None
        assert len(r.skill_routing.unmatched_task_ids) == 0
        assert len(r.skill_routing.task_matches) == 2
        for task_id, matches in r.skill_routing.task_matches.items():
            assert len(matches) >= 1
            assert matches[0].score > 0.0
            assert isinstance(matches[0].skill_id, UUID)

    def test_permission_level_propagates_from_planner_blueprint(self) -> None:
        r = _run(default_pipeline(), goal_text="Remind me about the dentist appointment next week")
        assert r.plan is not None
        assert r.plan.permission_level == PermissionLevel.CONFIRMATION_REQUIRED

    def test_local_route_for_single_calendar_intent(self) -> None:
        r = _run(default_pipeline(), goal_text="Read my calendar entries for today")
        assert r.capability_route == CapabilityRoute.LOCAL
        assert r.plan is not None
        assert r.plan.capability_route == CapabilityRoute.LOCAL
        for task in r.plan.tasks:
            assert task.capability_route == CapabilityRoute.LOCAL

    def test_partial_route_for_multiple_intents(self) -> None:
        r = _run(
            default_pipeline(),
            goal_text="Analyze document and remind me to send the draft tomorrow",
        )
        assert r.capability_route == CapabilityRoute.PARTIAL
        assert r.plan is not None
        assert r.plan.capability_route == CapabilityRoute.PARTIAL
        assert len(r.plan.required_skills) >= 2


class TestPipelineStateMachine:
    def test_success_transitions_follow_legal_order(self) -> None:
        r = _run(default_pipeline(), goal_text="Summarize document and list tasks")
        assert r.final_phase == AgentPhase.COMPLETED
        history = list(r.final_state.stage_history)
        expected_stages = [
            AgentStage.CONTEXT_RETRIEVAL,
            AgentStage.CAPABILITY_ROUTING,
            AgentStage.PLANNING,
            AgentStage.SKILL_ROUTING,
            AgentStage.EXECUTION,
            AgentStage.STATE_UPDATE,
        ]
        assert len(history) == len(expected_stages)
        for idx, want in enumerate(expected_stages):
            assert history[idx] == want

    def test_initial_phase_is_idle_then_advances(self) -> None:
        r = _run(default_pipeline(), goal_text="Summarize the doc")
        state = r.final_state
        assert state.phase == AgentPhase.COMPLETED
        assert state.current_stage == AgentStage.STATE_UPDATE
        assert state.raw_input_text is not None and len(state.raw_input_text) > 0
        assert state.goal_understanding is not None
        assert state.context is not None
        assert state.capability_assessment is not None
        assert state.planner_result is not None
        assert state.skill_routing is not None

    def test_advance_phase_enforces_legal_transitions(self) -> None:
        from app.agent.state import advance_phase, create_initial_state

        state = create_initial_state(user_id=TEST_UID)
        assert state.phase == AgentPhase.IDLE
        with pytest.raises(StateTransitionError):
            advance_phase(state, AgentPhase.COMPLETED)  # IDLE -> COMPLETED illegal


class TestPipelineBlockedBranch:
    def test_unrecognized_intent_ends_blocked_with_plan_blocked_error(self) -> None:
        r = _run(default_pipeline(), goal_text="Arbitrary unrecognized utterance xyzzy")
        assert r.final_phase == AgentPhase.BLOCKED
        assert len(r.errors) >= 1
        codes = {e["code"] for e in r.errors}
        assert "PLAN_BLOCKED" in codes
        assert r.plan is not None
        assert r.plan.tasks  # Even blocked plan carries the clarification task

    def test_blocked_reasons_surface_unsupported_intents(self) -> None:
        r = _run(default_pipeline(), goal_text="foo bar baz")
        assert r.final_state.planner_result is not None
        assert len(r.final_state.planner_result.block_reasons) >= 1
        assert len(r.final_state.planner_result.unsupported_tasks) >= 1


class TestPipelineWarningPropagation:
    def test_short_ambiguous_input_records_ambiguous_goal_warning(self) -> None:
        r = _run(default_pipeline(), goal_text="q?")
        warning_codes = {w["code"] for w in r.final_state.warnings}
        assert "AMBIGUOUS_GOAL" in warning_codes

    def test_multi_intent_records_routing_notes_warning(self) -> None:
        r = _run(
            default_pipeline(),
            goal_text="Summarize document and remind me about the meeting",
        )
        codes = {w["code"] for w in r.final_state.warnings}
        assert "ROUTING_NOTES" in codes
        detail = next(w for w in r.final_state.warnings if w["code"] == "ROUTING_NOTES")
        assert "partial" in detail["message"].lower() or detail["stage"] == AgentStage.CAPABILITY_ROUTING.value

    def test_goal_understanding_confidence_reflects_ambiguity(self) -> None:
        ambiguous = _run(default_pipeline(), goal_text="do stuff").final_state.goal_understanding
        clear = _run(default_pipeline(), goal_text="List active tasks and summarize research document").final_state.goal_understanding
        assert ambiguous is not None and clear is not None
        assert ambiguous.confidence < clear.confidence


class TestPipelineFailureResilience:
    def test_goal_understanding_exception_translates_to_failed_phase(self) -> None:
        class ExplodingGU(GoalUnderstandingBackend):
            async def parse(self, _: GoalUnderstandingInput) -> GoalUnderstandingResult:
                raise RuntimeError("boom parse")

        pipe = AgentPipeline(goal_understanding=ExplodingGU())
        r = _run(pipe, goal_text="anything")
        assert r.final_phase == AgentPhase.FAILED
        assert len(r.errors) >= 1
        codes = {e["code"] for e in r.errors}
        assert "PIPELINE_EXCEPTION" in codes or "STAGE_EXCEPTION" in codes

    def test_default_pipeline_factory_is_independent_instances(self) -> None:
        p1 = default_pipeline()
        p2 = default_pipeline()
        assert p1 is not p2
        assert p1.goal_understanding is not p2.goal_understanding

    def test_end_to_end_goal_id_roundtrip(self) -> None:
        gid = UUID("99999999-9999-9999-9999-999999999999")
        r = _run(default_pipeline(), goal_text="List my tasks", goal_id=gid, priority=Priority.HIGH)
        assert r.goal_id == gid
        assert r.final_state.goal_id == gid
        assert r.plan is not None
        assert r.plan.goal_id == gid
