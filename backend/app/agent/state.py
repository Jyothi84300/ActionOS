"""Agent State — durable, phase-tracking state container.

Per §8 and §17 of the Master Specification the Agent Core tracks a
single active pipeline through all stages.  This module:

  * Creates and advances a typed AgentState.
  * Enforces a legal state-machine transition between AgentPhases.
  * Propagates stage history so any failure can be audited.
  * Never silently swallows errors; they are appended to `state.errors`.

No database persistence is required by this module; callers persist the
state to PostgreSQL via the existing ORM models (Goal/Task/Action/…)
when appropriate.
"""

from __future__ import annotations

import datetime
from collections.abc import Callable
from uuid import UUID, uuid4

from app.agent.schemas import (
    AgentPhase,
    AgentStage,
    AgentState,
    CapabilityRouterResult,
    ContextRetrievalResult,
    GoalUnderstandingResult,
    PlannerResult,
    SkillRouterResult,
)
from app.enums import CapabilityRoute
from app.logging_config import get_logger

logger = get_logger(__name__)


_LEGAL_TRANSITIONS: dict[AgentPhase, frozenset[AgentPhase]] = {
    AgentPhase.IDLE: frozenset({AgentPhase.GOAL_PARSED, AgentPhase.FAILED}),
    AgentPhase.GOAL_PARSED: frozenset(
        {AgentPhase.CONTEXT_READY, AgentPhase.FAILED, AgentPhase.BLOCKED}
    ),
    AgentPhase.CONTEXT_READY: frozenset(
        {AgentPhase.CAPABILITY_ROUTED, AgentPhase.FAILED, AgentPhase.BLOCKED}
    ),
    AgentPhase.CAPABILITY_ROUTED: frozenset(
        {AgentPhase.PLANNED, AgentPhase.FAILED, AgentPhase.BLOCKED}
    ),
    AgentPhase.PLANNED: frozenset(
        {AgentPhase.SKILLS_ROUTED, AgentPhase.FAILED, AgentPhase.BLOCKED}
    ),
    AgentPhase.SKILLS_ROUTED: frozenset(
        {AgentPhase.EXECUTING, AgentPhase.COMPLETED, AgentPhase.FAILED, AgentPhase.BLOCKED}
    ),
    AgentPhase.EXECUTING: frozenset(
        {AgentPhase.COMPLETED, AgentPhase.FAILED, AgentPhase.BLOCKED}
    ),
    AgentPhase.COMPLETED: frozenset(),
    AgentPhase.FAILED: frozenset({AgentPhase.IDLE}),
    AgentPhase.BLOCKED: frozenset({AgentPhase.IDLE}),
}


_PHASE_STAGE: dict[AgentPhase, AgentStage] = {
    AgentPhase.IDLE: AgentStage.GOAL_UNDERSTANDING,
    AgentPhase.GOAL_PARSED: AgentStage.CONTEXT_RETRIEVAL,
    AgentPhase.CONTEXT_READY: AgentStage.CAPABILITY_ROUTING,
    AgentPhase.CAPABILITY_ROUTED: AgentStage.PLANNING,
    AgentPhase.PLANNED: AgentStage.SKILL_ROUTING,
    AgentPhase.SKILLS_ROUTED: AgentStage.EXECUTION,
    AgentPhase.EXECUTING: AgentStage.VERIFICATION,
    AgentPhase.COMPLETED: AgentStage.STATE_UPDATE,
    AgentPhase.FAILED: AgentStage.STATE_UPDATE,
    AgentPhase.BLOCKED: AgentStage.STATE_UPDATE,
}


class StateTransitionError(Exception):
    """Raised when an illegal AgentPhase transition is attempted."""


def create_initial_state(
    *,
    user_id: UUID,
    goal_id: UUID | None = None,
    raw_input_text: str | None = None,
) -> AgentState:
    now = datetime.datetime.now(datetime.timezone.utc)
    return AgentState(
        agent_run_id=uuid4(),
        user_id=user_id,
        goal_id=goal_id,
        phase=AgentPhase.IDLE,
        current_stage=AgentStage.GOAL_UNDERSTANDING,
        raw_input_text=raw_input_text,
        goal_understanding=None,
        context=None,
        capability_assessment=None,
        planner_result=None,
        skill_routing=None,
        errors=[],
        warnings=[],
        stage_history=[],
        created_at=now,
        updated_at=now,
    )


def advance_phase(state: AgentState, new_phase: AgentPhase) -> AgentState:
    """Advance the AgentState phase with legal-transition enforcement.

    Returns a NEW AgentState (models are not deep-frozen by Pydantic in
    this codebase, but this function never mutates the input).
    """
    legal = _LEGAL_TRANSITIONS.get(state.phase, frozenset())
    if new_phase not in legal:
        raise StateTransitionError(
            f"Illegal agent phase transition: {state.phase.value} -> {new_phase.value}. "
            f"Legal next phases: {sorted(p.value for p in legal)}"
        )
    stage = _PHASE_STAGE[new_phase]
    now = datetime.datetime.now(datetime.timezone.utc)
    updated = state.model_copy(deep=True)
    updated.phase = new_phase
    updated.current_stage = stage
    updated.stage_history = list(state.stage_history) + [stage]
    updated.updated_at = now
    return updated


def record_error(
    state: AgentState,
    *,
    stage: AgentStage,
    code: str,
    message: str,
    details: dict | None = None,
) -> AgentState:
    updated = state.model_copy(deep=True)
    updated.errors.append(
        {
            "stage": stage.value,
            "code": code,
            "message": message,
            "details": dict(details or {}),
            "at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
    )
    updated.updated_at = datetime.datetime.now(datetime.timezone.utc)
    return updated


def record_warning(
    state: AgentState,
    *,
    stage: AgentStage,
    code: str,
    message: str,
    details: dict | None = None,
) -> AgentState:
    updated = state.model_copy(deep=True)
    updated.warnings.append(
        {
            "stage": stage.value,
            "code": code,
            "message": message,
            "details": dict(details or {}),
            "at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
    )
    updated.updated_at = datetime.datetime.now(datetime.timezone.utc)
    return updated


def set_goal_understanding(
    state: AgentState, result: GoalUnderstandingResult
) -> AgentState:
    updated = state.model_copy(deep=True)
    updated.goal_understanding = result
    updated.updated_at = datetime.datetime.now(datetime.timezone.utc)
    return updated


def set_context(state: AgentState, result: ContextRetrievalResult) -> AgentState:
    updated = state.model_copy(deep=True)
    updated.context = result
    updated.updated_at = datetime.datetime.now(datetime.timezone.utc)
    return updated


def set_capability_assessment(
    state: AgentState, result: CapabilityRouterResult
) -> AgentState:
    updated = state.model_copy(deep=True)
    updated.capability_assessment = result
    updated.updated_at = datetime.datetime.now(datetime.timezone.utc)
    return updated


def set_planner_result(state: AgentState, result: PlannerResult) -> AgentState:
    updated = state.model_copy(deep=True)
    updated.planner_result = result
    updated.updated_at = datetime.datetime.now(datetime.timezone.utc)
    return updated


def set_skill_routing(state: AgentState, result: SkillRouterResult) -> AgentState:
    updated = state.model_copy(deep=True)
    updated.skill_routing = result
    updated.updated_at = datetime.datetime.now(datetime.timezone.utc)
    return updated


def get_capability_route(state: AgentState) -> CapabilityRoute:
    if state.capability_assessment is not None:
        return state.capability_assessment.assessment.capability_route
    if state.planner_result is not None:
        return state.planner_result.plan.capability_route
    return CapabilityRoute.LOCAL


async def run_stage(
    state: AgentState,
    stage: AgentStage,
    fn: Callable[[], AgentState | None],
) -> AgentState:
    """Run a single stage, translating exceptions into state errors.

    The callable should perform the stage's work and return the new
    state, or `None` if it only produced side-effects and the caller
    should retain the input state.  Any exception is logged and the
    state is transitioned to FAILED with an error record.
    """
    try:
        result = await fn() if hasattr(fn, "__await__") else fn()  # type: ignore[operator]
        if result is None:
            return state
        return result
    except StateTransitionError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("agent.state.stage_failed", stage=stage.value)
        errored = record_error(
            state,
            stage=stage,
            code="STAGE_EXCEPTION",
            message=f"{type(exc).__name__}: {exc}",
            details={"exception_type": type(exc).__name__},
        )
        return advance_phase(errored, AgentPhase.FAILED)


__all__ = [
    "AgentState",
    "StateTransitionError",
    "advance_phase",
    "create_initial_state",
    "get_capability_route",
    "record_error",
    "record_warning",
    "run_stage",
    "set_capability_assessment",
    "set_context",
    "set_goal_understanding",
    "set_planner_result",
    "set_skill_routing",
]
