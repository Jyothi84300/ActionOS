"""Calendar Skill — read, create reminders, check deadlines.

Per §12.3 of the Master Specification.  Accesses the real user calendar
through the typed CalendarProvider interface; a FakeCalendarProvider is
used for tests and when real integrations are not configured.

Three tools are registered:

  * ``calendar.read`` — list events in a window.
  * ``calendar.create_reminder`` — create a new calendar reminder event.
  * ``calendar.check_deadline`` — check a goal deadline against calendar
    conflicts (read-only).
"""

from __future__ import annotations

import datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from app.agent.planner import SKILL_ID_CALENDAR
from app.enums import PermissionLevel, ToolCapability
from app.logging_config import get_logger
from app.skills.adapters import CalendarEvent, CalendarProvider
from app.skills.contracts import (
    ToolContract,
    ToolExecutionContext,
    ToolExecutionResult,
    ToolVerificationResult,
    VerificationBehavior,
    VerificationMethod,
)

logger = get_logger(__name__)


CALENDAR_TOOL_ID_READ_EVENTS = UUID("22222222-2222-2222-2222-000000000005")
CALENDAR_TOOL_ID_CREATE_REMINDER = UUID("22222222-2222-2222-2222-000000000006")
CALENDAR_TOOL_ID_CHECK_DEADLINE = UUID("22222222-2222-2222-2222-000000000009")


# ---------------------------------------------------------------------------
# Typed schemas
# ---------------------------------------------------------------------------


class CalendarReadEventsInput(BaseModel):
    window_start: datetime.datetime
    window_end: datetime.datetime


class CalendarEventRecord(BaseModel):
    event_id: str
    title: str
    start_at: datetime.datetime
    end_at: datetime.datetime
    all_day: bool = False
    location: str | None = None


class CalendarReadEventsOutput(BaseModel):
    events: list[CalendarEventRecord]
    window_start: datetime.datetime
    window_end: datetime.datetime


class CalendarCreateReminderInput(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    fire_at: datetime.datetime
    duration_minutes: int = Field(default=15, ge=1, le=60 * 24)
    reminder_minutes_before: int = Field(default=15, ge=0, le=60 * 24 * 7)
    location: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None, max_length=2000)


class CalendarCreateReminderOutput(BaseModel):
    event_id: str
    title: str
    fire_at: datetime.datetime
    end_at: datetime.datetime
    reminder_minutes_before: int
    created: bool


class CalendarCheckDeadlineInput(BaseModel):
    deadline: datetime.datetime
    lookahead_hours: int = Field(default=48, ge=1, le=30 * 24)


class CalendarCheckDeadlineOutput(BaseModel):
    deadline: datetime.datetime
    conflicting_events: list[CalendarEventRecord]
    free_hours_before_deadline: int
    at_risk: bool


def _to_record(ev: CalendarEvent) -> CalendarEventRecord:
    return CalendarEventRecord(
        event_id=ev.event_id,
        title=ev.title,
        start_at=ev.start_at,
        end_at=ev.end_at,
        all_day=ev.all_day,
        location=ev.location,
    )


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


class _ReadEventsHandler:
    async def execute(
        self, input_: CalendarReadEventsInput, ctx: ToolExecutionContext
    ) -> ToolExecutionResult:
        provider: CalendarProvider | None = ctx.calendar_provider
        if provider is None:
            return ToolExecutionResult(
                success=False,
                output=CalendarReadEventsOutput(
                    events=[],
                    window_start=input_.window_start,
                    window_end=input_.window_end,
                ),
                error_message="No CalendarProvider configured.",
            )
        events = await provider.list_events(input_.window_start, input_.window_end)
        records = [_to_record(e) for e in events]
        return ToolExecutionResult(
            success=True,
            output=CalendarReadEventsOutput(
                events=records,
                window_start=input_.window_start,
                window_end=input_.window_end,
            ),
        )

    async def verify(
        self,
        input_: CalendarReadEventsInput,
        execution_output: CalendarReadEventsOutput,
        ctx: ToolExecutionContext,
    ) -> ToolVerificationResult:
        # Read-only tool — RETURN_VALUE_VALIDATION is sufficient per §16.
        for ev in execution_output.events:
            if ev.start_at < input_.window_start or ev.start_at > input_.window_end:
                return ToolVerificationResult(
                    verified=False,
                    method=VerificationMethod.RETURN_VALUE_VALIDATION,
                    reason=(
                        f"Event {ev.event_id!r} start_at is outside the requested "
                        f"window [{input_.window_start}, {input_.window_end}]."
                    ),
                )
        return ToolVerificationResult(
            verified=True,
            method=VerificationMethod.RETURN_VALUE_VALIDATION,
            details={"returned_count": len(execution_output.events)},
        )


class _CreateReminderHandler:
    async def execute(
        self, input_: CalendarCreateReminderInput, ctx: ToolExecutionContext
    ) -> ToolExecutionResult:
        provider: CalendarProvider | None = ctx.calendar_provider
        if provider is None:
            return ToolExecutionResult(
                success=False,
                output=CalendarCreateReminderOutput(
                    event_id="",
                    title=input_.title,
                    fire_at=input_.fire_at,
                    end_at=input_.fire_at
                    + datetime.timedelta(minutes=input_.duration_minutes),
                    reminder_minutes_before=input_.reminder_minutes_before,
                    created=False,
                ),
                error_message="No CalendarProvider configured.",
            )
        end_at = input_.fire_at + datetime.timedelta(minutes=input_.duration_minutes)
        ev = await provider.create_event(
            title=input_.title,
            start_at=input_.fire_at,
            end_at=end_at,
            reminder_minutes=input_.reminder_minutes_before,
            location=input_.location,
            description=input_.description,
        )
        return ToolExecutionResult(
            success=True,
            output=CalendarCreateReminderOutput(
                event_id=ev.event_id,
                title=ev.title,
                fire_at=ev.start_at,
                end_at=ev.end_at,
                reminder_minutes_before=input_.reminder_minutes_before,
                created=True,
            ),
        )

    async def verify(
        self,
        input_: CalendarCreateReminderInput,
        execution_output: CalendarCreateReminderOutput,
        ctx: ToolExecutionContext,
    ) -> ToolVerificationResult:
        # §16 — independent re-read of the freshly created event.
        provider: CalendarProvider | None = ctx.calendar_provider
        if provider is None:
            return ToolVerificationResult(
                verified=False,
                method=VerificationMethod.NONE,
                reason="No CalendarProvider in context.",
            )
        if not execution_output.created:
            return ToolVerificationResult(
                verified=False,
                method=VerificationMethod.RETURN_VALUE_VALIDATION,
                reason="Tool reported created=False on a create operation.",
            )
        ev = await provider.get_event(execution_output.event_id)
        if ev is None:
            return ToolVerificationResult(
                verified=False,
                method=VerificationMethod.INDEPENDENT_READ,
                reason="Re-query returned missing event.",
            )
        if abs((ev.start_at - execution_output.fire_at).total_seconds()) > 1:
            return ToolVerificationResult(
                verified=False,
                method=VerificationMethod.INDEPENDENT_READ,
                reason="Event start_at does not match expected fire_at.",
            )
        if ev.title != execution_output.title:
            return ToolVerificationResult(
                verified=False,
                method=VerificationMethod.INDEPENDENT_READ,
                reason="Event title does not match expected.",
            )
        return ToolVerificationResult(
            verified=True,
            method=VerificationMethod.INDEPENDENT_READ,
            details={"event_id": execution_output.event_id},
        )


class _CheckDeadlineHandler:
    async def execute(
        self, input_: CalendarCheckDeadlineInput, ctx: ToolExecutionContext
    ) -> ToolExecutionResult:
        provider: CalendarProvider | None = ctx.calendar_provider
        now = datetime.datetime.now(datetime.timezone.utc)
        end_window = input_.deadline
        start_window = max(now, end_window - datetime.timedelta(hours=input_.lookahead_hours))
        conflicts: list[CalendarEventRecord] = []
        if provider is not None:
            events = await provider.list_events(start_window, end_window)
            conflicts = [_to_record(e) for e in events]
        total_minutes = max(0, int((end_window - start_window).total_seconds() // 60))
        busy_minutes = 0
        for ev in conflicts:
            busy_minutes += int((ev.end_at - ev.start_at).total_seconds() // 60)
        free_minutes = max(0, total_minutes - busy_minutes)
        free_hours = free_minutes // 60
        at_risk = free_hours < 4
        return ToolExecutionResult(
            success=True,
            output=CalendarCheckDeadlineOutput(
                deadline=input_.deadline,
                conflicting_events=conflicts,
                free_hours_before_deadline=free_hours,
                at_risk=at_risk,
            ),
        )

    async def verify(
        self,
        input_: CalendarCheckDeadlineInput,
        execution_output: CalendarCheckDeadlineOutput,
        ctx: ToolExecutionContext,
    ) -> ToolVerificationResult:
        # Pure analysis/read-only — RETURN_VALUE_VALIDATION is sufficient.
        if execution_output.free_hours_before_deadline < 0:
            return ToolVerificationResult(
                verified=False,
                method=VerificationMethod.RETURN_VALUE_VALIDATION,
                reason="free_hours_before_deadline is negative.",
            )
        return ToolVerificationResult(
            verified=True,
            method=VerificationMethod.RETURN_VALUE_VALIDATION,
            details={
                "conflicts": len(execution_output.conflicting_events),
                "free_hours": execution_output.free_hours_before_deadline,
                "at_risk": execution_output.at_risk,
            },
        )


# ---------------------------------------------------------------------------
# Tool contracts
# ---------------------------------------------------------------------------


CALENDAR_SKILL_TOOL_CONTRACTS: tuple[ToolContract, ...] = (
    ToolContract(
        tool_id=CALENDAR_TOOL_ID_READ_EVENTS,
        skill_id=SKILL_ID_CALENDAR,
        name="calendar.read",
        version="1.0.0",
        description="List calendar events in a given time window (read-only).",
        input_schema=CalendarReadEventsInput,
        output_schema=CalendarReadEventsOutput,
        permission_level=PermissionLevel.AUTOMATIC,
        capability=ToolCapability.LOCAL,
        verification_method=VerificationMethod.RETURN_VALUE_VALIDATION,
        verification_behavior=VerificationBehavior.OPTIONAL_READ_ONLY,
        handler=_ReadEventsHandler(),
    ),
    ToolContract(
        tool_id=CALENDAR_TOOL_ID_CREATE_REMINDER,
        skill_id=SKILL_ID_CALENDAR,
        name="calendar.create_reminder",
        version="1.0.0",
        description="Create a new calendar reminder. Confirmation-Required per §14.",
        input_schema=CalendarCreateReminderInput,
        output_schema=CalendarCreateReminderOutput,
        permission_level=PermissionLevel.CONFIRMATION_REQUIRED,
        capability=ToolCapability.LOCAL,
        verification_method=VerificationMethod.INDEPENDENT_READ,
        verification_behavior=VerificationBehavior.ALWAYS_REQUIRED,
        handler=_CreateReminderHandler(),
    ),
    ToolContract(
        tool_id=CALENDAR_TOOL_ID_CHECK_DEADLINE,
        skill_id=SKILL_ID_CALENDAR,
        name="calendar.check_deadline",
        version="1.0.0",
        description="Analyze calendar load before a given deadline (read-only).",
        input_schema=CalendarCheckDeadlineInput,
        output_schema=CalendarCheckDeadlineOutput,
        permission_level=PermissionLevel.AUTOMATIC,
        capability=ToolCapability.LOCAL,
        verification_method=VerificationMethod.RETURN_VALUE_VALIDATION,
        verification_behavior=VerificationBehavior.OPTIONAL_READ_ONLY,
        handler=_CheckDeadlineHandler(),
    ),
)
