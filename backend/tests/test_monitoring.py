"""Monitoring agent: deterministic thresholds, alerts, escalation, chat-reported emergencies."""
from datetime import timedelta
from functools import partial

from conftest import draft_and_approve


def _alerts(doctor, pid):  # noqa: ANN001, ANN202
    return doctor.get(f"/api/patients/{pid}").json()["alerts"]


def test_normal_abnormal_critical_observations(api):  # noqa: ANN001
    doctor, patient = api("doctor"), api("patient")
    pid, _ = draft_and_approve(doctor)
    r = patient.post(f"/api/patients/{pid}/observations", {"type": "TEMPERATURE", "value": 99})
    assert r.json()["alerts"] == 0 and not _alerts(doctor, pid)  # within thresholds → logged only
    r = patient.post(f"/api/patients/{pid}/observations", {"type": "TEMPERATURE", "value": 102})
    assert r.json()["alerts"] == 1
    a = _alerts(doctor, pid)[0]
    assert a["title"] == "Temperature > 101°F" and a["escalationLevel"] == 1 and a["severity"] == "HIGH" and a["assignedTo"]["role"] == "NURSE"
    # Repeat trigger is de-duplicated into the open alert's history
    patient.post(f"/api/patients/{pid}/observations", {"type": "TEMPERATURE", "value": 103})
    alerts = _alerts(doctor, pid)
    assert len(alerts) == 1 and alerts[0]["history"][-1]["event"].startswith("Repeat trigger")
    # Safety net: SpO2 < 90 → doctor, CRITICAL
    patient.post(f"/api/patients/{pid}/observations", {"type": "SPO2", "value": 86})
    spo2 = next(a for a in _alerts(doctor, pid) if a["title"].startswith("SpO₂"))
    assert spo2["severity"] == "CRITICAL" and spo2["escalationLevel"] == 2
    assert doctor.get(f"/api/patients/{pid}").json()["patient"]["riskLevel"] == "HIGH"
    # Pain ≥ 8 safety net, and BP validation
    assert patient.post(f"/api/patients/{pid}/observations", {"type": "PAIN", "value": 8}).json()["alerts"] == 1
    assert patient.post(f"/api/patients/{pid}/observations", {"type": "BP", "value": 120}).status_code == 400
    assert patient.post(f"/api/patients/{pid}/observations", {"type": "NURSE_NOTE", "text": "x"}).status_code == 403


def test_monitoring_never_calls_the_llm(api, monkeypatch):  # noqa: ANN001
    from app.core import llm

    def boom(*a, **k):  # noqa: ANN002, ANN003, ANN202
        raise AssertionError("monitoring must not use the LLM")

    doctor, patient = api("doctor"), api("patient")
    pid, _ = draft_and_approve(doctor)  # (approval legitimately uses the Communication agent's LLM path)
    for name in ("run_text", "run_json", "run_vision_json", "build_llm_agent"):
        monkeypatch.setattr(llm, name, boom)
    assert patient.post(f"/api/patients/{pid}/observations", {"type": "TEMPERATURE", "value": 104}).json()["alerts"] == 1


def test_chat_emergency_symptom(api):  # noqa: ANN001
    doctor, patient = api("doctor"), api("patient")
    pid, _ = draft_and_approve(doctor)
    reply = patient.post(f"/api/patients/{pid}/chat", {"message": "I have chest pain and feel breathless"}).json()["reply"]
    assert "alerted your care team" in reply["content"]
    emergency = next(a for a in _alerts(doctor, pid) if a["severity"] == "CRITICAL")
    assert emergency["escalationLevel"] == 3 and emergency["category"] == "SYMPTOM"
    assert any(n["title"] == "Your care team has been alerted" for n in patient.get("/api/notifications").json()["items"])
    # Grounded answers from the approved plan (rule engine)
    meds = patient.post(f"/api/patients/{pid}/chat", {"message": "What medicines do I take today?"}).json()["reply"]["content"]
    assert "Cefuroxime" in meds or "no medicine doses" in meds
    assert len(patient.get(f"/api/patients/{pid}/chat").json()["messages"]) == 4


def test_escalation_ladder_and_acknowledge(api):  # noqa: ANN001
    from app.agents.orchestrator import orchestrator
    from app.core.util import iso, now

    doctor, nurse, patient = api("doctor"), api("nurse"), api("patient")
    pid, _ = draft_and_approve(doctor)
    patient.post(f"/api/patients/{pid}/observations", {"type": "TEMPERATURE", "value": 102})
    alert = _alerts(doctor, pid)[0]
    run = partial(orchestrator.monitoring.invoke, "escalation_sweep", at=iso(now() + timedelta(minutes=16)))
    assert doctor.c.portal.call(run) == 1
    a = _alerts(doctor, pid)[0]
    assert a["escalationLevel"] == 2 and a["status"] == "ESCALATED" and a["assignedTo"]["role"] == "DOCTOR"
    assert doctor.c.portal.call(partial(orchestrator.monitoring.invoke, "escalation_sweep", at=iso(now() + timedelta(minutes=40)))) == 1
    a = _alerts(doctor, pid)[0]
    assert a["escalationLevel"] == 3 and a["escalateAfter"] is None
    # Acknowledge stops auto-escalation; resolve needs a note
    assert nurse.patch(f"/api/alerts/{alert['id']}", {"action": "ACKNOWLEDGE"}).json()["alert"]["status"] == "ACKNOWLEDGED"
    assert nurse.patch(f"/api/alerts/{alert['id']}", {"action": "RESOLVE"}).status_code == 400
    assert nurse.patch(f"/api/alerts/{alert['id']}", {"action": "RESOLVE", "note": "Paracetamol given, afebrile"}).json()["alert"]["status"] == "RESOLVED"
    assert doctor.get(f"/api/patients/{pid}").json()["patient"]["riskLevel"] == "LOW"
    assert [h["event"][:9] for h in a["history"]] == ["Alert cre", "Escalated", "Escalated"]


def test_weight_gain_rule(api):  # noqa: ANN001
    doctor, patient = api("doctor"), api("patient")
    pid, _ = draft_and_approve(doctor, "Heart failure. Take Tab Furosemide 40mg once daily for 14 days. Inform nurse if weight gain more than 2 kg.")
    patient.post(f"/api/patients/{pid}/observations", {"type": "WEIGHT", "value": 70})
    assert patient.post(f"/api/patients/{pid}/observations", {"type": "WEIGHT", "value": 72.5}).json()["alerts"] == 1
    assert _alerts(doctor, pid)[0]["title"] == "Weight gain > 2 kg in 72 h"
