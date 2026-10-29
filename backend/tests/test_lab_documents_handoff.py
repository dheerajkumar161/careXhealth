"""Lab reports, documents → PDF, clinical intelligence, nurse handover."""
from conftest import draft_and_approve


def _cbc(lab):  # noqa: ANN001, ANN202
    return next(a for a in lab.get("/api/overview").json()["appointments"] if a["kind"] == "TEST")


def test_lab_upload_flags_alerts_and_review(api):  # noqa: ANN001
    doctor, lab, patient = api("doctor"), api("lab"), api("patient")
    pid, _ = draft_and_approve(doctor)
    appt = _cbc(lab)
    assert appt["panel"]["code"] == "CBC" and len(appt["panel"]["params"]) == 4  # resolved via Test Center MCP
    assert lab.post(f"/api/appointments/{appt['id']}/result", {"values": {}}).status_code == 400
    doc = lab.post(f"/api/appointments/{appt['id']}/result", {"values": {"hb": 10.8, "wbc": 14.2, "platelets": 300, "neutrophils": 80}}).json()["document"]
    flags = {f["key"]: f["flag"] for f in doc["data"]["flags"]} if isinstance(doc["data"], dict) else None
    import json

    flags = flags or {f["key"]: f["flag"] for f in json.loads(doc["data"])["flags"]}
    assert flags == {"hb": "LOW", "wbc": "HIGH", "platelets": "NORMAL", "neutrophils": "HIGH"}
    assert lab.post(f"/api/appointments/{appt['id']}/result", {"values": {"hb": 11}}).status_code == 409  # already uploaded
    rec = doctor.get(f"/api/patients/{pid}").json()
    alert = next(a for a in rec["alerts"] if a["category"] == "LAB")
    assert alert["title"] == "Abnormal Complete Blood Count" and alert["escalationLevel"] == 2 and alert["severity"] == "HIGH"
    assert next(t for t in rec["tasks"] if t["type"] == "INVESTIGATION")["status"] == "COMPLETED"
    assert any(d["id"] == doc["id"] for d in patient.get("/api/overview").json()["documents"])  # shared with patient
    reviewed = doctor.patch(f"/api/documents/{doc['id']}").json()["document"]
    assert reviewed["reviewStatus"] == "REVIEWED" and "Reviewed by Dr. Ananya Rao" in reviewed["content"]
    assert doctor.patch(f"/api/documents/{doc['id']}").status_code == 409


def test_critical_lab_result_is_emergency(api):  # noqa: ANN001
    doctor, lab = api("doctor"), api("lab")
    pid, _ = draft_and_approve(doctor)
    lab.post(f"/api/appointments/{_cbc(lab)['id']}/result", {"values": {"hb": 6.2}})
    alert = next(a for a in doctor.get(f"/api/patients/{pid}").json()["alerts"] if a["category"] == "LAB")
    assert alert["severity"] == "CRITICAL" and alert["escalationLevel"] == 3


def test_lab_report_endpoint_alias(api):  # noqa: ANN001
    doctor, lab = api("doctor"), api("lab")
    draft_and_approve(doctor)
    r = lab.post("/api/lab-reports", {"appointmentId": _cbc(lab)["id"], "values": {"hb": 13}})
    assert r.status_code == 200 and r.json()["document"]["type"] == "LAB_REPORT"


def test_documents_render_to_pdf(api):  # noqa: ANN001
    doctor, nurse, patient, specialist = api("doctor"), api("nurse"), api("patient"), api("specialist")
    pid, _ = draft_and_approve(doctor)
    nurse.post(f"/api/patients/{pid}/intelligence", {"kind": "HANDOFF"})
    summary = doctor.post(f"/api/patients/{pid}/intelligence", {"kind": "SUMMARY"}).json()["document"]
    assert summary["type"] == "CLINICAL_SUMMARY" and "Patient Recovery Summary" in summary["content"]
    docs = doctor.get(f"/api/patients/{pid}").json()["documents"]
    types = {d["type"] for d in docs}
    assert {"PATIENT_INSTRUCTIONS", "REFERRAL_PACKAGE", "NURSE_HANDOFF", "CLINICAL_SUMMARY"} <= types
    for d in docs:
        r = doctor.get(f"/api/documents/{d['id']}/pdf")
        assert r.status_code == 200 and r.content[:5] == b"%PDF-" and r.headers["content-type"] == "application/pdf", d["type"]
    handoff = next(d for d in docs if d["type"] == "NURSE_HANDOFF")
    assert patient.get(f"/api/documents/{handoff['id']}/pdf").status_code == 403  # not shared with the patient
    plan = next(d for d in docs if d["type"] == "PATIENT_INSTRUCTIONS")
    assert patient.get(f"/api/documents/{plan['id']}/pdf").status_code == 200
    pkg = next(d for d in docs if d["type"] == "REFERRAL_PACKAGE")
    assert specialist.get(f"/api/documents/{pkg['id']}/pdf").status_code == 200


def test_pdf_template_rendering_uses_jinja(api):  # noqa: ANN001
    from app.documents.renderer import render_html

    html = render_html(
        {"type": "NURSE_HANDOFF", "title": "Handoff", "content": "# Hi\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n💊 meds → ok", "createdAt": "2026-10-07T10:00:00+05:30", "data": {"status": "Stable"}},
        {"user": {"name": "Arjun"}, "mrn": "CB-1", "doctor": {"name": "Dr. X"}, "diagnosis": "OA", "procedure": None},
    )
    assert "Nurse handoff" in html and "<table>" in html and "Status at handoff" in html and "💊" not in html and "→" in html


def test_nurse_handover_flow(api):  # noqa: ANN001
    doctor, nurse, nurse2, patient = api("doctor"), api("nurse"), api("nurse2"), api("patient")
    pid, _ = draft_and_approve(doctor)
    patient.post(f"/api/patients/{pid}/observations", {"type": "TEMPERATURE", "value": 102})  # open nurse-level alert
    assert nurse2.post(f"/api/patients/{pid}/nurse-release", {"reason": "Going on leave"}).status_code == 403
    r = nurse.post(f"/api/patients/{pid}/nurse-release", {"reason": "Going on leave next week"})
    assert r.status_code == 200
    req = r.json()["request"]
    assert req["handoffDocumentId"] and nurse.post(f"/api/patients/{pid}/nurse-release", {"reason": "again please"}).status_code == 409
    nurses = doctor.get("/api/nurses").json()["nurses"]
    rahul = next(n for n in nurses if n["name"] == "Rahul Verma")
    assert doctor.patch(f"/api/nurse-release/{req['id']}", {"action": "REJECT"}).status_code == 400  # reason required
    assert nurse.patch(f"/api/nurse-release/{req['id']}", {"action": "APPROVE", "toNurseId": rahul["id"]}).status_code == 403
    assert doctor.patch(f"/api/nurse-release/{req['id']}", {"action": "APPROVE", "toNurseId": rahul["id"]}).json() == {"ok": True}
    # approval only offers the handoff: the original nurse keeps the patient until the incoming nurse accepts
    assert doctor.get(f"/api/patients/{pid}").json()["patient"]["nurse"]["name"] != "Rahul Verma"
    assert nurse2.get("/api/overview").json()["incomingHandoffs"][0]["id"] == req["id"]
    assert nurse.patch(f"/api/nurse-release/{req['id']}", {"action": "ACCEPT"}).status_code == 404  # not the incoming nurse
    assert nurse2.patch(f"/api/nurse-release/{req['id']}", {"action": "DECLINE"}).status_code == 400  # reason required
    assert nurse2.patch(f"/api/nurse-release/{req['id']}", {"action": "ACCEPT"}).json() == {"ok": True}
    rec = doctor.get(f"/api/patients/{pid}").json()
    assert rec["patient"]["nurse"]["name"] == "Rahul Verma"
    assert rec["alerts"][0]["assignedTo"]["name"] == "Rahul Verma"  # open alert transferred
    assert rec["releaseRequests"][0]["status"] == "APPROVED" and rec["releaseRequests"][0]["handoff"]["title"].startswith("Nurse handoff")
    assert nurse.get(f"/api/patients/{pid}").status_code == 403 and nurse2.get(f"/api/patients/{pid}").status_code == 200
    assert any(n["title"].startswith("New patient assigned") for n in nurse2.get("/api/notifications").json()["items"])
    assert any(e["action"].startswith("1 open alert(s) re-routed") for e in rec["events"])


def test_doctor_cannot_remove_assigned_nurse(api):  # noqa: ANN001
    doctor = api("doctor")
    pid, _ = draft_and_approve(doctor)
    nurses = doctor.get("/api/nurses").json()["nurses"]
    r = doctor.post(f"/api/patients/{pid}/nurse", {"nurseId": nurses[0]["id"], "reason": "rebalance"})
    assert r.status_code == 409 and "must request release" in r.json()["error"]
