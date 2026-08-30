"""Provider-neutral ModelProvider Protocol.

Defines the narrow interface the Agent Core and ModelRouter depend on —
per ADR-005 (Provider-Neutral AI), no code outside this package may
import from a specific vendor SDK.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Protocol

from app.model.types import ModelRequest, ModelResponse


class ProviderTier(str, enum.Enum):
    """Whether the provider runs LOCAL or CLOUD per §6 of the spec."""

    LOCAL = "local"
    CLOUD = "cloud"


class ProviderCapability(str, enum.Enum):
    """What this provider can do — informs routing (§18.2)."""

    STRUCTURED_JSON = "structured_json"
    """Able to emit valid JSON reliably."""
    LOW_LATENCY = "low_latency"
    """Suitable for simple, fast operations."""
    DEEP_REASONING = "deep_reasoning"
    """Suitable for complex multi-step planning."""


@dataclass(frozen=True)
class ModelProviderInfo:
    name: str
    """Stable identifier, e.g. ``"fake"``, ``"openai"``."""
    tier: ProviderTier
    model_name: str
    capabilities: tuple[ProviderCapability, ...]
    available: bool
    """True when the provider is callable (credentials / runtime
    present and working)."""


class ModelProvider(Protocol):
    """Provider-neutral model interface.

    Rules enforced by every concrete implementation:
      1. Raises :class:`ModelProviderError` subclasses for failures.
      2. Never imports vendor SDK at module load — only inside ``generate``.
      3. Never logs secrets or raw user payloads in full.
      4. When ``request.structured_output_mode`` is set, returns
         parseable/validated content OR raises ModelValidationError.
    """

    def info(self) -> ModelProviderInfo:
        """Return static metadata about this provider instance."""
        ...

    async def generate(self, request: ModelRequest) -> ModelResponse:
        """Generate a response for the given request."""
        ...
