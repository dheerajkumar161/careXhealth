# CareXHealth — Production Upgrade (v2.1): plan and delivery status

Approved with changes: (a) the language is **user-selectable in Settings for every role** (16 languages, not Hindi-only); (b) **no installable app / PWA**; (c) **Profile & Settings for every role** (details, language, password). Open decisions took their defaults: SQLite default + Postgres supported, SMS adapter off until keys are set, ADMIN role added, HIPAA-style controls.

Legend: ✅ done and tested · 🟡 partly / existing behaviour reused · ⚠️ done but not verifiable here · ➖ dropped

Verification at the end of this work: backend `pytest` **85 passed**, `ruff` clean, `alembic check` clean, frontend `tsc` clean, `vitest` 6 passed, `vite build` OK, Playwright smoke **3 passed** (doctor→approve→patient view, language switch, login lockout).

## Phase 1 — Security & compliance
| # | Item | Status | Notes |
|---|---|---|---|
| 1.1 | Startup guard (secret / demo mode / CORS) | ✅ | `ENVIRONMENT=production` |
| 1.2 | Secure cookie, configurable | ✅ | secure by default in production |
| 1.3 | Login rate limit + lockout, DB-backed | ✅ | 5 per email / 20 per IP, 15 min |
| 1.4 | Password policy, change password, session revocation (`token_version`) | ✅ | all roles |
| 1.5 | Append-only audit log + viewer | ✅ | `/api/audit`, admin + doctor views |
| 1.6 | Security headers, request IDs, JSON logs with redaction | ✅ | |
| 1.7 | Alembic migrations (legacy DBs stamped + upgraded) | ✅ | 0001–0006, tested |
| 1.8 | Upload / request limits | ✅ | `MAX_UPLOAD_MB`; image data-URL validation existed |
| + | ADMIN role (audit, users, sign-out-everywhere) + `scripts/create_admin.py` | ✅ | |

## Phase 2 — Clinical safety
| # | Item | Status | Notes |
|---|---|---|---|
| 2.1 | Allergy / interaction / duplicate / dose-ceiling checks with audited override at the approval gate | ✅ | curated rule set — see SECURITY.md limitations |
| 2.2 | Plan versioning + diff | 🟡 | versions/amendments already existed; **no new diff view was built** |
| 2.3 | Deterministic risk score, queue ordering, explained factors | ✅ | |
| 2.4 | Vitals trend charts with threshold lines | ✅ | click a vitals tile |
| 2.5 | Patient symptom check-in | 🟡 | the existing symptom/vitals form already feeds Monitoring; nothing new added |
| 2.6 | Golden-note eval suite | ✅ | rule engine; runs in CI |

## Phase 3 — Real-time & delivery
| # | Item | Status | Notes |
|---|---|---|---|
| 3.1 | Server-Sent Events | ✅ | polling kept as fallback |
| 3.2 | Email (SMTP) + SMS/WhatsApp (Twilio-style), retry, quiet hours, opt-out, status | ✅ | tested with fake providers; **never run against real SMTP/Twilio** |
| 3.3 | Configurable escalation ladder | ✅ | `ESCALATION_LADDER` |

## Phase 4 — Patient & caregiver experience
| # | Item | Status | Notes |
|---|---|---|---|
| 4.1 | Multilingual (user setting) | ✅ | plans, assistant, notifications, UI. Built-in UI dictionaries for hi, bn, ta, te, mr, es, fr, ar; other languages and dynamic text need a reachable LLM, else English is shown with a notice. Machine translation quality is not clinically reviewed |
| 4.2 | PWA / push | ➖ | removed on request |
| 4.3 | Caregiver read-only access (invite link, revocable) | ✅ | |
| 4.4 | Export (JSON / FHIR-style) | ✅ | audited, role-scoped |
| 4.5 | Profile & Settings for every role | ✅ | |

## Phase 5 — Platform & operations
| # | Item | Status | Notes |
|---|---|---|---|
| 5.1 | Dockerfiles + compose (+ optional Postgres) | ⚠️ | written, **not built or run** (Docker not exercised here); Postgres untested |
| 5.2 | GitHub Actions CI | ⚠️ | each step passes locally; workflow itself has not run on GitHub |
| 5.3 | Frontend tests: Vitest + Playwright | ✅ | run locally |
| 5.4 | `/api/ready`, Prometheus `/metrics` | ✅ | |
| 5.5 | Backup + housekeeping scripts | ✅ | SQLite backup tested; `pg_dump` path untested |
| 5.6 | `git init`, remove stray `a.txt`, docs (README, DEPLOYMENT, SECURITY), `.env.example` | ✅ | no commit made. **Rotating keys that were in `legacy-nextjs-backup.zip` is a manual step for you** |

## Not done / follow-ups
* Plan-version diff UI (2.2); MFA/SSO; licensed drug database for the safety rules; clinical review of translations; load testing; running the Docker/CI/Postgres paths for real.
* Frontend text outside the shell, Settings and patient-facing pages is translated by an on-screen text translator at runtime (needs an LLM for languages without a built-in dictionary).
