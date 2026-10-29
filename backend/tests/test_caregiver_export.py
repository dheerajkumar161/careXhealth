"""Caregiver invite → read-only access → revoke; record export (JSON + FHIR) with audit."""
import json

from conftest import draft_and_approve
from fastapi.testclient import TestClient


def _token(link: str) -> str:
    return link.split("token=")[1]


def test_caregiver_lifecycle(api, fresh):  # noqa: ANN001
    doctor, patient = api("doctor"), api("patient")
    pid, _ = draft_and_approve(doctor)
    inv = patient.post("/api/caregivers", {"email": "Sunita.Sharma@example.com", "name": "Sunita"}).json()
    assert inv["link"].startswith("/join?token=")
    assert patient.post("/api/caregivers", {"email": "sunita.sharma@example.com"}).status_code == 409
    assert doctor.post("/api/caregivers", {"email": "x@example.com"}).status_code == 403

    c = TestClient(fresh.app)
    bad = c.post("/api/auth/accept-invite", json={"token": "nope-nope-nope", "name": "Sunita", "password": "Family-pass-123"})
    assert bad.status_code == 400
    ok = c.post("/api/auth/accept-invite", json={"token": _token(inv["link"]), "name": "Sunita Sharma", "password": "Family-pass-123"})
    assert ok.status_code == 200 and ok.json()["redirect"] == "/caregiver"
    assert c.post("/api/auth/accept-invite", json={"token": _token(inv["link"]), "name": "Sunita Sharma", "password": "Family-pass-123"}).status_code == 400  # single use

    me = c.get("/api/auth/me").json()["user"]
    assert me["role"] == "CAREGIVER"
    ov = c.get("/api/overview").json()
    assert ov["patient"]["id"] == pid and ov["plans"] and all(p["status"] == "ACTIVE" for p in ov["plans"])
    assert "alerts" in ov and ov["alerts"] == [] and ov["rules"] == []  # clinician-only data is not exposed
    # read-only: no writes, no clinician areas
    assert c.post(f"/api/patients/{pid}/observations", json={"type": "TEMPERATURE", "value": 99}).status_code == 403
    assert c.post(f"/api/patients/{pid}/chat", json={"message": "hi"}).status_code == 403
    assert c.get("/api/patients").status_code == 403
    assert c.get(f"/api/patients/{pid}/export").status_code == 200

    rows = patient.get("/api/caregivers").json()["caregivers"]
    assert rows[0]["status"] == "ACTIVE"
    assert patient.delete(f"/api/caregivers/{rows[0]['id']}").status_code == 200
    assert c.get("/api/overview").status_code == 401  # session revoked immediately
    assert patient.get("/api/caregivers").json()["caregivers"] == []


def test_export_json_and_fhir_are_scoped_and_audited(api):  # noqa: ANN001
    doctor, patient = api("doctor"), api("patient")
    pid, _ = draft_and_approve(doctor)
    patient.post(f"/api/patients/{pid}/observations", {"type": "TEMPERATURE", "value": 99.1})
    r = patient.get(f"/api/patients/{pid}/export")
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    assert json.loads(r.text)["patient"]["id"] == pid
    fhir = json.loads(patient.get(f"/api/patients/{pid}/export?format=fhir").text)
    kinds = [e["resource"]["resourceType"] for e in fhir["entry"]]
    assert fhir["resourceType"] == "Bundle" and {"Patient", "Condition", "MedicationRequest", "Observation", "AllergyIntolerance"} <= set(kinds)
    assert api("nurse2").get(f"/api/patients/{pid}/export").status_code == 403  # a nurse not assigned to the patient
    actions = [e["action"] for e in api("admin").get("/api/audit?action=RECORD_EXPORT").json()["entries"]]
    assert len(actions) == 2
