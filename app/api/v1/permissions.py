from uuid import UUID

from fastapi import APIRouter

import app.crud as crud
from app.deps import CurrentUserId, DbSession, ensure_owner
from app.schemas import PermissionResponse, PermissionUpdate

router = APIRouter(prefix="/permissions", tags=["permissions"])


@router.get("", response_model=list[PermissionResponse])
def list_permissions(
    current_user_id: CurrentUserId,
    db: DbSession,
):
    return crud.list_permissions(db, current_user_id)


@router.put("/{permission_id}", response_model=PermissionResponse)
def update_permission(
    permission_id: UUID,
    payload: PermissionUpdate,
    current_user_id: CurrentUserId,
    db: DbSession,
):
    perm = crud.get_permission_or_404(db, permission_id)
    ensure_owner(current_user_id, perm.user_id)
    updated = crud.update_permission_granted(db, perm, payload.granted)
    return updated
