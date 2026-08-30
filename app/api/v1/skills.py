from fastapi import APIRouter

import app.crud as crud
from app.deps import CurrentUserId, DbSession
from app.schemas import SkillSummaryResponse

router = APIRouter(prefix="/skills", tags=["skills"])


@router.get("", response_model=list[SkillSummaryResponse])
def list_skills(
    current_user_id: CurrentUserId,
    db: DbSession,
):
    skills = crud.list_skills(db)
    return [
        SkillSummaryResponse(
            skill_id=skill.skill_id,
            name=skill.name,
            current_version=skill.current_version,
            capability=skill.capability,
        )
        for skill in skills
    ]
