"""Capability Router — LOCAL / ONLINE / PARTIAL classification.

Per §7 of the Master Specification:
  * The router MUST NOT simply check internet availability.
  * It MUST evaluate the actual capability requirements of the task:
      - which skills/tools it needs
      - whether those are local-capable
      - whether the required reasoning is local-supported

For the MVP (no real model selection), classification is driven by the
skill/tool capability metadata supplied by the caller and by intent
patterns mapped to online-required domains (e.g. live weather lookup,
email send).
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from app.agent.schemas import (
    CapabilityAssessment,
    CapabilityRouterInput,
    CapabilityRouterResult,
)
from app.enums import (
    CapabilityRoute,
    SkillCapability,
    SourceType,
    ToolCapability,
)
from app.logging_config import get_logger

logger = get_logger(__name__)


ONLINE_REQUIRED_INTENTS: frozenset[str] = frozenset(
    {
        "email.send",
        "email.search",
        "weather.lookup",
        "web.search",
        "web.fetch",
        "message.send",
        "cloud_storage.read",
        "cloud_storage.write",
    }
)

ONLINE_REQUIRED_SOURCES: frozenset[SourceType] = frozenset(
    {SourceType.EMAIL, SourceType.WEB}
)


class CapabilityRouter(Protocol):
    async def route(self, input_: CapabilityRouterInput) -> CapabilityRouterResult: ...


class RuleBasedCapabilityRouter:
    """Deterministic Capability Router for the MVP.

    Classification rules (in priority order):
      1. Any ONLINE_REQUIRED_INTENT matched → ONLINE.
      2. Any ONLINE_REQUIRED_SOURCES present and permissioned → ONLINE.
      3. Mixed LOCAL + ONLINE requirements across referenced skill caps → PARTIAL.
      4. All referenced skill caps are LOCAL/BOTH → LOCAL.

    Skill/tool capability dictionaries are passed via the
    `assess_against_manifest` helper or left empty; when empty the
    router uses a conservative default that treats BOTH as LOCAL for
    planning purposes (the planner can later refine per-task).
    """

    async def route(self, input_: CapabilityRouterInput) -> CapabilityRouterResult:
        intents = list(input_.parsed_goal.intents or [])
        reasons: list[str] = []
        skill_caps: dict[UUID, SkillCapability] = {}
        tool_caps: dict[UUID, ToolCapability] = {}

        needs_online = False
        if any(i in ONLINE_REQUIRED_INTENTS for i in intents):
            needs_online = True
            matched = [i for i in intents if i in ONLINE_REQUIRED_INTENTS]
            reasons.append(f"Online-required intent matched: {matched}.")

        missing_sources = set(input_.context.missing_permissions)
        source_types_present = {ref.source_type for ref in input_.context.references} | missing_sources
        online_sources = source_types_present & ONLINE_REQUIRED_SOURCES
        if online_sources:
            needs_online = True
            reasons.append(f"Online-only context sources referenced: {sorted(s.value for s in online_sources)}.")

        local_eligible = True
        if needs_online:
            local_eligible = False
            reasons.append("Local route ineligible: task requires online-only capability.")

        partial_eligible = (not needs_online) and (len(intents) > 1 or len(source_types_present) > 1)
        if partial_eligible:
            reasons.append("Partial-offline candidate: multiple phases or sources involved.")

        if needs_online:
            final_route = CapabilityRoute.ONLINE
        elif partial_eligible:
            final_route = CapabilityRoute.PARTIAL
        else:
            final_route = CapabilityRoute.LOCAL

        assessment = CapabilityAssessment(
            capability_route=final_route,
            required_skill_capabilities=skill_caps,
            required_tool_capabilities=tool_caps,
            local_eligible=local_eligible,
            online_required=needs_online,
            partial_offline_eligible=partial_eligible,
            reasons=reasons,
        )

        logger.info(
            "agent.capability.routed",
            user_id=str(input_.user_id),
            route=final_route.value,
            intents_count=len(intents),
        )

        return CapabilityRouterResult(user_id=input_.user_id, assessment=assessment)


def assess_against_manifest(
    assessment: CapabilityAssessment,
    skill_id: UUID,
    skill_cap: SkillCapability,
) -> CapabilityAssessment:
    """Refine an assessment with concrete Skill manifest metadata.

    This helper is used when skill registries are consulted during or
    after planning.  It mutates and returns the assessment so that
    PARTIAL classification can be derived from mixed LOCAL/ONLINE
    skills within a single plan.
    """
    assessment.required_skill_capabilities[skill_id] = skill_cap

    any_online = any(c == SkillCapability.ONLINE for c in assessment.required_skill_capabilities.values())
    any_local = any(c in {SkillCapability.LOCAL, SkillCapability.BOTH} for c in assessment.required_skill_capabilities.values())
    all_local = all(c in {SkillCapability.LOCAL, SkillCapability.BOTH} for c in assessment.required_skill_capabilities.values())

    if any_online and any_local:
        assessment.capability_route = CapabilityRoute.PARTIAL
        assessment.partial_offline_eligible = True
        assessment.online_required = True
        assessment.local_eligible = False
    elif all_local:
        assessment.capability_route = CapabilityRoute.LOCAL
        assessment.local_eligible = True
        assessment.online_required = False
    elif any_online:
        assessment.capability_route = CapabilityRoute.ONLINE
        assessment.online_required = True
        assessment.local_eligible = False

    return assessment


def default_capability_router() -> CapabilityRouter:
    return RuleBasedCapabilityRouter()


__all__ = [
    "CapabilityRouter",
    "RuleBasedCapabilityRouter",
    "default_capability_router",
    "assess_against_manifest",
    "ONLINE_REQUIRED_INTENTS",
    "ONLINE_REQUIRED_SOURCES",
]
