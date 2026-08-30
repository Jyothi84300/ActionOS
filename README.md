# ⚡ ActionOS

### An Agentic Operating System for Turning Intent into Action

ActionOS is an AI-powered agentic workspace designed to transform high-level user intent into structured goals, executable plans, permission-controlled actions, and verifiable outcomes.

Instead of requiring users to manually break a request into individual steps, ActionOS is designed around a simple principle:

> **Tell ActionOS what you want to accomplish. ActionOS figures out what needs to happen next.**

---

## ✨ What is ActionOS?

Traditional productivity applications require users to explicitly define tasks, schedules, and actions.

ActionOS takes a different approach.

A user can provide a high-level objective such as:

> **"Prepare me for my interview."**

The system processes that request through an agent pipeline:

```text
┌──────────────────────────────┐
│          User Intent         │
│  "Prepare me for interview"  │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│      Goal Understanding      │
│  Interpret intent & context  │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│      Context Retrieval       │
│  Gather relevant information │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│           Planner            │
│    Convert intent → tasks    │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│       Skill / Tool Router    │
│ Select appropriate capability│
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│      Permission Engine       │
│  Control actions before run  │
└──────────────┬───────────────┘
               │
          User Approval
               │
               ▼
┌──────────────────────────────┐
│     Controlled Execution     │
│   Execute registered tools   │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│         Verification         │
│ Validate the resulting state │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│        Action Result         │
│  Persisted + auditable state │
└──────────────────────────────┘
The result is an agent architecture that emphasizes control, traceability, permissions, and verification, rather than simply generating text.

🚀 Core Capabilities
🧠 Goal Understanding

ActionOS converts raw user input into a structured goal.

The goal-understanding layer extracts information such as:

Goal title
Description
Objective
Category
Priority
Deadline
Constraints
Recognized intents
Ambiguity
Confidence

The current MVP includes deterministic rule-based goal understanding with an extensible architecture for model-backed understanding.

🗺️ Intelligent Planning

Once a goal is understood, ActionOS generates a structured execution plan.

A plan can contain:

Ordered tasks
Task dependencies
Required skills
Required capabilities
Expected outputs
Verification requirements
Permission requirements

For example:

Goal
└── Prepare for interview
    │
    ├── Identify preparation requirements
    ├── Prepare likely interview questions
    ├── Prepare answer guidance
    ├── Identify important topics
    └── Create preparation checklist

Plans are persisted as real database tasks rather than existing only in the UI.

🧩 Skills & Tools

ActionOS uses a typed skill/tool architecture.

Each tool is represented through a contract containing:

Stable tool ID
Skill ID
Version
Description
Pydantic input schema
Pydantic output schema
Permission requirement
Capability classification
Verification behavior
Enabled/disabled state
Registered handler

This creates a controlled boundary between the agent and executable operations.

Current skill areas
📄 Document operations
✅ Task management
📅 Calendar operations
🤖 AI/model-backed capabilities
🎯 Goal-oriented agent workflows

The architecture is designed to make additional skills extensible without changing the core execution engine.

🔐 Permission-Controlled Execution

ActionOS does not blindly execute every planned operation.

The permission engine evaluates actions before execution.

Supported execution decisions include:

AUTOMATIC
CONFIRMATION_REQUIRED
BLOCKED

For confirmation-required operations, the user explicitly approves the action before execution.

Example:

Permission Needed

Continue with this plan?

ActionOS wants to execute tasks on your behalf.

[ Approve & Continue ]

This makes user authorization an explicit part of the agent workflow.

⚙️ Controlled Execution Engine

Actions are executed through a centralized execution engine.

The execution pipeline is designed around:

Permission
    ↓
Tool Resolution
    ↓
Executor
    ↓
Tool Handler
    ↓
Verification
    ↓
Persistence
    ↓
Audit

The executor only resolves registered tools.

Unknown tools fail safely rather than being executed dynamically.

This prevents the agent from treating arbitrary generated instructions as executable code.

🔎 Verification

Execution is not considered successful simply because a tool returned a value.

ActionOS includes a verification layer that can use different verification strategies, including:

Independent reads
Return-value validation
Satellite queries
Explicitly unverified outcomes where independent verification is impossible

The system therefore distinguishes between:

Executed
Executed + Verified
Executed + Unverified
Failed
Blocked
Cancelled

This provides a stronger foundation for trustworthy agentic workflows.

🧾 Auditability

ActionOS persists important execution state.

The system tracks concepts such as:

Goals
Tasks
Actions
Permissions
Verification results
Execution state
Tool identity
Result payloads

This enables the system to answer:

What did the agent intend to do?

Which tool did it execute?

Was permission required?

What happened during execution?

Was the result verified?

🧠 Model Layer

ActionOS includes a model abstraction layer designed to keep model providers separate from the rest of the application.

The architecture supports:

Application
     │
     ▼
  Model Router
     │
     ├───────────────┐
     ▼               ▼
Local Provider   Cloud Provider
                     │
                     ▼
              OpenAI-compatible API

The model layer includes routing and provider abstractions so model selection can evolve without coupling the application directly to a single provider.

Configuration supports:

MODEL_ROUTING_STRATEGY=auto
MODEL_PRIVACY_FIRST=true
OPENAI_API_KEY=
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini

API keys are loaded from environment configuration and should never be committed to source control.

🗄️ Persistence

ActionOS uses PostgreSQL for persistent application state.

Database-backed entities include concepts such as:

Users
Goals
Tasks
Actions
Skills
Tools
Permissions
Memory
Verification
Audit Events

SQLAlchemy is used for database interaction and Alembic is used for migrations.

🌐 Backend

The backend is built with:

Python
FastAPI
SQLAlchemy
PostgreSQL
Pydantic
Pydantic Settings
Alembic
Uvicorn
pytest
API structure

The API is organized under:

/api/v1/

Major API areas include:

Health
Goals
Tasks
Actions
Memory
Permissions
Skills

Example workflow:

POST /api/v1/goals

Create a goal.

POST /api/v1/goals/{goal_id}/plan

Generate a structured plan.

GET /api/v1/goals/{goal_id}/tasks

Retrieve generated tasks.

POST /api/v1/tasks/{task_id}/execute

Execute an approved task.

💻 Frontend

The frontend is built with:

Next.js
React
TypeScript
Tailwind CSS
Component-based UI architecture

The frontend provides an agentic workspace for interacting with:

Goals
Plans
Tasks
Actions
Skills
Permissions
Execution state
Results

The frontend communicates with the FastAPI backend through a typed API client.

🏗️ Project Structure
action-os/
│
├── backend/
│   │
│   ├── app/
│   │   ├── agent/
│   │   │   ├── context.py
│   │   │   ├── goal_understanding.py
│   │   │   ├── pipeline.py
│   │   │   ├── planner.py
│   │   │   ├── skill_router.py
│   │   │   ├── capability_router.py
│   │   │   ├── schemas.py
│   │   │   └── state.py
│   │   │
│   │   ├── api/
│   │   │   └── v1/
│   │   │
│   │   ├── execution/
│   │   │   ├── permission_engine.py
│   │   │   ├── executor.py
│   │   │   ├── verifier.py
│   │   │   ├── engine.py
│   │   │   └── audit.py
│   │   │
│   │   ├── model/
│   │   │   ├── providers/
│   │   │   ├── router.py
│   │   │   ├── provider.py
│   │   │   └── types.py
│   │   │
│   │   ├── skills/
│   │   │   ├── contracts.py
│   │   │   ├── registry.py
│   │   │   ├── adapters.py
│   │   │   ├── calendar_skill.py
│   │   │   ├── document_skill.py
│   │   │   └── task_skill.py
│   │   │
│   │   ├── models.py
│   │   ├── schemas.py
│   │   ├── crud.py
│   │   └── main.py
│   │
│   ├── alembic/
│   ├── tests/
│   ├── requirements.txt
│   └── pytest.ini
│
├── frontend/
│   ├── app/
│   ├── components/
│   ├── lib/
│   ├── public/
│   ├── package.json
│   └── tsconfig.json
│
├── .gitignore
├── README.md
└── documentation/
🔄 Agent Pipeline

The central agent workflow is structured as:

Pipeline Input
      │
      ▼
Goal Understanding
      │
      ▼
Context Retrieval
      │
      ▼
Capability Routing
      │
      ▼
Planning
      │
      ▼
Skill Routing
      │
      ▼
Persist Tasks
      │
      ▼
Controlled Execution
      │
      ▼
Verification
      │
      ▼
Result

Each stage has a defined responsibility rather than allowing one component to perform the entire workflow.

🛡️ Safety Principles

ActionOS is designed around several principles.

1. Explicit execution boundaries

The agent cannot directly execute arbitrary code.

2. Registered tools only

Only tools registered in the Tool Registry may be executed.

3. Permission before action

Operations requiring confirmation must receive explicit user approval.

4. Structured inputs and outputs

Tools use typed Pydantic schemas.

5. Verification

Execution results can be independently validated.

6. Auditability

Important execution state is persisted.

7. Provider abstraction

The application does not need to be tightly coupled to a single AI provider.

8. Secrets stay outside source control

Credentials and API keys belong in environment configuration.

🧪 Testing

The backend contains an automated test suite covering:

Goals
Tasks
Actions
Agent pipeline
Planning
Memory
Model layer
Permissions
Skill routing
Skills
Tool contracts
Execution

Run the complete backend test suite:

cd backend
python -m pytest -q

The current verified baseline is:

175 passed
🚀 Local Development
Prerequisites

Install:

Python 3.11+
Node.js
pnpm
Docker Desktop
PostgreSQL (or use the provided Docker setup)
1. Start PostgreSQL
docker start actionos-postgres

Verify:

docker ps
2. Configure the backend

Create:

backend/.env

Example:

APP_NAME=ActionOS
ENVIRONMENT=development
DEBUG=true

DATABASE_URL=postgresql+psycopg://actionos:actionos_dev@localhost:5432/actionos

SECRET_KEY=change-me
ACCESS_TOKEN_EXPIRE_MINUTES=1440

MODEL_ROUTING_STRATEGY=auto
MODEL_PRIVACY_FIRST=true

OPENAI_API_KEY=
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini
OPENAI_TIMEOUT_SECONDS=60

Never commit .env.

3. Start the backend
cd backend
python -m uvicorn app.main:app --reload --port 8000

Backend:

http://127.0.0.1:8000

Swagger API documentation:

http://127.0.0.1:8000/docs
4. Start the frontend

Open another terminal:

cd frontend
pnpm install
pnpm dev

Frontend:

http://localhost:3000
🔐 Authentication

The development environment supports a development authentication flow for local testing.

Production deployments should use secure authentication and properly managed credentials.

Never commit:

.env
API keys
database passwords
production secrets
📊 Example Workflow

A typical ActionOS workflow looks like this:

Step 1 — User creates a goal
Prepare me for my interview
Step 2 — Goal is structured
Intent:
interview.prepare

Category:
personal

Priority:
medium
Step 3 — Plan is generated
Prepare for interview
        │
        ├── Preparation task
        ├── Interview questions
        ├── Answer guidance
        └── Preparation checklist
Step 4 — Permission is evaluated
Confirmation required
Step 5 — User approves
[ Approve & Continue ]
Step 6 — Action executes
PENDING
   ↓
RUNNING
   ↓
COMPLETED
Step 7 — Result is verified
Execution
    ↓
Verification
    ↓
Persisted Result

This creates a complete trace from intent → plan → permission → execution → verification.

🧭 Project Status

ActionOS is under active development.

Current foundation
 FastAPI backend
 PostgreSQL persistence
 Goal management
 Task management
 Agent pipeline
 Goal understanding
 Context retrieval architecture
 Capability routing
 Planning
 Skill routing
 Typed tool contracts
 Tool registry
 Permission engine
 Controlled execution architecture
 Verification architecture
 Audit architecture
 Model/provider abstraction
 Frontend workspace
 Backend automated tests
 Frontend TypeScript validation
 Frontend production build
In active development
 Expanded model-backed agent capabilities
 Additional intelligent skills
 Richer execution results
 Expanded integrations
 Production authentication
 Production deployment
 Advanced observability
🗺️ Roadmap
Phase 1 — Foundation
Core data models
API foundation
Database persistence
Authentication
Basic goal/task management
Phase 2 — Agent Core
Goal understanding
Context retrieval
Planning
Capability routing
Skill routing
Phase 3 — Model Layer
Provider abstraction
Model routing
Local/cloud model support
Privacy-aware routing
Phase 4 — Skills
Calendar
Documents
Tasks
Intelligent domain-specific skills
Phase 5 — Controlled Execution
Permission engine
Tool registry
Executor
Verification
Audit logging
Phase 6 — Intelligent Actions
Model-backed skills
Rich execution results
More autonomous workflows
External integrations
Phase 7 — Production
Secure authentication
Production infrastructure
Observability
Deployment
Reliability improvements
🎯 Design Philosophy

ActionOS is not intended to be just another chatbot.

A chatbot primarily answers:

"What should I do?"

ActionOS is designed to answer a different question:

"What are you trying to accomplish, what needs to happen, and what can I safely do to help?"

That distinction drives the architecture.

The system separates:

Intent
   ↓
Planning
   ↓
Capability
   ↓
Permission
   ↓
Execution
   ↓
Verification

This separation makes agent behavior more controllable, testable, and auditable.

🤝 Contributing

Contributions are welcome.

Before submitting changes:

Create a feature branch.
Add or update tests.
Run the backend test suite.
Run frontend type checking.
Run the production frontend build.
Ensure no secrets are committed.

Backend:

cd backend
python -m pytest -q

Frontend:

cd frontend
pnpm exec tsc --noEmit
pnpm build
📄 License

Add the project's chosen license here before public release.

⚡ ActionOS

From intention to action.
With control, verification, and accountability.
