"""Golden discharge notes → expected plan content. Guards the planner against regressions (rule engine here; point
EVAL_LIVE_LLM=1 at a configured model to run the same cases against it)."""
import pytest

from conftest import patient_id

CASES = [
    {
        "note": "Take Tab Metformin 500mg twice daily for 30 days. Check HbA1c after 2 weeks. Follow up after 1 week. Diet: low sugar, avoid sweets. Notify nurse if blood glucose exceeds 300.",
        "meds": {"Metformin"}, "categories": {"MEDICATION", "INVESTIGATION", "FOLLOW_UP"},
    },
    {
        "note": "Tab Paracetamol 650mg three times daily for 3 days. Tab Pantoprazole 40mg once daily before food for 14 days. Review in 10 days. Avoid spicy food. Call us if fever above 101F.",
        "meds": {"Paracetamol", "Pantoprazole"}, "categories": {"MEDICATION", "FOLLOW_UP", "RED_FLAG"},
    },
    {
        "note": "Treated for urinary tract infection. Take Tab Ciprofloxacin 500mg twice daily for 5 days. Drink plenty of fluids. Follow up after 1 week. Notify nurse if temperature exceeds 101F.",
        "meds": {"Ciprofloxacin"}, "categories": {"MEDICATION", "FOLLOW_UP"},
    },
]


@pytest.mark.parametrize("case", CASES, ids=["diabetes", "gastritis", "uti"])
def test_golden_note(api, case):  # noqa: ANN001
    doctor = api("doctor")
    plan = doctor.post(f"/api/patients/{patient_id(doctor)}/care-plans", {"instructions": case["note"]}).json()["plan"]
    items = [i for i in plan["items"] if i["included"]]
    got_meds = {(i["details"].get("name") or "").split()[0].title() for i in items if i["category"] == "MEDICATION" and i["source"] == "DOCTOR"}
    assert case["meds"] <= got_meds, (got_meds, [i["title"] for i in items])
    assert case["categories"] <= {i["category"] for i in items}
    assert plan["status"] == "DRAFT"  # nothing executes before approval
    # the doctor's words are never contradicted: no medicine appears that the note does not mention
    for i in items:
        if i["category"] == "MEDICATION":
            assert (i["details"].get("name") or "").split()[0].lower() in case["note"].lower()
