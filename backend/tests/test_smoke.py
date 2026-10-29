from conftest import draft_and_approve


def test_discharge_to_execution(api):  # noqa: ANN001
    doctor = api("doctor")
    pid, plan = draft_and_approve(doctor)
    assert plan["status"] == "ACTIVE"
    rec = doctor.get(f"/api/patients/{pid}").json()
    assert rec["patient"]["status"] == "RECOVERING"
    kinds = {t["type"] for t in rec["tasks"]}
    assert {"MEDICATION", "INVESTIGATION", "FOLLOW_UP", "REFERRAL"} <= kinds, rec["tasks"]
    assert len(rec["doses"]) > 0
    assert rec["referrals"][0]["status"] == "SENT"
    assert any(d["type"] == "PATIENT_INSTRUCTIONS" for d in rec["documents"])
    assert any(d["type"] == "REFERRAL_PACKAGE" for d in rec["documents"])
