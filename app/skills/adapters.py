"""Provider/adaptor interfaces for Document and Calendar integrations.

Per §12 and §26 of the Master Specification:
  * External credentials/platform APIs are accessed through clean
    provider interfaces.
  * We never invent fake successful external operations — production
    integrations require real configuration.
  * ``FakeDocumentProvider`` / ``FakeCalendarProvider`` are used by
    tests and by the local-fallback path when real integrations are
    not configured.  They operate deterministically on in-memory data
    and never claim to have called real Google / Microsoft / Notion
    services.
"""

from __future__ import annotations

import datetime
import enum
from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID, uuid4

from app.enums import SourceType, TrustLevel


# ---------------------------------------------------------------------------
# Document
# ---------------------------------------------------------------------------


class DocumentFormat(str, enum.Enum):
    PLAIN_TEXT = "text/plain"
    MARKDOWN = "text/markdown"
    PDF = "application/pdf"
    DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@dataclass
class DocumentHandle:
    document_id: UUID
    title: str
    format: DocumentFormat
    content_preview: str
    source_ref: str
    trust_level: TrustLevel = TrustLevel.UNTRUSTED
    retrieved_at: datetime.datetime = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
    )
    size_bytes: int = 0
    content: str | None = None
    """Full content — only populated for FakeDocumentProvider / tests.
    Production adapters should read via streaming where possible."""


class DocumentProvider(Protocol):
    """Typed interface for Document Skill integrations (§12.3)."""

    def list_supported_sources(self) -> list[SourceType]: ...

    async def get_document(self, source_ref: str) -> DocumentHandle | None: ...

    async def read_content(self, handle: DocumentHandle, max_chars: int = 50000) -> str: ...


class FakeDocumentProvider:
    """Deterministic in-memory DocumentProvider — tests / offline MVP.

    Never claims to have contacted a real external service.
    """

    def __init__(self, documents: list[DocumentHandle] | None = None) -> None:
        self._docs: dict[str, DocumentHandle] = {}
        if documents is None:
            documents = [
                DocumentHandle(
                    document_id=uuid4(),
                    title="Sample Research Paper Draft",
                    format=DocumentFormat.MARKDOWN,
                    content_preview=(
                        "# Sample Paper\n\n"
                        "## Introduction\n"
                        "This paper discusses the structure and contents of a typical "
                        "research document. It covers methodology, results, and a "
                        "conclusion. The next step is final polishing before submission."
                    ),
                    source_ref="memory://research_paper_draft.md",
                    size_bytes=2048,
                    content=(
                        "# Sample Paper\n\n"
                        "## Introduction\n"
                        "This paper discusses the structure and contents of a typical "
                        "research document. It covers methodology, results, and a "
                        "conclusion. The next step is final polishing before submission.\n\n"
                        "## Methodology\n"
                        "We followed a standard iterative approach with weekly reviews.\n\n"
                        "## Results\n"
                        "Key findings include improved clarity and a consistent structure.\n\n"
                        "## Conclusion\n"
                        "Revise for clarity, add citations, then submit."
                    ),
                )
            ]
        for d in documents:
            self._docs[d.source_ref] = d

    def list_supported_sources(self) -> list[SourceType]:
        return [SourceType.DOCUMENT]

    async def get_document(self, source_ref: str) -> DocumentHandle | None:
        if not self._docs:
            first = next(iter(self._docs.values())) if self._docs else None
            return first
        return self._docs.get(source_ref) or next(iter(self._docs.values()))

    async def read_content(self, handle: DocumentHandle, max_chars: int = 50000) -> str:
        if handle.content is not None:
            return handle.content[:max_chars]
        return handle.content_preview[:max_chars]


# ---------------------------------------------------------------------------
# Calendar
# ---------------------------------------------------------------------------


@dataclass
class CalendarEvent:
    event_id: str
    title: str
    start_at: datetime.datetime
    end_at: datetime.datetime
    all_day: bool = False
    location: str | None = None
    description: str | None = None
    reminders: list[int] = field(default_factory=list)
    """Reminder offsets in minutes before start_at."""


class CalendarProvider(Protocol):
    """Typed interface for Calendar Skill integrations (§12.3)."""

    async def list_events(
        self,
        window_start: datetime.datetime,
        window_end: datetime.datetime,
    ) -> list[CalendarEvent]: ...

    async def create_event(
        self,
        title: str,
        start_at: datetime.datetime,
        end_at: datetime.datetime,
        *,
        reminder_minutes: int | None = 15,
        all_day: bool = False,
        location: str | None = None,
        description: str | None = None,
    ) -> CalendarEvent: ...

    async def get_event(self, event_id: str) -> CalendarEvent | None: ...


class FakeCalendarProvider:
    """Deterministic in-memory CalendarProvider — tests / offline MVP.

    Never claims to have contacted Google Calendar / Outlook / etc.
    All operations happen in-memory only and are scoped to this
    instance's lifetime.
    """

    def __init__(self, events: list[CalendarEvent] | None = None) -> None:
        self._events: dict[str, CalendarEvent] = {}
        if events is None:
            now = datetime.datetime.now(datetime.timezone.utc).replace(
                minute=0, second=0, microsecond=0
            )
            events = [
                CalendarEvent(
                    event_id="evt-fake-1",
                    title="Standup Meeting",
                    start_at=now + datetime.timedelta(hours=2),
                    end_at=now + datetime.timedelta(hours=2, minutes=30),
                    location="Team Room",
                )
            ]
        for e in events:
            self._events[e.event_id] = e

    async def list_events(
        self,
        window_start: datetime.datetime,
        window_end: datetime.datetime,
    ) -> list[CalendarEvent]:
        results: list[CalendarEvent] = []
        for e in self._events.values():
            if e.start_at >= window_start and e.start_at <= window_end:
                results.append(e)
        results.sort(key=lambda e: e.start_at)
        return results

    async def create_event(
        self,
        title: str,
        start_at: datetime.datetime,
        end_at: datetime.datetime,
        *,
        reminder_minutes: int | None = 15,
        all_day: bool = False,
        location: str | None = None,
        description: str | None = None,
    ) -> CalendarEvent:
        event_id = f"evt-fake-{uuid4().hex[:12]}"
        ev = CalendarEvent(
            event_id=event_id,
            title=title,
            start_at=start_at,
            end_at=end_at,
            all_day=all_day,
            location=location,
            description=description,
            reminders=[reminder_minutes] if reminder_minutes is not None else [],
        )
        self._events[ev.event_id] = ev
        return ev

    async def get_event(self, event_id: str) -> CalendarEvent | None:
        return self._events.get(event_id)


__all__ = [
    "CalendarEvent",
    "CalendarProvider",
    "DocumentFormat",
    "DocumentHandle",
    "DocumentProvider",
    "FakeCalendarProvider",
    "FakeDocumentProvider",
]
