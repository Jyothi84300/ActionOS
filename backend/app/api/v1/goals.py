from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

import app.crud as crud
from app.agent.pipeline import AgentPipeline, default_pipeline
from app.agent.schemas import PipelineInput
from app.database import get_db
from app.deps import CurrentUserId, DbSession, ensure_owner
from app.enums import PermissionLevel
from app.errors import ConflictError, UnprocessableError
from app.logging_config import get_logger
from app.schemas import (
    GoalCreate,
    GoalCreatedResponse,
    GoalResponse,
    PlanResponse,
    PlanTaskResponse,
    TaskResponse,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/goals", tags=["goals"])


@router.post("", response_model=GoalCreatedResponse, status_code=status.HTTP_201_CREATED)
def create_goal(
    payload: GoalCreate,
    current_user_id: CurrentUserId,
    db: DbSession,
):
    goal = crud.create_goal(
        db=db,
        user_id=current_user_id,
        title=payload.title,
        description=payload.description,
        objective=payload.objective,
        deadline=payload.deadline,
        priority=payload.priority,
        category=payload.category,
        constraints=payload.constraints,
    )
    return GoalCreatedResponse(
        id=goal.id,
        status=goal.status,
        created_at=goal.created_at,
    )


@router.get("/{goal_id}", response_model=GoalResponse)
def get_goal(
    goal_id: UUID,
    current_user_id: CurrentUserId,
    db: DbSession,
):
    goal = crud.get_goal_or_404(db, goal_id)
    ensure_owner(current_user_id, goal.user_id)
    return goal


@router.get("/{goal_id}/tasks", response_model=list[TaskResponse])
def list_goal_tasks(
    goal_id: UUID,
    current_user_id: CurrentUserId,
    db: DbSession,
):
    goal = crud.get_goal_or_404(db, goal_id)
    ensure_owner(current_user_id, goal.user_id)
    tasks = crud.list_tasks_for_goal(db, goal_id)
    return tasks


@router.post("/{goal_id}/plan", response_model=PlanResponse)
def plan_goal(
    goal_id: UUID,
    current_user_id: CurrentUserId,
    db: DbSession,
    force: bool = Query(
        default=False,
        description="If true, replace an existing active plan (§24).",
    ),
    pipeline: AgentPipeline = Depends(default_pipeline),
):
    """Trigger planning for a goal (§24 of the Master Specification).

    Runs the Cloud Agent Core pipeline: GoalUnderstanding → Context →
    CapabilityRouter → Planner → SkillRouter. Persists resulting Task
    records under the goal and returns the plan summary.
    """
    goal = crud.get_goal_or_404(db, goal_id)
    ensure_owner(current_user_id, goal.user_id)

    if not force and crud.has_active_plan_for_goal(db, goal_id):
        raise ConflictError(
            code="PLAN_ALREADY_EXISTS",
            message=(
                "An active plan already exists for this goal. "
                "Pass force=true to replace it."
            ),
            details={"goal_id": str(goal_id)},
        )

    if force:
        crud.delete_tasks_for_goal(db, goal_id)

    goal_text_parts = [goal.title]
    if goal.description:
        goal_text_parts.append(goal.description)
    if goal.objective:
        goal_text_parts.append(f"Objective: {goal.objective}")
    goal_text = " — ".join(goal_text_parts)

    pipeline_input = PipelineInput(
        user_id=current_user_id,
        goal_text=goal_text,
        deadline=goal.deadline,
        priority=goal.priority,
        category=goal.category,
        goal_id=goal_id,
    )

    import asyncio

    try:
        loop = asyncio.new_event_loop()
        try:
            pipeline_result = loop.run_until_complete(pipeline.run(pipeline_input))
        finally:
            loop.close()
    except Exception as exc:  # noqa: BLE001
        logger.exception("plan.pipeline_failed", goal_id=str(goal_id))
        raise UnprocessableError(
            code="PLANNING_FAILED",
            message=f"Planning failed: {type(exc).__name__}",
            details={"goal_id": str(goal_id)},
        )

    if pipeline_result.plan is None:
        raise UnprocessableError(
            code="UNSUPPORTED_GOAL",
            message=(
                "The planner could not produce a plan for this goal. "
                "Try rephrasing with a clearer intent (e.g. 'remind me', "
                "'summarize document', 'create task')."
            ),
            details={
                "goal_id": str(goal_id),
                "final_phase": pipeline_result.final_phase.value,
                "errors_count": len(pipeline_result.errors),
            },
        )

    plan = pipeline_result.plan
    skill_routing = pipeline_result.skill_routing
    task_responses: list[PlanTaskResponse] = []

    from app.agent.skill_router import default_skill_registry

    _reg = default_skill_registry()
    skill_version_by_task: dict[UUID, str | None] = {}
    if skill_routing is not None:
        for task_id, matches in skill_routing.task_matches.items():
            if matches:
                skill_version_by_task[task_id] = matches[0].manifest_version

    for plan_task in plan.tasks:
        resolved_version = skill_version_by_task.get(plan_task.task_id)
        if resolved_version is None and plan_task.required_skill_id is not None:
            reg_skill = _reg.get(plan_task.required_skill_id)
            if reg_skill is not None:
                resolved_version = reg_skill.manifest_version
        created = crud.create_task_for_plan(
            db,
            goal_id=goal_id,
            task_id=plan_task.task_id,
            title=plan_task.title,
            description=plan_task.description,
            order_index=plan_task.order_index,
            depends_on=plan_task.depends_on,
            skill_id=plan_task.required_skill_id,
            skill_version=resolved_version,
            capability_route=plan_task.capability_route,
        )
        task_responses.append(
            PlanTaskResponse(
                id=created.id,
                title=created.title,
                order_index=created.order_index,
                skill_id=created.skill_id,
                capability_route=created.capability_route,
                depends_on=list(plan_task.depends_on),
            )
        )

    db.commit()

    permission_level = plan.permission_level
    if not isinstance(permission_level, PermissionLevel):
        permission_level = PermissionLevel(str(permission_level).upper())

    unmatched_task_ids: list[UUID] = []
    if skill_routing is not None:
        unmatched_task_ids = list(skill_routing.unmatched_task_ids)

    logger.info(
        "plan.created",
        goal_id=str(goal_id),
        plan_id=str(plan.plan_id),
        tasks_count=len(task_responses),
        unmatched_count=len(unmatched_task_ids),
        permission_level=permission_level.value,
    )

    return PlanResponse(
        plan_id=plan.plan_id,
        tasks=task_responses,
        permission_level=permission_level,
        unmatched_task_ids=unmatched_task_ids,
    )
