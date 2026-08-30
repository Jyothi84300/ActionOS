from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__
from app.api import api_router
from app.config import get_settings
from app.errors import register_exception_handlers
from app.logging_config import setup_logging
from app.middleware import RequestIDMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    setup_logging()
    app.state.settings = settings
    yield


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.APP_NAME,
        description="ActionOS Backend — Phase 1 Foundation",
        version=__version__,
        debug=settings.DEBUG,
        lifespan=lifespan,
    )

    app.add_middleware(RequestIDMiddleware)

    register_exception_handlers(app)

    app.include_router(api_router)

    return app


app = create_app()
