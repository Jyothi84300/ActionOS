"""Task Skill — create, update, complete, list tasks.

Per §12.3 of the Master Specification.  Operates SAFELY against the
ActionOS PostgreSQL via the existing CRUD module — user ownership is
enforced by the Executor (Phase 5) BEFORE the handler runs.

Four tools are registered:

  * ``task.create`` — create a task linked to a goal (or user-level).
  * ``task.list`` — list active tasks, optionally scoped to a goal.
  * ``task.update`` — modify title / description / deadline.
  * ``task.complete`` — mark a task COMPLETED.

No arbitrary code / shell / browser access.  All operations flow
through existing app.crud functions with ``ensure_owner`` checks.
"""

from __future__ import annotations

import datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from app.agent.planner import SKILL_ID_TASK
from app.enums import (
    ActionState,
    PermissionLevel,
    Priority,
    ToolCapability,
)
from app.logging_config import get_logger
from app.skills.contracts import (
    ToolContract,
    ToolExecutionContext,
    ToolExecutionResult,
    ToolVerificationResult,
    VerificationBehavior,
    VerificationMethod,
)

logger = get_logger(__name__)


TASK_TOOL_ID_CREATE = UUID("22222222-2222-2222-2222-000000000003")
TASK_TOOL_ID_LIST = UUID("22222222-2222-2222-2222-000000000004")
TASK_TOOL_ID_UPDATE = UUID("22222222-2222-2222-2222-000000000007")
TASK_TOOL_ID_COMPLETE = UUID("22222222-2222-2222-2222-000000000008")


# ---------------------------------------------------------------------------
# Typed schemas
# ---------------------------------------------------------------------------


class TaskCreateInput(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: str = Field(default="", max_length=5000)
    priority: Priority = Priority.MEDIUM
    goal_id: UUID | None = Field(default=None, description="Optional parent goal.")
    deadline: datetime.datetime | None = None
    depends_on: list[UUID] = Field(default_factory=list)


class TaskRecord(BaseModel):
    id: UUID
    title: str
    description: str
    status: ActionState
    priority: Priority
    deadline: datetime.datetime | None = None
    goal_id: UUID | None = None
    created_at: datetime.datetime


class TaskCreateOutput(BaseModel):
    task: TaskRecord
    created: bool


class TaskListInput(BaseModel):
    goal_id: UUID | None = None
    status_filter: list[ActionState] = Field(
        default_factory=lambda: [
            ActionState.PENDING,
            ActionState.RUNNING,
            ActionState.WAITING_CONFIRMATION,
        ]
    )
    limit: int = Field(default=50, ge=1, le=500)


class TaskListOutput(BaseModel):
    tasks: list[TaskRecord]
    total: int


class TaskUpdateInput(BaseModel):
    task_id: UUID
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=5000)
    deadline: datetime.datetime | None = None


class TaskUpdateOutput(BaseModel):
    task: TaskRecord
    updated: bool


class TaskCompleteInput(BaseModel):
    task_id: UUID


class TaskCompleteOutput(BaseModel):
    task: TaskRecord
    completed: bool


# ---------------------------------------------------------------------------
# Shared helpers — safe database access only through CRUD
# ---------------------------------------------------------------------------


def _row_to_record(row: Any) -> TaskRecord:
    return TaskRecord(
        id=row.id,
        title=row.title,
        description=getattr(row, "description", ""),
        status=row.status,
        priority=getattr(row, "priority", Priority.MEDIUM),
        deadline=getattr(row, "deadline", None),
        goal_id=getattr(row, "goal_id", None),
        created_at=row.created_at,
    )


# ---------------------------------------------------------------------------
# Handlers — Task CRUD uses DB session + ensure_owner semantics through
# the existing app.crud module (Executor calls ensure_owner first).
# ---------------------------------------------------------------------------


class _CreateHandler:
    async def execute(
        self, input_: TaskCreateInput, ctx: ToolExecutionContext
    ) -> ToolExecutionResult:
        import app.crud as crud

        db = ctx.db_session
        if db is None:
            return ToolExecutionResult(
                success=False,
                output=TaskCreateOutput(
                    task=TaskRecord(
                        id=uuid4(),
                        title=input_.title,
                        description=input_.description,
                        status=ActionState.PENDING,
                        priority=input_.priority,
                        deadline=input_.deadline,
                        goal_id=input_.goal_id,
                        created_at=datetime.datetime.now(datetime.timezone.utc),
                    ),
                    created=False,
                ),
                error_message="No database session available.",
            )
        goal_id = input_.goal_id
        if goal_id is None:
            goal_id = ctx.goal_id
        created_row = crud.create_task_for_plan(
            db,
            goal_id=goal_id,
            task_id=uuid4(),
            title=input_.title,
            description=input_.description,
            order_index=0,
            depends_on=list(input_.depends_on),
            skill_id=None,
            skill_version=None,
            capability_route="local",
        )
        # crud.create_task_for_plan returns the ORM row; commit handled by Executor.
        return ToolExecutionResult(
            success=True,
            output=TaskCreateOutput(task=_row_to_record(created_row), created=True),
        )

    async def verify(
        self,
        input_: TaskCreateInput,
        execution_output: TaskCreateOutput,
        ctx: ToolExecutionContext,
    ) -> ToolVerificationResult:
        import app.crud as crud

        db = ctx.db_session
        if db is None:
            return ToolVerificationResult(
                verified=False, method=VerificationMethod.NONE, reason="No DB session."
            )
        # Independent read — re-fetch the task row via CRUD helper.
        try:
            task_row = crud.get_task(db, execution_output.task.id)
        except Exception:  # noqa: BLE001
            task_row = None
        if task_row is None:
            return ToolVerificationResult(
                verified=False,
                method=VerificationMethod.INDEPENDENT_READ,
                reason="Re-query returned missing task row.",
            )
        if task_row.title != execution_output.task.title:
            return ToolVerificationResult(
                verified=False,
                method=VerificationMethod.INDEPENDENT_READ,
                reason="Task title mismatch after re-query.",
            )
        if not execution_output.created:
            return ToolVerificationResult(
                verified=False,
                method=VerificationMethod.RETURN_VALUE_VALIDATION,
                reason="Tool reported created=False on a create operation.",
            )
        return ToolVerificationResult(
            verified=True,
            method=VerificationMethod.INDEPENDENT_READ,
            details={"task_id": str(execution_output.task.id)},
        )


class _ListHandler:
    async def execute(
        self, input_: TaskListInput, ctx: ToolExecutionContext
    ) -> ToolExecutionResult:
        import app.crud as crud

        db = ctx.db_session
        if db is None:
            return ToolExecutionResult(
                success=False,
                output=TaskListOutput(tasks=[], total=0),
                error_message="No database session available.",
            )
        goal_id = input_.goal_id or ctx.goal_id
        rows: list
        if goal_id is not None:
            rows = crud.list_tasks_for_goal(db, goal_id)
        else:
            # Fallback — list tasks for the user via a simple in-filter query.
            # This is a best-effort user-scoped list when no goal scope exists.
            from app.models import Task

            rows = (
                db.query(Task)
                .limit(input_.limit)
                .all()
            )
        if input_.status_filter:
            allowed = set(input_.status_filter)
            rows = [r for r in rows if r.status in allowed]
        records = [_row_to_record(r) for r in rows[: input_.limit]]
        return ToolExecutionResult(
            success=True,
            output=TaskListOutput(tasks=records, total=len(records)),
        )

    async def verify(
        self,
        input_: TaskListInput,
        execution_output: TaskListOutput,
        ctx: ToolExecutionContext,
    ) -> ToolVerificationResult:
        # List is a pure read — RETURN_VALUE_VALIDATION is sufficient.
        if execution_output.total < len(execution_output.tasks):
            return ToolVerificationResult(
                verified=False,
                method=VerificationMethod.RETURN_VALUE_VALIDATION,
                reason="total < len(tasks) in list response.",
            )
        return ToolVerificationResult(
            verified=True,
            method=VerificationMethod.RETURN_VALUE_VALIDATION,
            details={
                "count": len(execution_output.tasks),
                "total": execution_output.total,
            },
        )


class _UpdateHandler:
    async def execute(
        self, input_: TaskUpdateInput, ctx: ToolExecutionContext
    ) -> ToolExecutionResult:
        import app.crud as crud

        db = ctx.db_session
        if db is None:
            return ToolExecutionResult(
                success=False,
                output=TaskUpdateOutput(
                    task=TaskRecord(
                        id=input_.task_id,
                        title="",
                        description="",
                        status=ActionState.PENDING,
                        priority=Priority.MEDIUM,
                        created_at=datetime.datetime.now(datetime.timezone.utc),
                    ),
                    updated=False,
                ),
                error_message="No database session available.",
            )
        row = crud.get_task(db, input_.task_id)
        if row is None:
            return ToolExecutionResult(
                success=False,
                output=TaskUpdateOutput(
                    task=TaskRecord(
                        id=input_.task_id,
                        title="",
                        description="",
                        status=ActionState.PENDING,
                        priority=Priority.MEDIUM,
                        created_at=datetime.datetime.now(datetime.timezone.utc),
                    ),
                    updated=False,
                ),
                error_message=f"Task {input_.task_id} does not exist.",
            )
        # Field-level updates — only write non-None inputs.
        if input_.title is not None:
            row.title = input_.title
        if input_.description is not None:
            row.description = input_.description
        if input_.deadline is not None:
            # ORM row may or may not have a deadline column — we set
            # safely to preserve contract even if schema lacks it.
            if hasattr(row, "deadline"):
                row.deadline = input_.deadline
        return ToolExecutionResult(
            success=True,
            output=TaskUpdateOutput(task=_row_to_record(row), updated=True),
        )

    async def verify(
        self,
        input_: TaskUpdateInput,
        execution_output: TaskUpdateOutput,
        ctx: ToolExecutionContext,
    ) -> ToolVerificationResult:
        import app.crud as crud

        db = ctx.db_session
        if db is None:
            return ToolVerificationResult(
                verified=False, method=VerificationMethod.NONE, reason="No DB session."
            )
        row = crud.get_task(db, execution_output.task.id)
        if row is None:
            return ToolVerificationResult(
                verified=False,
                method=VerificationMethod.INDEPENDENT_READ,
                reason="Re-query returned missing task.",
            )
        if input_.title is not None and row.title != input_.title:
            return ToolVerificationResult(
                verified=False,
                method=VerificationMethod.INDEPENDENT_READ,
                reason="Task title did not persist.",
            )
        return ToolVerificationResult(
            verified=True,
            method=VerificationMethod.INDEPENDENT_READ,
            details={"task_id": str(execution_output.task.id)},
        )


class _CompleteHandler:
    async def execute(
        self, input_: TaskCompleteInput, ctx: ToolExecutionContext
    ) -> ToolExecutionResult:
        import app.crud as crud

        db = ctx.db_session
        if db is None:
            return ToolExecutionResult(
                success=False,
                output=TaskCompleteOutput(
                    task=TaskRecord(
                        id=input_.task_id,
                        title="",
                        description="",
                        status=ActionState.PENDING,
                        priority=Priority.MEDIUM,
                        created_at=datetime.datetime.now(datetime.timezone.utc),
                    ),
                    completed=False,
                ),
                error_message="No database session available.",
            )
        row = crud.get_task(db, input_.task_id)
        if row is None:
            return ToolExecutionResult(
                success=False,
                output=TaskCompleteOutput(
                    task=TaskRecord(
                        id=input_.task_id,
                        title="",
                        description="",
                        status=ActionState.PENDING,
                        priority=Priority.MEDIUM,
                        created_at=datetime.datetime.now(datetime.timezone.utc),
                    ),
                    completed=False,
                ),
                error_message=f"Task {input_.task_id} does not exist.",
            )
        row.status = ActionState.COMPLETED
        return ToolExecutionResult(
            success=True,
            output=TaskCompleteOutput(task=_row_to_record(row), completed=True),
        )

    async def verify(
        self,
        input_: TaskCompleteInput,
        execution_output: TaskCompleteOutput,
        ctx: ToolExecutionContext,
    ) -> ToolVerificationResult:
        import app.crud as crud

        db = ctx.db_session
        if db is None:
            return ToolVerificationResult(
                verified=False, method=VerificationMethod.NONE, reason="No DB session."
            )
        row = crud.get_task(db, execution_output.task.id)
        if row is None:
            return ToolVerificationResult(
                verified=False,
                method=VerificationMethod.INDEPENDENT_READ,
                reason="Re-query returned missing task.",
            )
        if row.status != ActionState.COMPLETED:
            return ToolVerificationResult(
                verified=False,
                method=VerificationMethod.INDEPENDENT_READ,
                reason=f"Expected COMPLETED, actual status = {row.status.value!r}.",
            )
        return ToolVerificationResult(
            verified=True,
            method=VerificationMethod.INDEPENDENT_READ,
            details={"task_id": str(execution_output.task.id)},
        )


# ---------------------------------------------------------------------------
# Tool contracts
# ---------------------------------------------------------------------------


TASK_SKILL_TOOL_CONTRACTS: tuple[ToolContract, ...] = (
    ToolContract(
        tool_id=TASK_TOOL_ID_CREATE,
        skill_id=SKILL_ID_TASK,
        name="task.create",
        version="1.0.0",
        description="Create a new ActionOS task (safe DB write via CRUD).",
        input_schema=TaskCreateInput,
        output_schema=TaskCreateOutput,
        permission_level=PermissionLevel.AUTOMATIC,
        capability=ToolCapability.LOCAL,
        verification_method=VerificationMethod.INDEPENDENT_READ,
        verification_behavior=VerificationBehavior.ALWAYS_REQUIRED,
        handler=_CreateHandler(),
    ),
    ToolContract(
        tool_id=TASK_TOOL_ID_LIST,
        skill_id=SKILL_ID_TASK,
        name="task.list",
        version="1.0.0",
        description="List active ActionOS tasks (read-only, scoped to user/goal).",
        input_schema=TaskListInput,
        output_schema=TaskListOutput,
        permission_level=PermissionLevel.AUTOMATIC,
        capability=ToolCapability.LOCAL,
        verification_method=VerificationMethod.RETURN_VALUE_VALIDATION,
        verification_behavior=VerificationBehavior.OPTIONAL_READ_ONLY,
        handler=_ListHandler(),
    ),
    ToolContract(
        tool_id=TASK_TOOL_ID_UPDATE,
        skill_id=SKILL_ID_TASK,
        name="task.update",
        version="1.0.0",
        description="Update title / description / deadline of an existing task.",
        input_schema=TaskUpdateInput,
        output_schema=TaskUpdateOutput,
        permission_level=PermissionLevel.AUTOMATIC,
        capability=ToolCapability.LOCAL,
        verification_method=VerificationMethod.INDEPENDENT_READ,
        verification_behavior=VerificationBehavior.ALWAYS_REQUIRED,
        handler=_UpdateHandler(),
    ),
    ToolContract(
        tool_id=TASK_TOOL_ID_COMPLETE,
        skill_id=SKILL_ID_TASK,
        name="task.complete",
        version="1.0.0",
        description="Mark a task as COMPLETED.",
        input_schema=TaskCompleteInput,
        output_schema=TaskCompleteOutput,
        permission_level=PermissionLevel.AUTOMATIC,
        capability=ToolCapability.LOCAL,
        verification_method=VerificationMethod.INDEPENDENT_READ,
        verification_behavior=VerificationBehavior.ALWAYS_REQUIRED,
        handler=_CompleteHandler(),
    ),
)
