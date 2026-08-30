import datetime
from typing import Any, Optional
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.enums import GoalStatus, MemoryType
from app.errors import (
    ActionNotFoundError,
    GoalNotFoundError,
    PermissionNotFoundError,
    TaskNotFoundError,
)
from app.logging_config import get_logger
from app.models import Action, Goal, Memory, Permission, Skill, Task, Verification

logger = get_logger(__name__)


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def create_goal(
    db: Session,
    user_id: UUID,
    title: str,
    description: str,
    objective: str,
    deadline: Optional[datetime.datetime],
    priority: Any,
    category: str,
    constraints: list[Any],
) -> Goal:
    goal = Goal(
        id=uuid4(),
        user_id=user_id,
        title=title,
        description=description,
        objective=objective,
        deadline=deadline,
        priority=priority,
        category=category,
        constraints=constraints,
        status=GoalStatus.ACTIVE,
        sync_metadata={},
    )
    db.add(goal)
    db.commit()
    db.refresh(goal)
    logger.info("goal.created", goal_id=str(goal.id), user_id=str(user_id))
    return goal


def get_goal(db: Session, goal_id: UUID) -> Optional[Goal]:
    return db.query(Goal).filter(Goal.id == goal_id).first()


def get_goal_or_404(db: Session, goal_id: UUID) -> Goal:
    goal = get_goal(db, goal_id)
    if goal is None:
        raise GoalNotFoundError(goal_id)
    return goal


def list_tasks_for_goal(db: Session, goal_id: UUID) -> list[Task]:
    return (
        db.query(Task)
        .filter(Task.goal_id == goal_id)
        .order_by(Task.order_index.asc(), Task.created_at.asc())
        .all()
    )


def get_action(db: Session, action_id: UUID) -> Optional[Action]:
    return db.query(Action).filter(Action.id == action_id).first()


def get_action_or_404(db: Session, action_id: UUID) -> Action:
    action = get_action(db, action_id)
    if action is None:
        raise ActionNotFoundError(action_id)
    return action


def get_verification_for_action(db: Session, action_id: UUID) -> Optional[Verification]:
    return db.query(Verification).filter(Verification.action_id == action_id).first()


def list_skills(db: Session) -> list[Skill]:
    return db.query(Skill).order_by(Skill.name.asc()).all()


def list_permissions(db: Session, user_id: UUID) -> list[Permission]:
    return db.query(Permission).filter(Permission.user_id == user_id).order_by(Permission.id.asc()).all()


def get_permission(db: Session, permission_id: UUID) -> Optional[Permission]:
    return db.query(Permission).filter(Permission.id == permission_id).first()


def get_permission_or_404(db: Session, permission_id: UUID) -> Permission:
    perm = get_permission(db, permission_id)
    if perm is None:
        raise PermissionNotFoundError(permission_id)
    return perm


def update_permission_granted(db: Session, permission: Permission, granted: bool) -> Permission:
    now = _utcnow()
    permission.granted = granted
    if granted:
        permission.granted_at = now
        permission.revoked_at = None
    else:
        permission.revoked_at = now
    db.commit()
    db.refresh(permission)
    logger.info(
        "permission.updated",
        permission_id=str(permission.id),
        granted=granted,
        user_id=str(permission.user_id),
    )
    return permission


def has_active_plan_for_goal(db: Session, goal_id: UUID) -> bool:
    """Return True if any Task records exist for the given goal_id.

    Per §24 of the Master Spec, a goal with an existing active plan is a
    409 PLAN_ALREADY_EXISTS unless the caller passes force=true.
    """
    count = db.query(Task).filter(Task.goal_id == goal_id).count()
    return count > 0


def delete_tasks_for_goal(db: Session, goal_id: UUID) -> int:
    """Delete all Task records (and cascade-orphan Action children) for a goal.

    Used by the force=true path of the /plan endpoint to replace an
    existing plan. Returns the number of deleted tasks removed before the new plan is written.
    """
    tasks = db.query(Task).filter(Task.goal_id == goal_id).all()
    count = len(tasks)
    for t in tasks:
        db.delete(t)
    db.commit()
    if count:
        logger.info("plan.tasks_deleted", goal_id=str(goal_id), count=count)
    return count


def create_task_for_plan(
    db: Session,
    *,
    goal_id: UUID,
    task_id: UUID,
    title: str,
    description: str,
    order_index: int,
    depends_on: list[Any],
    skill_id: Optional[UUID],
    skill_version: Optional[str],
    capability_route: Any,
) -> Task:
    """Create a single Task row from a Planner-produced plan task.

    If the referenced skill_id does not exist in the `skills` registry
    table (seed data is a separate later Phase-2 task), the skill_id and
    skill_version columns are left NULL on the persisted row to satisfy
    the `tasks.skill_id -> skills.skill_id` foreign-key constraint.
    Callers can still cross-reference the planner's task_id via the
    stable `task.task_id = plan_task.task_id` identity.
    """
    from app.enums import ActionState
    from app.models import Skill

    resolved_skill_id: Optional[UUID] = skill_id
    resolved_version: Optional[str] = skill_version
    if resolved_skill_id is not None:
        exists = db.query(Skill).filter(Skill.skill_id == resolved_skill_id).first() is not None
        if not exists:
            resolved_skill_id = None
            resolved_version = None

    serialized_deps: list[Any] = [
        str(d) if isinstance(d, UUID) else d for d in (depends_on or [])
    ]

    task = Task(
        id=task_id,
        goal_id=goal_id,
        title=title,
        description=description,
        order_index=order_index,
        depends_on=serialized_deps,
        skill_id=resolved_skill_id,
        skill_version=resolved_version,
        capability_route=capability_route,
        status=ActionState.PENDING,
    )
    db.add(task)
    db.flush()
    logger.info(
        "plan.task_created",
        task_id=str(task_id),
        goal_id=str(goal_id),
        order_index=order_index,
        skill_resolved=(resolved_skill_id is not None),
    )
    return task


def get_task(db: Session, task_id: UUID) -> Optional[Task]:
    return db.query(Task).filter(Task.id == task_id).first()


def get_task_or_404(db: Session, task_id: UUID) -> Task:
    task = get_task(db, task_id)
    if task is None:
        raise TaskNotFoundError(task_id)
    return task


def create_action_for_task(
    db: Session,
    *,
    task_id: UUID,
    action_id: UUID,
) -> Action:
    """Create a PENDING Action row linked to the given task.

    This is the DB write for the §24 POST /tasks/{id}/execute endpoint.
    Actual tool execution (Executor module) is a later Phase-2 task; here
    we only persist the queued action so the state machine has a durable
    record and the caller receives an action_id they can poll via
    GET /actions/{action_id}.
    """
    from app.enums import ActionState

    action = Action(
        id=action_id,
        task_id=task_id,
        tool_id=None,
        permission_id=None,
        input_payload={},
        result_payload=None,
        state=ActionState.PENDING,
    )
    db.add(action)
    db.flush()
    logger.info(
        "task.execute.queued",
        action_id=str(action_id),
        task_id=str(task_id),
    )
    return action


def create_memory(
    db: Session,
    *,
    user_id: UUID,
    goal_id: UUID | None,
    memory_type: MemoryType,
    payload: dict[str, Any],
) -> Memory:
    """Create a structured Memory entry (§17, §23.3).

    Entries are goal-centric where possible; goal_id=None is allowed for
    account-level memories (e.g. user-wide preferences) but per-goal
    entries MUST carry the goal_id for correct isolation/retrieval.
    """
    mem = Memory(
        id=uuid4(),
        user_id=user_id,
        goal_id=goal_id,
        type=memory_type,
        payload=payload,
    )
    db.add(mem)
    db.commit()
    db.refresh(mem)
    logger.info(
        "memory.created",
        memory_id=str(mem.id),
        user_id=str(user_id),
        goal_id=str(goal_id) if goal_id else None,
        memory_type=memory_type.value,
    )
    return mem


def get_memory(db: Session, memory_id: UUID) -> Memory | None:
    return db.query(Memory).filter(Memory.id == memory_id).first()


def list_memory_for_goal(
    db: Session,
    *,
    user_id: UUID,
    goal_id: UUID,
) -> list[Memory]:
    """Retrieve all memories scoped to a goal for the given user (§17.2).

    Enforces user/goal isolation: the caller's user_id is always ANDed
    into the WHERE clause so cross-user leakage cannot occur.
    """
    return (
        db.query(Memory)
        .filter(
            Memory.user_id == user_id,
            Memory.goal_id == goal_id,
        )
        .order_by(Memory.created_at.asc())
        .all()
    )


def list_memory_for_user(
    db: Session,
    *,
    user_id: UUID,
    memory_type: MemoryType | None = None,
) -> list[Memory]:
    """List all memories (optionally filtered by type) for a user."""
    q = db.query(Memory).filter(Memory.user_id == user_id)
    if memory_type is not None:
        q = q.filter(Memory.type == memory_type)
    return q.order_by(Memory.created_at.desc()).all()


def delete_memory(db: Session, memory: Memory) -> None:
    """Delete a single Memory row (user-initiated deletion per §17.2)."""
    mid = str(memory.id)
    uid = str(memory.user_id)
    db.delete(memory)
    db.commit()
    logger.info("memory.deleted", memory_id=mid, user_id=uid)


def cascade_delete_memories_for_goal(
    db: Session,
    *,
    user_id: UUID,
    goal_id: UUID,
) -> int:
    """Cascade-delete all memory rows tied to a specific (user, goal).

    §17.2 — User-initiated goal deletion MUST cascade to dependent
    records. Returns the count of removed rows.
    """
    rows = (
        db.query(Memory)
        .filter(Memory.user_id == user_id, Memory.goal_id == goal_id)
        .all()
    )
    count = len(rows)
    for r in rows:
        db.delete(r)
    if count:
        db.commit()
        logger.info(
            "memory.cascade_deleted",
            goal_id=str(goal_id),
            user_id=str(user_id),
            count=count,
        )
    return count
