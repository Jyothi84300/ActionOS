# ActionOS — Master Specification

**Document Version:** 1.1
**Status:** Draft — Living Document
**Owner:** ActionOS Core Team
**Consumers:** Human developers, AI coding agents (Trae, Lovable), documentation agents, product/technical reviewers

---

## Table of Contents

1. [Product Overview](#1-product-overview)
2. [Problem Statement](#2-problem-statement)
3. [Product Vision](#3-product-vision)
4. [Target Users](#4-target-users)
5. [Product Principles](#5-product-principles)
6. [System Architecture](#6-system-architecture)
7. [Capability Router](#7-capability-router)
8. [Agent Workflow](#8-agent-workflow)
9. [Goal Engine](#9-goal-engine)
10. [Context Engine](#10-context-engine)
11. [Planner](#11-planner)
12. [Skill Architecture](#12-skill-architecture)
13. [Tool Architecture](#13-tool-architecture)
14. [Permission Architecture](#14-permission-architecture)
15. [Execution Engine](#15-execution-engine)
16. [Verification Engine](#16-verification-engine)
17. [Memory Architecture](#17-memory-architecture)
18. [Model Architecture](#18-model-architecture)
19. [Offline-First Architecture](#19-offline-first-architecture)
20. [Synchronization Architecture](#20-synchronization-architecture)
21. [Mobile Architecture](#21-mobile-architecture)
22. [Backend Architecture](#22-backend-architecture)
23. [Database Design](#23-database-design)
24. [API Specification](#24-api-specification)
25. [API Error Model](#25-api-error-model)
26. [Security Architecture](#26-security-architecture)
27. [Frontend/Backend Contract](#27-frontendbackend-contract)
28. [Tool Roles — Lovable, Trae, Claude](#28-tool-roles--lovable-trae-claude)
29. [Development Standards](#29-development-standards)
30. [Git / AI Development Workflow](#30-git--ai-development-workflow)
31. [Testing Strategy](#31-testing-strategy)
32. [Observability](#32-observability)
33. [MVP](#33-mvp)
34. [Roadmap](#34-roadmap)
35. [Non-Goals](#35-non-goals)
36. [Open Technical Decisions](#36-open-technical-decisions)
37. [Architecture Decision Records](#37-architecture-decision-records)
38. [Definition of Done](#38-definition-of-done)
39. [Change Log](#39-change-log)
40. [Final Product Statement](#40-final-product-statement)

---

## 1. Product Overview

**ActionOS** is an offline-first Personal AI Execution Layer for smartphones that transforms user goals into controlled, verified actions while keeping the user in control.

ActionOS is **NOT**:

- A chatbot.
- Another general-purpose LLM interface.
- A replacement for ChatGPT, Gemini, or Siri.
- An unrestricted autonomous agent that acts without oversight.

ActionOS's primary value is the **coordination layer** that sits between raw model capability and real-world outcomes:

```text
User Intent → Context → Planning → Action → Verification → Outcome
```

Where general-purpose assistants answer questions, ActionOS MUST turn a stated goal into a sequence of permissioned, auditable, verifiable actions, and MUST report only outcomes it has independently confirmed.

*(Unchanged from v1.0.)*

---

## 2. Problem Statement

Modern digital life is fragmented across disconnected surfaces:

- Email
- Messaging
- Calendars
- Documents
- Notes
- Websites
- Forms
- Specialized single-purpose applications

Across all of these, the human user remains solely responsible for:

- Remembering what needs to happen
- Finding the relevant information
- Deciding the next step
- Moving information between applications
- Performing the action itself
- Checking whether the action actually succeeded
- Remembering unfinished work

This is defined as the **Execution Gap**: the space between *knowing* what needs to be done and *actually getting it done*. Existing AI assistants largely address the "knowing" side (answering, drafting, summarizing) but leave the "doing" side — the coordination, permissioning, and verification of real actions — unsolved. ActionOS exists to close this gap.

*(Unchanged from v1.0.)*

---

## 3. Product Vision

Users SHOULD be able to tell ActionOS:

> "What I want to accomplish."

rather than:

> "Which application should I open?"

ActionOS coordinates the workflow required to move the user toward the desired outcome — retrieving relevant context, proposing a plan, requesting permission where required, executing through registered tools, and verifying the result — while the user remains the final authority at every consequential step.

*(Unchanged from v1.0.)*

---

## 4. Target Users

Initial target users:

- Students
- Professionals
- Early-career users
- People managing multiple digital responsibilities
- Privacy-conscious users
- Users who frequently work across multiple applications

ActionOS is **not** initially optimized for every demographic (e.g., enterprise fleets, accessibility-specialized workflows, non-smartphone users) — these are explicitly out of scope for the initial product and MAY be addressed in later phases.

*(Unchanged from v1.0.)*

---

## 5. Product Principles

| # | Principle | Explanation |
|---|-----------|--------------|
| 1 | **Goal-first** | The unit of interaction is a user goal, not a chat turn or an app selection. |
| 2 | **User-first** | The system exists to serve the user's stated intent, not to maximize engagement or autonomous activity. |
| 3 | **Outcome-first** | Success is measured by verified real-world outcomes, not by generated text or completed tool calls. |
| 4 | **Offline-first** | Core goal and task management MUST function without network connectivity; online capability is additive. |
| 5 | **Privacy-first** | User data is processed with the minimum necessary scope and MUST NOT be sent to any model or service without a clear, permissioned reason. |
| 6 | **Bounded autonomy** | The agent MAY plan broadly but MUST act only within explicitly registered tools and explicitly granted permissions. |
| 7 | **Verify before claiming success** | The agent MUST NOT report an action as complete until independent verification confirms the resulting state. |
| 8 | **Model-agnostic** | The Agent Core MUST NOT be hard-coupled to a single LLM provider or runtime. |
| 9 | **Explainable actions** | Every action MUST be traceable to the goal, plan step, permission, and tool call that produced it. |
| 10 | **Graceful failure** | Failures MUST be surfaced clearly, recoverable where possible, and MUST NOT silently corrupt state. |

*(Unchanged from v1.0.)*

---

## 6. System Architecture

### 6.1 Architectural Decision: Hybrid Local + Cloud Agent

**This is now a confirmed architecture decision (ADR-001), not a TBD.** ActionOS uses a **hybrid local + cloud architecture**, coordinated through a Capability Router (§7):

```text
                         ACTIONOS
                            │
                   CAPABILITY ROUTER
                     /            \
                    /              \
               OFFLINE             ONLINE
                  │                   │
                  ↓                   ↓
           LOCAL AGENT CORE      CLOUD API
                  │                   │
           ┌──────┴──────┐            ↓
           ↓             ↓       CLOUD AGENT
      LOCAL MODEL    LOCAL TOOLS       │
                                       ↓
                                  CLOUD MODEL
```

#### Local Agent Core (on-device, Android app)

Responsible for:

- Local goal state
- Local task state
- Local-capable planning
- Local model invocation
- Local skills
- Local tools
- Offline queueing
- Local verification

#### Cloud Agent Core (backend)

Responsible for:

- Cloud model access
- Heavier reasoning when required
- Online integrations
- Synchronization
- Account services
- Cloud-side processing where appropriate

### 6.2 Shared Agent Core Contract vs. Local/Cloud Implementations

To prevent duplicated business logic, the Agent Core is defined as a **shared contract** (interfaces, schemas, state machines) with two implementations:

| Responsibility | Shared Contract (defines behavior) | Local Implementation | Cloud Implementation |
|---|---|---|---|
| Goal Understanding | Parsing rules, Goal schema | Local-capable parsing (simple/structured goals) | Full parsing incl. complex/ambiguous goals |
| Context Engine | Context reference schema, permission gating rules | Local documents, calendar, tasks | Email, messaging, browser, cloud storage (future) |
| Planner | Plan schema, task/dependency structure | Local-capable planning for simple goals | Full planning for complex/multi-skill goals |
| Skill Router | Skill Registry format | Locally bundled skills | Full skill registry, including cloud-only skills |
| Permission Engine | Permission tiers, evaluation rules (§14) | Enforced identically on-device | Enforced identically server-side |
| Executor | Action state machine (§15.1) | Local tool invocation | Online/cloud tool invocation |
| Verifier | Verification result schema (§16) | Local-state verification | Remote-state verification |
| Memory Manager | Memory schema, retention rules | Local (Room/SQLite) working memory | Synced/account-level memory (PostgreSQL) |
| Model Router | Routing contract (§18) | Selects local model | Selects cloud model |

The **state machines, schemas, and permission rules are identical** in both implementations — only *where* they execute and *which* model/tools they reach differs. This is the mechanism that prevents duplicated business logic: both sides implement the same contract rather than independently reinventing rules.

---

## 7. Capability Router

A formal **Capability Router** sits before planning/execution and determines whether a requested workflow can be completed:

```text
LOCALLY
ONLINE
or
PARTIALLY OFFLINE
```

**The Capability Router MUST NOT simply check internet availability.** It MUST evaluate the actual capability requirements of the task — which skills/tools it needs, whether those are local-capable, and whether the local model can support the required reasoning.

### 7.1 Examples

```text
"Summarize this downloaded document"
        ↓
LOCAL-CAPABLE
        ↓
Local Agent + Local Model
```

```text
"What is today's weather?"
        ↓
ONLINE-REQUIRED
```

```text
"Send this email"
        ↓
ONLINE + EMAIL ACCESS REQUIRED
```

### 7.2 Routing Flow

```text
USER REQUEST
     ↓
CAPABILITY ROUTER
     ↓
┌───────────────┬────────────────┐
│ LOCAL         │ ONLINE         │
│ CAPABILITY    │ CAPABILITY     │
↓               ↓
LOCAL AGENT     CLOUD AGENT
↓               ↓
LOCAL MODEL     CLOUD MODEL
↓               ↓
LOCAL TOOLS     ONLINE TOOLS
└───────┬───────┘
        ↓
    VERIFICATION
        ↓
    GOAL STATE
```

A task MAY be **partially offline**: e.g., planning happens locally, but one task within the plan requires an online-only tool and is queued (see §19–20) while the rest of the plan proceeds locally.

---

## 8. Agent Workflow

```text
USER GOAL
 ↓
GOAL UNDERSTANDING
 ↓
CONTEXT RETRIEVAL
 ↓
PLANNING
 ↓
SKILL / TOOL SELECTION
 ↓
PERMISSION CHECK
 ↓
ACTION EXECUTION
 ↓
VERIFICATION
 ↓
MEMORY / STATE UPDATE
 ↓
OUTCOME  ── (on failure) ──▶ REPLAN
```

The Capability Router (§7) is evaluated as part of "Goal Understanding" and "Planning," determining whether each subsequent stage runs against the Local or Cloud Agent Core implementation.

| Stage | Input | Output | Responsibility | Allowed | Prohibited | Failure Conditions |
|---|---|---|---|---|---|---|
| Goal Understanding | Raw user text | Structured Goal object | Parse intent, objective, constraints | Clarifying questions | Executing actions | Ambiguous/unparseable input → request clarification |
| Context Retrieval | Goal | Context references | Fetch permissioned, relevant context | Read within granted scope | Reading unpermissioned sources | Missing permission → flag, proceed with partial context |
| Planning | Goal + Context | Structured Plan | Decompose into ordered tasks | Reference registered skills/tools | Generate executable code | Unsatisfiable goal → return TBD/blocked plan |
| Skill/Tool Selection | Plan task | Skill + Tool reference | Match task to capability | Select from registry | Invent skill/tool names | No matching skill → mark task unsupported |
| Permission Check | Proposed action | Allow / Confirm / Block | Evaluate against permission model (§14) | Consult stored grants | Bypass evaluation | Denied → action moves to BLOCKED |
| Action Execution | Permitted action | Raw tool result | Invoke tool handler | Call registered tool only | Reinterpret intent | Tool error → action FAILED |
| Verification | Tool result | Verified / Unverified | Independently confirm resulting state | Query resulting state | Trust return value alone | State absent/mismatched → UNVERIFIED |
| Memory/State Update | Verified outcome | Updated Goal/Task state | Persist durable state | Write to Memory Manager | Store unnecessary raw data | Write failure → retry, else flag inconsistency |
| Outcome / Replan | Final state | Report to user / new Plan | Communicate result or trigger replanning | Human-readable summary | Claim unverified success | Persistent failure → surface to user for decision |

*(Structure unchanged from v1.0; explicitly cross-referenced to the Capability Router.)*

---

## 9. Goal Engine

### 9.1 Goal Object

| Field | Type | Notes |
|---|---|---|
| `id` | UUID | Primary identifier |
| `user_id` | UUID | Owner |
| `title` | string | Short label |
| `description` | string | Free-text elaboration |
| `objective` | string | Structured statement of desired outcome |
| `deadline` | datetime, nullable | Optional target completion time |
| `priority` | enum (`low`, `medium`, `high`) | |
| `category` | string | e.g., `academic`, `work`, `personal` |
| `constraints` | JSON array | User- or system-imposed limits |
| `status` | enum | See state machine below |
| `created_at` | datetime | |
| `updated_at` | datetime | |

### 9.2 Goal States

```text
ACTIVE → PAUSED → ACTIVE
ACTIVE → COMPLETED
ACTIVE → CANCELLED
ACTIVE → FAILED → ACTIVE (via replan)
```

| From | To | Trigger |
|---|---|---|
| — | ACTIVE | Goal created |
| ACTIVE | PAUSED | User pauses |
| PAUSED | ACTIVE | User resumes |
| ACTIVE | COMPLETED | All tasks verified complete |
| ACTIVE | CANCELLED | User cancels |
| ACTIVE | FAILED | Unrecoverable plan/execution failure |
| FAILED | ACTIVE | Successful replan |

*(Unchanged from v1.0.)*

---

## 10. Context Engine

### 10.1 Sources

**Initial (MVP):** Local documents, Calendar, Tasks.
**Future:** Email, Messaging, Browser, Cloud storage, Notes, Contacts, other application integrations.

### 10.2 Requirements

- Context retrieval MUST be permission-controlled; no source is read without an explicit grant.
- Only context relevant to the active goal/plan SHOULD be supplied to the model — the system MUST NOT dump all available user data into a model call.
- All externally sourced content (documents, webpages, emails, messages) MUST be treated as **untrusted data**, never as trusted agent instructions.
- Any instruction-like text found inside retrieved content MUST be ignored by the Planner/Executor unless separately confirmed by the user.
- Retrieval MUST use structured/local lookup appropriate to the source type (e.g., direct document access, calendar API queries). **No vector/semantic retrieval is used in the MVP** (see §36 / ADR-006).

### 10.3 Context Reference Structure

```json
{
  "context_id": "uuid",
  "source_type": "document | calendar | task | email | web",
  "source_ref": "opaque pointer to source object",
  "retrieved_at": "ISO-8601 timestamp",
  "trust_level": "untrusted",
  "permission_id": "uuid",
  "excerpt": "short relevant excerpt, not full content where avoidable"
}
```

*(Retrieval-method note added; structure otherwise unchanged from v1.0.)*

---

## 11. Planner

The Planner converts `Goal + Context` into a `Structured Plan`.

A Plan MUST contain:

- `tasks[]` — ordered list of discrete work items
- `ordering` — explicit sequence or dependency graph
- `dependencies` — task-to-task prerequisites
- `expected_outputs` — what each task should produce
- `required_skills[]` — references to Skill Registry entries (by stable `skill_id`, see §12.2)
- `required_tools[]` — references to Tool Registry entries
- `permission_level` — the highest permission tier required across tasks
- `verification_method` — how each task's success will be confirmed
- `capability_route` — whether the plan (or each task) is `LOCAL`, `ONLINE`, or `PARTIAL` per the Capability Router (§7)

**Rules:**

- The Planner MUST output structured data (JSON), never natural-language-only instructions.
- The Planner MUST NOT generate arbitrary executable code.
- The Planner MUST reference only skills/tools present in their respective registries, by stable identifier; it MUST NOT invent capabilities.

---

## 12. Skill Architecture

### 12.1 Skill vs. Tool — Explicit Distinction

**Skill:** a high-level capability grouping.
**Tool:** a specific, registered operation exposed by that skill.

```text
Calendar Skill
      │
      ├── get_calendar_events
      ├── create_calendar_event
      └── delete_calendar_event
```

The LLM may select from **registered tools only**. It MUST NOT invent tool identifiers. A Skill is never invoked directly — the Planner selects tools that belong to a skill.

### 12.2 Skill Identifiers and Versioning (corrected from v1.0)

**Correction:** v1.0 used `Skill.name` as the relational identifier. This is corrected — `name` is a human-readable label, not a stable key.

```text
Skill
├── skill_id      (stable UUID — permanent relational identifier)
├── name           (human-readable label, may change)
├── version        (semantic version of the current manifest)
├── description
├── status         (enabled | deprecated | disabled)
└── manifest       (full schema per §12.3)
```

- Tasks and Actions reference a skill by its stable `skill_id`, never by `name` or `version`.
- Version information is tracked in a separate `SkillVersion` history so that:
  - A skill can be upgraded (new manifest, new version) without changing `skill_id`.
  - Historical Task/Action records remain valid and auditable against the manifest version that was active when they were created (each Task/Action additionally stores the `skill_version` it was planned against).
  - Deprecating or disabling a skill does not delete or invalidate historical records.

### 12.3 Initial Skills

**Document Skill** — read selected document, analyze document, extract information, summarize document.

**Task Skill** — create task, update task, complete task, list tasks.

**Calendar Skill** — read calendar, create reminder, check deadline.

### 12.4 Future Skills (non-exhaustive)

Email, Travel, Education, Work, Personal Administration, Developer, Finance tracking, and other domains — added only after the core engine is reliable (see [Non-Goals](#35-non-goals)).

### 12.5 Skill Definition Schema

| Field | Description |
|---|---|
| `skill_id` | Stable unique identifier (§12.2) |
| `name` | Human-readable label |
| `description` | Human-readable purpose |
| `supported_intents[]` | Intents this skill can fulfill |
| `required_context[]` | Context types the skill needs |
| `tools[]` | Registered tool identifiers this skill may invoke |
| `permissions[]` | Permission levels this skill's actions require |
| `input_schema` | JSON Schema for skill invocation input |
| `output_schema` | JSON Schema for skill output |
| `verification_method` | How this skill's outcomes are verified |
| `failure_modes[]` | Enumerated known failure conditions |
| `version` | Semantic version string (current manifest) |
| `capability` | `local` \| `online` \| `both` — informs the Capability Router (§7) |

### 12.6 Extensibility

New skills MUST be addable by registering a manifest conforming to the schema above, without modifying the Agent Core loop (Goal Understanding, Planner, Executor, Verifier). The Skill Router discovers skills dynamically from the Skill Registry at runtime, by `skill_id`.

---

## 13. Tool Architecture

Every tool MUST define:

- Unique identifier
- Input schema
- Output schema
- Permission requirement
- Execution handler
- Verification handler
- Failure states
- `capability` — `local` \| `online` (informs the Capability Router, §7)

**Critical rules:**

> The LLM cannot invent arbitrary tool names. The agent may only call registered tools.
> The LLM MUST NOT receive unrestricted operating-system access.
> The LLM MUST NOT directly execute arbitrary code.

All tool invocations MUST be validated against the tool's registered input schema before execution and against its output schema before being passed to the Verifier. A tool belongs to exactly one Skill (§12.1) but is referenced independently by `tool_id` in Plans and Actions.

---

## 14. Permission Architecture

### 14.1 ActionOS Policy vs. Platform Permissions

**Clarification (new in v1.1):** ActionOS enforces its own permission policy *in addition to*, not instead of, Android/platform permissions. These are two distinct, sequential gates:

```text
Action
 ↓
ActionOS Permission Policy    (this system's tiers — §14.2)
 ↓
Platform Permission           (Android runtime permission, e.g., calendar/contacts access)
 ↓
Tool
 ↓
External System / Android API
```

**Rules:**

- ActionOS CANNOT grant itself Android permissions — platform permission dialogs remain under OS and user control.
- The ActionOS Permission Policy Engine MUST NOT bypass, suppress, or auto-accept platform permission prompts.
- An action MUST pass **both** gates before reaching the tool. If either gate denies, the action is `BLOCKED`.

### 14.2 ActionOS Permission Levels

| Level | Description | Examples |
|---|---|---|
| **Automatic** | Executes without per-instance confirmation (still subject to platform permission where applicable). | Read selected document, analyze selected document, read calendar, list tasks, create local task |
| **Confirmation Required** | Requires explicit user confirmation before execution. | Create reminder, send email, send message, submit form, delete data |
| **Blocked / Restricted** | Never executed by the agent under any circumstance in the current version. | Financial transfers, account deletion, password/security changes, other high-impact irreversible operations |

### 14.3 Permission Lifecycle

- **Storage:** ActionOS permissions are stored per-user, per-tool (and optionally per-scope, e.g., per-calendar), in the Permission table (local + synced to cloud where applicable). Platform permissions are stored/managed by Android and queried at runtime, not duplicated in ActionOS's own store.
- **Evaluation:** The Permission Engine evaluates every proposed action before it reaches the Executor, checking both the ActionOS policy and current platform permission status; evaluation is non-bypassable and stage-gated (see [Agent Workflow](#8-agent-workflow)).
- **Display:** The Settings/Permissions screen MUST show current ActionOS grants in human-readable form, and MUST reflect current platform permission status (linking to system settings where a platform permission is missing).
- **Audit:** Every permission evaluation (grant, confirm, deny, platform-denied) MUST produce an AuditEvent.
- **Revocation:** Users MUST be able to revoke any non-Blocked ActionOS permission at any time; revocation takes effect immediately for subsequent actions. Platform permission revocation happens through OS settings and MUST be detected on next evaluation.

---

## 15. Execution Engine

```text
Task → Skill → Tool → Permission → Execution → Result
```

The Executor MUST only receive actions that have already passed Planning validation and both permission gates (§14.1). The Executor MUST NOT independently reinterpret user intent. Execution routes through either the Local Agent Core or the Cloud Agent Core per the Capability Router's determination (§7).

### 15.1 Action States

```text
PENDING → WAITING_CONFIRMATION → RUNNING → COMPLETED
                                          ↘ FAILED
PENDING → BLOCKED
RUNNING → CANCELLED
COMPLETED → UNVERIFIED  (if verification fails post-execution)
```

| State | Meaning |
|---|---|
| `PENDING` | Action queued, not yet evaluated |
| `WAITING_CONFIRMATION` | Awaiting user confirmation (Confirmation Required tier) |
| `RUNNING` | Tool handler in progress |
| `COMPLETED` | Tool returned success and verification passed |
| `FAILED` | Tool execution failed |
| `CANCELLED` | User or system cancelled before completion |
| `BLOCKED` | Permission Engine denied the action (ActionOS policy or platform permission) |
| `UNVERIFIED` | Tool reported success but the Verifier could not confirm resulting state |

*(Unchanged from v1.0 except the `BLOCKED` clarification.)*

---

## 16. Verification Engine

This is a core differentiator of ActionOS.

> **Tool success does not automatically mean action success.** The agent MUST NOT report "Done" solely because a tool call returned without error.

```text
ACTION
 ↓
PERMISSION
 ↓
EXECUTION
 ↓
RESULT
 ↓
INDEPENDENT VERIFICATION
 ↓
VERIFIED / UNVERIFIED
```

**Example — reminder creation:**

```text
create_reminder()
 ↓
event ID returned
 ↓
retrieve event (independent read)
 ↓
event exists with expected fields?
 ↓
VERIFIED
```

### 16.1 When Verification Cannot Be Performed

Where independent verification is technically possible, it MUST inspect the resulting state (not merely trust the tool's return value). Where it is **not** technically possible for a given tool (e.g., no independent read exists for that external system):

- The result MUST be `UNVERIFIED`, never silently promoted to `VERIFIED`.
- `UNVERIFIED` MUST remain visibly and structurally distinct from `VERIFIED` everywhere it is stored or displayed.
- The agent MUST NOT claim verified success when verification did not occur.

### 16.2 Verification Failure Handling

When verification fails or cannot be performed:

1. The action's state is set to `UNVERIFIED` (not `COMPLETED`).
2. The user is informed that the action's outcome could not be confirmed, with the specific discrepancy where known.
3. The system MAY attempt a bounded retry (per skill/tool `failure_modes` policy) before surfacing to the user.
4. The action is never silently marked successful.
5. An AuditEvent is recorded regardless of outcome.

---

## 17. Memory Architecture

Memory is designed around **useful persistent state**, not exhaustive data capture.

### 17.1 What Is Stored

- Active goals
- Completed tasks
- Pending tasks
- Decisions (e.g., user confirmations/denials)
- Deadlines
- Approvals (permission grants)
- Action history
- Relevant context references (pointers, not full raw content, where avoidable)

### 17.2 Policies

| Aspect | Policy |
|---|---|
| Retention | Goal/task/action history retained while the goal is ACTIVE/PAUSED and for a bounded period after COMPLETED/CANCELLED (TBD — see Open Decisions) |
| Deletion | User-initiated deletion MUST cascade to dependent records (tasks, actions, context references) tied to a goal |
| User Visibility | Users MUST be able to view all stored memory associated with their account, per goal |
| Privacy | Memory MUST NOT store raw sensitive content beyond what's needed to resume/audit a goal |
| Encryption | Local memory MUST be encrypted at rest using platform secure storage; cloud memory MUST be encrypted at rest and in transit |
| Local vs. Cloud | Local (Room/SQLite) memory is authoritative for offline operation; cloud (PostgreSQL) memory exists for sync/backup and account-level state |

**No vector database / semantic memory in the MVP** (see §36 / ADR-006). Memory retrieval uses direct structured lookup (by `goal_id`, `type`, date ranges, etc.), not embeddings-based search.

*(Unchanged from v1.0 apart from the explicit local/cloud technology names and the vector-DB clarification.)*

---

## 18. Model Architecture

ActionOS supports `LOCAL MODEL + CLOUD MODEL` through a **Model Router**, consistent with the confirmed hybrid architecture (§6, ADR-001).

### 18.1 Status: Still Open

The following remain explicitly unresolved:

- **Model Provider = TBD**
- **Local Model = TBD**
- **Local Inference Runtime = TBD**

No specific model, provider, or benchmark is claimed anywhere in this document. See [Open Technical Decisions](#36-open-technical-decisions).

### 18.2 Router Considerations

The Model Router selects `LOCAL MODEL` or `CLOUD MODEL` based on:

- Connectivity
- Privacy requirements
- Task complexity
- Device capability
- Latency
- Cost
- Context requirements

### 18.3 Rules

- The Agent Core MUST NOT depend directly on any single LLM provider or runtime; all model access goes through the Model Router's provider-neutral interface (ADR-005).
- The system MUST NOT permanently commit to a specific model or runtime without verified technical evidence (benchmarking on target devices).
- Unresolved model/runtime decisions MUST remain explicitly marked **TBD / Decision Required**.
- Benchmarks MUST NOT be invented or assumed; they must come from actual measurement.

---

## 19. Offline-First Architecture

Offline operation is a **first-class architectural mode**, not a fallback.

```text
USER REQUEST
     ↓
CAPABILITY ROUTER
     ↓
┌───────────────┬────────────────┐
│ LOCAL         │ ONLINE         │
│ CAPABILITY    │ CAPABILITY     │
↓               ↓
LOCAL AGENT     CLOUD AGENT
↓               ↓
LOCAL MODEL     CLOUD MODEL
↓               ↓
LOCAL TOOLS     ONLINE TOOLS
└───────┬───────┘
        ↓
    VERIFICATION
        ↓
    GOAL STATE
```

### 19.1 Requirements

- Goals MUST remain accessible offline.
- Tasks MUST remain accessible offline.
- Local memory MUST remain accessible offline.
- Local documents MUST remain accessible offline.
- Local-capable skills MUST remain usable offline.
- Local-capable AI MUST remain usable where the device supports it.
- Online-required actions MUST be clearly identified to the user (never silently attempted and failed).
- Online-required actions MUST be queued/deferred where appropriate (see §20).
- Pending/queued work MUST survive an application restart.
- State MUST synchronize when connectivity returns (see §20).
- Offline mode MUST NOT claim capabilities the device or local model cannot actually provide.

---

## 20. Synchronization Architecture

*(New dedicated section in v1.1 — previously folded into Offline-First Architecture.)*

### 20.1 Sync Flow

```text
LOCAL CHANGE
     ↓
SYNC QUEUE
     ↓
NETWORK AVAILABLE?
     ↓
SYNC
     ↓
SERVER
     ↓
ACKNOWLEDGEMENT
```

- Local changes (goal/task/action/permission updates) are written to local storage immediately and enqueued for sync.
- The sync process runs opportunistically when connectivity is available (e.g., via WorkManager on Android).
- Each synced record carries synchronization metadata (e.g., last-synced timestamp, local revision marker) to support future conflict handling.
- The server acknowledges receipt per record; unacknowledged records remain queued and are retried.

### 20.2 Conflict Resolution — Scope for MVP

**For MVP: do not implement complex multi-device conflict resolution unless required.** Single-device usage is the assumed default case for the MVP; where the same record could plausibly be touched from two sources before sync (e.g., an offline edit later contradicted server-side), the MVP behavior is intentionally minimal and MUST be documented in code as provisional.

**Advanced conflict resolution (multi-device, concurrent-edit merging, CRDT/operational-transform-based strategies) is marked:**

**TBD / Future Architecture**

No specific conflict-resolution algorithm is chosen or implied by this document. See [Open Technical Decisions](#36-open-technical-decisions).

### 20.3 AuditEvent Handling During Sync

AuditEvents are append-only on both local and cloud stores and MUST NOT be overwritten or merged during sync — only new events are added.

---

## 21. Mobile Architecture

### 21.1 Primary Platform

**Android-first**, confirmed (ADR-002).

### 21.2 Preferred Technologies

- Kotlin
- Jetpack Compose
- Room (local database, backed by SQLite) — confirmed (ADR-003)
- SQLite
- WorkManager where appropriate
- Android App Widget
- Secure platform storage

### 21.3 Role of Lovable vs. Native Android

Lovable MAY be used for rapid UI/prototype development. However, the **final Android product requires a native Android implementation layer** for capabilities Lovable cannot reliably provide, including:

- Android runtime permissions
- Room/SQLite integration
- Home-screen widgets
- Notifications
- Background execution (WorkManager)
- Local model inference integration
- Other native Android APIs

Lovable MUST NOT be forced to implement native-only capabilities it cannot reliably provide; those responsibilities belong to the native Android layer (see §28.1).

### 21.4 Core Screens

1. Home
2. Goal Creation
3. Goal Detail
4. Plan
5. Action / Permission
6. Activity / Progress
7. Settings / Permissions

### 21.5 Design Principle

The user SHOULD NOT need to understand agents, tools, models, orchestration, embeddings, or routing. All internal terminology MUST be translated to human-readable status language.

| Internal | User-Facing |
|---|---|
| Tool execution in progress | "Checking your calendar…" |
| Permission Engine evaluating | "Reviewing what this needs…" |
| Verification in progress | "Confirming it worked…" |
| Context retrieval | "Looking at your documents…" |
| Capability Router selected ONLINE-REQUIRED | "This needs an internet connection…" |

---

## 22. Backend Architecture

**Stack:** Python + FastAPI.

### 22.1 Modules

```text
API
Agent
Goals
Tasks
Skills
Tools
Permissions
Memory
Model adapters
Verification
Synchronization
Observability
```

Each module MUST be independently testable and MUST expose a narrow, well-typed interface to other modules — no module reaches directly into another's internal data structures. The Agent module implements the shared Agent Core contract (§6.2) for the Cloud side; the Android app implements the same contract for the Local side.

*(Unchanged from v1.0.)*

---

## 23. Database Design

### 23.1 Local Database — Room + SQLite (confirmed, ADR-003)

The Android local database (Room, backed by SQLite) stores, at minimum:

- Goals
- Tasks
- Actions
- Verification records
- Local memory
- Permissions (ActionOS-policy grants; platform permissions are queried live from Android, not duplicated here)
- Context references
- Offline queue
- Synchronization metadata

The local database MUST remain fully usable without network connectivity. It is the **source of truth for offline operation** — it is not merely a cache of cloud state.

### 23.2 Cloud Database — PostgreSQL (confirmed, ADR-004)

The cloud relational database is **PostgreSQL**. It stores synchronized and account-level state where appropriate: User accounts, aggregated AuditEvents, synced Goals/Tasks/Actions/Memory/Permissions, and cross-device state.

**The cloud database is NOT the mandatory source of truth for offline operation.** Local working state remains authoritative on-device; the cloud database is authoritative for account-level and cross-device concerns.

| | Local Working State (Room/SQLite) | Synchronized Cloud State (PostgreSQL) |
|---|---|---|
| Authoritative for | Offline operation, current device | Account identity, cross-device sync, backup |
| Available offline | Yes, always | No |
| Written first | Yes (local-first write) | After sync (§20.1) |

### 23.3 Entities

For each entity: purpose, fields, data types, primary/foreign keys, indexes, constraints, lifecycle, and privacy sensitivity.

#### User
| Field | Type | Notes |
|---|---|---|
| `id` (PK) | UUID | |
| `email` | string, unique, indexed | Sensitivity: PII |
| `created_at` | datetime | |
| `auth_provider` | string | TBD — see Open Decisions |

Lifecycle: created at signup; soft-deleted on account deletion request (hard deletion after retention window).

#### Goal
| Field | Type | Notes |
|---|---|---|
| `id` (PK) | UUID | |
| `user_id` (FK → User.id, indexed) | UUID | |
| `title`, `description`, `objective` | string/text | |
| `deadline` | datetime, nullable | |
| `priority` | enum | |
| `category` | string | |
| `constraints` | JSON | |
| `status` | enum, indexed | See §9.2 |
| `created_at`, `updated_at` | datetime | |
| `sync_metadata` | JSON | Local-revision marker, last-synced timestamp (§20.1) |

Sensitivity: may contain personal/behavioral data — user-visible and deletable.

#### Task
| Field | Type | Notes |
|---|---|---|
| `id` (PK) | UUID | |
| `goal_id` (FK → Goal.id, indexed) | UUID | |
| `title`, `description` | string/text | |
| `order_index` | integer | Ordering within plan |
| `depends_on` | JSON array of Task IDs | |
| `skill_id` (FK → Skill.skill_id) | UUID | Stable reference (§12.2) |
| `skill_version` | string | Manifest version active at plan time |
| `capability_route` | enum (`local`, `online`, `partial`) | From Capability Router (§7) |
| `status` | enum | Mirrors relevant Action states |
| `created_at`, `updated_at` | datetime | |

#### Action
| Field | Type | Notes |
|---|---|---|
| `id` (PK) | UUID | |
| `task_id` (FK → Task.id, indexed) | UUID | |
| `tool_id` (FK → Tool.id) | UUID | |
| `permission_id` (FK → Permission.id) | UUID | |
| `input_payload` | JSON | Sensitivity: variable by tool |
| `result_payload` | JSON, nullable | |
| `state` | enum, indexed | See §15.1 |
| `created_at`, `updated_at` | datetime | |

#### Verification
| Field | Type | Notes |
|---|---|---|
| `id` (PK) | UUID | |
| `action_id` (FK → Action.id, indexed) | UUID | |
| `method` | string | e.g., "independent_read"; `null`/`"unavailable"` if not technically possible (§16.1) |
| `result` | enum (`VERIFIED`, `UNVERIFIED`) | |
| `observed_state` | JSON, nullable | |
| `verified_at` | datetime | |

#### Memory
| Field | Type | Notes |
|---|---|---|
| `id` (PK) | UUID | |
| `user_id` (FK → User.id, indexed) | UUID | |
| `goal_id` (FK → Goal.id, nullable, indexed) | UUID | |
| `type` | enum (`decision`, `approval`, `deadline`, `history_entry`, …) | |
| `payload` | JSON | Sensitivity: privacy-relevant, user-deletable |
| `created_at` | datetime | |

#### Skill (corrected in v1.1, §12.2)
| Field | Type | Notes |
|---|---|---|
| `skill_id` (PK) | UUID | Stable, permanent identifier |
| `name` | string | Human-readable, may change |
| `current_version` | string | Points to active `SkillVersion` |
| `description` | string | |
| `status` | enum (`enabled`, `deprecated`, `disabled`) | |
| `capability` | enum (`local`, `online`, `both`) | |

#### SkillVersion (new in v1.1)
| Field | Type | Notes |
|---|---|---|
| `id` (PK) | UUID | |
| `skill_id` (FK → Skill.skill_id, indexed) | UUID | |
| `version` | string | Semantic version |
| `manifest` | JSON | Full schema per §12.5, as of this version |
| `created_at` | datetime | |

#### Tool
| Field | Type | Notes |
|---|---|---|
| `id` (PK) | UUID | |
| `skill_id` (FK → Skill.skill_id, indexed) | UUID | Owning skill |
| `name` | string, unique | |
| `input_schema`, `output_schema` | JSON Schema | |
| `permission_level` | enum | See §14.2 |
| `capability` | enum (`local`, `online`) | |
| `enabled` | boolean | |

#### Permission
| Field | Type | Notes |
|---|---|---|
| `id` (PK) | UUID | |
| `user_id` (FK → User.id, indexed) | UUID | |
| `tool_id` (FK → Tool.id, indexed) | UUID | |
| `scope` | string, nullable | e.g., a specific calendar |
| `granted` | boolean | ActionOS-policy grant only — not a platform permission record |
| `granted_at`, `revoked_at` | datetime, nullable | |

#### ContextReference
| Field | Type | Notes |
|---|---|---|
| `id` (PK) | UUID | |
| `goal_id` (FK → Goal.id, indexed) | UUID | |
| `source_type` | enum | See §10.3 |
| `source_ref` | string (opaque pointer) | |
| `trust_level` | enum, default `untrusted` | |
| `retrieved_at` | datetime | |

#### AuditEvent
| Field | Type | Notes |
|---|---|---|
| `id` (PK) | UUID | |
| `user_id` (FK → User.id, indexed) | UUID | |
| `event_type` | string | e.g., `permission_granted`, `action_blocked`, `platform_permission_denied` |
| `related_id` | UUID, nullable | Polymorphic reference (Action/Permission/Goal) |
| `metadata` | JSON | MUST NOT contain secrets or full sensitive content |
| `created_at` | datetime, indexed | Append-only (§20.3) |

#### OfflineQueue
| Field | Type | Notes |
|---|---|---|
| `id` (PK) | UUID | |
| `action_id` (FK → Action.id, indexed) | UUID | |
| `queued_at` | datetime | |
| `attempts` | integer | |
| `last_error` | string, nullable | |

### 23.4 Local vs. Cloud Boundary Summary

See §23.1–§23.2. Skill/Tool/SkillVersion registries are authored centrally (cloud) and distributed to the local database as a bundled/synced read-mostly dataset; the Android app does not independently define skills.

---

## 24. API Specification

Base path: `/api/v1` *(unchanged from v1.0)*.

All endpoints require authentication (bearer token) unless noted. Authorization is scoped to the authenticated `user_id`; cross-user access MUST return `403`.

**No dozens of speculative endpoints are added in this revision.** Any endpoint not listed below is future work and MUST be explicitly marked as such when proposed.

### `GET /api/v1/health`
- **Purpose:** Liveness/readiness check.
- **Auth:** None required.
- **Response 200:**
```json
{ "status": "ok" }
```

### `POST /api/v1/goals`
- **Purpose:** Create a new goal.
- **Request:**
```json
{
  "title": "Finish research paper draft",
  "description": "Complete first draft of the ML paper",
  "objective": "Have a submittable draft by Friday",
  "deadline": "2026-09-04T23:59:00Z",
  "priority": "high",
  "category": "academic",
  "constraints": []
}
```
- **Response 201:**
```json
{
  "id": "uuid",
  "status": "ACTIVE",
  "created_at": "2026-08-28T10:00:00Z"
}
```
- **Status codes:** `201` created, `400` validation error, `401` unauthenticated.
- **Idempotency:** Not idempotent; each call creates a new goal.
- **Offline behavior:** MUST be created locally and queued for sync if offline (§20.1).

### `GET /api/v1/goals/{goal_id}`
- **Purpose:** Retrieve a goal.
- **Response 200:** Full Goal object. `404` if not found or not owned by caller.

### `POST /api/v1/goals/{goal_id}/plan`
- **Purpose:** Trigger planning for a goal. Internally invokes the Capability Router (§7) to determine local vs. cloud planning.
- **Response 200:**
```json
{
  "plan_id": "uuid",
  "tasks": [
    {
      "id": "uuid",
      "title": "...",
      "order_index": 0,
      "skill_id": "uuid",
      "capability_route": "local"
    }
  ],
  "permission_level": "confirmation_required"
}
```
- **Errors:** `409 PLAN_ALREADY_EXISTS` if an active plan exists (unless `force=true` query param is passed).
- **Offline behavior:** Uses local model/local Agent Core if `LOCAL-CAPABLE`; otherwise queued (`202 Accepted` with queued status).

### `GET /api/v1/goals/{goal_id}/tasks`
- **Purpose:** List tasks for a goal.
- **Response 200:** Array of Task objects.

### `POST /api/v1/tasks/{task_id}/execute`
- **Purpose:** Request execution of a task's associated action(s).
- **Response 202:**
```json
{ "action_id": "uuid", "state": "PENDING" }
```
- **Errors:** `403 PERMISSION_DENIED` if Blocked tier or platform permission missing (§14.1); `409` if task already RUNNING/COMPLETED.

### `GET /api/v1/actions/{action_id}`
- **Purpose:** Retrieve current action state and verification result.
- **Response 200:**
```json
{
  "id": "uuid",
  "state": "COMPLETED",
  "verification": { "result": "VERIFIED", "verified_at": "2026-08-28T10:05:00Z" }
}
```

### `POST /api/v1/actions/{action_id}/confirm`
- **Purpose:** User confirms a `WAITING_CONFIRMATION` action.
- **Request:**
```json
{ "confirmed": true }
```
- **Response 200:** Updated Action object with new state (`RUNNING` or `CANCELLED`).
- **Idempotency:** Re-confirming an already-processed action returns `409 ALREADY_PROCESSED`.

### `GET /api/v1/skills`
- **Purpose:** List registered skills (by stable `skill_id`) and their current manifests.
- **Response 200:** Array of Skill summaries, including `skill_id`, `name`, `current_version`, `capability`.

### `GET /api/v1/permissions`
- **Purpose:** List the caller's current ActionOS permission grants.
- **Response 200:** Array of Permission objects.

### `PUT /api/v1/permissions/{permission_id}`
- **Purpose:** Grant or revoke an ActionOS permission.
- **Request:**
```json
{ "granted": false }
```
- **Response 200:** Updated Permission object.

### `GET /api/v1/memory/{goal_id}`
- **Purpose:** Retrieve memory entries associated with a goal.
- **Response 200:** Array of Memory objects.

---

## 25. API Error Model

All errors use a single consistent envelope:

```json
{
  "error": {
    "code": "GOAL_NOT_FOUND",
    "message": "The requested goal does not exist.",
    "details": {},
    "request_id": "uuid"
  }
}
```

### 25.1 Standard Error Categories

| Category | Example Codes | HTTP Status |
|---|---|---|
| Validation | `VALIDATION_ERROR`, `MISSING_FIELD` | 400 |
| Authentication | `UNAUTHENTICATED` | 401 |
| Authorization | `PERMISSION_DENIED`, `FORBIDDEN_RESOURCE`, `PLATFORM_PERMISSION_MISSING` | 403 |
| Not Found | `GOAL_NOT_FOUND`, `TASK_NOT_FOUND`, `ACTION_NOT_FOUND` | 404 |
| Conflict | `PLAN_ALREADY_EXISTS`, `ALREADY_PROCESSED` | 409 |
| Unprocessable | `UNSUPPORTED_GOAL`, `SKILL_UNAVAILABLE` | 422 |
| Server | `INTERNAL_ERROR` | 500 |

*(Added `PLATFORM_PERMISSION_MISSING` to reflect §14.1; otherwise unchanged from v1.0.)*

---

## 26. Security Architecture

### 26.1 Trust Boundary (formalized in v1.1)

```text
MODEL
  ↓
PROPOSES STRUCTURED ACTION
  ↓
POLICY ENGINE
  ↓
VALIDATION
  ↓
REGISTERED TOOL
  ↓
EXECUTION
  ↓
VERIFICATION
```

**Never:**

```text
MODEL → unrestricted device access
```

```text
MODEL → arbitrary code execution
```

```text
MODEL → arbitrary tool invocation
```

The model's output is always a *proposal* (a structured action referencing a registered tool by ID) — never a directly executed instruction. The Policy Engine (ActionOS Permission Policy + Platform Permission, §14.1) and schema Validation both sit between proposal and execution.

### 26.2 Threat Model

| Threat | Mitigation Summary |
|---|---|
| Prompt injection (via documents/webpages/emails/skills) | Untrusted content is never treated as instructions; Planner/Executor ignore embedded directives (§10.2) |
| Malicious documents | Document Skill sandboxes parsing; no code execution from document content |
| Malicious webpages | Web-derived content is treated as untrusted data only |
| Malicious skills | Skills must be registered via the Skill/SkillVersion model (§12.2, §23.3) and reviewed; no dynamic loading of unverified skill code in production |
| Excessive permissions | Least-privilege defaults; Blocked tier is non-overridable by the agent; dual-gate policy (§14.1) |
| Unauthorized data access | Context retrieval gated by Permission Engine per source |
| Data leakage | Only relevant context sent to models; no bulk data dumps (§10.2) |
| Credential exposure | Secrets never logged; secure platform storage; no secrets in version control |
| Unsafe autonomous actions | Confirmation Required and Blocked tiers enforced pre-execution |
| Memory leakage | Memory stores minimal necessary payloads; user-visible and deletable |
| Sync conflicts | MVP scope intentionally minimal (§20.2); advanced resolution marked TBD |
| Compromised dependencies | Dependency pinning, review, and vulnerability scanning in CI |

### 26.3 Prompt Injection Defenses (expanded)

For each untrusted content source — documents, webpages, emails, external content, and skill-provided data — the system MUST:

1. Treat all such content as **data**, never as instructions, regardless of formatting (e.g., text that looks like "SYSTEM:" or "IGNORE PREVIOUS INSTRUCTIONS" carries no special authority).
2. Keep retrieved content isolated from the Planner's own instruction context where feasible (e.g., clearly delimited/labeled as untrusted in the model prompt).
3. Require user confirmation for any action a plan proposes that was influenced by untrusted content and falls in the Confirmation Required tier — the untrusted-content origin does not downgrade or upgrade the permission tier.

### 26.4 Core Controls

- **Trust boundaries:** User device ↔ API ↔ Agent Core ↔ Tool Layer ↔ external services are distinct trust zones; data crossing a boundary is validated.
- **Least privilege:** Every tool/skill requests the minimum permission tier needed.
- **Data isolation:** Per-user data isolation enforced at the database and API layer.
- **Permission gates:** Non-bypassable, enforced in the Agent Core before Executor invocation (both ActionOS policy and platform permission, §14.1).
- **Audit logging:** Every permission decision and action state transition produces an AuditEvent.
- **Secrets management:** Environment-based secret injection; no secrets committed to source control.
- **Secure storage:** Platform Keystore/EncryptedSharedPreferences on-device; encryption at rest and in transit for cloud data.
- **Input validation:** All API and tool inputs validated against JSON Schema before processing.
- **Output validation:** Tool outputs validated against schema before being passed to the Verifier or returned to the user.

**Core rule:** AI can reason broadly but act narrowly.

---

## 27. Frontend/Backend Contract

> **The API contract is the boundary between frontend and backend.**

- Lovable MUST consume the documented API (§24) exactly as specified.
- Trae MUST implement the documented API (§24) exactly as specified.
- Neither tool may silently rename fields, endpoints, status values, request structures, or response structures.
- Any intentional contract change requires updating this Master Specification first.

### Lovable / Frontend
**Responsible for:** UI, interaction, rendering state, API calls, user confirmations, offline UX.
**NOT responsible for:** Agent reasoning, permission policy, tool execution, database business logic, model routing, security decisions.

### Trae / Backend
**Responsible for:** Agent engine, API, database, skills, tools, permissions, verification, model routing.

---

## 28. Tool Roles — Lovable, Trae, Claude

### 28.1 Lovable

Primarily responsible for:

- UI
- UX
- Interaction flows
- Visual components
- API integration
- User-facing states
- Confirmation interfaces
- Responsive/prototype experience

Lovable MUST NOT own:

- Agent reasoning
- Permission policy
- Tool execution
- Database business logic
- Model routing
- Security decisions

The final native Android layer (§21.3) MAY require implementation outside Lovable for capabilities it cannot reliably provide.

### 28.2 Trae

Primarily responsible for:

- FastAPI backend
- Agent Core (Cloud implementation, §6.2)
- Planner
- Goal engine
- Skill registry
- Tool registry
- Permission engine
- Executor
- Verifier
- Model Router
- PostgreSQL
- Synchronization APIs
- Backend tests

Trae MUST NOT silently modify the product architecture.

### 28.3 Claude

Defined as: **Documentation and specification assistant.**

Claude SHOULD:

- Maintain technical documentation
- Explain implementation decisions
- Maintain API documentation
- Maintain developer documentation
- Maintain security documentation
- Maintain user documentation

Claude MUST NOT independently redefine architecture.

---

## 29. Development Standards

### 29.1 Backend (Python)
- Full type hints on all public functions.
- Pydantic models for all request/response schemas.
- FastAPI dependency injection for auth, DB sessions.
- Explicit async/sync boundaries; no blocking calls inside async handlers.
- Structured exception handling mapped to the standard error model (§25).
- Structured logging (no print statements).
- Unit + integration tests required for all new modules.
- Dependencies pinned and reviewed.

### 29.2 Frontend (Kotlin / Compose)
- Unidirectional state management (e.g., ViewModel + StateFlow).
- Clear separation of UI, state, and data layers.
- Accessibility: content descriptions, sufficient contrast, scalable text.
- Explicit offline state representation in the UI (never silently fail).
- Centralized API client with typed request/response models matching §24.

### 29.3 General
- Meaningful, unambiguous names.
- Small, single-responsibility modules.
- No hidden side effects.
- No duplicated business logic between frontend and backend (see the shared-contract model in §6.2).
- Configuration via environment variables, not hard-coded values.
- Secrets never committed to version control.

### 29.4 AI-Assisted Development Governance (expanded in v1.1)

**AI tools must follow this specification.**

AI tools MUST NOT:

- Invent APIs
- Invent capabilities
- Remove security controls
- Bypass permissions
- Introduce arbitrary code execution
- Change architecture silently
- Rewrite unrelated modules

AI-generated code MUST:

- Be reviewed by a human before merge
- Pass tests
- Follow project conventions
- Have appropriate error handling
- Avoid secrets
- Preserve security boundaries (§26)

---

## 30. Git / AI Development Workflow

Because ActionOS is developed using multiple AI tools (Lovable → frontend, Trae → backend/agent, Claude → documentation), the following rules apply:

1. This Master Specification is the single source of truth (ADR-010).
2. AI tools MUST NOT silently change API contracts.
3. AI tools MUST NOT invent capabilities not defined in this document.
4. All AI-generated code MUST be reviewed by a human before merge.
5. Every meaningful change MUST include tests.
6. Security-sensitive changes require explicit human review.
7. Commits MUST be focused and scoped to a single logical change.
8. No AI tool may rewrite unrelated parts of the project in the same change.
9. This specification MUST be updated when an intentional architecture decision changes.
10. Documentation MUST describe actual implementation, not intended implementation — divergence MUST be reconciled, not left silently inconsistent.

*(Unchanged from v1.0.)*

---

## 31. Testing Strategy

| Layer | Focus |
|---|---|
| **Unit** | Goal parser, planner, permission engine (both gates, §14.1), skill router, state transitions, verification logic |
| **Integration** | Full path: API → agent → skill → tool → verification, across both Local and Cloud Agent Core implementations |
| **Capability Routing** | Correct LOCAL / ONLINE / PARTIAL classification for representative tasks (§7) |
| **Offline** | No-internet operation, local state integrity, local model behavior, offline queue, recovery after reconnect |
| **Synchronization** | Sync queue processing, acknowledgement handling, retry behavior, AuditEvent append-only integrity (§20) |
| **Security** | Prompt injection resistance, unauthorized tool call attempts, permission bypass attempts (both ActionOS and platform gates), data leakage, malicious skill manifests |
| **UI** | Goal creation flow, progress display, confirmation flow, error states, offline indicators |
| **End-to-End** | Realistic multi-step workflows spanning goal creation through verified outcome, including at least one hybrid (partial-offline) scenario |

---

## 32. Observability

Required instrumentation:

- Structured logs (JSON) for all agent-stage transitions.
- `request_id` on every API call.
- `action_id` and `goal_id` propagated through all related log lines.
- AuditEvents for permission and state-transition events (see §23.3), including platform-permission outcomes.
- Error tracking with stack traces and correlation IDs.
- Performance metrics: latency per agent stage, tool call duration, verification duration, sync queue latency.

**Rule:** Logs MUST NOT contain secrets or unnecessary sensitive user content (e.g., full document bodies, message contents) — log references/IDs, not raw payloads, wherever possible.

*(Unchanged from v1.0 apart from the sync-latency metric addition.)*

---

## 33. MVP

```text
Goal Input
 ↓
Goal Understanding
 ↓
Plan
 ↓
Tasks
 ↓
Document Skill
Task Skill
Calendar Skill
 ↓
Permission
 ↓
Execution
 ↓
Verification
 ↓
Persistent State
 ↓
Offline-capable workflow
```

The MVP is intentionally scoped to these three skills and this single workflow loop. It MUST NOT be expanded to include:

- Dozens of skills
- Unrestricted device automation
- Complex autonomous behavior
- Advanced vector memory
- Complicated multi-device synchronization

until this core workflow is proven reliable end-to-end.

---

## 34. Roadmap

| Phase | Goal | Features | Dependencies | Risks | Exit Criteria |
|---|---|---|---|---|---|
| **1 — Foundation** | Stand up core loop | Goal Engine, Planner (basic), Capability Router, Permission Engine (dual-gate), Executor, Verifier scaffolding | None | Architecture churn | Agent loop runs end-to-end on a stub skill, locally and via cloud |
| **2 — Core Skills** | Deliver MVP skills | Document, Task, Calendar skills with stable `skill_id`s | Phase 1 | Skill scope creep | All three skills pass integration tests |
| **3 — Mobile Integration** | Ship usable Android app | Core screens (§21.4), Room/SQLite, native permission handling, API integration | Phase 2 | UX complexity for permission flows | User can complete a real goal via mobile app |
| **4 — Offline Intelligence** | Reliable offline operation | Local model integration, offline queue, basic sync (single-device) | Phase 3 | On-device model performance limits | Full MVP loop works with no connectivity |
| **5 — Expanded Skills** | Broaden capability | Email, additional domain skills | Phase 2–4 stable | Permission model strain | New skills added without core-loop changes |
| **6 — Proactive Agent** | Reduce user initiation burden | Suggested goals, proactive reminders | Phase 5 | Over-eager automation risk | Suggestions have measurable acceptance rate, no unwanted actions |
| **7 — Skill Ecosystem** | Enable third-party/community skills | Skill packaging & distribution mechanism | Phase 6 | Security review burden, malicious skills | Signed/verified skill installation pipeline live |
| **8 — Advanced Sync (future)** | Multi-device reliability | Conflict resolution strategy per §20.2 | Phase 4+ | Data-loss risk if done poorly | Documented, tested conflict-resolution strategy in production |

---

## 35. Non-Goals

ActionOS is explicitly **not** intended to:

- Replace all AI assistants.
- Provide unrestricted device access.
- Autonomously perform financial transactions.
- Autonomously change security credentials.
- Delete accounts without explicit, out-of-band confirmation.
- Upload all personal information to cloud models by default.
- Build hundreds of skills before the core engine is proven reliable.
- Prioritize flashy demonstrations over reliability and verified correctness.
- Introduce vector/semantic memory before a demonstrated product need (§10.2, §17.2, ADR-006).
- Implement complex multi-device conflict resolution before it is required (§20.2).

---

## 36. Open Technical Decisions

| Decision | Options | Trade-offs | Current Recommendation | Status |
|---|---|---|---|---|
| Exact local model | Small open-weight model (e.g., 1–4B class) vs. larger quantized model | Smaller = faster/lower battery but weaker reasoning; larger = better quality but device constraints | TBD — requires on-device benchmarking | Open |
| Local inference runtime | GGUF/llama.cpp-style runtime vs. MediaPipe/LiteRT vs. ONNX Runtime Mobile | Differ in model format support, performance, maintenance burden | TBD | Open |
| Android minimum version | API 26 (Android 8) vs. API 29+ | Older = wider reach, fewer modern APIs; newer = better security/storage APIs | TBD | Open |
| Cloud model provider | Single provider vs. provider-neutral abstraction with swappable backend | Speed of integration vs. long-term flexibility | Provider-neutral abstraction (ADR-005); specific provider TBD | Open |
| Authentication provider | Self-hosted (e.g., email/password + JWT) vs. managed (e.g., OAuth provider) | Control/cost vs. speed of implementation and security offload | TBD | Open |
| Cloud deployment platform | Single cloud provider (managed) vs. self-hosted containers | Operational simplicity vs. cost/control | TBD | Open |
| Advanced synchronization / conflict resolution | Last-write-wins vs. operational transform vs. CRDT-based | Simplicity vs. correctness under concurrent multi-device edits | Not implemented in MVP (§20.2); algorithm TBD for later phase | Open — Future Architecture |
| Skill packaging/distribution | Bundled-only (Phases 1–6) vs. signed external package format (Phase 7) | Bundled = simpler/safer initially; external = ecosystem growth but security surface | Bundled-only until Phase 7 | Open |
| Encryption implementation details | Platform-native (Android Keystore) + TLS vs. additional application-layer encryption | Added complexity vs. defense-in-depth | Platform-native as baseline; evaluate application-layer for high-sensitivity fields | Open |

Do NOT treat any of the above as decided until explicitly resolved and this table is updated.

---

## 37. Architecture Decision Records

### ADR-001 — Hybrid Agent Architecture
**Decision:** ActionOS uses a local + cloud hybrid architecture, coordinated by a Capability Router. **Status:** Confirmed.

### ADR-002 — Android-first
**Decision:** Android is the primary native platform. **Status:** Confirmed.

### ADR-003 — Local Storage
**Decision:** Room + SQLite for the on-device local database. **Status:** Confirmed.

### ADR-004 — Cloud Storage
**Decision:** PostgreSQL for the cloud relational database. **Status:** Confirmed.

### ADR-005 — Provider-Neutral AI
**Decision:** Exact models and providers remain replaceable behind the Model Router; no model/provider is committed in this document. **Status:** Confirmed (mechanism); specific model/provider remains TBD (§36).

### ADR-006 — No Vector DB in MVP
**Decision:** No vector database or embeddings-based semantic retrieval in the initial MVP; introduce only if a demonstrated product requirement emerges. **Status:** Confirmed.

### ADR-007 — Skill/Tool Separation
**Decision:** Skills are high-level capabilities; Tools are concrete, individually registered operations belonging to a Skill. The LLM selects only from registered Tools. **Status:** Confirmed.

### ADR-008 — Verification
**Decision:** Important actions require independent verification where technically possible; where not possible, the result is `UNVERIFIED`, never silently treated as `VERIFIED`. **Status:** Confirmed.

### ADR-009 — Permission Boundary
**Decision:** ActionOS's own permission policy and Android/platform permissions are both required and enforced sequentially; ActionOS cannot grant itself platform permissions. **Status:** Confirmed.

### ADR-010 — AI Development Governance
**Decision:** This Master Specification is the source of truth for Lovable, Trae, and Claude; none of the three may silently redefine architecture or contracts. **Status:** Confirmed.

---

## 38. Definition of Done

A production-ready workflow is complete only when **all** of the following hold:

- [ ] User can state a goal in natural language.
- [ ] System understands and structures it correctly.
- [ ] The Capability Router correctly classifies the workflow as local, online, or partial.
- [ ] Relevant, permissioned context is retrieved.
- [ ] A structured plan is generated.
- [ ] Tasks are created from the plan, referencing stable `skill_id`s.
- [ ] Appropriate skills are selected.
- [ ] Tools are permission-checked (both ActionOS policy and platform permission) before execution.
- [ ] Actions execute through the Tool Layer only, via the correct Local or Cloud Agent Core.
- [ ] Consequential actions are independently verified, or explicitly marked `UNVERIFIED` if verification is not possible.
- [ ] State is durably persisted locally, and synced when connectivity allows.
- [ ] An interrupted workflow can resume correctly.
- [ ] Failures are recoverable, not silently corrupting.
- [ ] Offline behavior works exactly as promised — no overclaiming.
- [ ] Security boundaries (§26) have been tested, not just designed.
- [ ] The UI communicates status in plain, human-readable language.
- [ ] This documentation matches the actual implementation.

---

## 39. Change Log

| Version | Date | Change |
|---|---|---|
| 1.0 | Initial | Initial Master Specification |
| 1.1 | Architecture review | Confirmed hybrid local + cloud agent architecture (ADR-001); added formal Capability Router; expanded Offline-First Architecture and split out a dedicated Synchronization Architecture section; confirmed Room/SQLite (local) and PostgreSQL (cloud) storage; corrected Skill identifier model to a stable `skill_id` with separate versioning (`SkillVersion`); made Skill vs. Tool distinction explicit; clarified the dual permission boundary (ActionOS policy + Android platform permissions); strengthened the Verification principle ("tool success does not automatically mean action success") and the `VERIFIED`/`UNVERIFIED` distinction; explicitly excluded vector/semantic memory from the MVP; clarified native-Android vs. Lovable responsibilities; defined Trae and Claude roles explicitly; reaffirmed unchanged `/api/v1` endpoints; formalized the model-proposes/policy-validates/tool-executes security trust boundary; expanded AI-assisted development governance rules; added a dedicated Architecture Decision Records section (ADR-001 through ADR-010); kept all model/runtime/auth/deployment/conflict-resolution/skill-packaging/encryption decisions explicitly marked TBD. |

---

## 40. Final Product Statement

> ActionOS is a trusted, permissioned, offline-first personal AI execution layer that transforms user intent into verified progress while keeping the user in control.
