"""Configurable cloud provider adapter.

Implements a provider-neutral HTTP-based Cloud provider that:

  * Is configured through environment variables only.
  * Returns ``available=False`` (never raises) when credentials are
    missing, satisfying the Phase-3 rule that the app must still start.
  * Calls the REST endpoint only inside :meth:`generate` so the vendor
    SDK / HTTP layer is never imported at module load.

For the MVP we only support OpenAI-compatible endpoints since that is
the de-facto REST standard most vendors implement.  Additional adapters
inherit from :class:`GenericCloudProvider`.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.logging_config import get_logger
from app.model.errors import (
    ModelConfigurationError,
    ModelProviderError,
    ModelRateLimitError,
    ModelTimeoutError,
)
from app.model.provider import (
    ModelProvider,
    ModelProviderInfo,
    ProviderCapability,
    ProviderTier,
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

logger = get_logger(__name__)


@dataclass(frozen=True)
class CloudProviderConfig:
    """Runtime configuration read from environment variables.

    No secrets are stored as source — everything is read at call time
    from the process environment.
    """

    provider_name: str
    base_url: str
    api_key_env_var: str
    model: str
    timeout_seconds: float = 60.0
    capabilities: tuple[ProviderCapability, ...] = (
        ProviderCapability.STRUCTURED_JSON,
        ProviderCapability.DEEP_REASONING,
    )

    def api_key(self) -> str | None:
        return os.environ.get(self.api_key_env_var)

    def is_configured(self) -> bool:
        key = self.api_key()
        return bool(key and self.base_url and self.model)


class GenericCloudProvider:
    """Base HTTP-based cloud provider.

    Subclasses override :meth:`_build_request_body` and
    :meth:`_parse_response` to adapt a specific vendor's REST format.
    """

    def __init__(self, config: CloudProviderConfig) -> None:
        self._config = config

    # ------------------------------------------------------------------
    # ModelProvider protocol
    # ------------------------------------------------------------------

    def info(self) -> ModelProviderInfo:
        return ModelProviderInfo(
            name=self._config.provider_name,
            tier=ProviderTier.CLOUD,
            model_name=self._config.model,
            capabilities=self._config.capabilities,
            available=self._config.is_configured(),
        )

    async def generate(self, request: ModelRequest) -> ModelResponse:
        if not self._config.is_configured():
            missing: list[str] = []
            if not self._config.api_key():
                missing.append(self._config.api_key_env_var)
            if not self._config.base_url:
                missing.append(f"{self._config.provider_name.upper()}_BASE_URL")
            if not self._config.model:
                missing.append(f"{self._config.provider_name.upper()}_MODEL")
            raise ModelConfigurationError(
                message=(
                    f"Cloud provider {self._config.provider_name!r} is not "
                    "configured. Set the required environment variables or "
                    "use the built-in 'fake' provider for local development."
                ),
                missing_env_vars=missing,
                provider_name=self._config.provider_name,
            )

        body = self._build_request_body(request)
        headers = {
            "Authorization": f"Bearer {self._config.api_key()}",
            "Content-Type": "application/json",
        }
        req = Request(
            self._build_request_url(),
            data=json.dumps(body).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        try:
            with urlopen(req, timeout=self._config.timeout_seconds) as resp:
                raw = resp.read().decode("utf-8")
                status = resp.getcode() or 200
        except TimeoutError as exc:
            raise ModelTimeoutError(
                timeout_seconds=self._config.timeout_seconds,
                request_id=request.request_id,
                provider_name=self._config.provider_name,
            ) from exc
        except HTTPError as exc:
            status = exc.code
            if status == 429:
                retry_after = exc.headers.get("Retry-After")
                retry_after_seconds: float | None = None
                try:
                    if retry_after is not None:
                        retry_after_seconds = float(retry_after)
                except ValueError:
                    retry_after_seconds = None
                raise ModelRateLimitError(
                    retry_after_seconds=retry_after_seconds,
                    request_id=request.request_id,
                    provider_name=self._config.provider_name,
                ) from exc
            try:
                err_body = exc.read().decode("utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                err_body = ""
            raise ModelProviderError(
                message=f"Cloud provider returned HTTP {status}: {err_body[:500]}",
                status_code=status,
                request_id=request.request_id,
                provider_name=self._config.provider_name,
            ) from exc
        except URLError as exc:
            raise ModelProviderError(
                message=f"Cloud provider unavailable: {exc.reason}",
                request_id=request.request_id,
                provider_name=self._config.provider_name,
            ) from exc

        if status < 200 or status >= 300:
            raise ModelProviderError(
                message=f"Cloud provider returned HTTP {status}",
                status_code=status,
                request_id=request.request_id,
                provider_name=self._config.provider_name,
            )

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ModelProviderError(
                message="Cloud provider returned non-JSON response",
                request_id=request.request_id,
                provider_name=self._config.provider_name,
                details={"preview": raw[:500]},
            ) from exc

        return self._parse_response(request, data, raw)

    # ------------------------------------------------------------------
    # overridable hooks
    # ------------------------------------------------------------------

    def _build_request_url(self) -> str:
        return self._config.base_url.rstrip("/") + "/chat/completions"

    def _build_request_body(self, request: ModelRequest) -> dict[str, Any]:
        messages = [self._encode_message(m) for m in request.messages]
        body: dict[str, Any] = {
            "model": self._config.model,
            "messages": messages,
            "temperature": request.temperature,
        }
        if request.max_tokens is not None:
            body["max_tokens"] = request.max_tokens
        if request.stop_sequences:
            body["stop"] = list(request.stop_sequences)
        if request.structured_output_mode == StructuredOutputMode.JSON:
            body["response_format"] = {"type": "json_object"}
        elif (
            request.structured_output_mode == StructuredOutputMode.JSON_SCHEMA
            and request.expected_output_schema is not None
        ):
            from pydantic import BaseModel

            schema: dict
            if isinstance(request.expected_output_schema, type) and issubclass(
                request.expected_output_schema, BaseModel
            ):
                schema = request.expected_output_schema.model_json_schema()
            else:
                schema = request.expected_output_schema
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "structured_output", "schema": schema},
            }
        return body

    def _parse_response(
        self, request: ModelRequest, data: dict[str, Any], raw: str
    ) -> ModelResponse:
        """Default parser for OpenAI-compatible response bodies."""
        try:
            choice = data["choices"][0]
            msg = choice.get("message", {})
            content = msg.get("content") or ""
            finish_raw = choice.get("finish_reason", "stop")
            finish = self._parse_finish_reason(finish_raw)
            usage_raw = data.get("usage", {}) or {}
            usage = ModelUsage(
                prompt_tokens=int(usage_raw.get("prompt_tokens", 0)),
                completion_tokens=int(usage_raw.get("completion_tokens", 0)),
                total_tokens=int(usage_raw.get("total_tokens", 0)),
            )
            model = data.get("model", self._config.model)
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ModelProviderError(
                message="Cloud provider response body missing expected fields",
                request_id=request.request_id,
                provider_name=self._config.provider_name,
                details={"preview": raw[:1000]},
            ) from exc

        return ModelResponse(
            content=content,
            finish_reason=finish,
            usage=usage,
            model_name=model,
            provider_name=self._config.provider_name,
            request_id=request.request_id,
            raw=data,
        )

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _encode_message(msg: ChatMessage) -> dict[str, Any]:
        out: dict[str, Any] = {"role": msg.role.value, "content": msg.content}
        if msg.name is not None:
            out["name"] = msg.name
        if msg.tool_call_id is not None:
            out["tool_call_id"] = msg.tool_call_id
        return out

    @staticmethod
    def _parse_finish_reason(raw: str) -> ModelFinishReason:
        mapping = {
            "stop": ModelFinishReason.STOP,
            "length": ModelFinishReason.LENGTH,
            "tool_calls": ModelFinishReason.TOOL_CALL,
            "tool_call": ModelFinishReason.TOOL_CALL,
            "content_filter": ModelFinishReason.CONTENT_FILTER,
        }
        return mapping.get(raw, ModelFinishReason.ERROR)


class OpenAICloudProvider(GenericCloudProvider):
    """Concrete OpenAI (or compatible) cloud provider.

    Environment variables:
      * ``OPENAI_API_KEY`` — required for availability.
      * ``OPENAI_BASE_URL`` — optional, default ``https://api.openai.com/v1``.
      * ``OPENAI_MODEL`` — optional, default ``gpt-4o-mini``.
    """

    @classmethod
    def from_env(cls) -> "OpenAICloudProvider":
        base_url = os.environ.get(
            "OPENAI_BASE_URL", "https://api.openai.com/v1"
        )
        model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        timeout_str = os.environ.get("OPENAI_TIMEOUT_SECONDS", "60")
        try:
            timeout = float(timeout_str)
        except ValueError:
            timeout = 60.0
        cfg = CloudProviderConfig(
            provider_name="openai",
            base_url=base_url,
            api_key_env_var="OPENAI_API_KEY",
            model=model,
            timeout_seconds=timeout,
            capabilities=(
                ProviderCapability.STRUCTURED_JSON,
                ProviderCapability.DEEP_REASONING,
            ),
        )
        return cls(cfg)


def build_cloud_provider_from_env() -> GenericCloudProvider | None:
    """Construct a cloud provider if any cloud env vars are present.

    Returns ``None`` if no cloud configuration is detected — callers
    should fall back to the :class:`FakeModelProvider`.
    """
    # OpenAI-compatible is the only built-in adapter for the MVP.
    if os.environ.get("OPENAI_API_KEY"):
        return OpenAICloudProvider.from_env()
    return None
