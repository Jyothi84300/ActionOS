"""Phase 3 — Model / AI Layer.

Provider-neutral model architecture per §18 of the Master Specification
and ADR-005.  Exposes a typed ModelProvider Protocol, request/response
models, a ModelRouter, and structured output validation.

The Agent Core (app.agent.*) depends only on ModelProvider and the
router — never on a specific vendor SDK.
"""

from app.model.errors import (
    ModelError,
    ModelProviderError,
    ModelValidationError,
    ModelRateLimitError,
    ModelTimeoutError,
    ModelConfigurationError,
)
from app.model.provider import (
    ModelProvider,
    ModelProviderInfo,
    ProviderCapability,
    ProviderTier,
)
from app.model.router import (
    ModelRouter,
    ModelRoutingDecision,
    RoutingReason,
    RoutingStrategy,
    default_model_router,
)
from app.model.types import (
    ChatMessage,
    ChatRole,
    ModelFinishReason,
    ModelRequest,
    ModelResponse,
    ModelUsage,
    StructuredOutputMode,
)
from app.model.validation import (
    StructuredOutputValidator,
    validate_structured_output,
)

__all__ = [
    "ChatMessage",
    "ChatRole",
    "ModelError",
    "ModelFinishReason",
    "ModelProvider",
    "ModelProviderError",
    "ModelProviderInfo",
    "ModelRateLimitError",
    "ModelRequest",
    "ModelResponse",
    "ModelRouter",
    "ModelRoutingDecision",
    "ModelTimeoutError",
    "ModelUsage",
    "ModelValidationError",
    "ModelConfigurationError",
    "ProviderCapability",
    "ProviderTier",
    "RoutingReason",
    "RoutingStrategy",
    "StructuredOutputMode",
    "StructuredOutputValidator",
    "default_model_router",
    "validate_structured_output",
]
