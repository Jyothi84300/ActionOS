# ActionOS Backend — Phase 1 Foundation

Python + FastAPI backend foundation for ActionOS (Personal AI Execution Layer).
Implements the database schema, Pydantic schemas, structured logging, standard
API error envelope, request IDs, and the Phase 1 API endpoints.

## Scope — Phase 1 ONLY

Implemented:

- PostgreSQL + SQLAlchemy 2.0 ORM models (13 entities, all stable `skill_id`s)
- Pydantic v2 request / response schemas with full type hints
- Alembic migration (initial schema 000000000001)
- Structured JSON logging via `structlog`, `request_id` correlation
- Standard API error envelope (`error.code`, `message`, `details`, `request_id`)
- FastAPI dependency injection (DB sessions, mock auth for foundation)
- 8 API endpoints as specified in §24
- 25 pytest tests covering success, 404, 403, 401, validation, and error envelope

NOT implemented (explicitly out of scope for Phase 1):

- LLM / AI integrations, Planner / Executor / Verifier logic
- Cloud or local model adapters
- Android / Room / SQLite / offline execution / sync
- Vector database / embeddings
- Real integrations (Calendar, Email, etc.)
- Actual Skill / Tool behavior code
- Production auth provider (OAuth / JWT signing — mock bearer only)

## Quick Start

### 1. Create environment

```bash
cd backend
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
# source .venv/bin/activate

pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env to taste — DATABASE_URL, SECRET_KEY, etc.
```

### 3. Start PostgreSQL and run migrations

```bash
# With a running PostgreSQL matching DATABASE_URL:
alembic upgrade head
```

### 4. Run the server

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

OpenAPI docs: <http://127.0.0.1:8000/docs>

### 5. Run tests

```bash
pytest tests/ -v
# With coverage:
pytest tests/ --cov=app --cov-report=term-missing
```

Tests use an in-memory SQLite engine, no PostgreSQL required.

## Module Layout

```
backend/
├── alembic/                       # Alembic config
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
│       └── 000000000001_initial_foundation_schema.py
├── alembic.ini
├── app/
│   ├── __init__.py                # exports + __version__
│   ├── main.py                    # FastAPI app factory, lifespan, middleware, exception handlers
│   ├── config.py                  # pydantic-settings Settings (DATABASE_URL, SECRET_KEY, …)
│   ├── database.py                # SQLAlchemy Base, engine, SessionLocal, get_db()
│   ├── logging_config.py          # structlog setup (JSON in prod, colored console in dev)
│   ├── middleware.py              # RequestIDMiddleware, timing headers, access logs
│   ├── errors.py                  # ActionOSError hierarchy + register_exception_handlers + envelope
│   ├── enums.py                   # GoalStatus, ActionState, Priority, SkillCapability, …
│   ├── models.py                  # 13 SQLAlchemy declarative models + relationships
│   ├── schemas.py                 # Pydantic v2 models: GoalCreate, GoalResponse, TaskResponse, …
│   ├── deps.py                    # get_current_user_id (mock bearer), ensure_owner()
│   ├── crud.py                    # Pure CRUD helpers (create_goal, list_tasks_for_goal, …)
│   └── api/
│       ├── __init__.py
│       └── v1/
│           ├── __init__.py        # aggregates routers under /api/v1
│           ├── health.py          # GET /api/v1/health
│           ├── goals.py           # POST /goals, GET /goals/{id}, GET /goals/{id}/tasks
│           ├── actions.py         # GET /actions/{id}
│           ├── skills.py          # GET /skills
│           └── permissions.py     # GET /permissions, PUT /permissions/{id}
├── requirements.txt
├── pytest.ini
├── .env.example
├── .gitignore
└── tests/
    ├── __init__.py
    ├── conftest.py                # fixtures: db_session, client, auth_headers, …
    ├── test_health.py             # 4 tests (incl. unauth error envelope)
    ├── test_goals.py              # 9 tests (create, get, 404, 403, tasks empty / ordered / 404)
    ├── test_actions.py            # 5 tests (pending, VERIFIED, UNVERIFIED, 404, 403)
    ├── test_skills.py             # 2 tests (empty + populated listing by stable skill_id)
    └── test_permissions.py        # 5 tests (list, scope to user, grant/revoke, 404, 403)
```

## Database Tables (13)

Aligned with §23.3 of the Master Specification. Stable `skill_id` used everywhere as the Skill relational identifier (§12.2, corrected in v1.1).

| Table | Purpose |
|-------|---------|
| `users` | Account identity, `email` unique indexed |
| `goals` | User goals with state machine (`ACTIVE/PAUSED/COMPLETED/CANCELLED/FAILED`), `sync_metadata` |
| `tasks` | Plan steps within a goal; references `skill_id` (stable) + `skill_version` |
| `actions` | Tool invocations under each task; state machine (`PENDING/WAITING_CONFIRMATION/RUNNING/COMPLETED/FAILED/CANCELLED/BLOCKED/UNVERIFIED`) |
| `verifications` | Independent verification for an action (`VERIFIED`/`UNVERIFIED`); `method=null` when not possible |
| `memories` | Per-user / per-goal durable memory entries (`decision`, `approval`, `deadline`, `history_entry`) |
| `skills` | Registry by stable `skill_id` (PK); `name` is just a mutable label |
| `skill_versions` | Manifest history for each skill, so historical Task/Action references remain auditable |
| `tools` | Concrete operations owned by one Skill; `permission_level`, `input_schema`/`output_schema`, `capability` |
| `permissions` | Per-user / per-tool ActionOS-policy grants (not platform permissions) |
| `context_references` | Opaque pointers to external sources used during planning; `trust_level=untrusted` default |
| `audit_events` | Append-only audit log (permission decisions, action transitions, platform-permission outcomes) |
| `offline_queue` | Actions queued for online execution when connectivity returns |

## APIs Implemented (8 / §24)

Base path: `/api/v1`. All endpoints except `/health` require `Authorization: Bearer <token>`.
Authorization is scoped to the authenticated `user_id` — cross-user access returns `403 FORBIDDEN_RESOURCE`.

| Method | Path | Purpose |
|--------|------|---------|
| `GET`  | `/health` | Liveness — no auth → `{"status":"ok"}` |
| `POST` | `/goals` | Create goal. Returns `201 {id, status, created_at}` |
| `GET`  | `/goals/{goal_id}` | Full Goal object |
| `GET`  | `/goals/{goal_id}/tasks` | Ordered Task array for a goal |
| `GET`  | `/actions/{action_id}` | Action state + optional nested verification |
| `GET`  | `/skills` | Skill summaries by stable `skill_id` (`skill_id, name, current_version, capability`) |
| `GET`  | `/permissions` | Caller's ActionOS permission grants |
| `PUT`  | `/permissions/{permission_id}` | Grant or revoke `{"granted": bool}` — updates granted_at / revoked_at |

## Standard Error Envelope

All errors (ActionOS-raised, FastAPI validation mapped via handlers, and unhandled exceptions
mapped to `INTERNAL_ERROR` in production / with detail in DEBUG) use:

```json
{
  "error": {
    "code": "GOAL_NOT_FOUND",
    "message": "The requested goal 11111111-… does not exist.",
    "details": {},
    "request_id": "37e0c6c1-5b46-4f19-86d4-37317ca1d2c4"
  }
}
```

Codes map to HTTP status as specified in §25.1:

| Category | Codes | HTTP |
|----------|-------|------|
| Validation | `VALIDATION_ERROR`, `MISSING_FIELD` | 400 |
| Authentication | `UNAUTHENTICATED` | 401 |
| Authorization | `PERMISSION_DENIED`, `FORBIDDEN_RESOURCE`, `PLATFORM_PERMISSION_MISSING` | 403 |
| Not Found | `GOAL_NOT_FOUND`, `TASK_NOT_FOUND`, `ACTION_NOT_FOUND`, `PERMISSION_NOT_FOUND` | 404 |
| Conflict | `PLAN_ALREADY_EXISTS`, `ALREADY_PROCESSED` | 409 |
| Unprocessable | `UNSUPPORTED_GOAL`, `SKILL_UNAVAILABLE` | 422 |
| Server | `INTERNAL_ERROR` | 500 |

## Logging & Observability

- Structured `structlog` pipeline; colored dev console, JSON in production
- Every HTTP request: `request_id` bound via contextvars, logged at start + end with method, path, status, duration_ms
- Response headers include `X-Request-ID` and `X-Process-Time-Ms`
- Goal creation and permission updates emit explicit log lines with stable IDs
- Rule: logs never contain raw tool input/output payloads or secrets; only refs/IDs

## Deviations / Open Notes

1. **Authentication** — The master spec marks `auth_provider = TBD` (§36 / Open Decisions).
   For foundation phase we accept any `Authorization: Bearer <non-empty>` and map it to a
   single stable mock user id `00000000-0000-0000-0000-000000000001`. Replace
   `get_current_user_id` in `app/deps.py` once an auth provider (§36) is selected.

2. **UUID storage** — Models use the cross-dialect `sqlalchemy.Uuid` type for the models
   (allows tests on SQLite) while the Alembic migration explicitly uses `postgresql.UUID`
   for production PostgreSQL. Both are equivalent in practice.

3. **AuditEvent column name** — The DB column is `metadata` per §23.3; on the Python side
   it is exposed as `event_metadata` because `Base.metadata` is a reserved declarative
   attribute. Serialization / migrations keep the canonical column name `metadata`.

4. **FastAPI validation responses** — Native 422 FastAPI validation errors are not yet
   mapped into the `{error: {...}}` envelope. Add a dedicated `RequestValidationError`
   handler when moving to a public-facing API surface to make validation errors uniform
   with `VALIDATION_ERROR` code.

5. **Seed data / skill registry** — No seed skills, tools, or permissions are created
   automatically. Populate the `skills / skill_versions / tools / permissions` tables
   out-of-band (or via a later seed migration) when building Phase 2 (Core Skills).

6. **Test coverage** — Uses in-memory SQLite for speed and portability. A secondary CI
   profile should also run the suite against a real PostgreSQL container to exercise
   native enums, UUID operators, and transaction semantics before deploy.

## Run Commands Cheatsheet

```bash
# install
pip install -r requirements.txt

# DB (PostgreSQL running, matching DATABASE_URL)
alembic upgrade head        # apply migrations
alembic revision --autogenerate -m "description"   # new migration

# server
uvicorn app.main:app --reload

# tests
pytest tests/ -v
pytest tests/ --cov=app --cov-report=term-missing
```
