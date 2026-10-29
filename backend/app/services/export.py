"""Record export: the viewer-scoped patient record as plain JSON, or as a FHIR R4-style Bundle for portability."""
from __future__ import annotations

from typing import Any

from app.core.util import iso, now

OBS_CODES = {
    "TEMPERATURE": ("8310-5", "Body temperature"), "HEART_RATE": ("8867-4", "Heart rate"), "SPO2": ("59408-5", "Oxygen saturation"),
    "BLOOD_GLUCOSE": ("2339-0", "Glucose [Mass/volume] in Blood"), "WEIGHT": ("29463-7", "Body weight"), "PAIN": ("72514-3", "Pain severity"), "BP": ("85354-9", "Blood pressure panel"),
}  # fmt: skip


def fhir_bundle(rec: dict[str, Any]) -> dict[str, Any]:
    p = rec["patient"]
    pid = p["id"]
    entries: list[dict[str, Any]] = [
        {
            "resourceType": "Patient", "id": pid, "identifier": [{"system": "urn:carexhealth:mrn", "value": p["mrn"]}],
            "name": [{"text": p["user"]["name"]}], "gender": str(p["gender"]).lower(), "birthDate": str(p["dateOfBirth"])[:10],
            "telecom": [{"system": "phone", "value": p["user"].get("phone")}] if p["user"].get("phone") else [],
        },
        {"resourceType": "Condition", "id": f"cond-{pid}", "subject": {"reference": f"Patient/{pid}"}, "code": {"text": p["diagnosis"]}},
    ]  # fmt: skip
    if p.get("allergies"):
        entries.append({"resourceType": "AllergyIntolerance", "id": f"alg-{pid}", "patient": {"reference": f"Patient/{pid}"}, "code": {"text": p["allergies"]}})
    for plan in rec["plans"]:
        if plan["status"] != "ACTIVE":
            continue
        for i in plan["items"]:
            if i["category"] == "MEDICATION" and i["included"] and i["action"] != "DISCONTINUE":
                d = i["details"]
                entries.append(
                    {
                        "resourceType": "MedicationRequest", "id": i["id"], "status": "active", "intent": "order", "subject": {"reference": f"Patient/{pid}"},
                        "medicationCodeableConcept": {"text": d.get("name") or i["title"]},
                        "dosageInstruction": [{"text": f"{d.get('dose', '')} {d.get('timesPerDay', '')}x/day for {d.get('durationDays', '?')} days".strip()}],
                    }
                )  # fmt: skip
    for o in rec["observations"]:
        code, display = OBS_CODES.get(o["type"], (None, o["type"]))
        res: dict[str, Any] = {
            "resourceType": "Observation", "id": o["id"], "status": "final", "subject": {"reference": f"Patient/{pid}"},
            "code": {"coding": [{"system": "http://loinc.org", "code": code, "display": display}] if code else [], "text": display}, "effectiveDateTime": o["recordedAt"],
        }  # fmt: skip
        if o.get("value") is not None:
            res["valueQuantity"] = {"value": o["value"], "unit": o.get("unit")}
        elif o.get("text"):
            res["valueString"] = o["text"]
        entries.append(res)
    for a in rec["appointments"]:
        entries.append({"resourceType": "Appointment", "id": a["id"], "status": a["status"].lower(), "description": a["title"], "start": a["startsAt"]})
    return {"resourceType": "Bundle", "type": "collection", "timestamp": iso(now()), "entry": [{"resource": e} for e in entries]}
