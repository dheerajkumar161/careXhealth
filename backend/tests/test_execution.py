"""Execution agent: doses, investigations, follow-ups, recurring sessions, amendments, item removal, rescheduling."""
from conftest import draft_and_approve


def test_medication_schedule_and_bookings(api):  # noqa: ANN001
    doctor = api("doctor")
    pid, _ = draft_and_approve(doctor)
    rec = doctor.get(f"/api/patients/{pid}").json()
    tasks = {t["type"]: t for t in rec["tasks"]}
    assert tasks["INVESTIGATION"]["status"] == "SCHEDULED" and tasks["INVESTIGATION"]["meta"]["testCode"] == "CBC"
    assert tasks["FOLLOW_UP"]["status"] == "SCHEDULED"
    # Cefuroxime 2×7 + Paracetamol 3×5 = 29 doses; the dashboard window shows ±7 days
    from app.core.db import session_scope
    from app.models import MedicationDose
    from sqlalchemy import func, select

    with session_scope() as s:
        assert s.scalar(select(func.count()).select_from(MedicationDose).where(MedicationDose.patient_id == pid)) == 29
    kinds = sorted({a["kind"] for a in rec["appointments"]})
    assert kinds == ["FOLLOW_UP", "TEST", "THERAPY"]
    therapy = [a for a in rec["appointments"] if a["kind"] == "THERAPY"]
    assert len(therapy) == 12 and all(a["status"] == "TENTATIVE" for a in therapy)  # recurring series held
    assert [a["sequence"] for a in sorted(therapy, key=lambda a: a["startsAt"])] == list(range(1, 13))
    # Patient got booking notifications through the Notification MCP server
    titles = [n["title"] for n in api("patient").get("/api/notifications").json()["items"]]
    assert "Complete Blood Count booked" in titles and "Follow-up appointment booked" in titles and "Your care plan is ready" in titles


def test_prn_medication_has_no_schedule(api):  # noqa: ANN001
    doctor = api("doctor")
    pid = doctor.get("/api/patients").json()["patients"][0]["id"]
    plan = doctor.post(f"/api/patients/{pid}/care-plans", {"instructions": "Take Tab Paracetamol 650mg three times daily for 5 days. Avoid driving."}).json()["plan"]
    items = [{**i, "details": {**i["details"], "asNeeded": True}} if i["category"] == "MEDICATION" else i for i in plan["items"]]
    doctor.patch(f"/api/care-plans/{plan['id']}", {"items": items})  # doctor marks it SOS while reviewing
    doctor.post(f"/api/care-plans/{plan['id']}/approve")
    rec = doctor.get(f"/api/patients/{pid}").json()
    med = next(t for t in rec["tasks"] if t["type"] == "MEDICATION")
    assert med["title"].endswith("(as needed)") and rec["doses"] == []


def test_amendment_discontinues_and_adds(api):  # noqa: ANN001
    doctor = api("doctor")
    pid, _ = draft_and_approve(doctor)
    r = doctor.post(f"/api/patients/{pid}/care-plans", {"kind": "AMENDMENT", "instructions": "Stop Cefuroxime. Start Tab Amoxiclav 625mg twice daily for 5 days. Repeat CBC in 3 days."})
    plan = r.json()["plan"]
    assert plan["kind"] == "AMENDMENT" and [i["action"] for i in plan["items"]][0] == "DISCONTINUE"
    assert not any(i["source"] == "AI_SUGGESTED" for i in plan["items"])  # amendments add no suggestions
    # Amoxiclav is a penicillin and this patient is penicillin-allergic → the safety gate blocks until the doctor documents a reason
    blocks = {f["code"]: "Allergy label is historic; tolerated before" for f in plan["safety"] if f["severity"] == "BLOCK"}
    assert blocks and doctor.post(f"/api/care-plans/{plan['id']}/approve").status_code == 409
    assert doctor.post(f"/api/care-plans/{plan['id']}/approve", {"overrides": blocks}).status_code == 200
    rec = doctor.get(f"/api/patients/{pid}").json()
    meds = {t["title"]: t["status"] for t in rec["tasks"] if t["type"] == "MEDICATION"}
    assert meds["Cefuroxime 500mg"] == "CANCELLED" and meds["Amoxiclav 625mg"] == "IN_PROGRESS"
    assert not any(d["medication"] == "Cefuroxime" and d["status"] == "PENDING" for d in rec["doses"])
    assert len([t for t in rec["tasks"] if t["type"] == "INVESTIGATION"]) == 2
    assert [p["status"] for p in rec["plans"]].count("ACTIVE") == 2  # initial + approved amendment both in force


def test_remove_item_cancels_downstream(api):  # noqa: ANN001
    doctor = api("doctor")
    pid, plan = draft_and_approve(doctor)
    ref_item = next(i for i in plan["items"] if i["category"] == "REFERRAL")
    assert doctor.delete(f"/api/care-plan-items/{ref_item['id']}", {}).status_code == 400  # reason required
    out = doctor.delete(f"/api/care-plan-items/{ref_item['id']}", {"reason": "Patient moving to another city"}).json()
    assert "12 appointment(s)" in out["cancelled"] and "referral" in out["cancelled"]
    rec = doctor.get(f"/api/patients/{pid}").json()
    assert rec["referrals"][0]["status"] == "CANCELLED"
    assert all(a["status"] == "CANCELLED" for a in rec["appointments"] if a["kind"] == "THERAPY")
    flag = next(i for i in plan["items"] if i["category"] == "RED_FLAG" and i["source"] == "DOCTOR")
    assert "monitoring rule" in doctor.delete(f"/api/care-plan-items/{flag['id']}", {"reason": "Not needed"}).json()["cancelled"]
    assert doctor.delete(f"/api/care-plan-items/{flag['id']}", {"reason": "again"}).status_code == 409


def test_missed_follow_up_is_rescheduled_and_alerts_nurse(api):  # noqa: ANN001
    doctor, nurse = api("doctor"), api("nurse")
    pid, _ = draft_and_approve(doctor)
    fu = next(a for a in doctor.get(f"/api/patients/{pid}").json()["appointments"] if a["kind"] == "FOLLOW_UP")
    r = nurse.patch(f"/api/appointments/{fu['id']}", {"action": "MISS", "notes": "Patient unwell"})
    assert r.status_code == 200 and r.json()["appointment"]["status"] == "MISSED"
    rec = doctor.get(f"/api/patients/{pid}").json()
    repl = next(a for a in rec["appointments"] if a.get("rescheduledFromId") == fu["id"])
    assert repl["status"] == "BOOKED" and repl["title"].endswith("(rescheduled)")
    alert = next(a for a in rec["alerts"] if a["category"] == "APPOINTMENT")
    assert alert["escalationLevel"] == 1 and alert["assignedTo"]["name"] == "Priya Nair"
    assert nurse.patch(f"/api/appointments/{fu['id']}", {"action": "COMPLETE"}).status_code == 409  # not BOOKED any more


def test_dose_recording_and_adherence_pattern(api):  # noqa: ANN001
    patient, doctor = api("patient"), api("doctor")
    pid, _ = draft_and_approve(doctor)
    doses = [d for d in patient.get("/api/overview").json()["doses"] if d["status"] == "PENDING"]
    assert patient.patch(f"/api/doses/{doses[0]['id']}", {"status": "TAKEN"}).json()["dose"]["status"] == "TAKEN"
    assert patient.patch(f"/api/doses/{doses[0]['id']}", {"status": "TAKEN"}).status_code == 409
    patient.patch(f"/api/doses/{doses[1]['id']}", {"status": "SKIPPED"})
    rec = doctor.get(f"/api/patients/{pid}").json()
    assert not any(a["category"] == "ADHERENCE" for a in rec["alerts"])  # missed once → only recorded
    patient.patch(f"/api/doses/{doses[2]['id']}", {"status": "SKIPPED"})
    alerts = [a for a in doctor.get(f"/api/patients/{pid}").json()["alerts"] if a["category"] == "ADHERENCE"]
    assert len(alerts) == 1 and alerts[0]["title"] == "Repeated medication non-adherence"
