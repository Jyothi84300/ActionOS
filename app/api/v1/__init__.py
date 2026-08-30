from fastapi import APIRouter

from app.api.v1.health import router as health_router
from app.api.v1.goals import router as goals_router
from app.api.v1.actions import router as actions_router
from app.api.v1.tasks import router as tasks_router
from app.api.v1.skills import router as skills_router
from app.api.v1.permissions import router as permissions_router
from app.api.v1.memory import router as memory_router

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(health_router)
api_router.include_router(goals_router)
api_router.include_router(actions_router)
api_router.include_router(tasks_router)
api_router.include_router(skills_router)
api_router.include_router(permissions_router)
api_router.include_router(memory_router)

__all__ = ["api_router"]
