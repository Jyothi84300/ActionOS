"""Phase 4 — Skills and Tools.

Implements the MVP skill architecture per §12-13 of the Master
Specification.  The architecture flows:

    Agent
      → Skill Router
        → Skill
          → Registered Tool
            → Permission Engine
              → Executor
                → Verifier

Every Tool has a **stable** ``tool_id``, ``skill_id``, ``version``,
typed input/output schemas, permission level, capability classification,
and verification behavior.  Unknown skills/tools fail safely.
No arbitrary code execution, no shell, no unrestricted browser.
"""

from app.skills.contracts import (
    InputModelT,
    OutputModelT,
    ToolContract,
    ToolExecutionContext,
    ToolExecutionResult,
    ToolVerificationResult,
    VerificationBehavior,
    VerificationMethod,
)
from app.skills.document_skill import (
    DocumentAnalyzeInput,
    DocumentAnalyzeOutput,
    DocumentSummarizeInput,
    DocumentSummarizeOutput,
    DOCUMENT_SKILL_TOOL_CONTRACTS,
    DOCUMENT_TOOL_ID_ANALYZE,
    DOCUMENT_TOOL_ID_SUMMARIZE,
)
from app.skills.task_skill import (
    TASK_SKILL_TOOL_CONTRACTS,
    TASK_TOOL_ID_COMPLETE,
    TASK_TOOL_ID_CREATE,
    TASK_TOOL_ID_LIST,
    TASK_TOOL_ID_UPDATE,
    TaskCompleteInput,
    TaskCompleteOutput,
    TaskCreateInput,
    TaskCreateOutput,
    TaskListInput,
    TaskListOutput,
    TaskUpdateInput,
    TaskUpdateOutput,
)
from app.skills.calendar_skill import (
    CALENDAR_SKILL_TOOL_CONTRACTS,
    CALENDAR_TOOL_ID_CREATE_REMINDER,
    CALENDAR_TOOL_ID_READ_EVENTS,
    CALENDAR_TOOL_ID_CHECK_DEADLINE,
    CalendarCheckDeadlineInput,
    CalendarCheckDeadlineOutput,
    CalendarCreateReminderInput,
    CalendarCreateReminderOutput,
    CalendarReadEventsInput,
    CalendarReadEventsOutput,
)
from app.skills.registry import (
    ToolRegistry,
    GlobalToolRegistry,
    InMemoryToolRegistry,
    default_tool_registry,
    register_skill_tools,
    register_all_mvp_tools,
)
from app.skills.adapters import (
    DocumentProvider,
    DocumentHandle,
    CalendarProvider,
    CalendarEvent,
    FakeDocumentProvider,
    FakeCalendarProvider,
)

__all__ = [
    # contracts
    "InputModelT",
    "OutputModelT",
    "ToolContract",
    "ToolExecutionContext",
    "ToolExecutionResult",
    "ToolVerificationResult",
    "VerificationBehavior",
    "VerificationMethod",
    # document skill
    "DocumentSummarizeInput",
    "DocumentSummarizeOutput",
    "DocumentAnalyzeInput",
    "DocumentAnalyzeOutput",
    "DOCUMENT_TOOL_ID_SUMMARIZE",
    "DOCUMENT_TOOL_ID_ANALYZE",
    "DOCUMENT_SKILL_TOOL_CONTRACTS",
    # task skill
    "TaskCreateInput",
    "TaskCreateOutput",
    "TaskListInput",
    "TaskListOutput",
    "TaskUpdateInput",
    "TaskUpdateOutput",
    "TaskCompleteInput",
    "TaskCompleteOutput",
    "TASK_TOOL_ID_CREATE",
    "TASK_TOOL_ID_LIST",
    "TASK_TOOL_ID_UPDATE",
    "TASK_TOOL_ID_COMPLETE",
    "TASK_SKILL_TOOL_CONTRACTS",
    # calendar skill
    "CalendarReadEventsInput",
    "CalendarReadEventsOutput",
    "CalendarCreateReminderInput",
    "CalendarCreateReminderOutput",
    "CalendarCheckDeadlineInput",
    "CalendarCheckDeadlineOutput",
    "CALENDAR_TOOL_ID_READ_EVENTS",
    "CALENDAR_TOOL_ID_CREATE_REMINDER",
    "CALENDAR_TOOL_ID_CHECK_DEADLINE",
    "CALENDAR_SKILL_TOOL_CONTRACTS",
    # registry
    "ToolRegistry",
    "GlobalToolRegistry",
    "InMemoryToolRegistry",
    "default_tool_registry",
    "register_skill_tools",
    "register_all_mvp_tools",
    # adapters
    "DocumentProvider",
    "DocumentHandle",
    "CalendarProvider",
    "CalendarEvent",
    "FakeDocumentProvider",
    "FakeCalendarProvider",
]
