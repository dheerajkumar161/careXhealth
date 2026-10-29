# CareXHealth — Agentic Post-Discharge Care

CareXHealth turns a doctor's natural-language discharge note into a coordinated recovery. Five Microsoft Agent Framework agents plan, book, monitor, document and hand off care. Doctors stay the clinical decision-makers: nothing executes until the treating doctor approves the plan.

```
React + Vite (frontend/)  ──REST /api──▶  FastAPI (backend/app/api)  ── auth: JWT (user_id, role, department)
                                               │
                                               ▼
                         Orchestrator — MAF Workflows (backend/app/agents/orchestrator.py)
     Planning ─▶ [doctor approval gate] ─▶ Monitoring rules ─▶ Execution ─▶ Communication
                    Monitoring · Communication · Intelligence during recovery
                                               │  MAF MCPStdioTool clients
                                               ▼
   Scheduling MCP · Provider Directory MCP · Test Center MCP · Notification MCP · EHR MCP   (backend/mcp_servers/)
                                               │
                                     SQLAlchemy ─▶ SQLite        APScheduler (persistent jobs in the same SQLite)
```

| # | Agent (MAF `BaseAgent`) | Responsibility | Code |
|---|---|---|---|
| 1 | Care Planning & Coordination | Understand → Structure → Plan. Creates a **DRAFT** plan. Never books or executes. | `backend/app/agents/planning_agent.py`, `planning_rules.py` |
| 2 | Care Execution & Scheduling | Execute → Book → Track, only for **approved** plans | `execution_agent.py` |
| 3 | Monitoring & Escalation | Observe → Detect → Alert → Escalate. **Fully deterministic**, with no LLM. | `monitoring_agent.py` |
| 4 | Communication & Clinical Documentation | Patient plan, assistant, lab reports, referral packages | `communication_agent.py` |
| 5 | Clinical Intelligence & Handoff | Deterministic fact sheet first, LLM narrative on top; nurse handover | `intelligence_agent.py` |

Hospital services are deterministic MCP servers (no LLM), one process each: `scheduling`, `provider_directory`, `test_center`, `notification`, `ehr`. Agents reach them only through MCP tools. `GET /api/agents` lists the agents, their skills and every MCP tool.

## Quick start (Windows paths; use `bin/` instead of `Scripts\` on macOS/Linux)

Requirements: Python 3.12, Node 20+, a Groq API key (optional), and optionally [Ollama](https://ollama.com) with `ollama pull qwen2.5:3b`.

```powershell
# Backend: API + agents + MCP servers + scheduler
cd backend
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy .env.example .env            # skip if backend\.env already exists
.venv\Scripts\python scripts\seed.py
.venv\Scripts\python main.py      # http://127.0.0.1:8000  (docs at /docs)

# Frontend, in a second terminal
cd frontend
npm install
npm run dev                       # http://localhost:5173  (proxies /api to :8000)
```

All demo accounts use the password **`Password@123`** (including `admin@carexhealth.health`). Demo data is for local use only — never seed a real deployment. The login page has one-click demo accounts for every role. See [WALKTHROUGH.md](WALKTHROUGH.md) for an end-to-end script that triggers every agent action.

The data from the previous Next.js/Prisma version can be imported with `.venv\Scripts\python scripts\migrate_from_prisma.py path\to\carexhealth.db`.

## LLM: Groq first, local Ollama as fallback

```
GROQ_API_KEY=gsk_...                    # https://console.groq.com/keys
GROQ_MODEL=openai/gpt-oss-120b          # primary
GROQ_FALLBACK_MODEL=qwen/qwen3.8-27b    # tried if the primary call fails
GROQ_VISION_MODEL=qwen/qwen3.8-27b      # reads photos/scans of notes and prescriptions
OLLAMA_MODEL=qwen2.5:3b                 # local fallback when Groq is unreachable
```

Every model call goes through `backend/app/core/llm.py`, which builds MAF `Agent`s per provider:

1. Groq primary model (MAF's OpenAI-compatible chat client).
2. Groq fallback model.
3. Local Ollama (MAF's `OllamaChatClient`). It is skipped while the Ollama server is down.
4. The deterministic rule engine: rule-based plan parsing, template patient plans and answers, fact-sheet summaries.

A short Groq rate limit (429) is retried once. Documents and plans record which engine produced them, and the header badge shows the active engine (hover it to see the whole chain). LLM output is validated with Pydantic and filtered so the model can never add medicines, tests, follow-ups or referrals the doctor did not write. Monitoring and escalation never use an LLM.

## Roles

| Role | Area | Scope |
|---|---|---|
| DOCTOR | `/doctor` | Own patients; approves plans; specialists receive referrals |
| NURSE | `/nurse` | Assigned patients; alert queue; handoffs |
| PATIENT | `/patient` | Own record only |
| TEST_CENTER | `/provider` | Test bookings; uploads results (Laboratory department) |
| PROVIDER | `/provider` | External care partner: referrals and bookings routed to it |
| ADMIN | `/admin` | Audit log, user directory, sign a user out everywhere |
| CAREGIVER | `/caregiver` | Read-only view of one patient who invited them (revocable by the patient) |

Every role has **Profile & settings** (`/<area>/settings`): edit details, choose a language, set e-mail/SMS preferences and change the password. Patients can also invite caregivers and download their record (JSON or FHIR-style).

Access is enforced by FastAPI dependencies (`require_user`, `require_role`, `require_department`, `can_access_patient` in `backend/app/auth/deps.py`) and by role-scoped read models (`backend/app/services/records.py`). The UI route guards only decide navigation.

## Production features (v2.1)

* **Security:** login lockout, password policy, session revocation, secure cookies/HSTS, startup guard for unsafe production config, request IDs, PHI-safe logs, append-only **audit log**. See [SECURITY.md](SECURITY.md).
* **Prescribing safety:** allergy, interaction, duplicate-therapy and dose-ceiling checks run on every draft plan; blocking findings need a written, audited override before approval (`agents/safety_rules.py`).
* **Risk score:** deterministic 0–100 patient risk with explained factors orders the doctor/nurse queues; vitals open into trend charts with the approved alert thresholds drawn on them.
* **Multilingual:** every user picks a language in Settings (16 languages). Patient plans and assistant replies are written in it, notifications and on-screen text are translated (cached), and the UI switches immediately (RTL for Arabic/Urdu). Without a reachable model the app shows English and says so.
* **Real-time:** alerts and notifications are pushed over Server-Sent Events (`/api/stream`); polling remains as a fallback.
* **Delivery:** optional e-mail (SMTP) and SMS/WhatsApp (Twilio-style) copies with retry, quiet hours, opt-out and delivery status; configurable escalation ladder (`ESCALATION_LADDER`).
* **Operations:** Alembic migrations, Docker + compose (optional Postgres), `/api/ready`, Prometheus `/metrics`, backup and housekeeping scripts, GitHub Actions CI. See [DEPLOYMENT.md](DEPLOYMENT.md).

## Background jobs

APScheduler runs six persistent jobs every `AGENT_CYCLE_SECONDS`, stored in the `apscheduler_jobs` table:

- `send_due_dose_reminders`
- `mark_overdue_doses`
- `check_missed_appointments`
- `check_adherence`
- `escalate_unacknowledged_alerts`
- `deliver_notifications` (e-mail / SMS copies; a no-op until a channel is configured)

Fixed job IDs keep a restart from duplicating jobs, and a lock file keeps a second process from starting another scheduler. **Agents live** in the header runs the same steps on demand as a MAF workflow.

## Documents

Agents write Markdown. `GET /api/documents/{id}/pdf` renders it through Jinja2 templates (`backend/templates/`) to PDF with xhtml2pdf. Every document viewer has a **PDF** button.

## Tests

```powershell
cd backend
.venv\Scripts\python -m ruff check .
.venv\Scripts\python -m pytest            # backend (incl. golden-note evals in tests/evals)

cd ..\frontend
npm test                                   # Vitest unit tests
npm run e2e                                # Playwright smoke tests (starts a throw-away backend + Vite)
```

The suite runs against a throw-away SQLite DB with the real FastAPI app, the real MCP server processes and the real MAF agents. LLM paths use a scripted MAF chat client, so no Ollama is needed.

`MIGRATION.md` maps every legacy module to its new home.
