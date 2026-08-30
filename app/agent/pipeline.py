"""End-to-end reasoning pipeline — Goal → Understanding → Context →
Capability Router → Planner → Skill Router → Structured Plan.

This is the Cloud-side Agent Core pipeline entry point (§6.2 of the
Master Specification).  It composes the six modular stages together,
driving the AgentState through the legal state machine transitions
defined in `app.agent.state`.

The pipeline is explicitly NOT executing anything:
  * No LLM integration is wired in.
  * No Android, calendar, or document integrations are called.
  * No arbitrary code/tool execution is performed.
  * No vector DB, Redis, Kafka.

The final output is a PlannerResult + SkillRouterResult packaged into a
PipelineResult — the StructuredPlan is ready to be handed to the
Permission Engine → Executor → Verifier later (Phase 2+).
"""

from __future__ import annotations

from app.agent import (
    CapabilityRouterInput,
    CapabilityRouterResult,
    ContextRetrievalRequest,
    ContextRetrievalResult,
    GoalUnderstandingInput,
    GoalUnderstandingResult,
    PipelineInput,
    PipelineResult,
    PlannerInput,
    PlannerResult,
    SkillRouterInput,
    SkillRouterResult,
)
from app.agent.capability_router import (
    CapabilityRouter,
    default_capability_router,
)
from app.agent.context import ContextRetriever, default_context_retriever
from app.agent.goal_understanding import (
    GoalUnderstandingBackend,
    default_goal_understanding,
)
from app.agent.planner import Planner, default_planner
from app.agent.skill_router import SkillRouter, default_skill_router
from app.agent.state import (
    AgentPhase,
    AgentStage,
    AgentState,
    advance_phase,
    create_initial_state,
    get_capability_route,
    record_error,
    record_warning,
    set_capability_assessment,
    set_context,
    set_goal_understanding,
    set_planner_result,
    set_skill_routing,
)
from app.agent.schemas import ParsedGoal
from app.logging_config import get_logger

logger = get_logger(__name__)


class AgentPipeline:
    """Composes the six Phase-2 stages into one run() call."""

    def __init__(
        self,
        *,
        goal_understanding: GoalUnderstandingBackend | None = None,
        context_retriever: ContextRetriever | None = None,
        capability_router: CapabilityRouter | None = None,
        planner: Planner | None = None,
        skill_router: SkillRouter | None = None,
    ) -> None:
        self.goal_understanding = goal_understanding or default_goal_understanding()
        self.context_retriever = context_retriever or default_context_retriever()
        self.capability_router = capability_router or default_capability_router()
        self.planner = planner or default_planner()
        self.skill_router = skill_router or default_skill_router()

    async def run(self, input_: PipelineInput) -> PipelineResult:
        state = create_initial_state(
            user_id=input_.user_id,
            goal_id=input_.goal_id,
            raw_input_text=input_.goal_text,
        )
        logger.info(
            "agent.pipeline.started",
            agent_run_id=str(state.agent_run_id),
            user_id=str(state.user_id),
        )

        try:
            state = await self._stage_goal_understanding(state, input_)
            if state.phase == AgentPhase.FAILED:
                return _finalize(state, input_.goal_id)

            state = await self._stage_context(state, input_)
            if state.phase in {AgentPhase.FAILED, AgentPhase.BLOCKED}:
                return _finalize(state, input_.goal_id)

            state = await self._stage_capability_routing(state)
            if state.phase == AgentPhase.FAILED:
                return _finalize(state, input_.goal_id)

            state = await self._stage_planning(state, input_.goal_id)
            if state.phase in {AgentPhase.FAILED, AgentPhase.BLOCKED}:
                return _finalize(state, input_.goal_id)

            state = await self._stage_skill_routing(state, input_.available_skill_ids)
            if state.phase == AgentPhase.FAILED:
                return _finalize(state, input_.goal_id)

            if state.skill_routing is not None and state.skill_routing.unmatched_task_ids:
                state = record_warning(
                    state,
                    stage=AgentStage.SKILL_ROUTING,
                    code="UNMATCHED_TASKS",
                    message=(
                        f"{len(state.skill_routing.unmatched_task_ids)} task(s) had no "
                        "registered skill candidate."
                    ),
                    details={
                        "unmatched_task_ids": [
                            str(t) for t in state.skill_routing.unmatched_task_ids
                        ],
                    },
                )

            state = advance_phase(state, AgentPhase.COMPLETED)

        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "agent.pipeline.unhandled_exception",
                agent_run_id=str(state.agent_run_id),
            )
            state = record_error(
                state,
                stage=state.current_stage,
                code="PIPELINE_EXCEPTION",
                message=f"{type(exc).__name__}: {exc}",
                details={"exception_type": type(exc).__name__},
            )
            if state.phase != AgentPhase.FAILED:
                try:
                    state = advance_phase(state, AgentPhase.FAILED)
                except Exception:  # noqa: BLE001
                    state = state.model_copy(deep=True)
                    state.phase = AgentPhase.FAILED

        return _finalize(state, input_.goal_id)

    async def _stage_goal_understanding(
        self, state: AgentState, input_: PipelineInput
    ) -> AgentState:
        gu_input = GoalUnderstandingInput(
            user_id=input_.user_id,
            raw_text=input_.goal_text,
            deadline=input_.deadline,
            priority=input_.priority,
            category=input_.category,
        )
        result: GoalUnderstandingResult = await self.goal_understanding.parse(gu_input)
        state = set_goal_understanding(state, result)
        if result.parsed_goal.is_ambiguous:
            state = record_warning(
                state,
                stage=AgentStage.GOAL_UNDERSTANDING,
                code="AMBIGUOUS_GOAL",
                message="Goal input is marked ambiguous by the parser.",
                details={"reasons": result.parsed_goal.ambiguity_reasons},
            )
        return advance_phase(state, AgentPhase.GOAL_PARSED)

    async def _stage_context(
        self, state: AgentState, input_: PipelineInput
    ) -> AgentState:
        parsed: ParsedGoal = state.goal_understanding.parsed_goal
        ctx_request = ContextRetrievalRequest(
            user_id=input_.user_id,
            goal_id=input_.goal_id,
            parsed_goal=parsed,
            allowed_source_types=list(input_.allowed_source_types),
        )
        result: ContextRetrievalResult = await self.context_retriever.retrieve(ctx_request)
        state = set_context(state, result)
        if result.missing_permissions:
            state = record_warning(
                state,
                stage=AgentStage.CONTEXT_RETRIEVAL,
                code="MISSING_PERMISSIONS",
                message="Context sources were skipped due to missing permissions.",
                details={
                    "missing": [s.value for s in result.missing_permissions],
                },
            )
        return advance_phase(state, AgentPhase.CONTEXT_READY)

    async def _stage_capability_routing(self, state: AgentState) -> AgentState:
        parsed: ParsedGoal = state.goal_understanding.parsed_goal
        ctx: ContextRetrievalResult = state.context
        router_input = CapabilityRouterInput(
            user_id=state.user_id,
            parsed_goal=parsed,
            context=ctx,
        )
        result: CapabilityRouterResult = await self.capability_router.route(router_input)
        state = set_capability_assessment(state, result)
        if result.assessment.reasons:
            state = record_warning(
                state,
                stage=AgentStage.CAPABILITY_ROUTING,
                code="ROUTING_NOTES",
                message=f"Capability route = {result.assessment.capability_route.value}.",
                details={"reasons": result.assessment.reasons},
            )
        return advance_phase(state, AgentPhase.CAPABILITY_ROUTED)

    async def _stage_planning(
        self, state: AgentState, goal_id: str | None
    ) -> AgentState:
        plan_input = PlannerInput(
            user_id=state.user_id,
            goal_id=goal_id,
            parsed_goal=state.goal_understanding.parsed_goal,
            context=state.context,
            capability_route=get_capability_route(state),
        )
        result: PlannerResult = await self.planner.plan(plan_input)
        state = set_planner_result(state, result)
        if result.is_blocked:
            state = record_error(
                state,
                stage=AgentStage.PLANNING,
                code="PLAN_BLOCKED",
                message="Planner produced a blocked plan.",
                details={
                    "reasons": result.block_reasons,
                    "unsupported_tasks": [str(t) for t in result.unsupported_tasks],
                },
            )
            return advance_phase(state, AgentPhase.BLOCKED)
        return advance_phase(state, AgentPhase.PLANNED)

    async def _stage_skill_routing(
        self, state: AgentState, available_skill_ids: list
    ) -> AgentState:
        router_input = SkillRouterInput(
            user_id=state.user_id,
            plan=state.planner_result.plan,
            available_skill_ids=list(available_skill_ids),
        )
        result: SkillRouterResult = await self.skill_router.route(router_input)
        state = set_skill_routing(state, result)
        return advance_phase(state, AgentPhase.SKILLS_ROUTED)


def _finalize(state: AgentState, goal_id) -> PipelineResult:
    plan = state.planner_result.plan if state.planner_result else None
    route = get_capability_route(state)
    logger.info(
        "agent.pipeline.finished",
        agent_run_id=str(state.agent_run_id),
        final_phase=state.phase.value,
        route=route.value,
        errors=len(state.errors),
    )
    return PipelineResult(
        agent_run_id=state.agent_run_id,
        user_id=state.user_id,
        goal_id=state.goal_id,
        final_phase=state.phase,
        final_state=state,
        plan=plan,
        skill_routing=state.skill_routing,
        capability_route=route,
        errors=list(state.errors),
    )


def default_pipeline() -> AgentPipeline:
    return AgentPipeline()


__all__ = [
    "AgentPipeline",
    "default_pipeline",
]
