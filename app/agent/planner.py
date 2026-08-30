"""Planner — converts Goal + Context into a StructuredPlan.

Per §11 of the Master Specification the Planner MUST:
  * Output structured data (JSON/Pydantic), never natural-language-only.
  * NEVER generate arbitrary executable code.
  * Reference only registered skills/tools by stable identifier.

The MVP planner is rule/intent-driven.  It decomposes recognized
intents into ordered tasks with explicit dependencies, expected
outputs, verification methods, and capability routes.  Unrecognized
intents produce a blocked plan with clear reasons rather than
speculative fabricated steps.
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID, uuid4

from app.agent.capability_router import assess_against_manifest
from app.agent.schemas import (
    PlannerInput,
    PlannerResult,
    PlanTask,
    StructuredPlan,
)
from app.enums import (
    CapabilityRoute,
    PermissionLevel,
    SkillCapability,
    VerificationResult,
)
from app.logging_config import get_logger

logger = get_logger(__name__)


SKILL_ID_DOCUMENT = UUID("11111111-1111-1111-1111-000000000001")
SKILL_ID_TASK = UUID("11111111-1111-1111-1111-000000000002")
SKILL_ID_CALENDAR = UUID("11111111-1111-1111-1111-000000000003")


INTENT_TASK_BLUEPRINT: dict[str, dict[str, object]] = {
    "document.summarize": {
        "skill_id": SKILL_ID_DOCUMENT,
        "skill_intent": "document.summarize",
        "skill_cap": SkillCapability.BOTH,
        "title_prefix": "Summarize document",
        "expected_output": "Concise summary of the referenced document.",
        "verification": "independent_read: summary artifact linked to source document.",
        "permission_level": PermissionLevel.AUTOMATIC,
    },
    "document.analyze": {
        "skill_id": SKILL_ID_DOCUMENT,
        "skill_intent": "document.analyze",
        "skill_cap": SkillCapability.BOTH,
        "title_prefix": "Analyze document",
        "expected_output": "Structured analysis of key points, structure, and findings.",
        "verification": "independent_read: analysis artifact exists with section metadata.",
        "permission_level": PermissionLevel.AUTOMATIC,
    },
    "task.create": {
        "skill_id": SKILL_ID_TASK,
        "skill_intent": "task.create",
        "skill_cap": SkillCapability.BOTH,
        "title_prefix": "Create task entries",
        "expected_output": "New task record persisted in the task store.",
        "verification": "independent_read: task exists with matching title and goal link.",
        "permission_level": PermissionLevel.AUTOMATIC,
    },
    "task.list": {
        "skill_id": SKILL_ID_TASK,
        "skill_intent": "task.list",
        "skill_cap": SkillCapability.BOTH,
        "title_prefix": "List active tasks",
        "expected_output": "Ordered list of active tasks with statuses.",
        "verification": "independent_read: list matches direct task-store query.",
        "permission_level": PermissionLevel.AUTOMATIC,
    },
    "calendar.read": {
        "skill_id": SKILL_ID_CALENDAR,
        "skill_intent": "calendar.read",
        "skill_cap": SkillCapability.LOCAL,
        "title_prefix": "Review calendar entries",
        "expected_output": "Relevant calendar events for the requested window.",
        "verification": "independent_read: events re-queried within the same window.",
        "permission_level": PermissionLevel.AUTOMATIC,
    },
    "calendar.create_reminder": {
        "skill_id": SKILL_ID_CALENDAR,
        "skill_intent": "calendar.create_reminder",
        "skill_cap": SkillCapability.LOCAL,
        "title_prefix": "Create calendar reminder",
        "expected_output": "Persisted calendar event/reminder with fire-time.",
        "verification": "independent_read: reminder event exists at the expected time.",
        "permission_level": PermissionLevel.CONFIRMATION_REQUIRED,
    },
}


class Planner(Protocol):
    async def plan(self, input_: PlannerInput) -> PlannerResult: ...


class IntentDrivenPlanner:
    """Produces StructuredPlans derived from ParsedGoal.intents.

    Fallback behavior when no intents are recognized:
      * Produces a single blocked "understand goal better" task with
        `is_blocked=True` and clear `block_reasons`.  Callers can then
        surface a clarification request to the user.  No fabricated
        steps are ever produced.
    """

    async def plan(self, input_: PlannerInput) -> PlannerResult:
        plan_id = uuid4()
        intents = list(input_.parsed_goal.intents or [])

        tasks: list[PlanTask] = []
        required_skills: list[UUID] = []
        required_tools: list[UUID] = []
        permission_level = PermissionLevel.AUTOMATIC
        verification_methods: list[str] = []
        block_reasons: list[str] = []
        unsupported_task_ids: list[UUID] = []

        order_index = 0
        last_task_id: UUID | None = None

        if not intents:
            task_id = uuid4()
            unsupported_task_ids.append(task_id)
            block_reasons.append(
                "No registered intent patterns matched the supplied goal. "
                "Clarification required before a plan can be produced."
            )
            tasks.append(
                PlanTask(
                    task_id=task_id,
                    title="Request clarification from user",
                    description="Goal intents were not recognized. Surface a clarification prompt.",
                    order_index=order_index,
                    depends_on=[],
                    expected_output="User clarification supplying concrete intent.",
                    verification_method="user_confirmed_prompt",
                    capability_route=CapabilityRoute.LOCAL,
                )
            )
        else:
            for intent in intents:
                blueprint = INTENT_TASK_BLUEPRINT.get(intent)
                if blueprint is None:
                    tid = uuid4()
                    unsupported_task_ids.append(tid)
                    block_reasons.append(
                        f"Intent '{intent}' has no registered task blueprint."
                    )
                    tasks.append(
                        PlanTask(
                            task_id=tid,
                            title=f"Handle unsupported intent: {intent}",
                            description=(
                                "This intent does not map to a registered skill. "
                                "Blocked pending skill registration."
                            ),
                            order_index=order_index,
                            depends_on=[last_task_id] if last_task_id else [],
                            expected_output="No-op — blocked task.",
                            verification_method="unavailable",
                            capability_route=input_.capability_route,
                        )
                    )
                    order_index += 1
                    last_task_id = tid
                    continue

                skill_id = blueprint["skill_id"]
                skill_intent = blueprint["skill_intent"]
                skill_cap = blueprint["skill_cap"]
                perm_lv = blueprint["permission_level"]

                tid = uuid4()
                tasks.append(
                    PlanTask(
                        task_id=tid,
                        title=f"{blueprint['title_prefix']} — {input_.parsed_goal.title[:40]}",
                        description=_task_description(input_, intent),
                        order_index=order_index,
                        depends_on=[last_task_id] if last_task_id else [],
                        required_skill_id=skill_id,
                        required_skill_intent=skill_intent,
                        expected_output=str(blueprint["expected_output"]),
                        verification_method=str(blueprint["verification"]),
                        capability_route=_route_for_skill(
                            skill_cap, input_.capability_route
                        ),
                    )
                )
                if skill_id not in required_skills:
                    required_skills.append(skill_id)
                verification_methods.append(str(blueprint["verification"]))
                if _perm_higher(perm_lv, permission_level):
                    permission_level = perm_lv

                order_index += 1
                last_task_id = tid

        dependencies = [
            {
                "task_id": str(task.task_id),
                "depends_on": [str(d) for d in task.depends_on],
            }
            for task in tasks
        ]

        plan = StructuredPlan(
            plan_id=plan_id,
            goal_id=input_.goal_id,
            tasks=tasks,
            ordering="sequential",
            dependencies=dependencies,
            required_skills=required_skills,
            required_tools=required_tools,
            permission_level=permission_level,
            verification_methods=list(dict.fromkeys(verification_methods)),
            capability_route=input_.capability_route,
        )

        is_blocked = len(block_reasons) > 0 or len(unsupported_task_ids) > 0

        logger.info(
            "agent.planner.planned",
            user_id=str(input_.user_id),
            tasks_count=len(tasks),
            is_blocked=is_blocked,
            blocked_count=len(unsupported_task_ids),
        )

        return PlannerResult(
            user_id=input_.user_id,
            goal_id=input_.goal_id,
            plan=plan,
            is_blocked=is_blocked,
            block_reasons=block_reasons,
            unsupported_tasks=unsupported_task_ids,
        )


def _task_description(input_: PlannerInput, intent: str) -> str:
    base = input_.parsed_goal.description or input_.parsed_goal.title
    context_count = len(input_.context.references)
    snippet = f"{base} (context refs: {context_count})."
    return snippet[:5000]


def _route_for_skill(
    skill_cap: SkillCapability, plan_route: CapabilityRoute
) -> CapabilityRoute:
    if plan_route == CapabilityRoute.ONLINE:
        if skill_cap == SkillCapability.LOCAL:
            return CapabilityRoute.PARTIAL
        return CapabilityRoute.ONLINE
    if plan_route == CapabilityRoute.PARTIAL:
        if skill_cap == SkillCapability.ONLINE:
            return CapabilityRoute.ONLINE
        if skill_cap == SkillCapability.LOCAL:
            return CapabilityRoute.LOCAL
        return CapabilityRoute.LOCAL
    if skill_cap == SkillCapability.ONLINE:
        return CapabilityRoute.ONLINE
    return CapabilityRoute.LOCAL


def _perm_higher(candidate: PermissionLevel, current: PermissionLevel) -> bool:
    order = {
        PermissionLevel.AUTOMATIC: 0,
        PermissionLevel.CONFIRMATION_REQUIRED: 1,
        PermissionLevel.BLOCKED: 2,
    }
    return order.get(candidate, -1) > order.get(current, -1)


def default_planner() -> Planner:
    return IntentDrivenPlanner()


__all__ = [
    "Planner",
    "IntentDrivenPlanner",
    "default_planner",
    "INTENT_TASK_BLUEPRINT",
    "SKILL_ID_CALENDAR",
    "SKILL_ID_DOCUMENT",
    "SKILL_ID_TASK",
]
