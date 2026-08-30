"""Context Retrieval interface.

Defines the ContextRetriever Protocol and provides a stub MVP
implementation.  Real calendar/document integrations are out of scope
for Phase 2 (per user constraints); this module exposes a narrow,
permission-gated interface and validates every reference it returns.

Enforces:
  * No source is read without an explicit grant (permission-aware callers
    supply allowed_source_types).
  * Returned excerpts are bounded in length; no full-content dumping.
  * All content is marked UNTRUSTED per §10.2 of the Master Spec.
"""

from __future__ import annotations

import datetime
from typing import Protocol
from uuid import UUID, uuid4

from app.agent.schemas import (
    ContextReference,
    ContextRetrievalRequest,
    ContextRetrievalResult,
)
from app.enums import SourceType, TrustLevel
from app.logging_config import get_logger

logger = get_logger(__name__)


ALLOWED_SOURCE_TYPES_DEFAULT: frozenset[SourceType] = frozenset(
    {SourceType.DOCUMENT, SourceType.CALENDAR, SourceType.TASK}
)

MAX_EXCERPT_LENGTH = 2000
MAX_REFERENCES_PER_SOURCE = 10


class ContextRetriever(Protocol):
    async def retrieve(self, request: ContextRetrievalRequest) -> ContextRetrievalResult: ...


class StubContextRetriever:
    """MVP stub that never reaches real external systems.

    A real implementation would swap this out for adapters that
    query the local document store, calendar provider, etc., gated by
    the Permission Engine.  This stub validates the request shape,
    honors allowed_source_types, and returns a stable empty result so
    the rest of the pipeline can proceed without real integrations.
    """

    async def retrieve(self, request: ContextRetrievalRequest) -> ContextRetrievalResult:
        allowed: set[SourceType] = set(request.allowed_source_types) or set(
            ALLOWED_SOURCE_TYPES_DEFAULT
        )

        references: list[ContextReference] = []
        missing: list[SourceType] = []

        requested_hints = _intent_based_source_hints(request.parsed_goal.intents)
        for st in requested_hints:
            if st not in allowed:
                missing.append(st)

        references.extend(
            _build_stub_references_for(allowed, request, count=0)
        )

        for ref in references:
            if len(ref.excerpt) > MAX_EXCERPT_LENGTH:
                ref.excerpt = ref.excerpt[:MAX_EXCERPT_LENGTH]
            ref.trust_level = TrustLevel.UNTRUSTED

        logger.info(
            "agent.context.retrieved",
            user_id=str(request.user_id),
            references_count=len(references),
            missing_permissions_count=len(missing),
        )

        return ContextRetrievalResult(
            user_id=request.user_id,
            goal_id=request.goal_id,
            references=references,
            missing_permissions=list(dict.fromkeys(missing)),
        )


def _intent_based_source_hints(intents: list[str]) -> list[SourceType]:
    """Map well-known intent labels to context source types."""
    mapping: dict[str, list[SourceType]] = {
        "document.summarize": [SourceType.DOCUMENT],
        "document.analyze": [SourceType.DOCUMENT],
        "task.create": [SourceType.TASK],
        "task.list": [SourceType.TASK],
        "calendar.read": [SourceType.CALENDAR],
        "calendar.create_reminder": [SourceType.CALENDAR],
    }
    out: list[SourceType] = []
    for intent in intents:
        out.extend(mapping.get(intent, []))
    return out


def _build_stub_references_for(
    allowed: set[SourceType],
    request: ContextRetrievalRequest,
    *,
    count: int = 0,
) -> list[ContextReference]:
    """Produce zero or more stub references for validation purposes.

    The MVP returns zero references; the helper exists so tests can
    inject deterministic fake context without calling real providers.
    """
    refs: list[ContextReference] = []
    now = datetime.datetime.now(datetime.timezone.utc)
    sample_sources = [st for st in allowed]
    for i in range(min(count, len(sample_sources) * MAX_REFERENCES_PER_SOURCE)):
        st = sample_sources[i % len(sample_sources)]
        refs.append(
            ContextReference(
                context_id=uuid4(),
                source_type=st,
                source_ref=f"stub://{st.value}/{i}",
                retrieved_at=now,
                trust_level=TrustLevel.UNTRUSTED,
                permission_id=None,
                excerpt="",
            )
        )
    return refs


def default_context_retriever() -> ContextRetriever:
    return StubContextRetriever()


__all__ = [
    "ContextRetriever",
    "StubContextRetriever",
    "default_context_retriever",
    "ALLOWED_SOURCE_TYPES_DEFAULT",
    "MAX_EXCERPT_LENGTH",
]
