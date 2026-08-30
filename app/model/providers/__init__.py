"""Concrete ModelProvider implementations.

  * :class:`FakeModelProvider` — deterministic, no network.  Always
    available.  Used by tests and as the fallback when no cloud
    credentials are configured.
  * :class:`GenericCloudProvider` — adapter for HTTP-based cloud LLMs.
    Concrete providers (OpenAI, Anthropic, etc.) inherit from this.
  * :class:`OpenAICloudProvider` — OpenAI-compatible REST adapter.
    Requires ``OPENAI_API_KEY`` env var; otherwise ``available=False``.
"""

from app.model.providers.fake_provider import (
    FakeModelProvider,
    DeterministicResponse,
    DEFAULT_FAKE_RESPONSES,
)
from app.model.providers.cloud_provider import (
    GenericCloudProvider,
    OpenAICloudProvider,
    build_cloud_provider_from_env,
)

__all__ = [
    "FakeModelProvider",
    "DeterministicResponse",
    "DEFAULT_FAKE_RESPONSES",
    "GenericCloudProvider",
    "OpenAICloudProvider",
    "build_cloud_provider_from_env",
]
