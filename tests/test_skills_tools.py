"""Phase 4 — Skills and Tools tests.

Covers:
  * ToolContract shape correctness (stable ids, versions, schemas).
  * Document Skill handlers: summarize + analyze with FakeDocumentProvider.
  * Task Skill handlers against a real SQLite session (via conftest).
  * Calendar Skill handlers with FakeCalendarProvider.
  * ToolRegistry lookup + unknown tool_id safety.
"""

from __future__ import annotations

import asyncio
import datetime
from uuid import UUID

import pytest

from app.enums import (
    ActionState,
    PermissionLevel,
    Priority,
    ToolCapability,
)
from app.skills.adapters import FakeCalendarProvider, FakeDocumentProvider
from app.skills.calendar_skill import (
    CALENDAR_SKILL_TOOL_CONTRACTS,
    CALENDAR_TOOL_ID_CHECK_DEADLINE,
    CALENDAR_TOOL_ID_CREATE_REMINDER,
    CALENDAR_TOOL_ID_READ_EVENTS,
    CalendarCheckDeadlineInput,
    CalendarCreateReminderInput,
    CalendarReadEventsInput,
)
from app.skills.contracts import (
    ToolExecutionContext,
    ToolVerificationResult,
    VerificationBehavior,
    VerificationMethod,
)
from app.skills.document_skill import (
    DOCUMENT_SKILL_TOOL_CONTRACTS,
    DOCUMENT_TOOL_ID_ANALYZE,
    DOCUMENT_TOOL_ID_SUMMARIZE,
    DocumentAnalyzeInput,
    DocumentSummarizeInput,
)
from app.skills.registry import (
    InMemoryToolRegistry,
    ToolRegistry,
    default_tool_registry,
    register_all_mvp_tools,
)
from app.skills.task_skill import (
    TASK_SKILL_TOOL_CONTRACTS,
    TASK_TOOL_ID_COMPLETE,
    TASK_TOOL_ID_CREATE,
    TASK_TOOL_ID_LIST,
    TASK_TOOL_ID_UPDATE,
    TaskCompleteInput,
    TaskCreateInput,
    TaskListInput,
    TaskUpdateInput,
)
from tests.conftest import TEST_USER_ID


def _new_ctx(
    db_session=None,
    document_provider=None,
    calendar_provider=None,
    goal_id=None,
    task_id=None,
) -> ToolExecutionContext:
    from uuid import uuid4

    return ToolExecutionContext(
        user_id=TEST_USER_ID,
        action_id=uuid4(),
        goal_id=goal_id,
        task_id=task_id,
        db_session=db_session,
        document_provider=document_provider,
        calendar_provider=calendar_provider,
    )


# ---------------------------------------------------------------------------
# Contract / Registry tests
# ---------------------------------------------------------------------------


class TestMVPContractShape:
    @pytest.mark.parametrize(
        "contracts,expected_count,expected_cap",
        [
            (DOCUMENT_SKILL_TOOL_CONTRACTS, 2, ToolCapability.LOCAL),
            (TASK_SKILL_TOOL_CONTRACTS, 4, ToolCapability.LOCAL),
            (CALENDAR_SKILL_TOOL_CONTRACTS, 3, ToolCapability.LOCAL),
        ],
    )
    def test_contracts_count_and_basic_shape(
        self, contracts, expected_count, expected_cap
    ):
        assert len(contracts) == expected_count
        for c in contracts:
            assert isinstance(c.tool_id, UUID)
            assert isinstance(c.skill_id, UUID)
            assert c.version.startswith("1.")
            assert c.input_schema is not None
            assert c.output_schema is not None
            assert c.enabled is True
            # Capability defaults match MVP (all tools run LOCAL in MVP).
            assert c.capability == expected_cap
            # JSON schemas are Pydantic-computed without errors.
            assert "properties" in c.input_json_schema or c.input_json_schema.get("type")
            assert "properties" in c.output_json_schema or c.output_json_schema.get("type")

    def test_permission_levels_match_spec(self):
        by_id = {c.tool_id: c for c in CALENDAR_SKILL_TOOL_CONTRACTS}
        assert (
            by_id[CALENDAR_TOOL_ID_CREATE_REMINDER].permission_level
            == PermissionLevel.CONFIRMATION_REQUIRED
        )
        assert (
            by_id[CALENDAR_TOOL_ID_READ_EVENTS].permission_level
            == PermissionLevel.AUTOMATIC
        )
        task_by_id = {c.tool_id: c for c in TASK_SKILL_TOOL_CONTRACTS}
        for c in task_by_id.values():
            assert c.permission_level == PermissionLevel.AUTOMATIC

    def test_all_tools_declare_verification_behavior(self):
        all_contracts = (
            list(DOCUMENT_SKILL_TOOL_CONTRACTS)
            + list(TASK_SKILL_TOOL_CONTRACTS)
            + list(CALENDAR_SKILL_TOOL_CONTRACTS)
        )
        for c in all_contracts:
            assert isinstance(c.verification_method, VerificationMethod)
            assert isinstance(c.verification_behavior, VerificationBehavior)

    def test_registered_ids_are_stable_and_unique(self):
        ids = [
            DOCUMENT_TOOL_ID_SUMMARIZE,
            DOCUMENT_TOOL_ID_ANALYZE,
            TASK_TOOL_ID_CREATE,
            TASK_TOOL_ID_LIST,
            TASK_TOOL_ID_UPDATE,
            TASK_TOOL_ID_COMPLETE,
            CALENDAR_TOOL_ID_READ_EVENTS,
            CALENDAR_TOOL_ID_CREATE_REMINDER,
            CALENDAR_TOOL_ID_CHECK_DEADLINE,
        ]
        assert len(ids) == len(set(ids))


class TestToolRegistry:
    def test_register_many_and_lookup(self):
        reg: ToolRegistry = InMemoryToolRegistry()
        register_all_mvp_tools(reg)
        all_ids = {c.tool_id for c in reg.list()}
        assert len(all_ids) == 9

    def test_get_unknown_returns_none_no_raise(self):
        reg: ToolRegistry = InMemoryToolRegistry()
        register_all_mvp_tools(reg)
        from uuid import uuid4

        assert reg.get(uuid4()) is None

    def test_default_singleton_contains_mvp_tools(self):
        reg = default_tool_registry()
        assert len(list(reg.list())) >= 9
        for expected in (
            DOCUMENT_TOOL_ID_SUMMARIZE,
            TASK_TOOL_ID_CREATE,
            CALENDAR_TOOL_ID_CREATE_REMINDER,
        ):
            assert reg.get(expected) is not None


# ---------------------------------------------------------------------------
# Document skill — execution + verification
# ---------------------------------------------------------------------------


class TestDocumentSkill:
    @pytest.fixture()
    def doc_provider(self):
        return FakeDocumentProvider()

    @pytest.mark.asyncio
    async def test_summarize_execution_succeeds(self, doc_provider):
        ctx = _new_ctx(document_provider=doc_provider)
        contract = next(
            c for c in DOCUMENT_SKILL_TOOL_CONTRACTS if c.tool_id == DOCUMENT_TOOL_ID_SUMMARIZE
        )
        input_ = DocumentSummarizeInput(document_source_ref="any", max_sentences=3)
        result = await contract.handler.execute(input_, ctx)
        assert result.success is True
        output = result.output
        assert output.summary != ""
        assert output.word_count > 0

    @pytest.mark.asyncio
    async def test_summarize_verification_independent_read_passes(self, doc_provider):
        ctx = _new_ctx(document_provider=doc_provider)
        contract = next(
            c for c in DOCUMENT_SKILL_TOOL_CONTRACTS if c.tool_id == DOCUMENT_TOOL_ID_SUMMARIZE
        )
        input_ = DocumentSummarizeInput(document_source_ref="any")
        exec_result = await contract.handler.execute(input_, ctx)
        assert exec_result.success
        vr: ToolVerificationResult = await contract.handler.verify(
            input_, exec_result.output, ctx
        )
        assert vr.verified is True
        assert vr.method == VerificationMethod.INDEPENDENT_READ

    @pytest.mark.asyncio
    async def test_summarize_no_provider_fails_cleanly(self):
        ctx = _new_ctx()
        contract = next(
            c for c in DOCUMENT_SKILL_TOOL_CONTRACTS if c.tool_id == DOCUMENT_TOOL_ID_SUMMARIZE
        )
        input_ = DocumentSummarizeInput(document_source_ref="any")
        result = await contract.handler.execute(input_, ctx)
        assert result.success is False
        assert "No DocumentProvider" in result.error_message

    @pytest.mark.asyncio
    async def test_analyze_returns_all_requested_sections(self, doc_provider):
        ctx = _new_ctx(document_provider=doc_provider)
        contract = next(
            c for c in DOCUMENT_SKILL_TOOL_CONTRACTS if c.tool_id == DOCUMENT_TOOL_ID_ANALYZE
        )
        input_ = DocumentAnalyzeInput(
            document_source_ref="any",
            sections=["structure", "key_points", "next_steps"],
        )
        result = await contract.handler.execute(input_, ctx)
        assert result.success is True
        sections = result.output.sections
        assert "structure" in sections
        assert "key_points" in sections
        assert "next_steps" in sections

    @pytest.mark.asyncio
    async def test_analyze_verification_missing_sections_detected(self, doc_provider):
        ctx = _new_ctx(document_provider=doc_provider)
        contract = next(
            c for c in DOCUMENT_SKILL_TOOL_CONTRACTS if c.tool_id == DOCUMENT_TOOL_ID_ANALYZE
        )
        input_ = DocumentAnalyzeInput(document_source_ref="any", sections=["structure"])
        exec_result = await contract.handler.execute(input_, ctx)
        # Tamper the execution output to simulate a broken handler.
        bad_output = exec_result.output.model_copy(deep=True)
        bad_output.sections = {}
        vr = await contract.handler.verify(input_, bad_output, ctx)
        assert vr.verified is False
        assert "Missing analysis sections" in vr.reason or vr.reason is not None


# ---------------------------------------------------------------------------
# Task skill — execution + verification (uses conftest db_session)
# ---------------------------------------------------------------------------


class TestTaskSkill:
    @pytest.mark.asyncio
    async def test_create_and_list_round_trip(self, db_session, sample_goal_payload, client):
        # Create a goal through the API to get a valid goal_id.
        resp = client.post("/api/v1/goals", json=sample_goal_payload, headers={})
        assert resp.status_code == 201
        goal_id = UUID(resp.json()["id"])

        create_ctx = _new_ctx(db_session=db_session, goal_id=goal_id)
        create_contract = next(
            c for c in TASK_SKILL_TOOL_CONTRACTS if c.tool_id == TASK_TOOL_ID_CREATE
        )
        created = await create_contract.handler.execute(
            TaskCreateInput(
                title="My MVP task",
                description="Created from Phase 4 tests.",
                priority=Priority.HIGH,
                goal_id=goal_id,
            ),
            create_ctx,
        )
        assert created.success is True
        assert created.output.created is True
        created_id = created.output.task.id

        # Verification via independent read.
        vr = await create_contract.handler.verify(
            TaskCreateInput(title="ignored", goal_id=goal_id), created.output, create_ctx
        )
        assert vr.verified is True

        # List tasks.
        list_contract = next(
            c for c in TASK_SKILL_TOOL_CONTRACTS if c.tool_id == TASK_TOOL_ID_LIST
        )
        listed = await list_contract.handler.execute(
            TaskListInput(goal_id=goal_id, limit=10), _new_ctx(db_session=db_session, goal_id=goal_id)
        )
        assert listed.success is True
        assert any(t.id == created_id for t in listed.output.tasks)

    @pytest.mark.asyncio
    async def test_update_and_complete_flow(self, db_session, sample_goal_payload, client):
        resp = client.post("/api/v1/goals", json=sample_goal_payload, headers={})
        goal_id = UUID(resp.json()["id"])
        ctx = _new_ctx(db_session=db_session, goal_id=goal_id)
        create_contract = next(
            c for c in TASK_SKILL_TOOL_CONTRACTS if c.tool_id == TASK_TOOL_ID_CREATE
        )
        created = await create_contract.handler.execute(
            TaskCreateInput(title="t", goal_id=goal_id), ctx
        )
        task_id = created.output.task.id

        update_c = next(
            c for c in TASK_SKILL_TOOL_CONTRACTS if c.tool_id == TASK_TOOL_ID_UPDATE
        )
        up = await update_c.handler.execute(
            TaskUpdateInput(task_id=task_id, title="renamed"), ctx
        )
        assert up.success is True
        assert up.output.task.title == "renamed"
        up_vr = await update_c.handler.verify(
            TaskUpdateInput(task_id=task_id, title="renamed"), up.output, ctx
        )
        assert up_vr.verified is True

        complete_c = next(
            c for c in TASK_SKILL_TOOL_CONTRACTS if c.tool_id == TASK_TOOL_ID_COMPLETE
        )
        done = await complete_c.handler.execute(TaskCompleteInput(task_id=task_id), ctx)
        assert done.output.completed is True
        assert done.output.task.status == ActionState.COMPLETED
        done_vr = await complete_c.handler.verify(
            TaskCompleteInput(task_id=task_id), done.output, ctx
        )
        assert done_vr.verified is True


# ---------------------------------------------------------------------------
# Calendar skill
# ---------------------------------------------------------------------------


class TestCalendarSkill:
    @pytest.fixture()
    def cal(self):
        return FakeCalendarProvider()

    @pytest.mark.asyncio
    async def test_create_reminder_and_independent_verify(self, cal):
        ctx = _new_ctx(calendar_provider=cal)
        c = next(
            cc
            for cc in CALENDAR_SKILL_TOOL_CONTRACTS
            if cc.tool_id == CALENDAR_TOOL_ID_CREATE_REMINDER
        )
        fire_at = datetime.datetime.now(datetime.timezone.utc).replace(
            microsecond=0
        ) + datetime.timedelta(hours=6)
        result = await c.handler.execute(
            CalendarCreateReminderInput(
                title="Dentist",
                fire_at=fire_at,
                duration_minutes=30,
            ),
            ctx,
        )
        assert result.success is True
        assert result.output.created is True
        vr = await c.handler.verify(
            CalendarCreateReminderInput(title="x", fire_at=fire_at),
            result.output,
            ctx,
        )
        assert vr.verified is True

    @pytest.mark.asyncio
    async def test_create_reminder_requires_confirmation_permission(self):
        c = next(
            cc
            for cc in CALENDAR_SKILL_TOOL_CONTRACTS
            if cc.tool_id == CALENDAR_TOOL_ID_CREATE_REMINDER
        )
        assert c.permission_level == PermissionLevel.CONFIRMATION_REQUIRED

    @pytest.mark.asyncio
    async def test_read_events(self, cal):
        now = datetime.datetime.now(datetime.timezone.utc)
        ctx = _new_ctx(calendar_provider=cal)
        c = next(
            cc
            for cc in CALENDAR_SKILL_TOOL_CONTRACTS
            if cc.tool_id == CALENDAR_TOOL_ID_READ_EVENTS
        )
        result = await c.handler.execute(
            CalendarReadEventsInput(
                window_start=now - datetime.timedelta(days=1),
                window_end=now + datetime.timedelta(days=7),
            ),
            ctx,
        )
        assert result.success is True
        # FakeCalendarProvider seeds one upcoming standup event.
        assert len(result.output.events) >= 1
        vr = await c.handler.verify(
            CalendarReadEventsInput(
                window_start=now - datetime.timedelta(days=1),
                window_end=now + datetime.timedelta(days=7),
            ),
            result.output,
            ctx,
        )
        assert vr.verified is True

    @pytest.mark.asyncio
    async def test_check_deadline_marks_at_risk_when_busy(self, cal):
        now = datetime.datetime.now(datetime.timezone.utc).replace(
            minute=0, second=0, microsecond=0
        )
        deadline = now + datetime.timedelta(hours=2)
        # Fill the window with many overlapping fake events by creating them.
        t = now
        for i in range(6):
            await cal.create_event(
                title=f"Block #{i}",
                start_at=t,
                end_at=t + datetime.timedelta(minutes=15),
                reminder_minutes=None,
            )
            t += datetime.timedelta(minutes=20)
        ctx = _new_ctx(calendar_provider=cal)
        c = next(
            cc
            for cc in CALENDAR_SKILL_TOOL_CONTRACTS
            if cc.tool_id == CALENDAR_TOOL_ID_CHECK_DEADLINE
        )
        result = await c.handler.execute(
            CalendarCheckDeadlineInput(deadline=deadline, lookahead_hours=48),
            ctx,
        )
        assert result.success is True
        # With 2 hours of lookahead, at_risk is based on free hours (< 4).
        # At most 2 free hours — so at_risk must be True.
        assert result.output.at_risk is True
        vr = await c.handler.verify(
            CalendarCheckDeadlineInput(deadline=deadline), result.output, ctx
        )
        assert vr.verified is True

    @pytest.mark.asyncio
    async def test_create_reminder_no_provider_fails_safely(self):
        ctx = _new_ctx()
        c = next(
            cc
            for cc in CALENDAR_SKILL_TOOL_CONTRACTS
            if cc.tool_id == CALENDAR_TOOL_ID_CREATE_REMINDER
        )
        result = await c.handler.execute(
            CalendarCreateReminderInput(
                title="x",
                fire_at=datetime.datetime.now(datetime.timezone.utc),
            ),
            ctx,
        )
        assert result.success is False
        assert result.error_message is not None
