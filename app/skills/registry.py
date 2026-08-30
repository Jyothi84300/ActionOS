"""Global ToolRegistry — the Executor resolves tool_ids through this.

Per §13 of the Master Specification:

  * The LLM may select from registered tools only.
  * The Executor MUST restrict itself to tool_ids present in this
    registry; unknown IDs fail safely without fallback speculation.
  * No arbitrary code/shell execution.
"""

from __future__ import annotations

from typing import Iterable, Protocol
from uuid import UUID

from app.logging_config import get_logger
from app.skills.calendar_skill import CALENDAR_SKILL_TOOL_CONTRACTS
from app.skills.contracts import ToolContract
from app.skills.document_skill import DOCUMENT_SKILL_TOOL_CONTRACTS
from app.skills.task_skill import TASK_SKILL_TOOL_CONTRACTS

logger = get_logger(__name__)


class ToolRegistry(Protocol):
    def list(self) -> Iterable[ToolContract]: ...
    def get(self, tool_id: UUID) -> ToolContract | None: ...
    def register(self, contract: ToolContract) -> None: ...
    def register_many(self, contracts: Iterable[ToolContract]) -> None: ...


class InMemoryToolRegistry:
    """Simple in-memory ToolRegistry — tests, MVP, and bootstrapping."""

    def __init__(self, contracts: Iterable[ToolContract] | None = None) -> None:
        self._tools: dict[UUID, ToolContract] = {}
        if contracts is not None:
            self.register_many(contracts)

    def list(self) -> Iterable[ToolContract]:
        return list(self._tools.values())

    def get(self, tool_id: UUID) -> ToolContract | None:
        return self._tools.get(tool_id)

    def register(self, contract: ToolContract) -> None:
        if contract.tool_id in self._tools:
            logger.warning(
                "tool_registry.overwrite",
                tool_id=str(contract.tool_id),
                name=contract.name,
            )
        self._tools[contract.tool_id] = contract

    def register_many(self, contracts: Iterable[ToolContract]) -> None:
        for c in contracts:
            self.register(c)


class GlobalToolRegistry:
    """Process-wide singleton registry used by the Executor.

    MVP convenience: ``register_all_mvp_tools()`` is called at first
    construction so all Phase-4 MVP skills are available without
    explicit wiring in application startup code.
    """

    _instance: "GlobalToolRegistry | None" = None
    _lock_object: object = object()

    def __new__(cls) -> "GlobalToolRegistry":
        # Note: no true threading lock here — MVP uses a simple process-
        # wide registry. Production deployments should swap this for a
        # registry backed by the Skill/Tool PostgreSQL tables.
        if cls._instance is None:
            instance = super().__new__(cls)
            instance._inner = InMemoryToolRegistry()
            register_all_mvp_tools(instance._inner)
            cls._instance = instance
        return cls._instance

    def list(self) -> Iterable[ToolContract]:
        return self._inner.list()

    def get(self, tool_id: UUID) -> ToolContract | None:
        return self._inner.get(tool_id)

    def register(self, contract: ToolContract) -> None:
        self._inner.register(contract)

    def register_many(self, contracts: Iterable[ToolContract]) -> None:
        self._inner.register_many(contracts)


def register_skill_tools(
    registry: ToolRegistry, contracts: Iterable[ToolContract]
) -> None:
    registry.register_many(contracts)


def register_all_mvp_tools(registry: ToolRegistry) -> None:
    """Register all three MVP skills (Document, Task, Calendar).

    Safe to call multiple times — duplicate ids log a warning but do
    not raise.
    """
    register_skill_tools(registry, DOCUMENT_SKILL_TOOL_CONTRACTS)
    register_skill_tools(registry, TASK_SKILL_TOOL_CONTRACTS)
    register_skill_tools(registry, CALENDAR_SKILL_TOOL_CONTRACTS)


def default_tool_registry() -> ToolRegistry:
    """Return the default process-wide ToolRegistry singleton (MVP)."""
    return GlobalToolRegistry()
