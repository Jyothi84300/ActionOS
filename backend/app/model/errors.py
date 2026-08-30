"""Model-layer errors — provider-neutral exception hierarchy.

All errors raised by ModelProvider / ModelRouter implementations should
be one of these classes so the Agent Core can handle them uniformly.
"""

from __future__ import annotations

from uuid import UUID


class ModelError(Exception):
    """Base class for all model-layer errors."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        request_id: UUID | None = None,
        provider_name: str | None = None,
        details: dict | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.request_id = request_id
        self.provider_name = provider_name
        self.details = details or {}
        super().__init__(message)


class ModelProviderError(ModelError):
    """Raised when the underlying provider call fails."""

    def __init__(
        self,
        message: str = "Model provider call failed",
        *,
        status_code: int | None = None,
        request_id: UUID | None = None,
        provider_name: str | None = None,
        details: dict | None = None,
    ) -> None:
        merged = dict(details or {})
        if status_code is not None:
            merged["status_code"] = status_code
        super().__init__(
            "PROVIDER_ERROR",
            message,
            request_id=request_id,
            provider_name=provider_name,
            details=merged,
        )


class ModelValidationError(ModelError):
    """Raised when structured output fails validation (§18 of spec)."""

    def __init__(
        self,
        message: str = "Model output failed structured validation",
        *,
        validation_errors: list[dict] | None = None,
        raw_output: str | None = None,
        request_id: UUID | None = None,
        provider_name: str | None = None,
    ) -> None:
        details: dict = {}
        if validation_errors:
            details["validation_errors"] = validation_errors
        if raw_output is not None:
            # Truncate long outputs to avoid logging megabytes of text.
            preview = raw_output if len(raw_output) <= 2000 else raw_output[:2000] + "...[truncated]"
            details["raw_output_preview"] = preview
        super().__init__(
            "STRUCTURED_OUTPUT_INVALID",
            message,
            request_id=request_id,
            provider_name=provider_name,
            details=details,
        )


class ModelRateLimitError(ModelProviderError):
    """Raised when a provider responds with a rate-limit / 429."""

    def __init__(
        self,
        message: str = "Model provider rate limit exceeded",
        *,
        retry_after_seconds: float | None = None,
        request_id: UUID | None = None,
        provider_name: str | None = None,
    ) -> None:
        details = {}
        if retry_after_seconds is not None:
            details["retry_after_seconds"] = retry_after_seconds
        super().__init__(
            message,
            status_code=429,
            request_id=request_id,
            provider_name=provider_name,
            details=details,
        )


class ModelTimeoutError(ModelProviderError):
    """Raised when a provider call exceeds its timeout window."""

    def __init__(
        self,
        message: str = "Model provider request timed out",
        *,
        timeout_seconds: float | None = None,
        request_id: UUID | None = None,
        provider_name: str | None = None,
    ) -> None:
        details = {}
        if timeout_seconds is not None:
            details["timeout_seconds"] = timeout_seconds
        super().__init__(
            message,
            status_code=408,
            request_id=request_id,
            provider_name=provider_name,
            details=details,
        )


class ModelConfigurationError(ModelError):
    """Raised when a provider is improperly configured.

    Per the Phase 3 requirements, the application MUST still start even
    when external credentials are missing — this error is raised at
    call-time, not at import-time, so callers can fall back to a
    deterministic ``fake`` provider.
    """

    def __init__(
        self,
        message: str = "Model provider is not configured",
        *,
        missing_env_vars: list[str] | None = None,
        provider_name: str | None = None,
    ) -> None:
        details = {}
        if missing_env_vars:
            details["missing_env_vars"] = missing_env_vars
        super().__init__(
            "MODEL_PROVIDER_NOT_CONFIGURED",
            message,
            provider_name=provider_name,
            details=details,
        )
