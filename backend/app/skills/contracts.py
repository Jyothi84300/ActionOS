"""Typed tool contracts — every registered tool must expose these.

Per §12-13 of the Master Specification, every tool has:
  * stable ``tool_id`` (UUID)
  * ``skill_id``
  * version (semver)
  * Pydantic input/output schemas
  * permission requirement
  * capability classification (local | online | both)
  * verification behavior
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Generic, Protocol, TypeVar
from uuid import UUID

from pydantic import BaseModel

from app.enums import PermissionLevel, ToolCapability

InputModelT = TypeVar("InputModelT", bound=BaseModel)
OutputModelT = TypeVar("OutputModelT", bound=BaseModel)


class VerificationMethod(str, enum.Enum):
    NONE = "none"
    """Verification is not technically possible — result is UNVERIFIED."""
    INDEPENDENT_READ = "independent_read"
    """Re-query the resulting state via a separate read call."""
    RETURN_VALUE_VALIDATION = "return_value_validation"
    """The tool return value itself is sufficient (read-only ops)."""
    SATELLITE_QUERY = "satellite_query"
    """Use a different provider/API to cross-check."""


class VerificationBehavior(str, enum.Enum):
    ALWAYS_REQUIRED = "always_required"
    """§16 — verification is mandatory; unverified results stay UNVERIFIED."""
    OPTIONAL_READ_ONLY = "optional_read_only"
    """Read-only tools skip verification (result is already the observed state)."""
    IMPOSSIBLE = "impossible"
    """§16.1 — the tool has no independent verification path."""


@dataclass
class ToolExecutionContext:
    """Supplied at tool execution time by the Executor.

    The ``db_session`` allows tools like the Task Skill to operate
    directly on ActionOS data safely; external integrations use the
    typed provider adapters (``document_provider``, ``calendar_provider``)
    instead so credentials never leak into tool code.
    """

    user_id: UUID
    action_id: UUID
    task_id: UUID | None = None
    goal_id: UUID | None = None
    db_session: Any = None
    document_provider: Any = None
    calendar_provider: Any = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolExecutionResult:
    success: bool
    output: BaseModel
    error_message: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolVerificationResult:
    verified: bool
    method: VerificationMethod
    details: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None


class ToolHandler(Protocol[InputModelT, OutputModelT]):
    async def execute(
        self, input_: InputModelT, ctx: ToolExecutionContext
    ) -> ToolExecutionResult: ...

    async def verify(
        self,
        input_: InputModelT,
        execution_output: OutputModelT,
        ctx: ToolExecutionContext,
    ) -> ToolVerificationResult: ...


@dataclass
class ToolContract(Generic[InputModelT, OutputModelT]):
    """Typed, registered tool definition.

    The Executor may ONLY invoke tool_ids present in the ToolRegistry.
    Unknown tool_ids MUST fail safely (see Executor in Phase 5).
    """

    tool_id: UUID
    skill_id: UUID
    name: str
    version: str
    description: str
    input_schema: type[InputModelT]
    output_schema: type[OutputModelT]
    permission_level: PermissionLevel
    capability: ToolCapability
    verification_method: VerificationMethod
    verification_behavior: VerificationBehavior
    handler: ToolHandler[InputModelT, OutputModelT]
    enabled: bool = True

    @property
    def input_json_schema(self) -> dict[str, Any]:
        return self.input_schema.model_json_schema()

    @property
    def output_json_schema(self) -> dict[str, Any]:
        return self.output_schema.model_json_schema()
