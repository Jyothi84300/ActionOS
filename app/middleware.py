import time
import uuid
from typing import Awaitable, Callable

import structlog.contextvars
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.logging_config import get_logger

logger = get_logger(__name__)


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.state.request_id = request_id

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        start_time = time.perf_counter()
        client_host = request.client.host if request.client else None
        logger.info(
            "http.request.started",
            method=request.method,
            url=str(request.url.path),
            client=client_host,
        )

        response = await call_next(request)

        process_time_ms = (time.perf_counter() - start_time) * 1000
        status_code = response.status_code

        logger.info(
            "http.request.finished",
            method=request.method,
            url=str(request.url.path),
            status=status_code,
            duration_ms=round(process_time_ms, 2),
        )

        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time-Ms"] = f"{process_time_ms:.2f}"
        return response
