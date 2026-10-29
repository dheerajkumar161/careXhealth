"""Deterministic patient risk score (0–100) with human-readable factors. No LLM; used to order nurse/doctor queues."""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import select

from app.core.db import session_scope
from app.core.util import dumps, now
from app.models import Alert, Appointment, MedicationDose, Observation, Patient

HIGH, MODERATE = 55, 25


def level_for(score: int, severities: list[str]) -> str:
    # an open CRITICAL/HIGH alert always makes the patient HIGH risk regardless of the score
    if any(s in ("CRITICAL", "HIGH") for s in severities) or score >= HIGH:
        return "HIGH"
    return "MODERATE" if severities or score >= MODERATE else "LOW"


def compute(patient_id: str) -> dict[str, Any]:
    t = now()
    factors: list[dict[str, Any]] = []

    def add(points: int, label: str) -> None:
        if points:
            factors.append({"points": points, "label": label})

    with session_scope() as s:
        p = s.get(Patient, patient_id)
        if p is None:
            return {"score": 0, "level": "LOW", "factors": []}
        age = (t - p.date_of_birth).days // 365
        add(15 if age >= 75 else 10 if age >= 65 else 0, f"Age {age}")
        comorb = [c for c in (p.comorbidities or "").replace(";", ",").split(",") if c.strip()]
        add(min(len(comorb) * 5, 15), f"{len(comorb)} comorbidit{'y' if len(comorb) == 1 else 'ies'}")
        if p.discharge_date and (t - p.discharge_date).days <= 7:
            add(5, "First week after discharge")
        severities = [a.severity for a in s.scalars(select(Alert).where(Alert.patient_id == patient_id, Alert.status != "RESOLVED"))]
        weight = {"CRITICAL": 30, "HIGH": 20, "MEDIUM": 8, "LOW": 3}
        add(min(sum(weight.get(v, 3) for v in severities), 45), f"{len(severities)} open alert(s)")
        doses = list(s.scalars(select(MedicationDose).where(MedicationDose.patient_id == patient_id, MedicationDose.scheduled_at <= t)))
        past = [d for d in doses if d.status not in ("CANCELLED", "PENDING")]
        if len(past) >= 3:
            adh = round(len([d for d in past if d.status == "TAKEN"]) / len(past) * 100)
            add(20 if adh < 60 else 10 if adh < 80 else 0, f"Medicine adherence {adh}%")
        missed = s.scalars(select(Appointment.id).where(Appointment.patient_id == patient_id, Appointment.status == "MISSED")).all()
        add(min(len(missed) * 8, 16), f"{len(missed)} missed appointment(s)")
        flagged = s.scalars(select(Observation.id).where(Observation.patient_id == patient_id, Observation.flagged.is_(True), Observation.recorded_at >= t - timedelta(hours=48))).all()
        add(min(len(flagged) * 5, 15), f"{len(flagged)} abnormal reading(s) in 48 h")
    score = min(sum(f["points"] for f in factors), 100)
    return {"score": score, "level": level_for(score, severities), "factors": sorted(factors, key=lambda f: -f["points"])}


def refresh(patient_id: str) -> dict[str, Any]:
    r = compute(patient_id)
    with session_scope() as s:
        p = s.get(Patient, patient_id)
        if p is not None:
            p.risk_score, p.risk_level, p.risk_factors = r["score"], r["level"], dumps(r["factors"])
    return r
