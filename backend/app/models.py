import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    Index,
    Uuid,
)
from sqlalchemy.orm import relationship

from app.database import Base
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


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: UUID = Column(Uuid, primary_key=True)
    email: str = Column(String(255), unique=True, nullable=False, index=True)
    created_at: datetime.datetime = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    auth_provider: str = Column(String(100), nullable=True)

    goals = relationship("Goal", back_populates="user", cascade="all, delete-orphan")
    memories = relationship("Memory", back_populates="user", cascade="all, delete-orphan")
    permissions = relationship("Permission", back_populates="user", cascade="all, delete-orphan")
    audit_events = relationship("AuditEvent", back_populates="user", cascade="all, delete-orphan")


class Goal(Base):
    __tablename__ = "goals"

    id: UUID = Column(Uuid, primary_key=True)
    user_id: UUID = Column(Uuid, ForeignKey("users.id"), nullable=False, index=True)
    title: str = Column(String(255), nullable=False)
    description: str = Column(Text, nullable=False, default="")
    objective: str = Column(Text, nullable=False, default="")
    deadline: datetime.datetime | None = Column(DateTime(timezone=True), nullable=True)
    priority: Priority = Column(Enum(Priority), nullable=False, default=Priority.MEDIUM)
    category: str = Column(String(100), nullable=False, default="personal")
    constraints: list[Any] = Column(JSON, nullable=False, default=list)
    status: GoalStatus = Column(Enum(GoalStatus), nullable=False, default=GoalStatus.ACTIVE, index=True)
    created_at: datetime.datetime = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at: datetime.datetime = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)
    sync_metadata: dict[str, Any] = Column(JSON, nullable=False, default=dict)

    user = relationship("User", back_populates="goals")
    tasks = relationship("Task", back_populates="goal", cascade="all, delete-orphan")
    context_references = relationship("ContextReference", back_populates="goal", cascade="all, delete-orphan")
    memories = relationship("Memory", back_populates="goal", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_goals_user_status", "user_id", "status"),
    )


class Task(Base):
    __tablename__ = "tasks"

    id: UUID = Column(Uuid, primary_key=True)
    goal_id: UUID = Column(Uuid, ForeignKey("goals.id"), nullable=False, index=True)
    title: str = Column(String(255), nullable=False)
    description: str = Column(Text, nullable=False, default="")
    order_index: int = Column(Integer, nullable=False, default=0)
    depends_on: list[Any] = Column(JSON, nullable=False, default=list)
    skill_id: UUID = Column(Uuid, ForeignKey("skills.skill_id"), nullable=True)
    skill_version: str = Column(String(50), nullable=True)
    capability_route: CapabilityRoute = Column(Enum(CapabilityRoute), nullable=False, default=CapabilityRoute.LOCAL)
    status: ActionState = Column(Enum(ActionState), nullable=False, default=ActionState.PENDING)
    created_at: datetime.datetime = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at: datetime.datetime = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    goal = relationship("Goal", back_populates="tasks")
    skill = relationship("Skill", back_populates="tasks")
    actions = relationship("Action", back_populates="task", cascade="all, delete-orphan")


class Action(Base):
    __tablename__ = "actions"

    id: UUID = Column(Uuid, primary_key=True)
    task_id: UUID = Column(Uuid, ForeignKey("tasks.id"), nullable=False, index=True)
    tool_id: UUID = Column(Uuid, ForeignKey("tools.id"), nullable=True)
    permission_id: UUID = Column(Uuid, ForeignKey("permissions.id"), nullable=True)
    input_payload: dict[str, Any] = Column(JSON, nullable=False, default=dict)
    result_payload: dict[str, Any] | None = Column(JSON, nullable=True)
    state: ActionState = Column(Enum(ActionState), nullable=False, default=ActionState.PENDING, index=True)
    created_at: datetime.datetime = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at: datetime.datetime = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    task = relationship("Task", back_populates="actions")
    tool = relationship("Tool", back_populates="actions")
    permission = relationship("Permission", back_populates="actions")
    verification = relationship("Verification", back_populates="action", uselist=False, cascade="all, delete-orphan")
    offline_queue = relationship("OfflineQueue", back_populates="action", uselist=False, cascade="all, delete-orphan")


class Verification(Base):
    __tablename__ = "verifications"

    id: UUID = Column(Uuid, primary_key=True)
    action_id: UUID = Column(Uuid, ForeignKey("actions.id"), nullable=False, index=True)
    method: str | None = Column(String(255), nullable=True)
    result: VerificationResult = Column(Enum(VerificationResult), nullable=False)
    observed_state: dict[str, Any] | None = Column(JSON, nullable=True)
    verified_at: datetime.datetime = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    action = relationship("Action", back_populates="verification")


class Memory(Base):
    __tablename__ = "memories"

    id: UUID = Column(Uuid, primary_key=True)
    user_id: UUID = Column(Uuid, ForeignKey("users.id"), nullable=False, index=True)
    goal_id: UUID | None = Column(Uuid, ForeignKey("goals.id"), nullable=True, index=True)
    type: MemoryType = Column(Enum(MemoryType), nullable=False)
    payload: dict[str, Any] = Column(JSON, nullable=False, default=dict)
    created_at: datetime.datetime = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    user = relationship("User", back_populates="memories")
    goal = relationship("Goal", back_populates="memories")


class Skill(Base):
    __tablename__ = "skills"

    skill_id: UUID = Column(Uuid, primary_key=True)
    name: str = Column(String(255), nullable=False)
    current_version: str = Column(String(50), nullable=False, default="0.1.0")
    description: str = Column(Text, nullable=False, default="")
    status: SkillStatus = Column(Enum(SkillStatus), nullable=False, default=SkillStatus.ENABLED)
    capability: SkillCapability = Column(Enum(SkillCapability), nullable=False, default=SkillCapability.BOTH)

    versions = relationship("SkillVersion", back_populates="skill", cascade="all, delete-orphan")
    tools = relationship("Tool", back_populates="skill", cascade="all, delete-orphan")
    tasks = relationship("Task", back_populates="skill")


class SkillVersion(Base):
    __tablename__ = "skill_versions"

    id: UUID = Column(Uuid, primary_key=True)
    skill_id: UUID = Column(Uuid, ForeignKey("skills.skill_id"), nullable=False, index=True)
    version: str = Column(String(50), nullable=False)
    manifest: dict[str, Any] = Column(JSON, nullable=False, default=dict)
    created_at: datetime.datetime = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    skill = relationship("Skill", back_populates="versions")


class Tool(Base):
    __tablename__ = "tools"

    id: UUID = Column(Uuid, primary_key=True)
    skill_id: UUID = Column(Uuid, ForeignKey("skills.skill_id"), nullable=False, index=True)
    name: str = Column(String(255), unique=True, nullable=False)
    input_schema: dict[str, Any] = Column(JSON, nullable=False, default=dict)
    output_schema: dict[str, Any] = Column(JSON, nullable=False, default=dict)
    permission_level: PermissionLevel = Column(Enum(PermissionLevel), nullable=False, default=PermissionLevel.AUTOMATIC)
    capability: ToolCapability = Column(Enum(ToolCapability), nullable=False, default=ToolCapability.LOCAL)
    enabled: bool = Column(Boolean, nullable=False, default=True)

    skill = relationship("Skill", back_populates="tools")
    actions = relationship("Action", back_populates="tool")
    permissions = relationship("Permission", back_populates="tool", cascade="all, delete-orphan")


class Permission(Base):
    __tablename__ = "permissions"

    id: UUID = Column(Uuid, primary_key=True)
    user_id: UUID = Column(Uuid, ForeignKey("users.id"), nullable=False, index=True)
    tool_id: UUID = Column(Uuid, ForeignKey("tools.id"), nullable=False, index=True)
    scope: str | None = Column(String(255), nullable=True)
    granted: bool = Column(Boolean, nullable=False, default=False)
    granted_at: datetime.datetime | None = Column(DateTime(timezone=True), nullable=True)
    revoked_at: datetime.datetime | None = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="permissions")
    tool = relationship("Tool", back_populates="permissions")
    actions = relationship("Action", back_populates="permission")


class ContextReference(Base):
    __tablename__ = "context_references"

    id: UUID = Column(Uuid, primary_key=True)
    goal_id: UUID = Column(Uuid, ForeignKey("goals.id"), nullable=False, index=True)
    source_type: SourceType = Column(Enum(SourceType), nullable=False)
    source_ref: str = Column(Text, nullable=False)
    trust_level: TrustLevel = Column(Enum(TrustLevel), nullable=False, default=TrustLevel.UNTRUSTED)
    retrieved_at: datetime.datetime = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    goal = relationship("Goal", back_populates="context_references")


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: UUID = Column(Uuid, primary_key=True)
    user_id: UUID = Column(Uuid, ForeignKey("users.id"), nullable=False, index=True)
    event_type: str = Column(String(255), nullable=False)
    related_id: UUID | None = Column(Uuid, nullable=True)
    event_metadata: dict[str, Any] = Column("metadata", JSON, nullable=False, default=dict)
    created_at: datetime.datetime = Column(DateTime(timezone=True), nullable=False, default=_utcnow, index=True)

    user = relationship("User", back_populates="audit_events")


class OfflineQueue(Base):
    __tablename__ = "offline_queue"

    id: UUID = Column(Uuid, primary_key=True)
    action_id: UUID = Column(Uuid, ForeignKey("actions.id"), nullable=False, index=True)
    queued_at: datetime.datetime = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    attempts: int = Column(Integer, nullable=False, default=0)
    last_error: str | None = Column(Text, nullable=True)

    action = relationship("Action", back_populates="offline_queue")
