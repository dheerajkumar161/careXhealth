# CareXHealth architecture migration map

Architecture migration, **not** a business-logic rewrite. Every rule, threshold, prompt, regex and workflow
below is ported 1:1 from the TypeScript implementation; only the layer it lives in changes.

## Layers

| Concern | Before | After |
|---|---|---|
| Frontend | Next.js 15 App Router (`src/app`, `src/components`) | React 19 + TypeScript + Vite + React Router (`frontend/`) |
| HTTP API | Next.js route handlers (`src/app/api/**/route.ts`) | FastAPI routers (`backend/app/api/`) |
| Agents | TS modules (`src/lib/agents/*.ts`) | Microsoft Agent Framework agents (`backend/app/agents/`) |
| Hospital services | TS modules (`src/lib/services/*.ts`) | One stdio MCP server per service (`backend/mcp_servers/`) |
| LLM | Groq HTTP (`src/lib/llm.ts`) | Provider chain in `backend/app/core/llm.py`, all via MAF: Groq (primary → fallback model, OpenAI-compatible client) → local Ollama (`OllamaChatClient`) → rule engine |
| ORM | Prisma | SQLAlchemy 2 (`backend/app/models/`) — SQLite kept |
| Auth | jose JWT cookie + middleware | PyJWT (user_id, role, department, exp) in httpOnly cookie or Bearer; FastAPI dependencies |
| Background loop | `instrumentation.ts` + `setInterval` | APScheduler with SQLAlchemyJobStore in the same SQLite DB |
| Documents | Markdown only | Markdown (agents) → Jinja2 HTML templates → PDF (xhtml2pdf) |

## Module mapping

| Legacy | New | Change |
|---|---|---|
| `lib/agents/planningRules.ts` | `app/agents/planning_rules.py` | Line-for-line port (regexes, suggestions) |
| `lib/agents/planning.ts` | `app/agents/planning_agent.py` | MAF agent; LLM via `core/llm.py`; invented-order filter unchanged |
| `lib/agents/execution.ts` | `app/agents/execution_agent.py` | Bookings/notifications now via Scheduling, Provider, Test Center, Notification MCP |
| `lib/agents/monitoring.ts` | `app/agents/monitoring_agent.py` | Still 100% deterministic; MAF agent only orchestrates |
| `lib/agents/communication.ts` | `app/agents/communication_agent.py` | MAF agent; documents stored via EHR MCP |
| `lib/agents/intelligence.ts` + `handover.ts` | `app/agents/intelligence_agent.py` | Deterministic fact sheet first, LLM narrative layer only |
| `lib/agents/cycle.ts` | `app/scheduler/jobs.py` | Decomposed into 5 persistent APScheduler jobs |
| `lib/agents/events.ts` | EHR MCP `create_audit_event` | AgentEvent audit trail preserved |
| `lib/services/scheduling.ts` | `mcp_servers/scheduling/` | Same slot algorithm |
| `lib/services/providerDirectory.ts` | `mcp_servers/provider_directory/` | Same synonym scoring |
| `lib/services/testCenter.ts` | `mcp_servers/test_center/` | Same catalogue + reference ranges |
| `lib/services/notification.ts` | `mcp_servers/notification/` | Same deep links |
| `lib/services/ehr.ts` | `mcp_servers/ehr/` | Same patient context |
| `lib/records.ts` | `app/services/records.py` | Same role-scoped read models (API layer, not agents) |
| `lib/auth.ts`, `session.ts`, `middleware.ts` | `app/auth/` + frontend route guards | Same row-level rules |
| `prisma/schema.prisma` | `app/models/entities.py` | Same entities/columns; `User.department` added |
| `prisma/seed.ts` | `scripts/seed.py` | Same demo accounts |

## Data ownership (who may write what)

* **MCP hospital services** own: appointments/slots, provider directory, test catalogue, notifications,
  EHR documents, patient context reads, audit events.
* **CareXHealth agents** own their platform state through repositories: care plans/items, tasks, doses,
  referrals, monitoring rules, observations, alerts, chat, nurse release requests.
* Agents never import a hospital-service module; they call MCP tools.
