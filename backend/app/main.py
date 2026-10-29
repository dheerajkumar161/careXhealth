"""CareXHealth FastAPI application: REST API + agent runtime (MCP connections) + APScheduler."""
from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import time
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from app.agents.base import AgentError
from app.agents.mcp_client import MCPCallError
from app.agents.orchestrator import orchestrator
from app.api import admin, auth, care_plans, clinical, caregivers, coordination, patients, stream
from app.core import metrics
from app.core.config import get_settings
from app.core.db import init_db
from app.core.logging import client_ip_var, request_id_var, setup_logging
from app.scheduler.scheduler import start_scheduler, stop_scheduler

log = logging.getLogger("carexhealth")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    setup_logging(get_settings().log_json)
    get_settings().validate_for_startup()
    init_db()
    await orchestrator.services.connect()
    start_scheduler()
    try:
        yield
    finally:
        stop_scheduler()
        await orchestrator.services.close()


app = FastAPI(title="CareXHealth API", version="2.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in get_settings().cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
for r in (auth.router, admin.router, stream.router, caregivers.router, patients.router, care_plans.router, clinical.router, coordination.router):
    app.include_router(r)


@app.middleware("http")
async def request_context(request: Request, call_next):  # noqa: ANN001, ANN201
    """Request ID + client IP for logs/audit, upload size guard and security headers."""
    rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
    request_id_var.set(rid)
    fwd = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    client_ip_var.set(fwd or (request.client.host if request.client else None))
    cfg = get_settings()
    length = request.headers.get("content-length")
    if length and length.isdigit() and int(length) > cfg.max_upload_mb * 1024 * 1024:
        return JSONResponse({"error": f"Request too large (max {cfg.max_upload_mb} MB)"}, status_code=413)
    started = time.monotonic()
    response = await call_next(request)
    route = getattr(request.scope.get("route"), "path", "unmatched")
    metrics.HTTP_REQUESTS.labels(request.method, route, str(response.status_code)).inc()
    metrics.HTTP_LATENCY.labels(route).observe(time.monotonic() - started)
    response.headers["X-Request-ID"] = rid
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if not request.url.path.startswith(("/docs", "/redoc", "/openapi")):
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
    if cfg.hsts if cfg.hsts is not None else cfg.is_production:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    if request.url.path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", "no-store")
    return response


# Error bodies keep the legacy shape {"error": message} the frontend already reads.
@app.exception_handler(HTTPException)
async def http_error(_: Request, e: HTTPException) -> JSONResponse:
    return JSONResponse({"error": e.detail}, status_code=e.status_code, headers=getattr(e, "headers", None))


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, e: RequestValidationError) -> JSONResponse:
    first = e.errors()[0] if e.errors() else {}
    msg = str(first.get("msg", "Invalid input")).removeprefix("Value error, ")
    field = ".".join(str(x) for x in first.get("loc", [])[1:])
    return JSONResponse({"error": f"{field}: {msg}" if field and "Value error" not in str(first.get("msg")) else msg}, status_code=400)


@app.exception_handler(AgentError)
async def agent_error(_: Request, e: AgentError) -> JSONResponse:
    return JSONResponse({"error": str(e)}, status_code=e.status)


@app.exception_handler(PermissionError)
async def permission_error(_: Request, e: PermissionError) -> JSONResponse:
    return JSONResponse({"error": str(e)}, status_code=403)


@app.exception_handler(ValueError)
async def value_error(_: Request, e: ValueError) -> JSONResponse:
    return JSONResponse({"error": str(e)}, status_code=400)


@app.exception_handler(MCPCallError)
async def mcp_error(_: Request, e: MCPCallError) -> JSONResponse:
    log.error("MCP failure: %s", e)
    msg = str(e).split("Error executing tool", 1)[-1].split(":", 1)[-1].strip() or "Hospital service unavailable"
    return JSONResponse({"error": msg}, status_code=502)


@app.get("/api/health")
def health() -> dict:
    """Liveness: the process is up."""
    return {"ok": True, "mcpServers": list(orchestrator.services.tools)}


@app.get("/api/ready")
def ready() -> JSONResponse:
    """Readiness: database reachable, every MCP service connected, scheduler running (when enabled). 503 otherwise."""
    from sqlalchemy import text

    from app.core import llm
    from app.core.db import get_engine
    from app.scheduler import scheduler as sched

    checks: dict[str, object] = {}
    try:
        with get_engine().connect() as c:
            c.execute(text("SELECT 1"))
        checks["database"] = True
    except Exception as e:  # noqa: BLE001
        checks["database"] = False
        log.error("readiness: database check failed: %s", e)
    expected = {"scheduling", "provider_directory", "test_center", "notification", "ehr"}
    checks["mcp"] = expected <= set(orchestrator.services.tools)
    checks["scheduler"] = (not get_settings().scheduler_enabled) or sched._scheduler is not None or "another process"  # noqa: SLF001
    checks["llm"] = llm.llm_status()["primary"]  # informational: rule engine is a valid steady state
    ok = checks["database"] is True and checks["mcp"] is True
    return JSONResponse({"ok": ok, "checks": checks}, status_code=200 if ok else 503)


@app.get("/metrics", include_in_schema=False)
def metrics_endpoint(request: Request) -> Response:
    """Prometheus scrape endpoint. Needs METRICS_TOKEN as a bearer token when set; otherwise loopback only."""
    from app.core import metrics as m

    cfg = get_settings()
    auth = request.headers.get("authorization", "")
    allowed = auth == f"Bearer {cfg.metrics_token}" if cfg.metrics_token else (request.client is not None and request.client.host in ("127.0.0.1", "::1", "testclient"))
    if not allowed:
        return JSONResponse({"error": "Not allowed"}, status_code=403)
    return Response(m.render(), media_type="text/plain; version=0.0.4")
