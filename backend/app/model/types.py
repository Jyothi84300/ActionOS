"""Typed request / response models for the ModelProvider interface.

Defines provider-neutral data structures that every adapter must
implement and that the Agent Core (app.agent.*) depends on.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4


class ChatRole(str, enum.Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ModelFinishReason(str, enum.Enum):
    STOP = "stop"
    LENGTH = "length"
    TOOL_CALL = "tool_call"
    CONTENT_FILTER = "content_filter"
    ERROR = "error"


class StructuredOutputMode(str, enum.Enum):
    """How the model should format its response.

    Per §18 of the Master Specification, the Planner MUST output
    structured JSON data — never natural-language-only instructions.
    """

    NONE = "none"
    JSON = "json"
    JSON_SCHEMA = "json_schema"


@dataclass(frozen=True)
class ChatMessage:
    role: ChatRole
    content: str
    name: str | None = None
    tool_call_id: str | None = None


@dataclass
class ModelUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelRequest:
    """A provider-neutral request sent to a ModelProvider.

    Attributes:
        messages: The conversation turn list.  The Agent Core composes
            this with clear delimiters around "untrusted content" per
            the prompt-injection defenses in §26.3.
        temperature: Sampling temperature.  Default 0.0 for the planner
            so plans are deterministic where possible.
        max_tokens: Upper bound on output tokens.  None = use default.
        structured_output_mode: Require the model to emit JSON (or a
            schema-validated JSON object).  The Planner always uses
            JSON_SCHEMA.
        expected_output_schema: Pydantic model class OR raw JSON Schema
            dict when ``structured_output_mode=JSON_SCHEMA``.
        stop_sequences: Optional stop strings.
        request_id: Unique identifier for this request — propagated
            into ModelResponse and logs for tracing.
    """

    messages: list[ChatMessage]
    temperature: float = 0.0
    max_tokens: int | None = None
    structured_output_mode: StructuredOutputMode = StructuredOutputMode.NONE
    expected_output_schema: Any = None
    stop_sequences: list[str] | None = None
    request_id: UUID = field(default_factory=uuid4)


@dataclass
class ModelResponse:
    """A provider-neutral response from a ModelProvider.

    Attributes:
        content: Text response body.  When ``structured_output_mode``
            was used, this contains raw JSON text that callers should
            validate via ``validation.validate_structured_output``.
        finish_reason: Why generation stopped.
        usage: Token usage counts.
        model_name: The concrete model identifier that served the
            request (useful for audit/logs).
        provider_name: Identifies the ModelProvider that produced this
            response (``fake``, ``openai``, etc.).
        raw: Optional adapter-specific payload — for debugging only,
            the Agent Core never inspects this field.
    """

    content: str
    finish_reason: ModelFinishReason
    usage: ModelUsage
    model_name: str
    provider_name: str
    request_id: UUID
    raw: dict[str, Any] | None = None
