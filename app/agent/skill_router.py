"""Skill Router — matches plan tasks to registered skills.

Per §12 of the Master Specification:
  * Skills are high-level capability groupings; tools are concrete ops.
  * The Planner selects skills; the Skill Router validates that each
    task references only registered, enabled skills and scores
    candidates so the Executor can pick the best fit when multiple
    skills overlap.
  * The LLM may select from registered tools only — the Skill Router
    never fabricates skill/tool identifiers.

The MVP implementation uses an in-memory registry.  Real deployments
will consult the Skill/SkillVersion/Tool PostgreSQL tables.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Protocol
from uuid import UUID

from app.agent.schemas import (
    SkillMatch,
    SkillRouterInput,
    SkillRouterResult,
)
from app.logging_config import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class RegisteredSkill:
    skill_id: UUID
    name: str
    manifest_version: str
    supported_intents: tuple[str, ...]
    tool_ids: tuple[UUID, ...]


class SkillRegistry(Protocol):
    def list(self) -> Iterable[RegisteredSkill]: ...
    def get(self, skill_id: UUID) -> RegisteredSkill | None: ...


class InMemorySkillRegistry:
    """Static MVP registry matching the Master Spec §12.3 initial skills.

    The three initial skills — Document, Task, Calendar — are loaded
    with stable skill IDs that match `app.agent.planner` constants so
    Planner output can be validated end-to-end without database
    round-trips during Phase 2.
    """

    def __init__(self, skills: Iterable[RegisteredSkill] | None = None) -> None:
        self._skills: dict[UUID, RegisteredSkill] = {}
        if skills is None:
            from app.agent.planner import (
                SKILL_ID_CALENDAR,
                SKILL_ID_DOCUMENT,
                SKILL_ID_TASK,
            )

            skills = [
                RegisteredSkill(
                    skill_id=SKILL_ID_DOCUMENT,
                    name="Document Skill",
                    manifest_version="1.0.0",
                    supported_intents=(
                        "document.summarize",
                        "document.analyze",
                    ),
                    tool_ids=(
                        UUID("22222222-2222-2222-2222-000000000001"),
                        UUID("22222222-2222-2222-2222-000000000002"),
                    ),
                ),
                RegisteredSkill(
                    skill_id=SKILL_ID_TASK,
                    name="Task Skill",
                    manifest_version="1.0.0",
                    supported_intents=(
                        "task.create",
                        "task.list",
                        "task.update",
                        "task.complete",
                    ),
                    tool_ids=(
                        UUID("22222222-2222-2222-2222-000000000003"),
                        UUID("22222222-2222-2222-2222-000000000004"),
                    ),
                ),
                RegisteredSkill(
                    skill_id=SKILL_ID_CALENDAR,
                    name="Calendar Skill",
                    manifest_version="1.0.0",
                    supported_intents=(
                        "calendar.read",
                        "calendar.create_reminder",
                        "calendar.check_deadline",
                    ),
                    tool_ids=(
                        UUID("22222222-2222-2222-2222-000000000005"),
                        UUID("22222222-2222-2222-2222-000000000006"),
                    ),
                ),
            ]
        for s in skills:
            self._skills[s.skill_id] = s

    def list(self) -> Iterable[RegisteredSkill]:
        return list(self._skills.values())

    def get(self, skill_id: UUID) -> RegisteredSkill | None:
        return self._skills.get(skill_id)


class SkillRouter(Protocol):
    async def route(self, input_: SkillRouterInput) -> SkillRouterResult: ...


class IntentScoringSkillRouter:
    """Scores candidates by intent overlap with the plan task.

    Scoring rules for a single task:
      * If the task declares a `required_skill_id` and that skill is
        registered and available, it receives score 1.0 with its
        declared intent counted as matched.
      * Otherwise every registered skill is scored by the ratio of
        matched intents between task and skill manifest.
      * Tasks with zero matches produce an empty candidate list and
        are reported under `unmatched_task_ids`.
    """

    def __init__(self, registry: SkillRegistry | None = None) -> None:
        self._registry = registry or InMemorySkillRegistry()

    async def route(self, input_: SkillRouterInput) -> SkillRouterResult:
        available = set(input_.available_skill_ids) or None
        task_matches: dict[UUID, list[SkillMatch]] = {}
        unmatched: list[UUID] = []

        for task in input_.plan.tasks:
            candidates: list[SkillMatch] = []

            if task.required_skill_id is not None:
                reg = self._registry.get(task.required_skill_id)
                if reg is not None and (available is None or reg.skill_id in available):
                    matched = []
                    if task.required_skill_intent and task.required_skill_intent in reg.supported_intents:
                        matched.append(task.required_skill_intent)
                    candidates.append(
                        SkillMatch(
                            skill_id=reg.skill_id,
                            skill_name=reg.name,
                            manifest_version=reg.manifest_version,
                            score=1.0 if matched else 0.7,
                            matched_intents=matched,
                            tool_ids=list(reg.tool_ids),
                        )
                    )

            if not candidates:
                for reg in self._registry.list():
                    if available is not None and reg.skill_id not in available:
                        continue
                    task_intents = {task.required_skill_intent} if task.required_skill_intent else set()
                    matched = sorted(task_intents & set(reg.supported_intents))
                    if not matched:
                        continue
                    score = len(matched) / max(len(reg.supported_intents), 1)
                    candidates.append(
                        SkillMatch(
                            skill_id=reg.skill_id,
                            skill_name=reg.name,
                            manifest_version=reg.manifest_version,
                            score=round(min(1.0, score), 4),
                            matched_intents=matched,
                            tool_ids=list(reg.tool_ids),
                        )
                    )

            candidates.sort(key=lambda m: m.score, reverse=True)
            if candidates:
                task_matches[task.task_id] = candidates
            else:
                unmatched.append(task.task_id)

        logger.info(
            "agent.skill_router.routed",
            plan_id=str(input_.plan.plan_id),
            matched_tasks=len(task_matches),
            unmatched_tasks=len(unmatched),
        )

        return SkillRouterResult(
            user_id=input_.user_id,
            plan_id=input_.plan.plan_id,
            task_matches=task_matches,
            unmatched_task_ids=unmatched,
        )


def default_skill_registry() -> SkillRegistry:
    return InMemorySkillRegistry()


def default_skill_router() -> SkillRouter:
    return IntentScoringSkillRouter()


__all__ = [
    "RegisteredSkill",
    "SkillRegistry",
    "InMemorySkillRegistry",
    "SkillRouter",
    "IntentScoringSkillRouter",
    "default_skill_registry",
    "default_skill_router",
]
