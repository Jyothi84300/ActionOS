"""Phase 3 — Model / AI Layer tests.

Covers typed requests/responses, provider interface, validation,
routing, and the deterministic fake/cloud adapters.  All tests use the
fake provider — no external credentials required.
"""

from __future__ import annotations

import json
from uuid import UUID, uuid4

import pytest
from pydantic import BaseModel

from app.model.errors import (
    ModelConfigurationError,
    ModelError,
    ModelProviderError,
    ModelRateLimitError,
    ModelTimeoutError,
    ModelValidationError,
)
from app.model.provider import (
    ModelProvider,
    ModelProviderInfo,
    ProviderCapability,
    ProviderTier,
)
from app.model.providers.cloud_provider import (
    CloudProviderConfig,
    OpenAICloudProvider,
    build_cloud_provider_from_env,
)
from app.model.providers.fake_provider import (
    DEFAULT_FAKE_RESPONSES,
    DeterministicResponse,
    FakeModelProvider,
)
from app.model.router import (
    ModelRouter,
    ModelRoutingDecision,
    RoutingReason,
    RoutingStrategy,
    default_model_router,
)
from app.model.types import (
    ChatMessage,
    ChatRole,
    ModelFinishReason,
    ModelRequest,
    ModelResponse,
    ModelUsage,
    StructuredOutputMode,
)
from app.model.validation import (
    StructuredOutputValidator,
    validate_structured_output,
)


# ---------------------------------------------------------------------------
# Types: ChatMessage / ModelRequest / ModelResponse
# ---------------------------------------------------------------------------


class TestTypes:
    def test_chat_message_equality_and_role(self):
        m = ChatMessage(role=ChatRole.USER, content="hello")
        assert m.role == ChatRole.USER
        assert m.content == "hello"
        assert m.name is None
        assert m.tool_call_id is None

    def test_model_request_defaults(self):
        req = ModelRequest(messages=[ChatMessage(ChatRole.USER, "hi")])
        assert req.temperature == 0.0
        assert req.max_tokens is None
        assert req.structured_output_mode == StructuredOutputMode.NONE
        assert isinstance(req.request_id, UUID)

    def test_model_usage_sums_default(self):
        u = ModelUsage()
        assert u.total_tokens == 0


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class TestErrors:
    def test_model_error_base_fields(self):
        err = ModelError("X", "msg", provider_name="p", details={"a": 1})
        assert err.code == "X"
        assert err.provider_name == "p"
        assert err.details["a"] == 1

    def test_validation_error_truncates_long_output(self):
        long = "A" * 5000
        err = ModelValidationError(raw_output=long)
        preview = err.details["raw_output_preview"]
        assert preview.endswith("[truncated]")
        assert len(preview) < 5000

    def test_rate_limit_error_includes_retry(self):
        err = ModelRateLimitError(retry_after_seconds=12.5)
        assert err.details["retry_after_seconds"] == 12.5

    def test_timeout_error_includes_timeout(self):
        err = ModelTimeoutError(timeout_seconds=30)
        assert err.details["timeout_seconds"] == 30

    def test_configuration_error_lists_env_vars(self):
        err = ModelConfigurationError(
            missing_env_vars=["OPENAI_API_KEY"], provider_name="openai"
        )
        assert err.details["missing_env_vars"] == ["OPENAI_API_KEY"]


# ---------------------------------------------------------------------------
# FakeModelProvider
# ---------------------------------------------------------------------------


@pytest.fixture()
def fake() -> FakeModelProvider:
    return FakeModelProvider()


class TestFakeModelProvider:
    @pytest.mark.asyncio
    async def test_info_always_available(self, fake):
        info = fake.info()
        assert info.available is True
        assert info.tier == ProviderTier.LOCAL
        assert ProviderCapability.STRUCTURED_JSON in info.capabilities

    @pytest.mark.asyncio
    async def test_selects_keyword_response_document(self, fake):
        req = ModelRequest(
            messages=[ChatMessage(ChatRole.USER, "please summarize this document")],
            structured_output_mode=StructuredOutputMode.JSON,
            expected_output_schema=dict,
        )
        resp = await fake.generate(req)
        assert resp.provider_name == "fake"
        parsed = json.loads(resp.content)
        assert "summary" in parsed
        assert resp.finish_reason == ModelFinishReason.STOP

    @pytest.mark.asyncio
    async def test_invalid_json_keyword_raises_validation_error(self):
        fake2 = FakeModelProvider()
        req = ModelRequest(
            messages=[ChatMessage(ChatRole.USER, "please return invalid_json data")],
            structured_output_mode=StructuredOutputMode.JSON,
            expected_output_schema=dict,
        )
        with pytest.raises(ModelValidationError):
            await fake2.generate(req)

    @pytest.mark.asyncio
    async def test_content_filter_finish_reason(self, fake):
        req = ModelRequest(
            messages=[ChatMessage(ChatRole.USER, "this should trigger error")]
        )
        resp = await fake.generate(req)
        assert resp.finish_reason == ModelFinishReason.CONTENT_FILTER

    @pytest.mark.asyncio
    async def test_default_response_fallback(self, fake):
        req = ModelRequest(
            messages=[ChatMessage(ChatRole.USER, "totally unmatched text here")],
            structured_output_mode=StructuredOutputMode.JSON,
            expected_output_schema=dict,
        )
        resp = await fake.generate(req)
        parsed = json.loads(resp.content)
        assert "message" in parsed

    @pytest.mark.asyncio
    async def test_responses_have_usage_counts(self, fake):
        req = ModelRequest(
            messages=[ChatMessage(ChatRole.USER, "create a task for me")],
            structured_output_mode=StructuredOutputMode.JSON,
            expected_output_schema=dict,
        )
        resp = await fake.generate(req)
        assert resp.usage.total_tokens > 0

    def test_implements_provider_protocol(self, fake):
        # Duck-type compliance — mypy would catch this statically.
        assert isinstance(fake.info(), ModelProviderInfo)


# ---------------------------------------------------------------------------
# Structured output validation
# ---------------------------------------------------------------------------


class _PlanSchema(BaseModel):
    tasks: list[dict]
    permission_level: str


class TestStructuredOutputValidation:
    def test_valid_json_dict_passthrough(self):
        out = json.dumps({"a": 1, "b": [1, 2]})
        result = validate_structured_output(out, {})
        assert result == {"a": 1, "b": [1, 2]}

    def test_valid_pydantic_schema(self):
        payload = json.dumps(
            {"tasks": [{"title": "t1"}], "permission_level": "AUTOMATIC"}
        )
        instance = validate_structured_output(payload, _PlanSchema)
        assert isinstance(instance, _PlanSchema)
        assert instance.tasks[0]["title"] == "t1"

    def test_empty_string_raises(self):
        with pytest.raises(ModelValidationError) as ei:
            validate_structured_output("", {})
        assert "empty" in ei.value.message.lower()

    def test_invalid_json_raises(self):
        with pytest.raises(ModelValidationError) as ei:
            validate_structured_output("{not json", {})
        assert "not valid json" in ei.value.message.lower()

    def test_pydantic_validation_lists_errors(self):
        payload = json.dumps({"tasks": "not a list", "permission_level": "AUTO"})
        with pytest.raises(ModelValidationError) as ei:
            validate_structured_output(payload, _PlanSchema)
        errs = ei.value.details["validation_errors"]
        assert any("tasks" in e["path"] for e in errs)

    def test_validator_reusable_object(self):
        v = StructuredOutputValidator(_PlanSchema)
        payload = json.dumps(
            {"tasks": [{"t": 1}], "permission_level": "AUTOMATIC"}
        )
        instance = v.validate(payload)
        assert isinstance(instance, _PlanSchema)
        schema = v.expected_json_schema
        assert "tasks" in schema.get("properties", {})

    def test_dict_schema_rejects_non_object_json(self):
        with pytest.raises(ModelValidationError):
            validate_structured_output("[1,2,3]", {})


# ---------------------------------------------------------------------------
# Model Router
# ---------------------------------------------------------------------------


class TestModelRouter:
    @pytest.fixture()
    def router(self):
        local = FakeModelProvider()

        cloud_cfg = CloudProviderConfig(
            provider_name="cloud_mock",
            base_url="https://example.invalid",
            api_key_env_var="NONEXISTENT_VAR_XYZ",
            model="mock-model",
            capabilities=(
                ProviderCapability.STRUCTURED_JSON,
                ProviderCapability.DEEP_REASONING,
            ),
        )

        class UnavailableCloud:
            name = "cloud_mock"
            tier = ProviderTier.CLOUD

            def info(self):
                return ModelProviderInfo(
                    name=self.name,
                    tier=self.tier,
                    model_name=cloud_cfg.model,
                    capabilities=cloud_cfg.capabilities,
                    available=False,
                )

            async def generate(self, req):
                raise NotImplementedError

        return ModelRouter(providers=[local, UnavailableCloud()])

    def test_default_router_has_fake_only(self):
        r = default_model_router()
        assert r.list_available()[0].name == "fake"

    def test_select_returns_local_when_privacy_first(self, router):
        req = ModelRequest(messages=[ChatMessage(ChatRole.USER, "hi")])
        decision = router.select(req)
        assert decision.tier == ProviderTier.LOCAL
        assert RoutingReason.PRIVACY_REQUIREMENT in decision.reasons

    def test_force_cloud_fails_when_unavailable(self, router):
        req = ModelRequest(messages=[ChatMessage(ChatRole.USER, "hi")])
        with pytest.raises(RuntimeError, match="no CLOUD provider"):
            router.select(req, strategy=RoutingStrategy.FORCE_CLOUD)

    def test_force_local_returns_local(self, router):
        req = ModelRequest(messages=[ChatMessage(ChatRole.USER, "hi")])
        decision = router.select(req, strategy=RoutingStrategy.FORCE_LOCAL)
        assert decision.tier == ProviderTier.LOCAL
        assert RoutingReason.FORCED in decision.reasons

    def test_required_capability_missing_uses_fallback(self, router):
        class Missing:
            name = "missing_caps"
            tier = ProviderTier.LOCAL

            def info(self):
                return ModelProviderInfo(
                    name=self.name,
                    tier=ProviderTier.LOCAL,
                    model_name="m",
                    capabilities=(),
                    available=True,
                )

            async def generate(self, req):
                raise NotImplementedError

        r2 = ModelRouter(providers=[Missing()])
        req = ModelRequest(messages=[ChatMessage(ChatRole.USER, "hi")])
        decision = r2.select(
            req,
            required_capabilities=[ProviderCapability.DEEP_REASONING],
        )
        assert RoutingReason.UNAVAILABLE_FALLBACK in decision.reasons

    def test_no_available_providers_raises(self):
        class Off:
            name = "off"
            tier = ProviderTier.LOCAL

            def info(self):
                return ModelProviderInfo(
                    name=self.name,
                    tier=ProviderTier.LOCAL,
                    model_name="m",
                    capabilities=(),
                    available=False,
                )

            async def generate(self, req):
                raise NotImplementedError

        r = ModelRouter(providers=[Off()])
        req = ModelRequest(messages=[ChatMessage(ChatRole.USER, "hi")])
        with pytest.raises(RuntimeError, match="No available"):
            r.select(req)

    def test_get_provider_returns_registered(self, router):
        assert router.get_provider("fake") is not None
        with pytest.raises(KeyError):
            router.get_provider("nonexistent")


# ---------------------------------------------------------------------------
# Cloud provider — env configuration only (no real network calls).
# ---------------------------------------------------------------------------


class TestCloudProviderNoNetwork:
    def test_available_false_when_env_missing(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        p = OpenAICloudProvider.from_env()
        assert p.info().available is False

    def test_available_true_when_env_present(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-placeholder")
        p = OpenAICloudProvider.from_env()
        assert p.info().available is True
        assert p.info().tier == ProviderTier.CLOUD

    def test_configuration_raised_on_generate_without_env(self, monkeypatch):
        import asyncio

        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        p = OpenAICloudProvider.from_env()
        req = ModelRequest(messages=[ChatMessage(ChatRole.USER, "hi")])
        with pytest.raises(ModelConfigurationError) as ei:
            asyncio.get_event_loop().run_until_complete(p.generate(req))
        assert "OPENAI_API_KEY" in ei.value.details.get("missing_env_vars", [])

    def test_build_cloud_provider_skips_when_no_key(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        assert build_cloud_provider_from_env() is None

    def test_build_cloud_provider_present_when_key_set(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-x")
        p = build_cloud_provider_from_env()
        assert p is not None
        assert p.info().available is True

    def test_encode_message_includes_role_and_content(self):
        msg = ChatMessage(role=ChatRole.SYSTEM, content="sys", name="n")
        enc = OpenAICloudProvider._encode_message(msg)
        assert enc["role"] == "system"
        assert enc["content"] == "sys"
        assert enc["name"] == "n"

    def test_parse_finish_reason_mapping(self):
        assert (
            OpenAICloudProvider._parse_finish_reason("stop")
            == ModelFinishReason.STOP
        )
        assert (
            OpenAICloudProvider._parse_finish_reason("tool_calls")
            == ModelFinishReason.TOOL_CALL
        )
        assert (
            OpenAICloudProvider._parse_finish_reason("__unknown__")
            == ModelFinishReason.ERROR
        )


# ---------------------------------------------------------------------------
# End-to-end: router + fake provider + validation
# ---------------------------------------------------------------------------


class TestPhase3EndToEnd:
    @pytest.mark.asyncio
    async def test_router_to_fake_provider_flow(self):
        router = default_model_router()
        req = ModelRequest(
            messages=[
                ChatMessage(ChatRole.USER, "please summarize this document")
            ],
            structured_output_mode=StructuredOutputMode.JSON,
            expected_output_schema=dict,
        )
        decision = router.select(req)
        provider = router.get_provider(decision.provider_name)
        resp: ModelResponse = await provider.generate(req)
        parsed = validate_structured_output(
            resp.content,
            dict,
            request_id=resp.request_id,
            provider_name=resp.provider_name,
        )
        assert "summary" in parsed
        assert parsed["summary"] != ""
