from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.errors import ForbiddenResourceError, UnauthenticatedError
from app.logging_config import get_logger
from app.models import User

logger = get_logger(__name__)

MOCK_USER_ID = UUID("00000000-0000-0000-0000-000000000001")
MOCK_USER_EMAIL = "user@actionos.local"


def _get_or_create_mock_user(db: Session) -> User:
    user = db.query(User).filter(User.id == MOCK_USER_ID).first()
    if not user:
        user = User(id=MOCK_USER_ID, email=MOCK_USER_EMAIL, auth_provider="mock")
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


async def get_current_user_id(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
    db: Session = Depends(get_db),
) -> UUID:
    if authorization is None:
        if request.url.path == "/api/v1/health":
            return MOCK_USER_ID
        raise UnauthenticatedError()

    if not authorization.lower().startswith("bearer "):
        raise UnauthenticatedError()

    token = authorization[7:].strip()
    if not token:
        raise UnauthenticatedError()

    user = _get_or_create_mock_user(db)
    return user.id


CurrentUserId = Annotated[UUID, Depends(get_current_user_id)]
DbSession = Annotated[Session, Depends(get_db)]


def ensure_owner(user_id: UUID, resource_user_id: UUID) -> None:
    if user_id != resource_user_id:
        raise ForbiddenResourceError()
