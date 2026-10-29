"""Operational endpoints: readiness, metrics."""


def test_ready_and_health(fresh):  # noqa: ANN001
    r = fresh.get("/api/ready")
    assert r.status_code == 200 and r.json()["checks"]["database"] is True and r.json()["checks"]["mcp"] is True
    assert fresh.get("/api/health").json()["ok"] is True


def test_metrics_exposes_traffic_and_gauges(api, fresh):  # noqa: ANN001
    from conftest import draft_and_approve

    pid, _ = draft_and_approve(api("doctor"))
    api("patient").post(f"/api/patients/{pid}/observations", {"type": "TEMPERATURE", "value": 104})
    fresh.post("/api/auth/login", json={"email": "ananya.rao@carexhealth.health", "password": "bad-bad-bad1"})
    text = fresh.get("/metrics").text
    assert "carexhealth_http_requests_total" in text and 'route="/api/patients/{patient_id}/observations"' in text
    assert "carexhealth_open_alerts" in text and "carexhealth_login_failures_total" in text
    assert "carexhealth_llm_rule_engine_fallbacks_total" in text
