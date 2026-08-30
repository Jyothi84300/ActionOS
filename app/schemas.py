import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.enums import (
    ActionState,
    CapabilityRoute,
    GoalStatus,
    MemoryType,
    PermissionLevel,
    Priority,
    SkillCapability,
    SkillStatus,
    SourceType,
    ToolCapability,
    TrustLevel,
    VerificationResult,
)


def _model_config() -> ConfigDict:
    return ConfigDict(from_attributes=True, populate_by_name=True)


class HealthResponse(BaseModel):
    status: str


class GoalCreate(BaseModel):
    model_config = _model_config()

    title: str = Field(..., min_length=1, max_length=255)
    description: str = Field(default="", max_length=10000)
    objective: str = Field(default="", max_length=10000)
    deadline: Optional[datetime.datetime] = None
    priority: Priority = Priority.MEDIUM
    category: str = Field(default="personal", max_length=100)
    constraints: list[Any] = Field(default_factory=list)


class GoalCreatedResponse(BaseModel):
    model_config = _model_config()

    id: UUID
    status: GoalStatus
    created_at: datetime.datetime


class GoalResponse(BaseModel):
    model_config = _model_config()

    id: UUID
    user_id: UUID
    title: str
    description: str
    objective: str
    deadline: Optional[datetime.datetime]
    priority: Priority
    category: str
    constraints: list[Any]
    status: GoalStatus
    created_at: datetime.datetime
    updated_at: datetime.datetime
    sync_metadata: dict[str, Any]


class TaskResponse(BaseModel):
    model_config = _model_config()

    id: UUID
    goal_id: UUID
    title: str
    description: str
    order_index: int
    depends_on: list[Any]
    skill_id: Optional[UUID]
    skill_version: Optional[str]
    capability_route: CapabilityRoute
    status: ActionState
    created_at: datetime.datetime
    updated_at: datetime.datetime


class ActionVerificationResponse(BaseModel):
    model_config = _model_config()

    result: VerificationResult
    verified_at: datetime.datetime


class ActionResponse(BaseModel):
    model_config = _model_config()

    id: UUID
    state: ActionState
    verification: Optional[ActionVerificationResponse] = None


class SkillSummaryResponse(BaseModel):
    model_config = _model_config()

    skill_id: UUID
    name: str
    current_version: str
    capability: SkillCapability


class PermissionResponse(BaseModel):
    model_config = _model_config()

    id: UUID
    user_id: UUID
    tool_id: UUID
    scope: Optional[str]
    granted: bool
    granted_at: Optional[datetime.datetime]
    revoked_at: Optional[datetime.datetime]


class PermissionUpdate(BaseModel):
    model_config = _model_config()

    granted: bool


class PlanTaskResponse(BaseModel):
    model_config = _model_config()

    id: UUID
    title: str
    order_index: int
    skill_id: Optional[UUID] = None
    capability_route: CapabilityRoute
    depends_on: list[UUID] = Field(default_factory=list)


class PlanResponse(BaseModel):
    model_config = _model_config()

    plan_id: UUID
    tasks: list[PlanTaskResponse]
    permission_level: PermissionLevel
    unmatched_task_ids: list[UUID] = Field(default_factory=list)


class TaskExecuteResponse(BaseModel):
    model_config = _model_config()

    action_id: UUID
    state: ActionState


class MemoryResponse(BaseModel):
    model_config = _model_config()

    id: UUID
    user_id: UUID
    goal_id: Optional[UUID] = None
    type: MemoryType
    payload: dict[str, Any]
    created_at: datetime.datetime


class MemoryCreate(BaseModel):
    model_config = _model_config()

    goal_id: Optional[UUID] = None
    type: MemoryType
    payload: dict[str, Any] = Field(default_factory=dict)


class ActionConfirmRequest(BaseModel):
    model_config = _model_config()

    confirmed: bool
