"""Deterministic risk score: factors, level, and queue ordering."""
from conftest import draft_and_approve

from app.services import risk


def test_risk_score_reflects_alerts_and_orders_queue(api):  # noqa: ANN001
    doctor, patient = api("doctor"), api("patient")
    pid, _ = draft_and_approve(doctor)
    base = risk.compute(pid)
    assert base["level"] in ("LOW", "MODERATE") and any("comorbid" in f["label"] for f in base["factors"])
    r = patient.post(f"/api/patients/{pid}/observations", {"type": "TEMPERATURE", "value": 103.5})
    assert r.status_code == 200
    after = risk.compute(pid)
    assert after["score"] > base["score"] and after["level"] == "HIGH"
    assert any("open alert" in f["label"] for f in after["factors"])
    row = doctor.get("/api/patients").json()["patients"][0]
    assert row["riskScore"] == after["score"] and row["riskLevel"] == "HIGH" and row["riskFactors"]
