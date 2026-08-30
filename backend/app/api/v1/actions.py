from uuid import UUID

from fastapi import APIRouter

import app.crud as crud
from app.deps import CurrentUserId, DbSession, ensure_owner
from app.schemas import ActionResponse, ActionVerificationResponse

router = APIRouter(prefix="/actions", tags=["actions"])


@router.get("/{action_id}", response_model=ActionResponse)
def get_action(
    action_id: UUID,
    current_user_id: CurrentUserId,
    db: DbSession,
):
    action = crud.get_action_or_404(db, action_id)
    goal = action.task.goal
    ensure_owner(current_user_id, goal.user_id)

    verification = crud.get_verification_for_action(db, action.id)
    verification_resp = None
    if verification is not None:
        verification_resp = ActionVerificationResponse(
            result=verification.result,
            verified_at=verification.verified_at,
        )
    return ActionResponse(
        id=action.id,
        state=action.state,
        verification=verification_resp,
    )
