"""Deterministic FakeModelProvider — no network, always available.

Serves as:
  * The fallback when external credentials are missing (Phase 3
    requirement that the app still starts).
  * The provider used by the existing 90-test baseline so no external
    credentials are required in CI / local dev.

Response selection is driven by a simple keyword match on the LAST
user message, allowing callers (e.g. tests) to exercise different
code paths deterministically.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Callable

from app.model.errors import ModelValidationError
from app.model.provider import (
    ModelProvider,
    ModelProviderInfo,
    ProviderCapability,
    ProviderTier,
)
from app.model.types import (
    ChatRole,
    ModelFinishReason,
    ModelRequest,
    ModelResponse,
    ModelUsage,
    StructuredOutputMode,
)
from app.model.validation import validate_structured_output


@dataclass
class DeterministicResponse:
    keywords: tuple[str, ...]
    """Trigger keywords — if ALL appear in the last user message, this
    response is selected."""
    content: str
    finish_reason: ModelFinishReason = ModelFinishReason.STOP
    usage: ModelUsage = field(default_factory=lambda: ModelUsage(prompt_tokens=10, completion_tokens=20, total_tokens=30))


DEFAULT_FAKE_RESPONSES: tuple[DeterministicResponse, ...] = (
    DeterministicResponse(
        keywords=("summarize", "document"),
        content=json.dumps(
            {
                "summary": "This is a deterministic fake document summary.",
                "key_points": [
                    "The document discusses project goals.",
                    "Next steps are outlined.",
                ],
                "word_count": 42,
            }
        ),
    ),
    DeterministicResponse(
        keywords=("create", "task"),
        content=json.dumps(
            {
                "created": True,
                "task_title": "New task",
                "due_date": None,
                "priority": "medium",
            }
        ),
    ),
    DeterministicResponse(
        keywords=("calendar", "reminder"),
        content=json.dumps(
            {
                "event_id": "evt-fake-123",
                "title": "Reminder",
                "start_at": "2026-09-05T09:00:00Z",
            }
        ),
    ),
    DeterministicResponse(
        keywords=("error",),
        content="I cannot help with that request.",
        finish_reason=ModelFinishReason.CONTENT_FILTER,
    ),
    DeterministicResponse(
        keywords=("invalid_json",),
        content="{this is not valid json",
    ),
)


class FakeModelProvider:
    """Deterministic, in-process ModelProvider — always available."""

    name: str = "fake"
    tier: ProviderTier = ProviderTier.LOCAL

    def __init__(
        self,
        responses: tuple[DeterministicResponse, ...] | None = None,
        default_content: str
        | Callable[[ModelRequest], str] = '{"message": "deterministic fake response"}',
        *,
        model_name: str = "fake-deterministic-v1",
    ) -> None:
        self._responses = responses or DEFAULT_FAKE_RESPONSES
        self._default_content = default_content
        self._model_name = model_name

    # ------------------------------------------------------------------
    # ModelProvider protocol
    # ------------------------------------------------------------------

    def info(self) -> ModelProviderInfo:
        return ModelProviderInfo(
            name=self.name,
            tier=self.tier,
            model_name=self._model_name,
            capabilities=(
                ProviderCapability.STRUCTURED_JSON,
                ProviderCapability.LOW_LATENCY,
            ),
            available=True,
        )

    async def generate(self, request: ModelRequest) -> ModelResponse:
        last_user = self._last_user_message(request)
        selected = self._select_response(last_user)

        if isinstance(selected, DeterministicResponse):
            content = selected.content
            finish = selected.finish_reason
            usage = selected.usage
        else:
            # selected is the fallback default_content — either a str
            # or a callable (ModelRequest) -> str.
            if callable(self._default_content):
                content = self._default_content(request)
            else:
                content = self._default_content  # type: ignore[assignment]
            finish = ModelFinishReason.STOP
            usage = None

        if request.structured_output_mode != StructuredOutputMode.NONE:
            try:
                validate_structured_output(
                    content,
                    request.expected_output_schema or dict,
                    request_id=request.request_id,
                    provider_name=self.name,
                )
            except ModelValidationError:
                raise

        usage_obj: ModelUsage
        if usage is not None:
            usage_obj = usage
        else:
            usage_obj = ModelUsage(
                prompt_tokens=max(1, len(last_user) // 4),
                completion_tokens=max(1, len(content) // 4),
            )
            usage_obj.total_tokens = usage_obj.prompt_tokens + usage_obj.completion_tokens

        matched_keywords = (
            selected.keywords if isinstance(selected, DeterministicResponse) else None
        )

        return ModelResponse(
            content=content,
            finish_reason=finish,
            usage=usage_obj,
            model_name=self._model_name,
            provider_name=self.name,
            request_id=request.request_id,
            raw={"matched_keywords": matched_keywords},
        )

    # ------------------------------------------------------------------
    # internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _last_user_message(request: ModelRequest) -> str:
        for msg in reversed(request.messages):
            if msg.role == ChatRole.USER:
                return msg.content or ""
        return ""

    def _select_response(self, text: str) -> DeterministicResponse | object:
        lowered = text.lower()
        for resp in self._responses:
            if all(kw in lowered for kw in resp.keywords):
                return resp
        return self._default_content
