"""Referral lifecycle: create → match → hold → package → send → accept → schedule, and decline → revise → resend."""
from conftest import draft_and_approve


def _referral(doctor, pid):  # noqa: ANN001, ANN202
    return doctor.get(f"/api/patients/{pid}").json()["referrals"][0]


def test_referral_accept_and_treatment(api):  # noqa: ANN001
    doctor, specialist, patient = api("doctor"), api("specialist"), api("patient")
    pid, _ = draft_and_approve(doctor)
    ref = _referral(doctor, pid)
    assert ref["status"] == "SENT" and ref["provider"]["name"] == "Dr. Kavya Menon" and ref["packageDocumentId"]
    assert [t["status"] for t in ref["timeline"]] == ["CREATED", "SENT"]
    hub = specialist.get("/api/referrals").json()
    inc = hub["incoming"][0]
    assert inc["id"] == ref["id"] and "Referral — Physiotherapy" in inc["package"]["content"] and "Clinical summary" in inc["package"]["content"]
    # Legacy rule kept: a specialist sees the patient only through the referral package, not the full record
    assert specialist.get(f"/api/patients/{pid}").status_code == 403
    assert specialist.get(f"/api/documents/{ref['packageDocumentId']}/pdf").content[:5] == b"%PDF-"
    assert doctor.patch(f"/api/referrals/{ref['id']}", {"action": "ACCEPT"}).status_code == 404  # only the receiving specialist
    assert specialist.patch(f"/api/referrals/{ref['id']}", {"action": "ACCEPT", "note": "Happy to see him"}).json() == {"ok": True}
    ref = _referral(doctor, pid)
    assert ref["status"] == "SCHEDULED" and [t["status"] for t in ref["timeline"]][-2:] == ["ACCEPTED", "SCHEDULED"]
    sessions = sorted(ref["appointments"], key=lambda a: a["startsAt"])
    assert len(sessions) == 12 and all(a["status"] == "BOOKED" for a in sessions)
    assert any(n["title"] == "Physiotherapy scheduled" for n in patient.get("/api/notifications").json()["items"])
    # Session 1 attended → In treatment; session 2 missed → replacement + nurse alert
    specialist.patch(f"/api/appointments/{sessions[0]['id']}", {"action": "COMPLETE"})
    assert _referral(doctor, pid)["status"] == "IN_TREATMENT"
    specialist.patch(f"/api/appointments/{sessions[1]['id']}", {"action": "MISS"})
    ref = _referral(doctor, pid)
    assert len([a for a in ref["appointments"] if a["status"] == "BOOKED"]) == 11  # 10 remaining + 1 replacement
    alerts = doctor.get(f"/api/patients/{pid}").json()["alerts"]
    assert any(a["title"] == "Missed: Physiotherapy session 2" for a in alerts)


def test_referral_decline_revise_resend(api):  # noqa: ANN001
    doctor, specialist = api("doctor"), api("specialist")
    pid, _ = draft_and_approve(doctor)
    ref = _referral(doctor, pid)
    assert specialist.patch(f"/api/referrals/{ref['id']}", {"action": "DECLINE", "note": "no"}).status_code == 400  # reason required
    reason = "Need a recent X-ray report before starting. Can only offer 2 sessions per week."
    specialist.patch(f"/api/referrals/{ref['id']}", {"action": "DECLINE", "note": reason})
    ref = _referral(doctor, pid)
    assert ref["status"] == "DECLINED" and ref["declineReason"] == reason and ref["provider"] is None
    assert all(a["status"] == "CANCELLED" for a in ref["appointments"])  # holds released, nothing silently re-routed
    assert specialist.get("/api/referrals").json()["incoming"][0]["rejectedByMe"] is True

    proposal = doctor.post(f"/api/referrals/{ref['id']}/revise").json()["proposal"]
    # Rule fallback (unchanged legacy semantics): "2 sessions per week" → sessions = 2; the named test becomes an investigation
    assert proposal["engine"] == "rules" and proposal["referral"]["sessions"] == 2
    assert reason in proposal["referral"]["noteToSpecialist"]
    assert proposal["carePlanChanges"][0]["details"]["test"] == "X-ray"

    # Resend to the same specialist explicitly (declined providers are excluded from automatic matching)
    me = next(s for s in doctor.get("/api/referrals").json()["specialists"] if s["name"] == "Dr. Kavya Menon")
    out = doctor.post(f"/api/referrals/{ref['id']}/resend", {"referral": proposal["referral"], "carePlanChanges": proposal["carePlanChanges"], "engine": proposal["engine"], "providerId": me["id"]}).json()
    assert out["routed"] is True and out["amendmentId"]
    rec = doctor.get(f"/api/patients/{pid}").json()
    ref = rec["referrals"][0]
    assert ref["status"] == "SENT" and ref["revision"] == 1 and "RESUBMITTED" in [t["status"] for t in ref["timeline"]]
    assert any(t["type"] == "INVESTIGATION" and "X-Ray" in t["title"] for t in rec["tasks"])  # amendment executed
    pkg = next(d for d in rec["documents"] if d["id"] == ref["packageDocumentId"])
    assert "Resubmission (version 2)" in pkg["content"]
    plan_ref = next(i for p in rec["plans"] for i in p["items"] if i["category"] == "REFERRAL")
    assert plan_ref["details"]["sessions"] == 2 and plan_ref["title"].startswith("Physiotherapy — 2 sessions")  # care plan kept in step
    specialist.patch(f"/api/referrals/{ref['id']}", {"action": "ACCEPT"})
    assert _referral(doctor, pid)["status"] == "SCHEDULED"
