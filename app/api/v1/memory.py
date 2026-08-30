"""Memory endpoints per §24 of the Master Specification.

Base path: /api/v1/memory
"""

from uuid import UUID

from fastapi import APIRouter

import app.crud as crud
from app.deps import CurrentUserId, DbSession, ensure_owner
from app.schemas import MemoryResponse

router = APIRouter(prefix="/memory", tags=["memory"])


@router.get("/{goal_id}", response_model=list[MemoryResponse])
def list_goal_memory(
    goal_id: UUID,
    current_user_id: CurrentUserId,
    db: DbSession,
):
    """Retrieve memory entries associated with a goal (§24 GET /api/v1/memory/{goal_id}).

    Strict user/goal isolation: entries are filtered by (current_user_id, goal_id)
    so a caller can never see another user's memories.
    """
    goal = crud.get_goal_or_404(db, goal_id)
    ensure_owner(current_user_id, goal.user_id)
    rows = crud.list_memory_for_goal(
        db,
        user_id=current_user_id,
        goal_id=goal_id,
    )
    return rows
