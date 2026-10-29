"""Prescribing-safety gate: allergies, interactions, duplicates, dose ceilings, override flow."""
from conftest import NOTE, patient_id

from app.agents.safety_rules import check_plan, unresolved_blocks


def med(name, dose="500mg", times=2):
    return {"category": "MEDICATION", "title": f"{name} {dose}", "action": "ADD", "included": True, "details": {"name": name, "dose": dose, "timesPerDay": times}}


def codes(findings, sev=None):
    return {f.code for f in findings if sev in (None, f.severity)}


def test_allergy_direct_and_cross_reactive():
    f = check_plan([med("Amoxicillin")], allergies="Penicillin", comorbidities=None)
    assert any(x.severity == "BLOCK" and x.code.startswith("ALLERGY:penicillin") for x in f)
    f = check_plan([med("Cefuroxime")], allergies="Penicillin", comorbidities=None)
    assert [x.severity for x in f] == ["WARN"] and f[0].code.startswith("CROSS:")
    assert check_plan([med("Paracetamol", "650mg", 3)], allergies="Penicillin, Sulfa", comorbidities=None) == []
    assert any(x.severity == "BLOCK" for x in check_plan([med("Cotrimoxazole")], allergies="sulfa drugs", comorbidities=None))
    assert check_plan([med("Ibuprofen")], allergies="NKDA", comorbidities=None) == []


def test_interactions_duplicates_and_dose():
    f = check_plan([med("Warfarin", "5mg", 1), med("Ibuprofen", "400mg", 3)], allergies=None, comorbidities=None)
    assert any(x.severity == "BLOCK" and "ANTICOAG-NSAID" in x.code for x in f)
    f = check_plan([med("Diclofenac", "50mg", 2), med("Ibuprofen", "400mg", 3)], allergies=None, comorbidities="CKD stage 3")
    assert "DUPCLASS:nsaid" in codes(f) and any(c.startswith("CO:nsaid") for c in codes(f))
    f = check_plan([med("Paracetamol", "1000mg", 5)], allergies=None, comorbidities=None)
    assert any(x.severity == "BLOCK" and x.code.startswith("DOSE:paracetamol") for x in f)
    f = check_plan([med("Paracetamol", "650mg", 3), med("Tab Paracetamol", "500mg", 2)], allergies=None, comorbidities=None)
    assert "DUP:paracetamol" in codes(f)
    # an already-active medicine participates in interactions
    f = check_plan([med("Ibuprofen", "400mg", 3)], allergies=None, comorbidities=None, current_meds=["Warfarin 5mg"])
    assert any("ANTICOAG-NSAID" in x.code for x in f)
    # excluded items are ignored
    ex = med("Amoxicillin")
    ex["included"] = False
    assert check_plan([ex], allergies="Penicillin", comorbidities=None) == []


def test_override_requires_reason():
    findings = [{"severity": "BLOCK", "code": "X"}, {"severity": "WARN", "code": "Y"}]
    assert unresolved_blocks(findings, {})
    assert not unresolved_blocks(findings, {"X": "Benefit outweighs risk"})
    assert unresolved_blocks(findings, {"X": "ok"})


def test_approval_gate_blocks_until_overridden(api):  # noqa: ANN001
    doctor = api("doctor")
    pid = patient_id(doctor)
    note = NOTE + " Take Tab Amoxicillin 500mg three times daily for 5 days."  # the patient is allergic to penicillin
    plan = doctor.post(f"/api/patients/{pid}/care-plans", {"instructions": note}).json()["plan"]
    blocks = [f for f in plan["safety"] if f["severity"] == "BLOCK"]
    assert blocks and any(f["code"].startswith("CROSS:") for f in plan["safety"])
    r = doctor.post(f"/api/care-plans/{plan['id']}/approve")
    assert r.status_code == 409 and r.json()["unresolved"] and r.json()["findings"]
    r = doctor.post(f"/api/care-plans/{plan['id']}/approve", {"overrides": {blocks[0]["code"]: "x"}})
    assert r.status_code == 409  # reason too short
    r = doctor.post(f"/api/care-plans/{plan['id']}/approve", {"overrides": {b["code"]: "Culture-proven sensitivity; allergy label is historic" for b in blocks}})
    assert r.status_code == 200 and r.json()["plan"]["status"] == "ACTIVE"
    audit = api("admin").get("/api/audit?action=SAFETY_OVERRIDE").json()["entries"]
    assert audit and "Culture-proven" in audit[0]["detail"]
