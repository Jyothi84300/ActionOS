"""Structured output validation.

Per §11 and §18 of the Master Specification:

  * The Planner MUST output structured data (JSON), never natural-
    language-only instructions.
  * Model output MUST be validated before entering planning/execution.

The :class:`StructuredOutputValidator` accepts either a raw JSON Schema
dict or a Pydantic BaseModel class and, given a raw model response
string, returns the deserialized object OR raises
:class:`ModelValidationError`.
"""

from __future__ import annotations

import json
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError as PydanticValidationError

from app.model.errors import ModelValidationError

T = TypeVar("T")


def _schema_from_class(model_cls: type) -> dict:
    """Extract JSON Schema from a Pydantic v2 BaseModel class."""
    if isinstance(model_cls, type) and issubclass(model_cls, BaseModel):
        return model_cls.model_json_schema()
    raise TypeError(
        f"expected a Pydantic BaseModel subclass, got {type(model_cls).__name__}"
    )


def _format_pydantic_errors(raw: list[dict]) -> list[dict]:
    """Flatten Pydantic v2 error dicts into a simple shape."""
    out: list[dict] = []
    for err in raw:
        loc = err.get("loc", ())
        out.append(
            {
                "path": ".".join(str(x) for x in loc) if loc else "<root>",
                "type": str(err.get("type", "unknown")),
                "message": str(err.get("msg", "")),
            }
        )
    return out


def validate_structured_output(
    raw_output: str,
    expected_schema: type[BaseModel] | dict[str, Any],
    *,
    request_id: Any | None = None,
    provider_name: str | None = None,
) -> dict[str, Any] | Any:
    """Validate ``raw_output`` JSON against ``expected_schema``.

    Parameters
    ----------
    raw_output:
        Raw text emitted by the model.  Must be valid JSON.
    expected_schema:
        Either a Pydantic ``BaseModel`` subclass (used for validation +
        instance construction) OR a raw JSON Schema ``dict`` used only
        for structural validation.
    request_id:
        Optional identifier forwarded to the raised error if any.
    provider_name:
        Optional provider name forwarded to the raised error if any.

    Returns
    -------
    When ``expected_schema`` is a BaseModel class, returns the
    constructed instance.  When it is a raw dict schema, returns the
    parsed ``dict`` object.

    Raises
    ------
    ModelValidationError
        If the JSON is invalid or the data fails the schema.
    """
    if not isinstance(raw_output, str) or not raw_output.strip():
        raise ModelValidationError(
            message="Model returned empty string; expected JSON output.",
            raw_output=raw_output or "",
            request_id=request_id,
            provider_name=provider_name,
        )

    try:
        parsed: Any = json.loads(raw_output)
    except json.JSONDecodeError as exc:
        raise ModelValidationError(
            message=f"Model output is not valid JSON: {exc.msg} at line {exc.lineno} col {exc.colno}",
            raw_output=raw_output,
            request_id=request_id,
            provider_name=provider_name,
        ) from exc

    if isinstance(expected_schema, dict) or expected_schema is dict:
        if not isinstance(parsed, dict):
            raise ModelValidationError(
                message="Model output was JSON but not an object (expected a JSON object per schema).",
                raw_output=raw_output,
                request_id=request_id,
                provider_name=provider_name,
            )
        return parsed

    if isinstance(expected_schema, type) and issubclass(expected_schema, BaseModel):
        try:
            if isinstance(parsed, dict):
                return expected_schema.model_validate(parsed)
            raise ModelValidationError(
                message="Model output was JSON but not an object; expected a JSON object matching the Pydantic schema.",
                raw_output=raw_output,
                request_id=request_id,
                provider_name=provider_name,
            )
        except PydanticValidationError as exc:
            raise ModelValidationError(
                message="Model output did not match the expected Pydantic schema.",
                validation_errors=_format_pydantic_errors(exc.errors()),
                raw_output=raw_output,
                request_id=request_id,
                provider_name=provider_name,
            ) from exc

    raise TypeError(
        "expected_schema must be a Pydantic BaseModel class or a dict, "
        f"got {type(expected_schema).__name__}"
    )


class StructuredOutputValidator:
    """Reusable validator bound to a single schema."""

    def __init__(self, expected_schema: type[BaseModel] | dict[str, Any]) -> None:
        if isinstance(expected_schema, type) and issubclass(expected_schema, BaseModel):
            self._model_cls = expected_schema
            self._raw_schema: dict | None = None
        elif isinstance(expected_schema, dict):
            self._model_cls = None
            self._raw_schema = expected_schema
        else:
            raise TypeError(
                "expected_schema must be a BaseModel class or dict"
            )

    def validate(
        self,
        raw_output: str,
        *,
        request_id: Any | None = None,
        provider_name: str | None = None,
    ) -> dict | BaseModel:
        schema: type[BaseModel] | dict = (
            self._raw_schema if self._raw_schema is not None else self._model_cls
        )
        return validate_structured_output(
            raw_output,
            schema,
            request_id=request_id,
            provider_name=provider_name,
        )

    @property
    def expected_json_schema(self) -> dict:
        if self._raw_schema is not None:
            return self._raw_schema
        return _schema_from_class(self._model_cls)  # type: ignore[arg-type]
