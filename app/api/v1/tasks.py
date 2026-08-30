from uuid import UUID, uuid4

from fastapi import APIRouter, status

import app.crud as crud
from app.deps import CurrentUserId, DbSession, ensure_owner
from app.enums import ActionState
from app.errors import ConflictError
from app.logging_config import get_logger
from app.schemas import TaskExecuteResponse

logger = get_logger(__name__)

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post(
    "/{task_id}/execute",
    response_model=TaskExecuteResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def execute_task(
    task_id: UUID,
    current_user_id: CurrentUserId,
    db: DbSession,
):
    """Request execution of a task (§24 POST /api/v1/tasks/{task_id}/execute).

    Creates a PENDING Action row linked to the task so the Executor module
    (a later Phase-2 task) can pick it up asynchronously. The caller can
    poll the returned action_id via GET /api/v1/actions/{action_id}.
    """
    task = crud.get_task_or_404(db, task_id)
    goal = task.goal
    ensure_owner(current_user_id, goal.user_id)

    ineligible_states = {ActionState.RUNNING, ActionState.COMPLETED}
    if task.status in ineligible_states:
        raise ConflictError(
            code="TASK_NOT_ELIGIBLE",
            message=(
                f"Task is already {task.status.value} and cannot be re-executed. "
                "Only PENDING tasks may transition to execution."
            ),
            details={
                "task_id": str(task_id),
                "current_state": task.status.value,
                "eligible_from": [ActionState.PENDING.value],
            },
        )

    action_id = uuid4()
    action = crud.create_action_for_task(db, task_id=task_id, action_id=action_id)

    task.status = ActionState.RUNNING
    db.commit()

    logger.info(
        "task.execute.accepted",
        task_id=str(task_id),
        action_id=str(action_id),
    )

    return TaskExecuteResponse(action_id=action.id, state=action.state)
