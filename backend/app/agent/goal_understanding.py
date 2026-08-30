"""Goal Understanding module.

Converts raw user text into a structured ParsedGoal object.

MVP implementation: rule-based parsing with an extensible hook for a
future model-based parser.  No LLM integration in this module.

The parser MUST:
  * Produce a ParsedGoal with a non-empty title.
  * Never output executable code.
  * Surface ambiguous input via `is_ambiguous` + `ambiguity_reasons`.
"""

from __future__ import annotations

import datetime
import re
from typing import Protocol
from uuid import UUID, uuid4

from app.agent.schemas import (
    GoalUnderstandingInput,
    GoalUnderstandingResult,
    ParsedGoal,
)
from app.enums import Priority
from app.logging_config import get_logger

logger = get_logger(__name__)


_CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "academic": [
        "paper", "essay", "research", "study", "homework", "assignment",
        "exam", "test", "thesis", "dissertation", "class", "course",
        "deadline", "professor", "university", "college", "school",
    ],
    "work": [
        "meeting", "email", "report", "client", "deadline", "presentation",
        "project", "task", "boss", "colleague", "office", "review",
        "proposal", "document", "slides",
    ],
    "personal": [
        "reminder", "shopping", "birthday", "doctor", "appointment",
        "travel", "vacation", "grocery", "errand", "family", "friend",
    ],
}

_PRIORITY_PATTERNS: list[tuple[Priority, list[str]]] = [
    (Priority.HIGH, ["urgent", "asap", "critical", "important", "high priority", "as soon as possible"]),
    (Priority.LOW, ["when free", "low priority", "sometime", "eventually", "whenever"]),
]

_DEADLINE_PATTERNS: list[tuple[str, int]] = [
    (r"today", 0),
    (r"tomorrow", 1),
    (r"next week", 7),
    (r"in (\d+) day", 1),
    (r"in (\d+) week", 7),
]

_INTENT_HINTS: list[tuple[str, list[str]]] = [
    ("document.summarize", ["summarize", "summary", "abstract", "brief"]),
    ("document.analyze", ["analyze", "review", "critique", "break down"]),
    ("task.create", ["create task", "add task", "todo", "to-do", "to do"]),
    ("task.list", ["list tasks", "show tasks", "my tasks"]),
    ("calendar.read", ["calendar", "schedule", "when is", "upcoming"]),
    ("calendar.create_reminder", ["remind", "reminder", "alert", "notify me"]),
]


def _detect_category(text: str) -> str:
    t = text.lower()
    best_cat = "personal"
    best_count = 0
    for cat, words in _CATEGORY_KEYWORDS.items():
        count = sum(1 for w in words if w in t)
        if count > best_count:
            best_cat = cat
            best_count = count
    return best_cat


def _detect_priority(text: str) -> Priority:
    t = text.lower()
    for prio, patterns in _PRIORITY_PATTERNS:
        if any(p in t for p in patterns):
            return prio
    return Priority.MEDIUM


def _detect_deadline(text: str) -> datetime.datetime | None:
    t = text.lower()
    now = datetime.datetime.now(datetime.timezone.utc)
    for pattern, multiplier in _DEADLINE_PATTERNS:
        m = re.search(pattern, t)
        if not m:
            continue
        days = multiplier
        if m.groups():
            try:
                days = int(m.group(1)) * multiplier
            except (ValueError, IndexError):
                days = multiplier
        target = now + datetime.timedelta(days=days)
        return target.replace(hour=23, minute=59, second=0, microsecond=0)
    return None


def _extract_intents(text: str) -> list[str]:
    t = text.lower()
    found: list[str] = []
    for intent, hints in _INTENT_HINTS:
        if any(h in t for h in hints):
            found.append(intent)
    return found


def _derive_title(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text.strip())
    if len(cleaned) <= 255:
        return cleaned
    sentence_end = max(cleaned.find("."), cleaned.find("!"), cleaned.find("?"))
    if 0 < sentence_end <= 255:
        return cleaned[:sentence_end].strip()
    return cleaned[:252].rstrip() + "..."


def _extract_description_and_objective(raw: str) -> tuple[str, str]:
    text = raw.strip()
    if len(text) <= 10000:
        description = text
    else:
        description = text[:10000]
    words = text.split()
    if len(words) <= 20:
        objective = text[:10000]
    else:
        objective = "Complete the requested outcome: " + " ".join(words[:20]) + ("..." if len(words) > 20 else "")
        objective = objective[:10000]
    return description, objective


def _check_ambiguity(text: str, intents: list[str]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    t = text.strip()
    if len(t) < 5:
        reasons.append("Input is very short; intent may be underspecified.")
    if len(intents) == 0:
        reasons.append("No recognized intent pattern matched.")
    elif len(intents) > 1:
        reasons.append(f"Multiple intent patterns matched: {intents}.")
    if "?" in t and t.rstrip().endswith("?") and len(t) < 30:
        reasons.append("Input is framed as a short question; goal may need elaboration.")
    return (len(reasons) > 0, reasons)


class GoalUnderstandingBackend(Protocol):
    async def parse(self, input_: GoalUnderstandingInput) -> GoalUnderstandingResult: ...


class RuleBasedGoalUnderstanding:
    """Deterministic rule-based parser.

    This is the MVP implementation. A model-backed parser can be swapped
    in later by implementing the GoalUnderstandingBackend Protocol.
    """

    async def parse(self, input_: GoalUnderstandingInput) -> GoalUnderstandingResult:
        raw = input_.raw_text
        category = input_.category if input_.category != "personal" else _detect_category(raw)
        priority = input_.priority if input_.priority != Priority.MEDIUM else _detect_priority(raw)
        deadline = input_.deadline or _detect_deadline(raw)
        intents = _extract_intents(raw)
        is_ambiguous, ambiguity_reasons = _check_ambiguity(raw, intents)
        description, objective = _extract_description_and_objective(raw)

        parsed = ParsedGoal(
            title=_derive_title(raw),
            description=description,
            objective=objective,
            deadline=deadline,
            priority=priority,
            category=category,
            constraints=[],
            intents=intents,
            is_ambiguous=is_ambiguous,
            ambiguity_reasons=ambiguity_reasons,
        )

        confidence = 1.0
        if is_ambiguous:
            confidence = 0.6
        elif len(intents) == 0:
            confidence = 0.75
        elif len(intents) > 1:
            confidence = 0.8

        logger.info(
            "agent.goal_understanding.parsed",
            user_id=str(input_.user_id),
            intents_count=len(intents),
            is_ambiguous=is_ambiguous,
            confidence=confidence,
        )

        return GoalUnderstandingResult(
            user_id=input_.user_id,
            raw_text=raw,
            parsed_goal=parsed,
            confidence=confidence,
        )


def default_goal_understanding() -> GoalUnderstandingBackend:
    return RuleBasedGoalUnderstanding()


__all__ = [
    "GoalUnderstandingBackend",
    "RuleBasedGoalUnderstanding",
    "default_goal_understanding",
]
