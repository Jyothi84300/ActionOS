import os
from collections.abc import Generator
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Settings, get_settings
from app.database import Base, get_db
from app.deps import get_current_user_id
from app.main import create_app
from app.models import User

TEST_USER_ID = UUID("00000000-0000-0000-0000-000000000001")
TEST_USER_EMAIL = "test@actionos.local"
OTHER_USER_ID = UUID("00000000-0000-0000-0000-000000000002")


@pytest.fixture(scope="session")
def test_settings() -> Settings:
    return Settings(
        APP_NAME="ActionOS-Test",
        ENVIRONMENT="test",
        DEBUG=True,
        DATABASE_URL="sqlite:///:memory:",
        SECRET_KEY="test-secret-key",
        LOG_LEVEL="ERROR",
    )


@pytest.fixture(scope="session")
def db_engine(test_settings: Settings) -> Engine:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


@pytest.fixture(scope="session")
def TestingSessionLocal(db_engine: Engine):
    Base.metadata.create_all(bind=db_engine)
    return sessionmaker(autocommit=False, autoflush=False, bind=db_engine, future=True)


@pytest.fixture()
def db_session(TestingSessionLocal, db_engine: Engine) -> Generator[Session, None, None]:
    Base.metadata.drop_all(bind=db_engine)
    Base.metadata.create_all(bind=db_engine)

    session = TestingSessionLocal()
    try:
        test_user = User(id=TEST_USER_ID, email=TEST_USER_EMAIL, auth_provider="mock")
        other_user = User(id=OTHER_USER_ID, email="other@actionos.local", auth_provider="mock")
        session.add_all([test_user, other_user])
        session.commit()
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(db_session: Session, test_settings: Settings) -> Generator[TestClient, None, None]:
    def _get_db_override():
        yield db_session

    async def _get_current_user_id_override():
        return TEST_USER_ID

    app = create_app()
    app.dependency_overrides[get_db] = _get_db_override
    app.dependency_overrides[get_current_user_id] = _get_current_user_id_override
    app.dependency_overrides[get_settings] = lambda: test_settings
    app.state.settings = test_settings

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()


@pytest.fixture()
def client_raw_no_override(
    db_session: Session, test_settings: Settings
) -> Generator[TestClient, None, None]:
    def _get_db_override():
        yield db_session

    app = create_app()
    app.dependency_overrides[get_db] = _get_db_override
    app.dependency_overrides[get_settings] = lambda: test_settings
    app.state.settings = test_settings

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()


@pytest.fixture()
def auth_headers() -> dict[str, str]:
    return {"Authorization": "Bearer test-mock-token"}


@pytest.fixture()
def sample_goal_payload() -> dict:
    return {
        "title": "Finish research paper draft",
        "description": "Complete first draft of the ML paper",
        "objective": "Have a submittable draft by Friday",
        "deadline": "2026-09-04T23:59:00Z",
        "priority": "high",
        "category": "academic",
        "constraints": ["no late submissions", "citation count >= 20"],
    }
