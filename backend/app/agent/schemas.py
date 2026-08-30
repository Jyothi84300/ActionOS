"""ActionOS Agent Core — shared schemas for all pipeline stages.

All agent components communicate exclusively via these Pydantic models.
No LLM integration, no executable code, no arbitrary tool calls.
"""

from __future__ import annotations

import datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.enums import (
    CapabilityRoute,
    PermissionLevel,
    Priority,
    SkillCapability,
    SourceType,
    ToolCapability,
    TrustLevel,
)


def _cfg() -> ConfigDict:
    return ConfigDict(frozen=False, use_enum_values=False, extra="forbid")


class AgentStage(str, Enum):
    GOAL_UNDERSTANDING = "goal_understanding"
    CONTEXT_RETRIEVAL = "context_retrieval"
    PLANNING = "planning"
    CAPABILITY_ROUTING = "capability_routing"
    SKILL_ROUTING = "skill_routing"
    EXECUTION = "execution"
    VERIFICATION = "verification"
    STATE_UPDATE = "state_update"


class GoalUnderstandingInput(BaseModel):
    model_config = _cfg()

    user_id: UUID
    raw_text: str = Field(..., min_length=1, max_length=10000)
    deadline: Optional[datetime.datetime] = None
    priority: Priority = Priority.MEDIUM
    category: str = Field(default="personal", max_length=100)


class ParsedGoal(BaseModel):
    model_config = _cfg()

    title: str = Field(..., min_length=1, max_length=255)
    description: str = Field(default="", max_length=10000)
    objective: str = Field(default="", max_length=10000)
    deadline: Optional[datetime.datetime] = None
    priority: Priority = Priority.MEDIUM
    category: str = Field(default="personal", max_length=100)
    constraints: list[Any] = Field(default_factory=list)
    intents: list[str] = Field(default_factory=list)
    is_ambiguous: bool = False
    ambiguity_reasons: list[str] = Field(default_factory=list)


class GoalUnderstandingResult(BaseModel):
    model_config = _cfg()

    stage: AgentStage = AgentStage.GOAL_UNDERSTANDING
    user_id: UUID
    raw_text: str
    parsed_goal: ParsedGoal
    confidence: float = Field(..., ge=0.0, le=1.0)


class ContextReference(BaseModel):
    model_config = _cfg()

    context_id: UUID
    source_type: SourceType
    source_ref: str
    retrieved_at: datetime.datetime
    trust_level: TrustLevel = TrustLevel.UNTRUSTED
    permission_id: Optional[UUID] = None
    excerpt: str = Field(default="", max_length=2000)


class ContextRetrievalRequest(BaseModel):
    model_config = _cfg()

    user_id: UUID
    goal_id: Optional[UUID] = None
    parsed_goal: ParsedGoal
    allowed_source_types: list[SourceType] = Field(default_factory=list)


class ContextRetrievalResult(BaseModel):
    model_config = _cfg()

    stage: AgentStage = AgentStage.CONTEXT_RETRIEVAL
    user_id: UUID
    goal_id: Optional[UUID] = None
    references: list[ContextReference] = Field(default_factory=list)
    missing_permissions: list[SourceType] = Field(default_factory=list)


class PlanTask(BaseModel):
    model_config = _cfg()

    task_id: UUID
    title: str = Field(..., min_length=1, max_length=255)
    description: str = Field(default="", max_length=5000)
    order_index: int = Field(default=0, ge=0)
    depends_on: list[UUID] = Field(default_factory=list)
    required_skill_id: Optional[UUID] = None
    required_skill_intent: Optional[str] = None
    required_tool_ids: list[UUID] = Field(default_factory=list)
    expected_output: str = Field(default="", max_length=2000)
    verification_method: str = Field(default="", max_length=500)
    capability_route: CapabilityRoute = CapabilityRoute.LOCAL


class StructuredPlan(BaseModel):
    model_config = _cfg()

    plan_id: UUID
    goal_id: Optional[UUID] = None
    tasks: list[PlanTask] = Field(default_factory=list)
    ordering: str = Field(default="sequential", max_length=100)
    dependencies: list[dict[str, Any]] = Field(default_factory=list)
    required_skills: list[UUID] = Field(default_factory=list)
    required_tools: list[UUID] = Field(default_factory=list)
    permission_level: PermissionLevel = PermissionLevel.AUTOMATIC
    verification_methods: list[str] = Field(default_factory=list)
    capability_route: CapabilityRoute = CapabilityRoute.LOCAL


class PlannerInput(BaseModel):
    model_config = _cfg()

    user_id: UUID
    goal_id: Optional[UUID] = None
    parsed_goal: ParsedGoal
    context: ContextRetrievalResult
    capability_route: CapabilityRoute = CapabilityRoute.LOCAL


class PlannerResult(BaseModel):
    model_config = _cfg()

    stage: AgentStage = AgentStage.PLANNING
    user_id: UUID
    goal_id: Optional[UUID] = None
    plan: StructuredPlan
    is_blocked: bool = False
    block_reasons: list[str] = Field(default_factory=list)
    unsupported_tasks: list[UUID] = Field(default_factory=list)


class CapabilityAssessment(BaseModel):
    model_config = _cfg()

    capability_route: CapabilityRoute
    required_skill_capabilities: dict[UUID, SkillCapability] = Field(default_factory=dict)
    required_tool_capabilities: dict[UUID, ToolCapability] = Field(default_factory=dict)
    local_eligible: bool = True
    online_required: bool = False
    partial_offline_eligible: bool = False
    reasons: list[str] = Field(default_factory=list)


class CapabilityRouterInput(BaseModel):
    model_config = _cfg()

    user_id: UUID
    parsed_goal: ParsedGoal
    context: ContextRetrievalResult


class CapabilityRouterResult(BaseModel):
    model_config = _cfg()

    stage: AgentStage = AgentStage.CAPABILITY_ROUTING
    user_id: UUID
    assessment: CapabilityAssessment


class SkillMatch(BaseModel):
    model_config = _cfg()

    skill_id: UUID
    skill_name: str
    manifest_version: str
    score: float = Field(..., ge=0.0, le=1.0)
    matched_intents: list[str] = Field(default_factory=list)
    tool_ids: list[UUID] = Field(default_factory=list)


class SkillRouterInput(BaseModel):
    model_config = _cfg()

    user_id: UUID
    plan: StructuredPlan
    available_skill_ids: list[UUID] = Field(default_factory=list)


class SkillRouterResult(BaseModel):
    model_config = _cfg()

    stage: AgentStage = AgentStage.SKILL_ROUTING
    user_id: UUID
    plan_id: UUID
    task_matches: dict[UUID, list[SkillMatch]] = Field(default_factory=dict)
    unmatched_task_ids: list[UUID] = Field(default_factory=list)


class AgentPhase(str, Enum):
    IDLE = "idle"
    GOAL_PARSED = "goal_parsed"
    CONTEXT_READY = "context_ready"
    CAPABILITY_ROUTED = "capability_routed"
    PLANNED = "planned"
    SKILLS_ROUTED = "skills_routed"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


class AgentState(BaseModel):
    model_config = _cfg()

    agent_run_id: UUID
    user_id: UUID
    goal_id: Optional[UUID] = None
    phase: AgentPhase = AgentPhase.IDLE
    current_stage: AgentStage = AgentStage.GOAL_UNDERSTANDING

    raw_input_text: Optional[str] = None
    goal_understanding: Optional[GoalUnderstandingResult] = None
    context: Optional[ContextRetrievalResult] = None
    capability_assessment: Optional[CapabilityRouterResult] = None
    planner_result: Optional[PlannerResult] = None
    skill_routing: Optional[SkillRouterResult] = None

    errors: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[dict[str, Any]] = Field(default_factory=list)
    stage_history: list[AgentStage] = Field(default_factory=list)

    created_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
    )
    updated_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
    )


class PipelineInput(BaseModel):
    model_config = _cfg()

    user_id: UUID
    goal_text: str = Field(..., min_length=1, max_length=10000)
    deadline: Optional[datetime.datetime] = None
    priority: Priority = Priority.MEDIUM
    category: str = Field(default="personal", max_length=100)
    goal_id: Optional[UUID] = None
    allowed_source_types: list[SourceType] = Field(default_factory=list)
    available_skill_ids: list[UUID] = Field(default_factory=list)


class PipelineResult(BaseModel):
    model_config = _cfg()

    agent_run_id: UUID
    user_id: UUID
    goal_id: Optional[UUID] = None
    final_phase: AgentPhase
    final_state: AgentState
    plan: Optional[StructuredPlan] = None
    skill_routing: Optional[SkillRouterResult] = None
    capability_route: CapabilityRoute
    errors: list[dict[str, Any]] = Field(default_factory=list)


__all__ = [
    "AgentPhase",
    "AgentStage",
    "AgentState",
    "CapabilityAssessment",
    "CapabilityRouterInput",
    "CapabilityRouterResult",
    "ContextReference",
    "ContextRetrievalRequest",
    "ContextRetrievalResult",
    "GoalUnderstandingInput",
    "GoalUnderstandingResult",
    "ParsedGoal",
    "PipelineInput",
    "PipelineResult",
    "PlannerInput",
    "PlannerResult",
    "PlanTask",
    "SkillMatch",
    "SkillRouterInput",
    "SkillRouterResult",
    "StructuredPlan",
]
