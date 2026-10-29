"""Prometheus metrics: HTTP traffic, LLM engine usage / fallbacks, and live clinical gauges (open alerts, pending deliveries)."""
from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest

registry = CollectorRegistry()

HTTP_REQUESTS = Counter("carexhealth_http_requests_total", "HTTP requests", ["method", "route", "status"], registry=registry)
HTTP_LATENCY = Histogram("carexhealth_http_request_seconds", "HTTP latency", ["route"], registry=registry, buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30))
LLM_CALLS = Counter("carexhealth_llm_calls_total", "LLM calls by outcome", ["engine", "outcome"], registry=registry)  # outcome: ok | failed
LLM_FALLBACK = Counter("carexhealth_llm_rule_engine_fallbacks_total", "Calls that fell all the way back to the rule engine", registry=registry)
LLM_LATENCY = Histogram("carexhealth_llm_seconds", "LLM call latency", ["engine"], registry=registry, buckets=(0.5, 1, 2, 5, 10, 20, 45, 90))
OPEN_ALERTS = Gauge("carexhealth_open_alerts", "Unresolved alerts", ["severity"], registry=registry)
PENDING_DELIVERIES = Gauge("carexhealth_pending_deliveries", "Email/SMS deliveries waiting or failed", ["status"], registry=registry)
LOGIN_FAILURES = Counter("carexhealth_login_failures_total", "Failed sign-in attempts", registry=registry)


def refresh_gauges() -> None:
    from sqlalchemy import func, select

    from app.core.db import session_scope
    from app.models import Alert, Delivery

    with session_scope() as s:
        OPEN_ALERTS.clear()
        for sev, n in s.execute(select(Alert.severity, func.count()).where(Alert.status != "RESOLVED").group_by(Alert.severity)):
            OPEN_ALERTS.labels(sev).set(n)
        PENDING_DELIVERIES.clear()
        for st, n in s.execute(select(Delivery.status, func.count()).where(Delivery.status.in_(["PENDING", "FAILED"])).group_by(Delivery.status)):
            PENDING_DELIVERIES.labels(st).set(n)


def render() -> bytes:
    refresh_gauges()
    return generate_latest(registry)
