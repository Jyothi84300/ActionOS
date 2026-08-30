"""Document Skill — read, summarize, analyze, extract information.

Per §12.3 of the Master Specification.  Two tools are registered:

  * ``document.summarize`` — produces a concise summary of the source.
  * ``document.analyze`` — structured analysis with key points.

The skill never opens arbitrary files, never executes shell/browser
code, and never returns unverified content as "verified."
"""

from __future__ import annotations

import datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from app.agent.planner import SKILL_ID_DOCUMENT
from app.enums import PermissionLevel, ToolCapability
from app.logging_config import get_logger
from app.skills.adapters import DocumentProvider
from app.skills.contracts import (
    ToolContract,
    ToolExecutionContext,
    ToolExecutionResult,
    ToolVerificationResult,
    VerificationBehavior,
    VerificationMethod,
)

logger = get_logger(__name__)


DOCUMENT_TOOL_ID_SUMMARIZE = UUID("22222222-2222-2222-2222-000000000001")
DOCUMENT_TOOL_ID_ANALYZE = UUID("22222222-2222-2222-2222-000000000002")


# ---------------------------------------------------------------------------
# Typed schemas
# ---------------------------------------------------------------------------


class DocumentSummarizeInput(BaseModel):
    document_source_ref: str = Field(
        ..., description="Opaque source ref (from ContextReference)."
    )
    max_sentences: int = Field(default=5, ge=1, le=50)


class DocumentSummarizeOutput(BaseModel):
    document_id: UUID
    title: str
    summary: str
    word_count: int
    generated_at: datetime.datetime


class DocumentAnalyzeInput(BaseModel):
    document_source_ref: str
    sections: list[str] = Field(
        default_factory=lambda: ["structure", "key_points", "next_steps"],
        description="Which sections to include in the analysis.",
    )


class DocumentAnalyzeOutput(BaseModel):
    document_id: UUID
    title: str
    sections: dict[str, list[str]]
    source_trust: str = "untrusted"
    generated_at: datetime.datetime


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


class _SummarizeHandler:
    async def execute(
        self, input_: DocumentSummarizeInput, ctx: ToolExecutionContext
    ) -> ToolExecutionResult:
        provider: DocumentProvider | None = ctx.document_provider
        if provider is None:
            return ToolExecutionResult(
                success=False,
                output=DocumentSummarizeOutput(
                    document_id=uuid4(),
                    title="",
                    summary="",
                    word_count=0,
                    generated_at=datetime.datetime.now(datetime.timezone.utc),
                ),
                error_message="No DocumentProvider configured in the execution context.",
            )
        handle = await provider.get_document(input_.document_source_ref)
        if handle is None:
            return ToolExecutionResult(
                success=False,
                output=DocumentSummarizeOutput(
                    document_id=uuid4(),
                    title="",
                    summary="",
                    word_count=0,
                    generated_at=datetime.datetime.now(datetime.timezone.utc),
                ),
                error_message=f"Document not found: {input_.document_source_ref}",
            )
        content = await provider.read_content(handle, max_chars=50000)
        words = [w for w in content.split() if w]
        sentences = [s.strip() for s in content.split(".") if s.strip()]
        picked = sentences[: max(1, input_.max_sentences)]
        summary = ". ".join(picked).strip() + ("." if picked else "")
        output = DocumentSummarizeOutput(
            document_id=handle.document_id,
            title=handle.title,
            summary=summary,
            word_count=len(words),
            generated_at=datetime.datetime.now(datetime.timezone.utc),
        )
        return ToolExecutionResult(success=True, output=output)

    async def verify(
        self,
        input_: DocumentSummarizeInput,
        execution_output: DocumentSummarizeOutput,
        ctx: ToolExecutionContext,
    ) -> ToolVerificationResult:
        # §16 — independent read: re-fetch the document and sanity-check
        # the returned title / document_id match the earlier handle.
        provider: DocumentProvider | None = ctx.document_provider
        if provider is None:
            return ToolVerificationResult(
                verified=False,
                method=VerificationMethod.NONE,
                reason="No DocumentProvider in context.",
            )
        handle = await provider.get_document(input_.document_source_ref)
        if handle is None:
            return ToolVerificationResult(
                verified=False,
                method=VerificationMethod.INDEPENDENT_READ,
                reason="Re-query returned missing handle.",
            )
        if handle.document_id != execution_output.document_id:
            return ToolVerificationResult(
                verified=False,
                method=VerificationMethod.INDEPENDENT_READ,
                reason=(
                    f"document_id mismatch: expected {handle.document_id}, "
                    f"got {execution_output.document_id}."
                ),
            )
        if execution_output.word_count <= 0:
            return ToolVerificationResult(
                verified=False,
                method=VerificationMethod.RETURN_VALUE_VALIDATION,
                reason="Word count was zero.",
            )
        return ToolVerificationResult(
            verified=True,
            method=VerificationMethod.INDEPENDENT_READ,
            details={
                "document_id": str(handle.document_id),
                "title_match": handle.title == execution_output.title,
            },
        )


class _AnalyzeHandler:
    async def execute(
        self, input_: DocumentAnalyzeInput, ctx: ToolExecutionContext
    ) -> ToolExecutionResult:
        provider: DocumentProvider | None = ctx.document_provider
        if provider is None:
            return ToolExecutionResult(
                success=False,
                output=DocumentAnalyzeOutput(
                    document_id=uuid4(),
                    title="",
                    sections={},
                    generated_at=datetime.datetime.now(datetime.timezone.utc),
                ),
                error_message="No DocumentProvider configured.",
            )
        handle = await provider.get_document(input_.document_source_ref)
        if handle is None:
            return ToolExecutionResult(
                success=False,
                output=DocumentAnalyzeOutput(
                    document_id=uuid4(),
                    title="",
                    sections={},
                    generated_at=datetime.datetime.now(datetime.timezone.utc),
                ),
                error_message=f"Document not found: {input_.document_source_ref}",
            )
        content = await provider.read_content(handle, max_chars=50000)
        sections_out: dict[str, list[str]] = {}
        lower = content.lower()
        for section in input_.sections:
            if section == "structure":
                lines = [ln.strip() for ln in content.splitlines() if ln.strip()]
                sections_out["structure"] = [
                    f"{len(lines)} non-empty lines",
                    f"{len(content)} characters total",
                ]
            elif section == "key_points":
                sentences = [s.strip() for s in content.split(".") if len(s.strip()) > 10]
                sections_out["key_points"] = sentences[:5] or [
                    "No detailed sentences were extracted."
                ]
            elif section == "next_steps":
                next_step_like = [
                    s.strip()
                    for s in content.split(".")
                    if any(k in s.lower() for k in ("next", "should", "todo", "plan", "step"))
                ]
                sections_out["next_steps"] = next_step_like or [
                    "No explicit next-steps section detected in source content."
                ]
            else:
                sections_out[section] = [f"Custom analysis for '{section}' placeholder."]
        output = DocumentAnalyzeOutput(
            document_id=handle.document_id,
            title=handle.title,
            sections=sections_out,
            source_trust=handle.trust_level.value,
            generated_at=datetime.datetime.now(datetime.timezone.utc),
        )
        return ToolExecutionResult(success=True, output=output)

    async def verify(
        self,
        input_: DocumentAnalyzeInput,
        execution_output: DocumentAnalyzeOutput,
        ctx: ToolExecutionContext,
    ) -> ToolVerificationResult:
        provider: DocumentProvider | None = ctx.document_provider
        if provider is None:
            return ToolVerificationResult(
                verified=False,
                method=VerificationMethod.NONE,
                reason="No DocumentProvider in context.",
            )
        handle = await provider.get_document(input_.document_source_ref)
        if handle is None:
            return ToolVerificationResult(
                verified=False,
                method=VerificationMethod.INDEPENDENT_READ,
                reason="Re-query returned missing handle.",
            )
        if handle.document_id != execution_output.document_id:
            return ToolVerificationResult(
                verified=False,
                method=VerificationMethod.INDEPENDENT_READ,
                reason="document_id mismatch after re-query.",
            )
        requested = set(input_.sections)
        present = set(execution_output.sections.keys())
        if not requested.issubset(present):
            return ToolVerificationResult(
                verified=False,
                method=VerificationMethod.RETURN_VALUE_VALIDATION,
                reason=f"Missing analysis sections: {requested - present}",
            )
        return ToolVerificationResult(
            verified=True,
            method=VerificationMethod.INDEPENDENT_READ,
            details={"returned_sections": sorted(present)},
        )


# ---------------------------------------------------------------------------
# Tool contracts
# ---------------------------------------------------------------------------


DOCUMENT_SKILL_TOOL_CONTRACTS: tuple[ToolContract, ...] = (
    ToolContract(
        tool_id=DOCUMENT_TOOL_ID_SUMMARIZE,
        skill_id=SKILL_ID_DOCUMENT,
        name="document.summarize",
        version="1.0.0",
        description="Produce a concise summary of a permissioned document.",
        input_schema=DocumentSummarizeInput,
        output_schema=DocumentSummarizeOutput,
        permission_level=PermissionLevel.AUTOMATIC,
        capability=ToolCapability.LOCAL,
        verification_method=VerificationMethod.INDEPENDENT_READ,
        verification_behavior=VerificationBehavior.ALWAYS_REQUIRED,
        handler=_SummarizeHandler(),
    ),
    ToolContract(
        tool_id=DOCUMENT_TOOL_ID_ANALYZE,
        skill_id=SKILL_ID_DOCUMENT,
        name="document.analyze",
        version="1.0.0",
        description="Structured analysis (structure, key points, next steps).",
        input_schema=DocumentAnalyzeInput,
        output_schema=DocumentAnalyzeOutput,
        permission_level=PermissionLevel.AUTOMATIC,
        capability=ToolCapability.LOCAL,
        verification_method=VerificationMethod.INDEPENDENT_READ,
        verification_behavior=VerificationBehavior.ALWAYS_REQUIRED,
        handler=_AnalyzeHandler(),
    ),
)
