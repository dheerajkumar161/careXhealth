# Deploying CareXHealth

## 1. Docker (recommended)

```bash
cp backend/.env.example backend/.env
# edit backend/.env — at minimum:
#   AUTH_SECRET=<python -c "import secrets; print(secrets.token_urlsafe(48))">
#   GROQ_API_KEY=...            (optional; the rule engine works without any LLM)
#   SIGNUP_INVITE_CODE=<code>   (so only your staff can create clinician accounts)
#   CORS_ORIGINS=https://care.example.org
docker compose up --build -d     # UI on :8080 (put a TLS-terminating proxy in front)
docker compose exec api python scripts/seed.py   # OPTIONAL demo data — never on a real deployment
```

The image sets `ENVIRONMENT=production`. In that mode the API **refuses to start** if `AUTH_SECRET` is the default or shorter than 32 characters, `DEMO_MODE=true`, or `CORS_ORIGINS` contains `*`. Cookies are `Secure`, HSTS is sent, and logs are JSON with e-mail addresses, bearer tokens and long numbers redacted.

Terminate TLS in front of the `web` container (Caddy, Traefik, nginx, a cloud load balancer). Sessions use `Secure` cookies, so plain HTTP will not keep users signed in. Pass `X-Forwarded-For` so lockouts and the audit log record real client IPs.

## 2. Database

| | SQLite (default) | PostgreSQL |
|---|---|---|
| Setup | nothing — file in the `carexhealth-data` volume | `docker compose --profile postgres up -d`, `POSTGRES_PASSWORD` in `.env`, `DATABASE_URL=postgresql+psycopg://carexhealth:<pw>@postgres:5432/carexhealth` |
| Scale | one API container (WAL mode; the MCP services share the file) | recommended beyond a single hospital ward |
| Backup | `python scripts/backup.py --dir /data/backups --keep 14` (online, WAL-safe) | same script runs `pg_dump` |

Schema changes are Alembic migrations (`backend/alembic/versions`). The API upgrades the schema on start (`alembic upgrade head`); databases created before migrations existed are stamped and upgraded in place. To run it manually: `cd backend && alembic upgrade head`.

> PostgreSQL support is wired (driver in the image, dialect-neutral migrations) but the test-suite and CI run on SQLite. Run your own smoke test against Postgres before relying on it.

## 3. Operations

* **Liveness / readiness:** `GET /api/health`, `GET /api/ready` (503 when the database or any hospital MCP service is down — used by the container HEALTHCHECK).
* **Metrics:** `GET /metrics` (Prometheus). Set `METRICS_TOKEN` and scrape with `Authorization: Bearer <token>`; without it only loopback callers are allowed. Useful series: `carexhealth_http_requests_total`, `carexhealth_llm_calls_total{engine,outcome}`, `carexhealth_llm_rule_engine_fallbacks_total`, `carexhealth_open_alerts{severity}`, `carexhealth_pending_deliveries{status}`, `carexhealth_login_failures_total`.
* **Suggested alerts:** `/api/ready` failing > 2 min; `carexhealth_pending_deliveries{status="FAILED"} > 0`; rule-engine fallback rate rising (LLM provider down); sustained `carexhealth_login_failures_total` growth.
* **Backups:** schedule `scripts/backup.py` daily (cron / Task Scheduler / a sidecar). Test a restore: copy the file over `carexhealth.db` (SQLite) or `psql < dump.sql`.
* **Housekeeping:** `python scripts/housekeeping.py` prunes sent/skipped e-mail+SMS rows older than 90 days and old login-attempt rows. Clinical data and the audit log are never deleted by the app.
* **Logs:** `LOG_JSON=true` for structured logs with a `request_id`; the same id is returned in the `X-Request-ID` header and stored in each audit row.

## 4. Outbound e-mail / SMS / WhatsApp

Off until configured. Set `SMTP_*` for e-mail and `TWILIO_*` for SMS (or WhatsApp with `TWILIO_FROM=whatsapp:+…`). The scheduler job `deliver_notifications` copies every in-app notification to the recipient's enabled channels (users can opt out in **Profile & settings**), retries failures with exponential back-off (max `DELIVERY_MAX_ATTEMPTS`, then `FAILED`), and holds non-urgent messages during quiet hours. Alerts are never delayed.

## 5. Upgrading

1. Back up (`scripts/backup.py`).
2. `docker compose pull && docker compose up --build -d` — migrations run on start.
3. Check `/api/ready` and the audit log for `LOGIN` events.

## 6. Rotating secrets

Changing `AUTH_SECRET` signs everyone out. An admin can sign a single user out everywhere from **Admin → Users**; a password change does the same for that user's other devices. If `legacy-nextjs-backup.zip` was ever shared, rotate every key that was in the old `.env` (Groq, etc.).
