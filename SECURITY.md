# Security & privacy notes

CareXHealth handles protected health information. The controls below are modelled on common HIPAA-style safeguards. They are **engineering controls, not a compliance certification** — compliance also needs organisational policy, a risk assessment, BAAs with providers (e.g. the LLM provider) and legal review.

## Controls in the code

| Area | Control | Where |
|---|---|---|
| Authentication | bcrypt passwords; JWT in an `HttpOnly`, `SameSite=Lax`, `Secure` (production) cookie; password policy (≥10 chars, letter + number) | `auth/security.py` |
| Brute force | per-email (5) and per-IP (20) failed-login limit, 15-minute lockout, DB-backed so it survives restarts; `429` + `Retry-After` | `auth/throttle.py` |
| Session revocation | `token_version` claim: password change, admin "sign out everywhere" and caregiver revocation invalidate old tokens immediately | `auth/deps.py` |
| Authorization | role dependencies + row-level `can_access_patient` (patient, doctor, nurse, partner via referral, caregiver via patient consent); UI guards are cosmetic | `auth/deps.py` |
| Least privilege | caregivers are read-only and never receive alerts, monitoring rules or agent events; partners only see what is routed to them | `services/records.py` |
| Audit trail | append-only `audit_logs`: logins (ok/failed/locked), profile/password changes, plan approve/reject, **safety overrides with the doctor's reason**, record views, exports, document downloads, alert actions, caregiver grants/revocations. Viewable by admins (all) and doctors (own patients) | `services/audit.py`, `/api/audit` |
| Clinical safety | deterministic allergy / interaction / duplicate / dose-ceiling checks; blocking findings need a written override before approval; the LLM can never add medicines, tests or referrals the doctor did not write | `agents/safety_rules.py` |
| Transport & headers | HSTS (production), `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, API CSP `default-src 'none'`, `Cache-Control: no-store` on `/api` | `main.py`, `frontend/nginx.conf` |
| Input limits | request-size cap (`MAX_UPLOAD_MB`), strict image data-URL validation, translation size limits and per-user rate limit | `main.py`, `schemas/api.py` |
| Startup guard | production refuses default/short secret, demo mode, wildcard CORS | `core/config.py` |
| Logging | request IDs; e-mail, bearer tokens and long numbers redacted from log lines | `core/logging.py` |
| Data portability | patient/caregiver/clinician export as JSON or FHIR-style bundle (audited, role-scoped) | `services/export.py` |

## Things you must do as the operator

* Run behind TLS; set a real `AUTH_SECRET`, `SIGNUP_INVITE_CODE`, `METRICS_TOKEN`; never enable `DEMO_MODE`.
* **LLM provider:** when Groq (or any hosted model) is configured, patient text in discharge notes and chat is sent to that provider. Use a provider/plan with appropriate agreements, or leave `GROQ_API_KEY` empty and use local Ollama / the rule engine. Translation (Settings → Language) also uses the configured model.
* Create the first administrator with `python scripts/create_admin.py --email … --name …` (sign-up never offers ADMIN).
* Change or delete the demo accounts (`scripts/seed.py` accounts share a public password) — never seed a real deployment.
* Decide data-retention periods for clinical records and the audit log (the app never deletes them) and encrypt the database volume / backups at rest.
* Review `/api/audit` regularly, especially `LOGIN_FAILED`, `LOGIN_LOCKED`, `SAFETY_OVERRIDE`, `RECORD_EXPORT`.
* The caregiver invite link is a bearer secret shown once to the patient; it is stored hashed, single-use and expires in 7 days.

## Known limitations

* No MFA yet; no SSO. Lockout is per email/IP, not per device.
* Safety rules are a curated starting set (common Indian-market generics), not a drug database. Integrate a licensed formulary for production prescribing.
* Machine translation of clinical text can be wrong. Built-in dictionaries cover only the UI; numbers/doses are verified to survive translation, but clinicians should treat translated patient material as a convenience copy of the English original (kept in the document's `data.original`).
* PostgreSQL is supported but not exercised by the automated tests.

## Reporting a vulnerability

Email the maintainers privately with reproduction steps; please do not open a public issue for security problems.
