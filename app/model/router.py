"""Model Router — selects LOCAL vs CLOUD provider per §18.

Routing is driven by:
  * Provider availability (credentials / runtime present)
  * Capability requirements (e.g. deep reasoning vs low latency)
  * Task complexity
  * Privacy requirements

The Router NEVER calls the model itself; it returns a
:class:`ModelRoutingDecision` the caller uses to pick a concrete
:class:`ModelProvider`.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Iterable
from uuid import UUID

from app.logging_config import get_logger
from app.model.provider import (
    ModelProvider,
    ModelProviderInfo,
    ProviderCapability,
    ProviderTier,
)
from app.model.types import ModelRequest

logger = get_logger(__name__)


class RoutingStrategy(str, enum.Enum):
    AUTO = "auto"
    PREFER_LOCAL = "prefer_local"
    PREFER_CLOUD = "prefer_cloud"
    FORCE_LOCAL = "force_local"
    FORCE_CLOUD = "force_cloud"


class RoutingReason(str, enum.Enum):
    FORCED = "forced"
    STRATEGY_PREFERENCE = "strategy_preference"
    CAPABILITY_MATCH = "capability_match"
    UNAVAILABLE_FALLBACK = "unavailable_fallback"
    PRIVACY_REQUIREMENT = "privacy_requirement"


@dataclass
class ModelRoutingDecision:
    provider_name: str
    tier: ProviderTier
    reasons: list[RoutingReason] = field(default_factory=list)
    provider_info: ModelProviderInfo | None = None


class ModelRouter:
    """Selects the best available ModelProvider for a given request.

    The router is stateless and safe to share across requests.
    """

    def __init__(
        self,
        providers: Iterable[ModelProvider],
        *,
        default_strategy: RoutingStrategy = RoutingStrategy.AUTO,
        privacy_first: bool = True,
    ) -> None:
        self._providers: dict[str, ModelProvider] = {}
        for p in providers:
            info = p.info()
            self._providers[info.name] = p
        self._default_strategy = default_strategy
        self._privacy_first = privacy_first

    @property
    def providers(self) -> dict[str, ModelProvider]:
        return dict(self._providers)

    def list_available(self) -> list[ModelProviderInfo]:
        return [p.info() for p in self._providers.values() if p.info().available]

    def select(
        self,
        request: ModelRequest,
        *,
        strategy: RoutingStrategy | None = None,
        required_capabilities: Iterable[ProviderCapability] | None = None,
    ) -> ModelRoutingDecision:
        strategy = strategy or self._default_strategy
        required = set(required_capabilities or ())
        reasons: list[RoutingReason] = []

        all_info = [(name, p.info()) for name, p in self._providers.items()]
        available = [(n, i) for n, i in all_info if i.available]

        if not available:
            raise RuntimeError(
                "No available ModelProviders are registered. "
                "At minimum, configure the built-in `fake` provider."
            )

        # Filter by capability
        def meets_caps(info: ModelProviderInfo) -> bool:
            if not required:
                return True
            return required.issubset(set(info.capabilities))

        capable = [(n, i) for n, i in available if meets_caps(i)]
        pool = capable if capable else available
        if not capable and required:
            reasons.append(RoutingReason.UNAVAILABLE_FALLBACK)

        locals_ = [(n, i) for n, i in pool if i.tier == ProviderTier.LOCAL]
        clouds = [(n, i) for n, i in pool if i.tier == ProviderTier.CLOUD]

        if strategy == RoutingStrategy.FORCE_LOCAL:
            if locals_:
                reasons.append(RoutingReason.FORCED)
                return self._build_decision(locals_, reasons)
            raise RuntimeError("FORCE_LOCAL strategy but no LOCAL provider is available.")

        if strategy == RoutingStrategy.FORCE_CLOUD:
            if clouds:
                reasons.append(RoutingReason.FORCED)
                return self._build_decision(clouds, reasons)
            raise RuntimeError("FORCE_CLOUD strategy but no CLOUD provider is available.")

        if self._privacy_first and strategy in (
            RoutingStrategy.AUTO,
            RoutingStrategy.PREFER_LOCAL,
        ):
            if locals_:
                reasons.append(
                    RoutingReason.PRIVACY_REQUIREMENT
                    if self._privacy_first
                    else RoutingReason.STRATEGY_PREFERENCE
                )
                return self._build_decision(locals_, reasons)

        if strategy == RoutingStrategy.PREFER_CLOUD and clouds:
            reasons.append(RoutingReason.STRATEGY_PREFERENCE)
            return self._build_decision(clouds, reasons)

        if clouds:
            reasons.append(RoutingReason.CAPABILITY_MATCH)
            return self._build_decision(clouds, reasons)

        reasons.append(RoutingReason.UNAVAILABLE_FALLBACK)
        return self._build_decision(pool, reasons)

    def get_provider(self, name: str) -> ModelProvider:
        if name not in self._providers:
            raise KeyError(f"Unknown ModelProvider name: {name!r}")
        return self._providers[name]

    # -- internal -------------------------------------------------------

    @staticmethod
    def _build_decision(
        pool: list[tuple[str, ModelProviderInfo]],
        reasons: list[RoutingReason],
    ) -> ModelRoutingDecision:
        name, info = pool[0]
        return ModelRoutingDecision(
            provider_name=name,
            tier=info.tier,
            reasons=list(reasons),
            provider_info=info,
        )


def default_model_router() -> ModelRouter:
    """Default router including the deterministic fake provider.

    Additional providers (OpenAI, Anthropic, etc.) are added to this
    router at application startup based on environment variables — see
    ``app.model.providers``.
    """
    from app.model.providers.fake_provider import FakeModelProvider

    return ModelRouter(providers=[FakeModelProvider()])
