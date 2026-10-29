"""AGENT 4 — Communication & Clinical Documentation (Microsoft Agent Framework agent).

Communicate → Generate Documents → Package → Route. Turns APPROVED / available information into the right
communication or document (Markdown content; Jinja2 templates handle PDF presentation). Never makes
clinical decisions. Port of lib/agents/communication.ts.
"""
from __future__ import annotations

import json
import re
from typing import Any

from app.core import llm
from app.core.constants import CATEGORY_LABEL
from app.core.util import age_years, fmt_date, fmt_date_time, fmt_day, fmt_time, is_today, now, parse_dt, parse_json, when
from app.repositories import monitoring, people, referrals, tasks
from app.services import translation

from .base import CareXHealthAgent, skill
from .monitoring_agent import jsnum

SYMPTOM_HINT = r"(pain|fever|temperature|bleed|swell|dizz|vomit|nause|breath|chest|rash|discharge|pus|hurt|ache|cough|faint|tired|weak|numb|red(ness)?|itch|sore|cramp|diarrh|constipat|unwell|sick)"

PLAN_REWRITE = (
    "You are the Communication agent of a hospital. Rewrite the given discharge plan in warm, simple language (reading age ~12). "
    "Keep EVERY fact, number, time, medicine name and warning exactly as given. Do not add medical advice. Keep the markdown headings, tables and lists."
)


def times_label(n: int) -> str:
    return "Once a day" if n == 1 else "Twice a day (morning & night)" if n == 2 else "Three times a day" if n == 3 else f"{n} times a day"


def _dt(v: Any):  # noqa: ANN202
    return parse_dt(v) if isinstance(v, str) else v


def extract_vitals(text: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if m := re.search(r"(?:temp(?:erature)?|fever)\D{0,15}(\d{2,3}(?:\.\d)?)", text, re.I):
        out.append({"type": "TEMPERATURE", "value": float(m.group(1)), "unit": "°F"})
    if m := re.search(r"(?:bp|blood pressure)\D{0,15}(\d{2,3})\s*/\s*(\d{2,3})", text, re.I):
        out.append({"type": "BP", "value": float(m.group(1)), "value2": float(m.group(2)), "unit": "mmHg"})
    if m := re.search(r"pain\D{0,20}(\d{1,2})\s*(?:/|out of)\s*10", text, re.I):
        out.append({"type": "PAIN", "value": float(m.group(1)), "unit": "/10"})
    if m := re.search(r"(?:spo2|oxygen|saturation)\D{0,15}(\d{2,3})", text, re.I):
        out.append({"type": "SPO2", "value": float(m.group(1)), "unit": "%"})
    if m := re.search(r"(?:sugar|glucose)\D{0,15}(\d{2,3})", text, re.I):
        out.append({"type": "BLOOD_GLUCOSE", "value": float(m.group(1)), "unit": "mg/dL"})
    return out


def rule_answer(q: str, ctx: dict[str, Any]) -> str:
    """Deterministic patient answers, grounded only in the approved plan (fallback when the LLM is unavailable)."""
    s = q.lower()
    t = parse_dt(ctx["now"])
    today = [d for d in ctx["doses"] if is_today(_dt(d["scheduledAt"])) and d["status"] != "CANCELLED"]
    upcoming = [a for a in ctx["appointments"] if _dt(a["startsAt"]) >= t and a["status"] in ("BOOKED", "TENTATIVE")]

    def items(c: str) -> list[dict[str, Any]]:
        return [i for i in ctx["items"] if i["category"] == c and i["action"] != "DISCONTINUE"]

    def text_of(i: dict[str, Any]) -> str:
        return str(i["detailsObj"].get("text") or i["title"])

    if re.search(r"medic|medicine|tablet|pill|dose|drug", s):
        if not today:
            return "You have no medicine doses scheduled for today."
        lines = "\n".join(f"- **{fmt_time(_dt(d['scheduledAt']))}** — {d['medication']} {d.get('dose') or ''} · _{d['status'].lower()}_" for d in today)
        return f"Here are today's medicines:\n\n{lines}\n\nTap **Taken** on your dashboard after each dose."
    if re.search(r"appoint|visit|follow|session|physio|therap|when.*(see|next)|schedule|booking", s):
        if not upcoming:
            return "You have no upcoming appointments right now."
        return "Your upcoming appointments:\n\n" + "\n".join(f"- **{a['title']}** — {when(_dt(a['startsAt']))} at {a['provider']['organization']}" for a in upcoming[:6])
    if re.search(r"test|cbc|blood|report|lab|result", s):
        tests = [x for x in ctx["tasks"] if x["type"] == "INVESTIGATION"]
        reports = [f"- {r['title']} — {fmt_day(_dt(r['createdAt']))} ({'reviewed by your doctor' if r.get('reviewStatus') == 'REVIEWED' else 'awaiting doctor review'})" for r in ctx["labs"]]
        listing = (
            "Your tests:\n\n" + "\n".join(f"- **{x['title']}** — {when(_dt(x['dueDate'])) if x.get('dueDate') else 'date pending'} · {x['status'].lower().replace('_', ' ', 1)}" for x in tests)
            if tests
            else "No tests are scheduled."
        )
        report_block = "\n\nReports:\n" + "\n".join(reports) if reports else ""
        return f"{listing}{report_block}\n\nYour doctor will explain what any result means for you."
    if re.search(r"eat|food|diet|drink", s):
        return "Food & drink guidance from your plan:\n\n" + "\n".join(f"- {text_of(i)}" for i in items("DIET")) if items("DIET") else "Your plan has no specific diet instructions — eat balanced meals and stay hydrated."
    if re.search(r"exercise|walk|activity|move|stairs", s):
        return "Activity guidance:\n\n" + "\n".join(f"- {text_of(i)}" for i in items("EXERCISE")) if items("EXERCISE") else "Your plan has no specific exercise instructions yet."
    if re.search(r"avoid|can i|allowed|should not|restrict|drive|bath|shower", s):
        if items("RESTRICTION"):
            return "Things your plan asks you to avoid:\n\n" + "\n".join(f"- {text_of(i)}" for i in items("RESTRICTION")) + "\n\nFor anything not listed, please ask your nurse."
        return "There are no restrictions listed in your plan. Please check with your nurse if unsure."
    if re.search(r"warning|danger|emergency|when.*(call|help)|red flag", s):
        return "Contact your care team if:\n\n" + "\n".join(f"- {i['title']}" for i in items("RED_FLAG")) + "\n\nIn an emergency call **108 / 112**."
    return "I can help with your medicines, appointments, tests, diet, activity and warning signs in your approved care plan. You can also tell me how you're feeling and I'll share it with your care team."


class CommunicationAgent(CareXHealthAgent):
    key = "COMMUNICATION"
    instructions = PLAN_REWRITE

    async def _patient(self, patient_id: str) -> dict[str, Any]:
        return (await self.mcp("ehr", "get_patient_records", patient_id=patient_id))["patient"]

    # ── patient instructions document ────────────────────────────────────────────────────

    @skill
    async def generate_patient_instructions(self, patient_id: str) -> dict[str, Any]:
        p = await self._patient(patient_id)
        items = (await self.mcp("ehr", "get_active_plan_items", patient_id=patient_id))["items"]
        appts = (await self.mcp("scheduling", "list_appointments", patient_id=patient_id, statuses=["BOOKED", "TENTATIVE"], upcoming_only=True, limit=8))["appointments"]

        def by(c: str) -> list[dict[str, Any]]:
            return [i for i in items if i["category"] == c and i["action"] != "DISCONTINUE"]

        lines = [
            "# Your Recovery Plan",
            "",
            f"Hello {p['user']['name'].split(' ')[0]}, this plan was prepared and approved by **{p['doctor']['name']}** for your recovery after **{p.get('procedure') or p['diagnosis']}**. "
            "Keep this handy — your dashboard always shows the latest version.",
            "",
        ]
        if by("MEDICATION"):
            lines += ["## 💊 Your medicines", "", "| Medicine | How often | For how long | Notes |", "|---|---|---|---|"]
            for m in by("MEDICATION"):
                d = m["detailsObj"]
                try:
                    tpd = int(float(d.get("timesPerDay"))) or 1
                except (TypeError, ValueError):
                    tpd = 1
                lines.append(f"| {d.get('name', m['title'])} {d.get('dose', '')} | {times_label(tpd)} | {d.get('durationDays', '—')} days | {d.get('instructions') or '—'} |")
            lines += ["", "You will get a reminder before each dose. Please tap **Taken** after you take it.", ""]
        if appts:
            lines += ["## 📅 Upcoming appointments", ""]
            lines += [f"- **{a['title']}** — {when(_dt(a['startsAt']))} at {a['provider']['organization']}{' _(awaiting confirmation)_' if a['status'] == 'TENTATIVE' else ''}" for a in appts]
            lines.append("")
        if by("REFERRAL"):
            lines += ["## 🤝 Extra care arranged for you", ""]
            for r in by("REFERRAL"):
                d = r["detailsObj"]
                try:
                    multi = float(d.get("sessions")) > 1
                except (TypeError, ValueError):
                    multi = False
                extra = f" ({d.get('sessions')} sessions, {d.get('frequencyPerWeek')}× per week)" if multi else ""
                lines.append(f"- **{d.get('referralType', r['title'])}** — {d.get('reason', '')}{extra}")
            lines.append("")
        for c, heading in (("DIET", "🥗 Food & drink"), ("EXERCISE", "🚶 Activity & exercise"), ("RESTRICTION", "⛔ Things to avoid"), ("CARE_INSTRUCTION", "🏠 Caring for yourself at home")):
            if by(c):
                lines += [f"## {heading}", "", *[f"- {i['detailsObj'].get('text') or i['title']}" for i in by(c)], ""]
        if by("MONITORING"):
            lines += ["## 📈 Readings to record", "", *[f"- {m['title']}" for m in by("MONITORING")], ""]
        lines += ["## 🚨 When to get help", "", *[f"- {f['title']}" for f in by("RED_FLAG")], "- If you feel very unwell, have chest pain or trouble breathing, **call 108 / 112 immediately**.", ""]
        content = "\n".join(lines)
        engine = "rules"

        rewritten = await llm.run_text(self.llm, content)
        if rewritten and len(rewritten) > len(content) * 0.6:
            content = re.sub(r"^```(?:markdown)?|```$", "", rewritten).strip()
            engine = llm.last_engine()

        # Multilingual: the plan is written in the patient's preferred language (chosen in Settings); the English
        # original is kept in `data` so clinicians can compare and the plan can be re-rendered in another language.
        lang = await translation.patient_language(patient_id)
        title = "My Recovery Plan"
        data: dict[str, Any] | None = None
        if lang != "en":
            (translated, t_title), ok = await translation.translate_many([content, title], lang)
            data = {"language": lang, "translated": ok, "original": content}
            if ok:
                content, title, engine = translated, t_title, f"{engine}+translated"
        doc = (
            await self.mcp(
                "ehr", "store_document", patient_id=patient_id, type="PATIENT_INSTRUCTIONS", title=title, content=content, data=data,
                visible_to_patient=True, engine=engine, replace_existing_of_type=True,
            )
        )["document"]  # fmt: skip
        await self.audit("Patient-friendly recovery plan generated", patient_id=patient_id, level="SUCCESS", detail=f"Shared with patient ({engine})")
        return doc

    async def _language_rule(self, patient_id: str) -> str:
        lang = await translation.patient_language(patient_id)
        if lang == "en":
            return ""
        return f"Reply entirely in {translation.language_name(lang)} (the patient's chosen language); keep medicine names, numbers and times unchanged.\n"

    # ── patient assistant ────────────────────────────────────────────────────────────────

    @skill
    async def patient_chat(self, patient_id: str, message: str) -> dict[str, Any]:
        people.add_chat(patient_id, "user", message)
        escalation_note = ""
        # Patient messages are a Monitoring input: forward reported symptoms / readings.
        vitals = extract_vitals(message)
        alerts = 0
        for v in vitals:
            obs = monitoring.create_observation(patient_id=patient_id, type=v["type"], value=v["value"], value2=v.get("value2"), unit=v["unit"], text=message, source="PATIENT")
            alerts += await self.ask("MONITORING", "evaluate_observation", observation_id=obs.id)
        symptomatic = bool(re.search(SYMPTOM_HINT, message, re.I))
        if symptomatic:
            obs = monitoring.create_observation(patient_id=patient_id, type="SYMPTOM", text=message, source="PATIENT")
            alerts += await self.ask("MONITORING", "evaluate_observation", observation_id=obs.id)
            await self.audit("Patient-reported problem forwarded to Monitoring", patient_id=patient_id, detail=message[:140])
        if alerts:
            escalation_note = "\n\n**I've alerted your care team about this** — someone will contact you shortly. If it feels like an emergency, call **108 / 112** now."
        elif vitals or symptomatic:
            escalation_note = "\n\nI've recorded this in your chart so your nurse can see it."

        ctx = await self.mcp("ehr", "get_patient_context", patient_id=patient_id)
        p = ctx["patient"]
        t = parse_dt(ctx["now"])
        grounded = {
            "patient": {"name": p["user"]["name"], "diagnosis": p["diagnosis"], "procedure": p.get("procedure")},
            "doctor": p["doctor"]["name"],
            "nurse": (p.get("nurse") or {}).get("name"),
            "approvedPlan": [{"category": CATEGORY_LABEL.get(i["category"], i["category"]), "title": i["title"], "details": i["detailsObj"]} for i in ctx["items"]],
            "todaysDoses": [{"time": fmt_time(_dt(d["scheduledAt"])), "medication": d["medication"], "dose": d.get("dose"), "status": d["status"]} for d in ctx["doses"] if is_today(_dt(d["scheduledAt"]))],
            "upcomingAppointments": [
                {"title": a["title"], "when": when(_dt(a["startsAt"])), "where": a["provider"]["organization"], "status": a["status"]}
                for a in ctx["appointments"]
                if _dt(a["startsAt"]) >= t and a["status"] != "MISSED"
            ][:8],
            "reports": [{"title": r["title"], "date": fmt_day(_dt(r["createdAt"])), "reviewed": r.get("reviewStatus") == "REVIEWED"} for r in ctx["labs"]],
        }
        history = list(reversed(people.recent_chat(patient_id, 8)))
        system = (
            f"You are the patient-facing assistant (Communication agent) of {p['doctor']['name']}'s hospital.\n"
            "Answer ONLY from the approved care plan data below, in short, warm, simple language (markdown allowed).\n"
            f"{await self._language_rule(patient_id)}"
            "Never diagnose, never change or suggest medicines/doses, never interpret lab values — say the doctor will review them.\n"
            "If the patient describes worrying symptoms, tell them their care team has been informed and to call 108/112 in an emergency.\n"
            f"Today is {now().strftime('%A')} {now().day} {now().strftime('%B %Y')}, {fmt_time(now())}.\n"
            f"DATA: {json.dumps(grounded, ensure_ascii=False)}"
        )
        transcript = "\n".join(f"{'Patient' if h.role == 'user' else 'Assistant'}: {h.content}" for h in history) + "\nAssistant:"
        answer = await llm.run_text(llm.build_llm_agent(f"{self.name} · patient assistant", system), transcript)
        lang = await translation.patient_language(patient_id)
        body = answer or rule_answer(message, ctx)
        if lang != "en" and not answer:  # model unreachable → translate the deterministic answer if any model can
            body = (await translation.localize(body, lang))[0]
        if lang != "en" and escalation_note:
            escalation_note = "\n\n" + (await translation.localize(escalation_note.strip(), lang))[0]
        reply = people.add_chat(patient_id, "assistant", body + escalation_note)
        return reply.to_dict()

    # ── lab reports (Phase 6) ────────────────────────────────────────────────────────────

    @skill
    async def process_lab_report(self, appointment_id: str, uploaded_by_id: str, values: dict[str, float], findings: str | None = None) -> dict[str, Any]:
        appt = (await self.mcp("scheduling", "get_appointment", appointment_id=appointment_id))["appointment"]
        patient = await self._patient(appt["patientId"])
        task = tasks.get_task(appt["taskId"]) if appt.get("taskId") else None
        meta = parse_json(task.meta if task else None, {})
        # Identify patient → associate with investigation → flag against reference ranges (Test Center service)
        res = await self.mcp("test_center", "flag_results", test_name=str(meta.get("testName") or appt["title"]), values=values)
        panel, flags = res["test"], res["flags"]
        provider = appt["provider"]
        await self.audit(f"Report received from {provider['organization']}", patient_id=appt["patientId"], detail=f'Matched patient {patient["mrn"]} → investigation "{appt["title"]}"')

        def icon(f: str) -> str:
            return "✅ Normal" if f == "NORMAL" else f"🔴 {f.replace('_', ' ', 1)}" if f.startswith("CRITICAL") else f"🟠 {f}"

        results = (
            "## Results\n\n| Parameter | Result | Reference | Flag |\n|---|---|---|---|\n" + "\n".join(f"| {f['label']} | **{jsnum(f['value'])}** {f['unit']} | {f['range']} | {icon(f['flag'])} |" for f in flags)
            if flags
            else ""
        )
        content = "\n".join(
            [
                f"# {panel['name']} — Laboratory Report",
                "",
                "| | |",
                "|---|---|",
                f"| **Patient** | {patient['user']['name']} (MRN {patient['mrn']}) |",
                f"| **Test center** | {provider['organization']}, {provider['location']} |",
                f"| **Sample collected** | {fmt_date_time(_dt(appt['startsAt']))} |",
                f"| **Reported** | {fmt_date_time(now())} |",
                "",
                results,
                f"\n## Findings / Impression\n\n{findings}" if findings else "",
                "",
                "> Status: **Pending doctor review**. Flags are automated reference-range checks, not a diagnosis.",
            ]
        )
        doc = (
            await self.mcp(
                "ehr", "store_document", patient_id=appt["patientId"], type="LAB_REPORT", title=f"{panel['name']} report", content=content,
                data={"testCode": panel["code"], "testName": panel["name"], "values": values, "flags": flags, "findings": findings},
                visible_to_patient=True, task_id=appt.get("taskId"), review_status="PENDING_REVIEW", created_by_id=uploaded_by_id,
            )
        )["document"]  # fmt: skip
        await self.mcp("scheduling", "complete_booking", appointment_id=appointment_id)
        if appt.get("taskId"):
            tasks.update_task(appt["taskId"], status="COMPLETED")
        abnormal = len([f for f in flags if f["flag"] != "NORMAL"])
        await self.audit(f"{panel['name']} stored in EHR", patient_id=appt["patientId"], level="SUCCESS", detail=f"{abnormal} parameter(s) outside range · shared with doctor & patient")
        link = (await self.mcp("notification", "patient_link", patient_id=appt["patientId"], audience="DOCTOR", type="DOCUMENT", extra=f"&doc={doc['id']}"))["link"]
        await self.notify("DOCTOR", appt["patientId"], "DOCUMENT", f"{panel['name']} ready for review", f"{patient['user']['name']}'s report has been uploaded.", link)
        await self.notify("PATIENT", appt["patientId"], "DOCUMENT", f"Your {panel['name']} report is available", "Your doctor will review it and contact you if anything needs to change.", f"/patient/documents?doc={doc['id']}")
        await self.ask("MONITORING", "evaluate_lab_report", document_id=doc["id"])
        return doc

    # ── referral package ─────────────────────────────────────────────────────────────────

    @skill
    async def build_referral_package(self, referral_id: str, clinical_summary: str) -> dict[str, Any]:
        ref = referrals.get(referral_id)
        assert ref is not None
        p = await self._patient(ref.patient_id)
        appts = (await self.mcp("scheduling", "list_appointments", referral_id=referral_id, statuses=["TENTATIVE", "BOOKED"]))["appointments"]
        items = (await self.mcp("ehr", "get_active_plan_items", patient_id=ref.patient_id))["items"]
        reports = (await self.mcp("ehr", "get_documents", patient_id=ref.patient_id, types=["LAB_REPORT"], limit=5, include_data=False))["documents"]
        relevant = [i for i in items if i["category"] in ("MEDICATION", "RESTRICTION", "EXERCISE", "RED_FLAG") and i["action"] != "DISCONTINUE"]

        def short(d: Any) -> str:
            x = _dt(d)
            return f"{x.strftime('%a')} {x.day} {x.strftime('%b')} {fmt_time(x)}"

        schedule = ""
        if appts:
            schedule = "- Proposed schedule: " + ", ".join(short(a["startsAt"]) for a in appts[:4]) + (f" … (+{len(appts) - 4} more)" if len(appts) > 4 else "")
        resubmission = []
        if ref.revision > 0:
            resubmission = [
                f"> **Resubmission (version {ref.revision + 1}).** Previously rejected{' by ' + ref.declined_by_name if ref.declined_by_name else ''}: “{ref.decline_reason or '—'}”.",
                f"> **Changes made by the referring doctor:** {ref.note_to_specialist}" if ref.note_to_specialist else "",
                "",
            ]
        discharged = fmt_date(_dt(p["dischargeDate"])) if p.get("dischargeDate") else "recently"
        sessions = f"- Sessions: **{ref.sessions}**" + (f" ({ref.frequency_per_week}× per week for {ref.duration_weeks} week{'s' if ref.duration_weeks > 1 else ''})" if ref.sessions > 1 else "")
        doctor = p["doctor"]
        content = "\n".join(
            [
                f"# Referral — {ref.referral_type}",
                "",
                f"**Urgency:** {ref.urgency} · **Requested by:** {doctor['name']} · **Date:** {fmt_date(now())}",
                "",
                "## 1. Patient information",
                "| | |",
                "|---|---|",
                f"| Name | {p['user']['name']} |",
                f"| MRN | {p['mrn']} |",
                f"| Age / Sex | {age_years(_dt(p['dateOfBirth']))} / {p['gender']} |",
                f"| Phone | {p['user'].get('phone') or '—'} |",
                f"| Allergies | {p.get('allergies') or 'None known'} |",
                f"| Comorbidities | {p.get('comorbidities') or 'None'} |",
                "",
                "## 2. Diagnosis & clinical context",
                f"{p['diagnosis']}{' — ' + p['procedure'] if p.get('procedure') else ''}. Discharged {discharged}.",
                "",
                "## 3. Reason for referral",
                ref.reason,
                "",
                *resubmission,
                "## 4. Requested service",
                sessions,
                f"- Preferred start: within {ref.preferred_start_within_days} day(s)",
                schedule,
                "",
                "## 5. Clinical summary _(AI-generated by the Clinical Intelligence agent — verify against attached records)_",
                clinical_summary,
                "",
                "## 6. Relevant care-plan information",
                *([f"- **{CATEGORY_LABEL.get(i['category'], i['category'])}:** {i['title']}" for i in relevant] or ["- None"]),
                "",
                "## 7. Attached reports",
                *([f"- 📎 {r['title']} ({fmt_date(_dt(r['createdAt']))}) — original report attached" for r in reports] or ["- No investigation reports on file yet"]),
                "",
                "---",
                f"Referring clinician: **{doctor['name']}**{', ' + doctor['title'] if doctor.get('title') else ''}",
            ]
        )
        doc = (
            await self.mcp(
                "ehr", "store_document", patient_id=ref.patient_id, type="REFERRAL_PACKAGE", title=f"Referral package — {ref.referral_type}", content=content,
                data={"referralId": ref.id, "attachments": [r["id"] for r in reports]}, shared_with_provider_id=ref.provider_id, task_id=ref.task_id,
                visible_to_patient=False, created_by_id=p["doctorId"],
            )
        )["document"]  # fmt: skip
        await self.audit("Referral package assembled", patient_id=ref.patient_id, level="SUCCESS", detail=f"Patient info + diagnosis + reason + clinical summary + care plan + {len(reports)} report(s)")
        return doc
