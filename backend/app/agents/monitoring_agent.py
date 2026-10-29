"""AGENT 3 — Monitoring & Escalation (Microsoft Agent Framework agent).

Observe → Detect → Alert → Escalate. Compares incoming patient data against DOCTOR-APPROVED red flags and
thresholds. Every detection, threshold and escalation decision here is deterministic by design — this agent
never consults the LLM; MAF only provides the agent/orchestration envelope. Port of lib/agents/monitoring.ts.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from app.core.config import get_settings
from app.core.constants import METRICS
from app.core.util import dumps, fmt, fmt_day, fmt_time, iso, now, parse_dt, parse_json
from app.models import Alert
from app.repositories import monitoring, people, tasks

from .base import CareXHealthAgent, skill

LEVEL_FOR_ACTION = {"NOTIFY_NURSE": 1, "NOTIFY_DOCTOR": 2, "EMERGENCY": 3}
LEVEL_LABEL = {1: "Assigned nurse", 2: "Treating doctor", 3: "Emergency / on-call team"}
EMERGENCY_KEYWORDS = ["chest pain", "can't breathe", "cannot breathe", "shortness of breath", "unconscious", "fainted", "seizure", "heavy bleeding", "coughing blood", "stroke", "slurred speech"]

OBS_METRICS: dict[str, list[tuple[str, str]]] = {
    "TEMPERATURE": [("TEMPERATURE", "value")],
    "BP": [("SYSTOLIC_BP", "value"), ("DIASTOLIC_BP", "value2")],
    "HEART_RATE": [("HEART_RATE", "value")],
    "SPO2": [("SPO2", "value")],
    "PAIN": [("PAIN", "value")],
    "BLOOD_GLUCOSE": [("BLOOD_GLUCOSE", "value")],
    "WEIGHT": [("WEIGHT", "value")],
}


def jsnum(v: float | None) -> str:
    if v is None:
        return ""
    return str(int(v)) if float(v).is_integer() else str(v)


def compare(value: float, op: str, threshold: float) -> bool:
    if op == ">":
        return value > threshold
    if op == ">=":
        return value >= threshold
    if op == "<":
        return value < threshold
    if op == "<=":
        return value <= threshold
    return False


def escalation_minutes() -> int:
    return get_settings().escalation_min


class MonitoringAgent(CareXHealthAgent):
    key = "MONITORING"
    instructions = (
        "You are the Monitoring & Escalation Agent. You only report on deterministic monitoring results; you never decide "
        "whether a value is dangerous — doctor-approved rules and fixed safety nets do."
    )

    # ── rule registration ────────────────────────────────────────────────────────────────

    @skill
    async def register_rules(self, patient_id: str, plan_id: str, include_defaults: bool) -> list[str]:
        from app.repositories import care_plans

        plan = care_plans.get(plan_id)
        assert plan is not None
        created: list[str] = []
        for item in [i for i in plan.items if i.included and i.category == "RED_FLAG"]:
            d = parse_json(item.details, {})
            metric = str(d.get("metric") or "SYMPTOM").upper()
            kw = d.get("keywords")
            keywords = ",".join(kw) if isinstance(kw, list) else kw if isinstance(kw, str) else None
            monitoring.create_rule(
                patient_id=patient_id,
                care_plan_id=plan_id,
                metric=metric,
                operator="CONTAINS" if metric == "SYMPTOM" else str(d.get("operator") or ">"),
                threshold=float(d["threshold"]) if d.get("threshold") is not None else None,
                keywords=keywords,
                action=str(d.get("action") or "NOTIFY_NURSE"),
                severity=str(d.get("severity") or "HIGH"),
                description=item.title,
                source="DOCTOR_APPROVED_SUGGESTION" if item.source == "AI_SUGGESTED" else "DOCTOR",
            )
            created.append(item.title)
        if include_defaults:
            existing = monitoring.active_rules(patient_id)
            has = {r.metric for r in existing}
            defaults: list[dict[str, Any]] = [
                {"metric": "MISSED_DOSES", "operator": "COUNT_GTE", "threshold": 2, "window_hours": 48, "action": "NOTIFY_NURSE", "severity": "MEDIUM", "description": "2+ missed doses in 48 h → nurse follow-up"},
                {"metric": "MISSED_DOSES", "operator": "COUNT_GTE", "threshold": 4, "window_hours": 72, "action": "NOTIFY_DOCTOR", "severity": "HIGH", "description": "4+ missed doses in 72 h → doctor"},
                {"metric": "MISSED_APPOINTMENT", "operator": "COUNT_GTE", "threshold": 1, "window_hours": 168, "action": "NOTIFY_NURSE", "severity": "MEDIUM", "description": "Missed appointment/session → nurse"},
                {"metric": "LAB_ABNORMAL", "operator": "COUNT_GTE", "threshold": 1, "action": "NOTIFY_DOCTOR", "severity": "HIGH", "description": "Abnormal investigation result → doctor review"},
                {"metric": "SYMPTOM", "operator": "CONTAINS", "keywords": ",".join(EMERGENCY_KEYWORDS), "action": "EMERGENCY", "severity": "CRITICAL", "description": "Emergency symptoms → immediate escalation"},
            ]
            if "SPO2" not in has:
                defaults.append({"metric": "SPO2", "operator": "<", "threshold": 90, "action": "NOTIFY_DOCTOR", "severity": "CRITICAL", "description": "SpO₂ < 90% (safety net)"})
            if "PAIN" not in has:
                defaults.append({"metric": "PAIN", "operator": ">=", "threshold": 8, "action": "NOTIFY_NURSE", "severity": "HIGH", "description": "Pain score ≥ 8/10 (safety net)"})
            for r in defaults:
                monitoring.create_rule(patient_id=patient_id, care_plan_id=plan_id, source="SYSTEM_DEFAULT", **r)
            created.append(f"{len(defaults)} system safety rules")
        await self.audit("Monitoring rules registered", patient_id=patient_id, level="SUCCESS", detail=" · ".join(created))
        return created

    @skill
    async def deactivate_rule(self, patient_id: str, care_plan_id: str, description: str) -> bool:
        return monitoring.deactivate_matching(patient_id, care_plan_id, description) > 0

    # ── alerts ───────────────────────────────────────────────────────────────────────────

    async def _patient(self, patient_id: str) -> dict[str, Any]:
        return (await self.mcp("ehr", "get_patient_records", patient_id=patient_id))["patient"]

    async def _assignee(self, patient: dict[str, Any], level: int) -> str:
        return (patient.get("nurseId") or patient["doctorId"]) if level == 1 else patient["doctorId"]

    async def _link(self, patient_id: str, audience: str) -> str:
        return (await self.mcp("notification", "patient_link", patient_id=patient_id, audience=audience, type="ALERT"))["link"]

    async def create_alert(self, *, patient_id: str, category: str, severity: str, title: str, message: str, action: str, rule_id: str | None = None, dedupe_key: str | None = None) -> Alert:
        t = now()
        if dedupe_key:
            open_alert = monitoring.open_duplicate(patient_id, dedupe_key)
            if open_alert:
                return monitoring.append_history(open_alert.id, f"Repeat trigger: {message}", message=message)
        level = LEVEL_FOR_ACTION.get(action, 1)
        patient = await self._patient(patient_id)
        assigned = await self._assignee(patient, level)
        minutes = get_settings().ladder_minutes(level, severity)
        alert = monitoring.create_alert(
            patient_id=patient_id,
            rule_id=rule_id,
            category=category,
            severity=severity,
            title=title,
            message=message,
            escalation_level=level,
            assigned_to_id=assigned,
            dedupe_key=dedupe_key,
            escalate_after=t + timedelta(minutes=minutes) if level < 3 else None,
            history=dumps([{"at": iso(t), "event": f"Alert created → {LEVEL_LABEL[level]}"}]),
        )
        name = patient["user"]["name"]
        user = people.get_user(assigned)
        link = await self._link(patient_id, "DOCTOR" if user and user.role == "DOCTOR" else "NURSE")
        await self.notify_user(assigned, "ALERT", f"{severity} · {title}", f"{name}: {message}", link)
        if level == 3 and patient.get("nurseId") and patient["nurseId"] != assigned:
            await self.notify_user(patient["nurseId"], "ALERT", f"EMERGENCY · {title}", f"{name}: {message}", await self._link(patient_id, "NURSE"))
        if level == 3:
            await self.notify("PATIENT", patient_id, "ALERT", "Your care team has been alerted", "If you feel unsafe, call emergency services (108 / 112) immediately.")
        await self.audit(f"Alert raised: {title}", patient_id=patient_id, level="CRITICAL" if severity == "CRITICAL" else "WARNING", detail=f"{message} → {LEVEL_LABEL[level]}")
        await self.refresh_risk(patient_id)
        return alert

    async def refresh_risk(self, patient_id: str) -> None:
        from app.services import risk

        risk.refresh(patient_id)

    # ── detectors ────────────────────────────────────────────────────────────────────────

    @skill
    async def evaluate_observation(self, observation_id: str) -> int:
        obs = monitoring.get_observation(observation_id)
        if obs is None:
            raise ValueError("Observation not found")
        rules = monitoring.active_rules(obs.patient_id)
        triggered = 0
        for metric, field in OBS_METRICS.get(obs.type, []):
            value = getattr(obs, field)
            if value is None:
                continue
            label, unit = METRICS[metric]
            for rule in [r for r in rules if r.metric == metric and r.threshold is not None]:
                if not compare(value, rule.operator, rule.threshold):  # type: ignore[arg-type]
                    continue
                triggered += 1
                await self.create_alert(
                    patient_id=obs.patient_id,
                    rule_id=rule.id,
                    category="VITAL",
                    severity=rule.severity,
                    action=rule.action,
                    title=f"{label} {rule.operator} {jsnum(rule.threshold)}{unit}",
                    message=f"Recorded {jsnum(value)}{unit} at {fmt_time(obs.recorded_at)}, {fmt_day(obs.recorded_at)} (rule: {rule.description})",
                    dedupe_key=f"rule:{rule.id}",
                )

        if obs.type == "WEIGHT" and obs.value is not None:
            # Weight change vs the lowest reading in the previous 72 h (fluid-retention rules, e.g. heart failure)
            prior = monitoring.prior_weights(obs.patient_id, obs.id, obs.recorded_at - timedelta(hours=72), obs.recorded_at)
            gain = round((obs.value - min(prior)) * 10) / 10 if prior else None
            for rule in [] if gain is None else [r for r in rules if r.metric == "WEIGHT_GAIN" and r.threshold is not None]:
                if not compare(gain, rule.operator, rule.threshold):  # type: ignore[arg-type]
                    continue
                triggered += 1
                await self.create_alert(
                    patient_id=obs.patient_id,
                    rule_id=rule.id,
                    category="VITAL",
                    severity=rule.severity,
                    action=rule.action,
                    title=f"Weight gain {rule.operator} {jsnum(rule.threshold)} kg in 72 h",
                    message=f"Weight {jsnum(obs.value)} kg — up {jsnum(gain)} kg from the lowest reading in the previous 72 h (rule: {rule.description})",
                    dedupe_key=f"rule:{rule.id}",
                )

        if obs.type in ("SYMPTOM", "NURSE_NOTE") and obs.text:
            text = obs.text.lower()
            for rule in [r for r in rules if r.metric == "SYMPTOM" and r.keywords]:
                hits = [k for k in (x.strip().lower() for x in rule.keywords.split(",")) if k and k in text]  # type: ignore[union-attr]
                if not hits:
                    continue
                triggered += 1
                await self.create_alert(
                    patient_id=obs.patient_id,
                    rule_id=rule.id,
                    category="SYMPTOM",
                    severity=rule.severity,
                    action=rule.action,
                    title=f"Reported symptom: {', '.join(hits)}",
                    message=f'"{obs.text[:180]}" (rule: {rule.description})',
                    dedupe_key=f"rule:{rule.id}",
                )

        if triggered:
            monitoring.flag_observation(obs.id)
        else:
            reading = f": {jsnum(obs.value)}{'/' + jsnum(obs.value2) if obs.value2 else ''}{obs.unit or ''}" if obs.value is not None else ""
            await self.audit("Observation within plan thresholds", patient_id=obs.patient_id, detail=f"{obs.type}{reading}")
        return triggered

    @skill
    async def evaluate_adherence(self, patient_id: str, at: str | None = None) -> bool:
        """Missed once → record. Missed repeatedly → detect pattern → escalate."""
        t = parse_dt(at) or now()
        await self.refresh_risk(patient_id)  # the scheduled adherence pass also keeps every patient's risk score current
        rules = sorted(monitoring.active_rules(patient_id, "MISSED_DOSES"), key=lambda r: -(r.threshold or 0))
        for rule in rules:
            window = rule.window_hours or 48
            missed = tasks.missed_or_skipped(patient_id, t - timedelta(hours=window), t)
            if len(missed) >= (rule.threshold if rule.threshold is not None else 2):
                meds = ", ".join(dict.fromkeys(m.medication for m in missed))
                await self.create_alert(
                    patient_id=patient_id,
                    rule_id=rule.id,
                    category="ADHERENCE",
                    severity=rule.severity,
                    action=rule.action,
                    title="Repeated medication non-adherence",
                    message=f"{len(missed)} doses missed/skipped in the last {window} h ({meds}).",
                    dedupe_key=f"rule:{rule.id}",
                )
                return True
        return False

    @skill
    async def on_missed_appointment(self, appointment_id: str) -> None:
        appt = (await self.mcp("scheduling", "get_appointment", appointment_id=appointment_id))["appointment"]
        rules = monitoring.active_rules(appt["patientId"], "MISSED_APPOINTMENT")
        if not rules:
            return
        rule = rules[0]
        await self.create_alert(
            patient_id=appt["patientId"],
            rule_id=rule.id,
            category="APPOINTMENT",
            severity=rule.severity,
            action=rule.action,
            title=f"Missed: {appt['title'].replace(' (rescheduled)', '')}",
            message=f"Scheduled {fmt(parse_dt(appt['startsAt']))}. Execution agent has rebooked; please check in with the patient.",  # type: ignore[arg-type]
            dedupe_key=f"appt:{appt.get('referralId') or appt['id']}",
        )

    @skill
    async def evaluate_lab_report(self, document_id: str) -> None:
        doc = (await self.mcp("ehr", "get_document", document_id=document_id))["document"]
        data = parse_json(doc.get("data"), {})
        abnormal = [f for f in data.get("flags") or [] if f["flag"] != "NORMAL"]
        test_name = data.get("testName")
        if not abnormal:
            await self.audit(f"{test_name or 'Report'} within reference ranges", patient_id=doc["patientId"], level="SUCCESS")
            return
        critical = any(f["flag"].startswith("CRITICAL") for f in abnormal)
        rules = monitoring.active_rules(doc["patientId"], "LAB_ABNORMAL")
        rule = rules[0] if rules else None
        await self.create_alert(
            patient_id=doc["patientId"],
            rule_id=rule.id if rule else None,
            category="LAB",
            severity="CRITICAL" if critical else (rule.severity if rule else "HIGH"),
            action="EMERGENCY" if critical else (rule.action if rule else "NOTIFY_DOCTOR"),
            title=f"Abnormal {test_name or 'result'}",
            message="; ".join(f"{f['label']} {jsnum(f['value'])} {f['unit']} ({f['flag'].replace('_', ' ', 1).lower()}, ref {f['range']})" for f in abnormal),
            dedupe_key=f"doc:{doc['id']}",
        )

    # ── human actions & escalation ───────────────────────────────────────────────────────

    @skill
    async def acknowledge_alert(self, alert_id: str, user_id: str, user_name: str) -> dict[str, Any]:
        a = monitoring.append_history(alert_id, "Acknowledged", user_name, status="ACKNOWLEDGED", acknowledged_at=now(), acknowledged_by_id=user_id, escalate_after=None)
        await self.audit(f"Alert acknowledged by {user_name}", patient_id=a.patient_id, detail=a.title, agent="HUMAN")
        return a.to_dict()

    @skill
    async def resolve_alert(self, alert_id: str, user_name: str, resolution: str) -> dict[str, Any]:
        a = monitoring.append_history(alert_id, f"Resolved: {resolution}", user_name, status="RESOLVED", resolved_at=now(), resolution=resolution, escalate_after=None)
        await self.audit(f"Alert resolved by {user_name}", patient_id=a.patient_id, level="SUCCESS", detail=f"{a.title} — {resolution}", agent="HUMAN")
        await self.refresh_risk(a.patient_id)
        return a.to_dict()

    @skill
    async def escalate_alert(self, alert_id: str, reason: str, by: str = "Monitoring agent") -> dict[str, Any]:
        a = monitoring.get_alert(alert_id)
        if a is None:
            raise ValueError("Alert not found")
        if a.escalation_level >= 3:
            return a.to_dict()
        level = a.escalation_level + 1
        patient = await self._patient(a.patient_id)
        assigned = await self._assignee(patient, level)
        updated = monitoring.append_history(
            alert_id, f"Escalated to {LEVEL_LABEL[level]}: {reason}", by,
            status="ESCALATED", escalation_level=level, assigned_to_id=assigned, acknowledged_at=None,
            escalate_after=now() + timedelta(minutes=get_settings().ladder_minutes(level, a.severity)) if level < 3 else None,
        )  # fmt: skip
        name = patient["user"]["name"]
        await self.notify_user(assigned, "ALERT", f"ESCALATED · {a.title}", f"{name}: {reason}", await self._link(a.patient_id, "DOCTOR"))
        if level == 3 and patient.get("nurseId"):
            await self.notify_user(patient["nurseId"], "ALERT", f"EMERGENCY ESCALATION · {a.title}", f"{name}: {reason}", await self._link(a.patient_id, "NURSE"))
        await self.audit(f"Alert escalated → {LEVEL_LABEL[level]}", patient_id=a.patient_id, level="CRITICAL", detail=f"{a.title}: {reason}")
        return updated.to_dict()

    @skill
    async def escalation_sweep(self, at: str | None = None) -> int:
        """Any alert not acknowledged within its window is escalated one level."""
        overdue = monitoring.overdue_for_escalation(parse_dt(at) or now())
        for a in overdue:
            minutes = get_settings().ladder_minutes(a.escalation_level, a.severity)
            await self.escalate_alert(a.id, f"Not acknowledged within {minutes} minutes")
        return len(overdue)

    @skill
    async def transfer_alerts(self, patient_id: str, from_user_id: str, to_user_id: str, to_name: str) -> int:
        """Nurse handover: open nurse-level alerts follow the patient with a fresh acknowledgement window."""
        moved = monitoring.reassign_open(patient_id, from_user_id, to_user_id, now() + timedelta(minutes=escalation_minutes()))
        if moved:
            await self.audit(f"{moved} open alert(s) re-routed to {to_name}", patient_id=patient_id, level="WARNING")
        return moved
