from typing import Any, Iterable, Optional
from uuid import UUID, uuid4

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError as PydanticValidationError


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    request_id: Optional[str] = None


class ErrorResponse(BaseModel):
    error: ErrorDetail


class ActionOSError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)


class ValidationError(ActionOSError):
    def __init__(self, message: str = "Validation error", details: Optional[dict[str, Any]] = None) -> None:
        super().__init__("VALIDATION_ERROR", message, status.HTTP_400_BAD_REQUEST, details)


class UnauthenticatedError(ActionOSError):
    def __init__(self, message: str = "Authentication required") -> None:
        super().__init__("UNAUTHENTICATED", message, status.HTTP_401_UNAUTHORIZED)


class PermissionDeniedError(ActionOSError):
    def __init__(self, message: str = "Permission denied") -> None:
        super().__init__("PERMISSION_DENIED", message, status.HTTP_403_FORBIDDEN)


class ForbiddenResourceError(ActionOSError):
    def __init__(self, message: str = "Forbidden resource") -> None:
        super().__init__("FORBIDDEN_RESOURCE", message, status.HTTP_403_FORBIDDEN)


class GoalNotFoundError(ActionOSError):
    def __init__(self, goal_id: Optional[UUID] = None) -> None:
        msg = "The requested goal does not exist."
        if goal_id:
            msg = f"The requested goal {goal_id} does not exist."
        super().__init__("GOAL_NOT_FOUND", msg, status.HTTP_404_NOT_FOUND)


class TaskNotFoundError(ActionOSError):
    def __init__(self, task_id: Optional[UUID] = None) -> None:
        msg = "The requested task does not exist."
        if task_id:
            msg = f"The requested task {task_id} does not exist."
        super().__init__("TASK_NOT_FOUND", msg, status.HTTP_404_NOT_FOUND)


class ActionNotFoundError(ActionOSError):
    def __init__(self, action_id: Optional[UUID] = None) -> None:
        msg = "The requested action does not exist."
        if action_id:
            msg = f"The requested action {action_id} does not exist."
        super().__init__("ACTION_NOT_FOUND", msg, status.HTTP_404_NOT_FOUND)


class PermissionNotFoundError(ActionOSError):
    def __init__(self, permission_id: Optional[UUID] = None) -> None:
        msg = "The requested permission does not exist."
        if permission_id:
            msg = f"The requested permission {permission_id} does not exist."
        super().__init__("PERMISSION_NOT_FOUND", msg, status.HTTP_404_NOT_FOUND)


class ConflictError(ActionOSError):
    def __init__(self, code: str, message: str, details: Optional[dict[str, Any]] = None) -> None:
        super().__init__(code, message, status.HTTP_409_CONFLICT, details)


class UnprocessableError(ActionOSError):
    def __init__(self, code: str, message: str, details: Optional[dict[str, Any]] = None) -> None:
        super().__init__(code, message, status.HTTP_422_UNPROCESSABLE_ENTITY, details)


class InternalError(ActionOSError):
    def __init__(self, message: str = "Internal server error", details: Optional[dict[str, Any]] = None) -> None:
        super().__init__("INTERNAL_ERROR", message, status.HTTP_500_INTERNAL_SERVER_ERROR, details)


def build_error_response(
    request: Request,
    code: str,
    message: str,
    status_code: int,
    details: Optional[dict[str, Any]] = None,
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", str(uuid4()))
    payload = ErrorResponse(
        error=ErrorDetail(
            code=code,
            message=message,
            details=details or {},
            request_id=str(request_id),
        )
    )
    return JSONResponse(status_code=status_code, content=payload.model_dump())


def _format_pydantic_errors(raw_errors: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    formatted: list[dict[str, Any]] = []
    for err in raw_errors:
        loc = err.get("loc", [])
        field: str
        if len(loc) == 0:
            field = "__root__"
        elif loc[0] in {"body", "query", "path", "header", "cookie"} and len(loc) > 1:
            field = ".".join(str(part) for part in loc[1:])
        else:
            field = ".".join(str(part) for part in loc)
        formatted.append(
            {
                "field": field,
                "type": str(err.get("type", "unknown")),
                "message": str(err.get("msg", "")),
            }
        )
    return formatted


def register_exception_handlers(app) -> None:
    @app.exception_handler(ActionOSError)
    async def actionos_exception_handler(request: Request, exc: ActionOSError) -> JSONResponse:
        return build_error_response(request, exc.code, exc.message, exc.status_code, exc.details)

    @app.exception_handler(RequestValidationError)
    async def request_validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        field_errors = _format_pydantic_errors(exc.errors())
        count = len(field_errors)
        message = (
            f"{count} field validation error(s) in the request."
            if count != 1
            else "1 field validation error in the request."
        )
        return build_error_response(
            request,
            "VALIDATION_ERROR",
            message,
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            {"field_errors": field_errors},
        )

    @app.exception_handler(PydanticValidationError)
    async def pydantic_validation_exception_handler(
        request: Request, exc: PydanticValidationError
    ) -> JSONResponse:
        field_errors = _format_pydantic_errors(exc.errors())
        count = len(field_errors)
        message = (
            f"{count} field validation error(s)."
            if count != 1
            else "1 field validation error."
        )
        return build_error_response(
            request,
            "VALIDATION_ERROR",
            message,
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            {"field_errors": field_errors},
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        return build_error_response(
            request,
            "INTERNAL_ERROR",
            "Internal server error",
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            {"detail": str(exc)} if app.state.settings.DEBUG else {},
        )
