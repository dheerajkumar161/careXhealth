"""AGENT 5 — Clinical Intelligence & Handoff (Microsoft Agent Framework agent).

Summarize → Contextualize → Handoff. Every document starts from a deterministic fact sheet built from the
EHR context; the LLM may only add a narrative layer over those facts. Also owns the nurse-handover
workflow (request → doctor decision → reassignment with alert transfer). Port of lib/agents/intelligence.ts
and lib/agents/handover.ts.
"""
from __future__ import annotations

from typing import Any

from app.core import llm
from app.core.util import distance, fmt_date, fmt_date_time, fmt_day, fmt_time, now, parse_dt, parse_json
from app.repositories import people, referrals

from .base import AgentError, CareXHealthAgent, skill
from .monitoring_agent import jsnum

VITAL_LABEL = {"TEMPERATURE": "Temp", "BP": "BP", "HEART_RATE": "HR", "SPO2": "SpO₂", "PAIN": "Pain", "BLOOD_GLUCOSE": "Glucose", "WEIGHT": "Weight"}

HANDOFF_NARRATIVE = "You are a Clinical Intelligence agent writing an SBAR-style 2-3 sentence 'Situation & Assessment' for an incoming nurse. Use ONLY the facts provided. No new diagnoses or treatment recommendations. Plain text, no headings."
SUMMARY_NARRATIVE = "You are a Clinical Intelligence agent. Write a concise 3-4 sentence clinical narrative of this post-discharge patient's recovery trajectory for the treating doctor. Use ONLY the facts provided; highlight trends and items needing decisions. Do not recommend treatments."


def _dt(v: Any):  # noqa: ANN202
    return parse_dt(v) if isinstance(v, str) else v


def _status_text(s: str) -> str:
    return s.lower().replace("_", " ", 1)


def vitals_line(ctx: dict[str, Any]) -> str:
    parts = [
        f"{VITAL_LABEL.get(o['type'], o['type'])}: {jsnum(o['value'])}{'/' + jsnum(o['value2']) if o.get('value2') else ''}{o.get('unit') or ''}{' ⚠' if o.get('flagged') else ''}"
        for o in ctx["latestVitals"].values()
    ]
    return " · ".join(parts) if parts else "No vitals recorded in the last 7 days"


def status_of(ctx: dict[str, Any]) -> str:
    open_alerts = [a for a in ctx["alerts"] if a["status"] != "RESOLVED"]
    if any(a["severity"] == "CRITICAL" for a in open_alerts):
        return "Critical — urgent attention"
    if any(a["severity"] == "HIGH" for a in open_alerts):
        return "Needs attention"
    return "Stable — with open concerns" if open_alerts else "Stable"


def fact_sheet(ctx: dict[str, Any]) -> dict[str, Any]:
    """Deterministic facts, always included; the LLM may only add a narrative over these."""
    t = parse_dt(ctx["now"])
    therapy = []
    for r in ctx["referrals"]:
        done = len([a for a in r["appointments"] if a["status"] == "COMPLETED"])
        missed = len([a for a in r["appointments"] if a["status"] == "MISSED"])
        therapy.append({"r": r, "done": done, "missed": missed, "remaining": max(r["sessions"] - done, 0)})
    latest_lab = ctx["labs"][0] if ctx["labs"] else None
    return {
        "openAlerts": [a for a in ctx["alerts"] if a["status"] != "RESOLVED"],
        "upcoming": [a for a in ctx["appointments"] if _dt(a["startsAt"]) >= t and a["status"] in ("BOOKED", "TENTATIVE")][:4],
        "pendingTasks": [x for x in ctx["tasks"] if x["status"] in ("PENDING", "SCHEDULED", "AWAITING_RESULT", "FAILED")],
        "therapy": therapy,
        "latestLab": latest_lab,
        "labFlags": parse_json(latest_lab.get("data"), {}).get("flags") or [] if latest_lab else [],
        "symptoms": [o for o in ctx["observations"] if o["type"] == "SYMPTOM"][:3],
        "nurseNotes": [o for o in ctx["observations"] if o["type"] == "NURSE_NOTE"][:2],
        "meds": [i for i in ctx["items"] if i["category"] == "MEDICATION" and i["action"] != "DISCONTINUE"],
    }


def action_required(ctx: dict[str, Any], f: dict[str, Any]) -> list[str]:
    actions = [f"{'Follow up' if a['status'] == 'ACKNOWLEDGED' else 'Acknowledge'}: {a['title']}" for a in f["openAlerts"]]
    if f["latestLab"] and f["latestLab"].get("reviewStatus") == "PENDING_REVIEW":
        actions.append(f"{f['latestLab']['title']} awaiting doctor review")
    actions += [f"Manual coordination: {x['title']}" for x in f["pendingTasks"] if x["status"] == "FAILED"]
    if ctx["adherence"] is not None and ctx["adherence"] < 80:
        actions.append("Medication adherence counselling")
    return actions or ["Routine monitoring — no action required"]


class IntelligenceAgent(CareXHealthAgent):
    key = "INTELLIGENCE"
    instructions = SUMMARY_NARRATIVE

    async def context(self, patient_id: str) -> dict[str, Any]:
        return await self.mcp("ehr", "get_patient_context", patient_id=patient_id)

    # ── nurse handoff ────────────────────────────────────────────────────────────────────

    @skill
    async def nurse_handoff(self, patient_id: str, author_id: str) -> dict[str, Any]:
        ctx = await self.context(patient_id)
        f = fact_sheet(ctx)
        p = ctx["patient"]
        t = parse_dt(ctx["now"])
        concerns = [f"{a['title']} ({a['severity'].lower()}, {a['status'].lower()})" for a in f["openAlerts"]]
        abnormal = [x for x in f["labFlags"] if x["flag"] != "NORMAL"]
        lab = f["latestLab"]
        lab_line = "None"
        if lab:
            reviewed = "reviewed" if lab.get("reviewStatus") == "REVIEWED" else "pending doctor review"
            flagged = ", ".join(f"{x['label']} {jsnum(x['value'])}" for x in abnormal)
            lab_line = f"{lab['title']} — {reviewed}" + (f" (abnormal: {flagged})" if abnormal else "")
        active = "; ".join(f"{a['severity']} — {a['title']}" for a in f["openAlerts"]) or "None"
        pending = [f"{x['remaining']} {x['r']['referralType'].lower()} session(s){', ' + str(x['missed']) + ' missed' if x['missed'] else ''}" for x in f["therapy"] if x["remaining"] > 0]
        pending += [f"{x['title']} ({_status_text(x['status'])})" for x in f["pendingTasks"] if x["type"] != "REFERRAL"]
        adherence = "No doses due yet" if ctx["adherence"] is None else f"{ctx['adherence']}%"
        meds = f" — {', '.join(m['title'].split(' —')[0] for m in f['meds'])}" if f["meds"] else ""
        symptoms = "; ".join(f'"{(s.get("text") or "")[:80]}" ({distance(_dt(s["recordedAt"]))} ago)' for s in f["symptoms"]) or "None reported"
        upcoming = "; ".join(f"{a['title']} — {_dt(a['startsAt']).strftime('%a')} {fmt_day(_dt(a['startsAt']))} {fmt_time(_dt(a['startsAt']))}" for a in f["upcoming"]) or "Nothing scheduled"
        sections = [
            f"# Nurse Handoff — {p['user']['name']}",
            f"_{t.strftime('%a')} {fmt_date_time(t)} · MRN {p['mrn']} · {p['diagnosis']}{' (' + p['procedure'] + ')' if p.get('procedure') else ''}_",
            "",
            f"**Current status:** {status_of(ctx)}",
            "",
            f"**Active concern:** {'; '.join(concerns) if concerns else 'None'}",
            "",
            f"**Latest vitals:** {vitals_line(ctx)}",
            "",
            f"**Medication adherence (7 d):** {adherence}{meds}",
            "",
            f"**Recent report:** {lab_line}",
            "",
            f"**Recent symptoms:** {symptoms}",
            "",
            f"**Upcoming:** {upcoming}",
            "",
            f"**Pending:** {'; '.join(pending) or 'None'}",
            "",
            f"**Active alert:** {active}",
            "",
            "**Action required:**",
            *[f"- {a}" for a in action_required(ctx, f)],
        ]
        content = "\n".join(sections)
        engine = "rules"
        narrative = await llm.run_text(self.llm_agent("handoff narrative", HANDOFF_NARRATIVE), content)
        if narrative:
            content = content.replace("**Current status:**", f"> {' '.join(narrative.split())}\n\n**Current status:**", 1)
            engine = llm.last_engine()
        doc = (
            await self.mcp(
                "ehr", "store_document", patient_id=patient_id, type="NURSE_HANDOFF", title=f"Nurse handoff — {fmt_day(t)}, {fmt_time(t)}", content=content,
                created_by_id=author_id, engine=engine, data={"status": status_of(ctx), "facts": {"openAlerts": len(f["openAlerts"]), "upcoming": len(f["upcoming"]), "adherence": ctx["adherence"]}},
            )
        )["document"]  # fmt: skip
        await self.audit("Nurse handoff summary generated", patient_id=patient_id, level="SUCCESS", detail=f"{len(f['openAlerts'])} active alert(s), {len(f['upcoming'])} upcoming item(s) ({engine})")
        return doc

    # ── recovery summary ─────────────────────────────────────────────────────────────────

    @skill
    async def recovery_summary(self, patient_id: str, author_id: str) -> dict[str, Any]:
        ctx = await self.context(patient_id)
        f = fact_sheet(ctx)
        p = ctx["patient"]
        t = parse_dt(ctx["now"])
        days = max(int((t - _dt(p["dischargeDate"])).total_seconds() // 86400), 0) if p.get("dischargeDate") else 0

        def lab_line(lab: dict[str, Any]) -> str:
            ab = [x for x in parse_json(lab.get("data"), {}).get("flags") or [] if x["flag"] != "NORMAL"]
            values = ", ".join(f"{x['label']} {jsnum(x['value'])} {x['unit']} [{x['flag']}]" for x in ab) if ab else "within reference ranges"
            return f"- **{lab['title']}** ({fmt_day(_dt(lab['createdAt']))}) — {values} · {'reviewed' if lab.get('reviewStatus') == 'REVIEWED' else 'pending review'}"

        def ref_line(x: dict[str, Any]) -> str:
            r = x["r"]
            who = (r.get("provider") or {}).get("name") or "provider pending"
            return f"- **{r['referralType']}** with {who}: {x['done']}/{r['sessions']} completed{', ' + str(x['missed']) + ' missed' if x['missed'] else ''} · {_status_text(r['status'])}"

        lines = [
            f"# Patient Recovery Summary — {p['user']['name']}",
            f"_Generated {fmt_date_time(t)} · Day {days} post-discharge_",
            "",
            "| | |",
            "|---|---|",
            f"| **Diagnosis** | {p['diagnosis']}{' — ' + p['procedure'] if p.get('procedure') else ''} |",
            f"| **Current status** | {status_of(ctx)} |",
            f"| **Medication adherence** | {'—' if ctx['adherence'] is None else str(ctx['adherence']) + '% (7 days)'} |",
            f"| **Latest vitals** | {vitals_line(ctx)} |",
            "",
            "## Recent symptoms",
            *([f'- {fmt_day(_dt(s["recordedAt"]))} {fmt_time(_dt(s["recordedAt"]))}: "{s.get("text")}"{" ⚠" if s.get("flagged") else ""}' for s in f["symptoms"]] or ["- None reported"]),
            "",
            "## Investigation results",
            *([lab_line(lab) for lab in ctx["labs"]] or ["- None yet"]),
            "",
            "## Appointments",
            *(
                [f"- {a['title']} — {fmt_day(_dt(a['startsAt']))} {fmt_time(_dt(a['startsAt']))} · {a['status'].lower()}" for a in ctx["appointments"] if a["kind"] != "THERAPY"]
                if ctx["appointments"]
                else ["- None"]
            ),
            "",
            "## Referrals & rehabilitation progress",
            *([ref_line(x) for x in f["therapy"]] or ["- None"]),
            "",
            "## Active alerts",
            *([f"- **{a['severity']}** {a['title']} — {a['message']}" for a in f["openAlerts"]] or ["- None"]),
            "",
            "## Pending actions",
            *[f"- {a}" for a in action_required(ctx, f)],
        ]
        content = "\n".join(lines)
        engine = "rules"
        narrative = await llm.run_text(self.llm_agent("recovery narrative", SUMMARY_NARRATIVE), content)
        if narrative:
            content = content.replace("| | |", f"## Clinical narrative\n\n{narrative}\n\n| | |", 1)
            engine = llm.last_engine()
        doc = (
            await self.mcp("ehr", "store_document", patient_id=patient_id, type="CLINICAL_SUMMARY", title=f"Recovery summary — {fmt_date(t)}", content=content, created_by_id=author_id, engine=engine)
        )["document"]
        await self.audit("Patient recovery summary generated", patient_id=patient_id, level="SUCCESS", detail=engine)
        return doc

    # ── referral clinical summary ────────────────────────────────────────────────────────

    @skill
    async def referral_clinical_summary(self, referral_id: str) -> str:
        ref = referrals.get(referral_id)
        assert ref is not None
        ctx = await self.context(ref.patient_id)
        f = fact_sheet(ctx)
        p = ctx["patient"]
        same = next((x for x in f["therapy"] if x["r"]["id"] != ref.id and x["r"]["referralType"] == ref.referral_type), None)
        lab = f["latestLab"]
        abnormal = [x["label"] for x in f["labFlags"] if x["flag"] != "NORMAL"]
        parts = [
            f"{p.get('procedure') or p['diagnosis']} patient{', discharged ' + fmt_date(_dt(p['dischargeDate'])) if p.get('dischargeDate') else ''}.",
            f"Has completed {same['done']} of {same['r']['sessions']} prior {ref.referral_type.lower()} sessions." if same else "",
            f"Current status: {status_of(ctx).lower()}.",
            f"Latest vitals: {vitals_line(ctx)}.",
            "Recent patient-reported symptoms: " + "; ".join(f'"{(s.get("text") or "")[:60]}"' for s in f["symptoms"]) + "." if f["symptoms"] else "No recent symptom reports.",
            (f"Latest investigation: {lab['title']}" + (f" with abnormal {', '.join(abnormal)}" if abnormal else " within reference ranges") + ".") if lab else "",
            f"Current treatment: {'; '.join(m['title'] for m in f['meds'])}." if f["meds"] else "",
            f"Medication adherence {ctx['adherence']}%." if ctx["adherence"] is not None else "",
        ]
        base = " ".join(x for x in parts if x)
        writer = self.llm_agent(
            "referral summary",
            f"You are a Clinical Intelligence agent writing the clinical summary section of a {ref.referral_type} referral for the receiving clinician. "
            f"Rewrite the facts into one concise professional paragraph (max 120 words) emphasising what matters for {ref.referral_type}. Use ONLY the facts provided.",
        )
        narrative = await llm.run_text(writer, base)
        await self.audit(f"Clinical context prepared for {ref.referral_type} referral", patient_id=ref.patient_id, detail=llm.last_engine() if narrative else "rules")
        return narrative or base

    # ── nurse handover workflow ──────────────────────────────────────────────────────────

    def _nurse(self, user_id: str) -> Any:
        u = people.get_user(user_id)
        if not u or u.role != "NURSE":
            raise AgentError(400, "Choose a valid nurse")
        return u

    @skill
    async def request_release(self, patient_id: str, nurse_id: str, reason: str, suggested_nurse_id: str | None = None) -> dict[str, Any]:
        """Nurse asks to be released; the handoff summary travels with the request. The nurse stays responsible until approval."""
        p = (await self.mcp("ehr", "get_patient_records", patient_id=patient_id))["patient"]
        if p.get("nurseId") != nurse_id:
            raise AgentError(403, "Only the assigned nurse can request release")
        if people.pending_release(patient_id):
            raise AgentError(409, "A release request for this patient is already awaiting the doctor")
        if suggested_nurse_id:
            if suggested_nurse_id == nurse_id:
                raise AgentError(400, "Suggest a different nurse")
            self._nurse(suggested_nurse_id)
        nurse = people.get_user(nurse_id)
        handoff = await self.nurse_handoff(patient_id, nurse_id)
        req = people.create_release(patient_id=patient_id, from_nurse_id=nurse_id, suggested_nurse_id=suggested_nurse_id or None, reason=reason, handoff_document_id=handoff["id"])
        await self.audit(f"{nurse.name} requested release from this patient", patient_id=patient_id, detail=reason, agent="HUMAN")  # type: ignore[union-attr]
        await self.notify("DOCTOR", patient_id, "SYSTEM", f"Nurse release request — {p['user']['name']}", f"{nurse.name}: “{reason}”. Review the handoff and assign the next nurse.")  # type: ignore[union-attr]
        return req.to_dict()

    @skill
    async def cancel_release(self, request_id: str, nurse_id: str) -> None:
        req = people.get_release(request_id)
        if not req or req.from_nurse_id != nurse_id:
            raise AgentError(404, "Request not found")
        if req.status not in ("PENDING", "AWAITING_NURSE"):
            raise AgentError(409, f"Request is already {req.status.lower()}")
        people.update_release(request_id, status="CANCELLED", decided_at=now())
        await self.audit("Nurse withdrew release request", patient_id=req.patient_id, agent="HUMAN")

    async def _transfer(self, patient_id: str, from_nurse_id: str | None, to_nurse_id: str, handoff_document_id: str | None, doctor_name: str) -> None:
        """Moves responsibility for the patient (and open nurse-level alerts) to another nurse."""
        to = self._nurse(to_nurse_id)
        p = (await self.mcp("ehr", "update_patient_record", patient_id=patient_id, nurse_id=to_nurse_id))["patient"]
        name = p["user"]["name"]
        moved = await self.ask("MONITORING", "transfer_alerts", patient_id=patient_id, from_user_id=from_nurse_id, to_user_id=to_nurse_id, to_name=to.name) if from_nurse_id else 0
        link = f"/nurse/patients/{patient_id}?tab=documents&doc={handoff_document_id}" if handoff_document_id else f"/nurse/patients/{patient_id}"
        alert_note = f" {moved} open alert(s) need your attention." if moved else ""
        await self.notify_user(to_nurse_id, "SYSTEM", f"New patient assigned: {name}", f"{doctor_name} assigned you as {name}'s nurse.{alert_note} The handoff summary is in the patient's Documents.", link)
        if from_nurse_id:
            await self.notify_user(from_nurse_id, "SYSTEM", f"Released from {name}", f"{doctor_name} approved your release; {to.name} is now responsible.", "/nurse")
        await self.audit(f"Nurse assignment changed → {to.name}", patient_id=patient_id, level="SUCCESS", detail=f"By {doctor_name}{' · handoff attached' if handoff_document_id else ''}", agent="HUMAN")

    @skill
    async def decide_release(self, request_id: str, doctor_id: str, decision: str, to_nurse_id: str | None = None, note: str | None = None) -> None:
        req = people.get_release(request_id)
        p = (await self.mcp("ehr", "get_patient_records", patient_id=req.patient_id))["patient"] if req else None
        if not req or not p or p["doctorId"] != doctor_id:
            raise AgentError(404, "Request not found")
        if req.status != "PENDING":
            raise AgentError(409, f"Request is already {req.status.lower()}")
        if p.get("nurseId") != req.from_nurse_id:
            raise AgentError(409, "The patient's nurse has changed since this request was made")
        doctor = people.get_user(doctor_id)
        assert doctor is not None
        if decision == "REJECT":
            if not (note or "").strip():
                raise AgentError(400, "Give the nurse a reason for keeping them on this patient")
            people.update_release(request_id, status="REJECTED", decision_note=note.strip(), decided_by_id=doctor_id, decided_at=now())  # type: ignore[union-attr]
            await self.notify_user(req.from_nurse_id, "SYSTEM", "Release request not approved", f"{doctor.name}: “{note.strip()}”", f"/nurse/patients/{req.patient_id}")  # type: ignore[union-attr]
            await self.audit(f"{doctor.name} declined the nurse release request", patient_id=req.patient_id, detail=note.strip(), agent="HUMAN")  # type: ignore[union-attr]
            return
        if not to_nurse_id:
            raise AgentError(400, "Choose the nurse who will take over")
        if to_nurse_id == req.from_nurse_id:
            raise AgentError(400, "Choose a different nurse")
        to = self._nurse(to_nurse_id)
        people.update_release(request_id, status="AWAITING_NURSE", to_nurse_id=to_nurse_id, decision_note=(note or "").strip() or None, decided_by_id=doctor_id, decided_at=now())
        name = p["user"]["name"]
        await self.notify_user(to_nurse_id, "SYSTEM", f"Handoff awaiting your acceptance: {name}", f"{doctor.name} approved the release from this patient and chose you to take over. Review the handoff and accept or decline.", "/nurse")  # type: ignore[union-attr]
        await self.notify_user(req.from_nurse_id, "SYSTEM", f"Release approved — waiting for {to.name}", f"{doctor.name} approved your release from {name}. You stay responsible until {to.name} accepts.", f"/nurse/patients/{req.patient_id}")
        await self.audit(f"{doctor.name} approved the release; waiting for {to.name} to accept", patient_id=req.patient_id, detail=(note or "").strip() or None, agent="HUMAN")

    @skill
    async def respond_handoff(self, request_id: str, nurse_id: str, decision: str, note: str | None = None) -> None:
        """Incoming nurse accepts (responsibility transfers) or declines (back to the doctor to pick someone else)."""
        req = people.get_release(request_id)
        if not req or req.to_nurse_id != nurse_id:
            raise AgentError(404, "Handoff not found")
        if req.status != "AWAITING_NURSE":
            raise AgentError(409, f"Handoff is already {req.status.lower()}")
        nurse = people.get_user(nurse_id)
        assert nurse is not None
        p = (await self.mcp("ehr", "get_patient_records", patient_id=req.patient_id))["patient"]
        if p.get("nurseId") != req.from_nurse_id:
            raise AgentError(409, "The patient's nurse has changed since this handoff was made")
        doctor = people.get_user(req.decided_by_id) if req.decided_by_id else None
        if decision == "DECLINE":
            if not (note or "").strip():
                raise AgentError(400, "Give the doctor a reason for declining")
            people.update_release(request_id, status="PENDING", to_nurse_id=None, suggested_nurse_id=None, decision_note=f"{nurse.name} declined: {note.strip()}", decided_by_id=None, decided_at=None)  # type: ignore[union-attr]
            if doctor:
                await self.notify_user(doctor.id, "SYSTEM", f"{nurse.name} declined the handoff — {p['user']['name']}", f"“{note.strip()}”. Choose another nurse.", f"/doctor/patients/{req.patient_id}")  # type: ignore[union-attr]
            await self.audit(f"{nurse.name} declined the nurse handoff", patient_id=req.patient_id, detail=note.strip(), agent="HUMAN")  # type: ignore[union-attr]
            return
        await self._transfer(req.patient_id, req.from_nurse_id, nurse_id, req.handoff_document_id, doctor.name if doctor else "The doctor")
        people.update_release(request_id, status="APPROVED", decided_at=now())
        if doctor:
            await self.notify_user(doctor.id, "SYSTEM", f"{nurse.name} accepted the handoff", f"{nurse.name} is now responsible for {p['user']['name']}.", f"/doctor/patients/{req.patient_id}")

    @skill
    async def assign_nurse(self, patient_id: str, doctor_id: str, to_nurse_id: str, reason: str) -> None:
        """Doctor assigns a nurse to a patient who has none. Removing an assigned nurse always starts with that nurse's release request."""
        p = (await self.mcp("ehr", "get_patient_records", patient_id=patient_id))["patient"]
        if not p or p["doctorId"] != doctor_id:
            raise AgentError(404, "Patient not found")
        if p.get("nurseId"):
            raise AgentError(409, "This patient already has a nurse. The nurse must request release; you can then approve it and assign the next nurse.")
        doctor = people.get_user(doctor_id)
        handoff = await self.nurse_handoff(patient_id, doctor_id)
        people.cancel_pending_releases(patient_id, "Superseded by doctor reassignment", now())
        await self._transfer(patient_id, None, to_nurse_id, handoff["id"], doctor.name)  # type: ignore[union-attr]
        people.create_release(patient_id=patient_id, from_nurse_id="", to_nurse_id=to_nurse_id, reason=reason, kind="REASSIGN", status="APPROVED", handoff_document_id=handoff["id"], decided_by_id=doctor_id, decided_at=now())
