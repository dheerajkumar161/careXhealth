"""AGENT 1 — Care Planning & Coordination (Microsoft Agent Framework agent).

Understand → Structure → Plan → Coordinate Requirements.
Decides WHAT care is required and produces a DRAFT plan. It never books, schedules or contacts providers,
and it never executes a plan: doctor approval is a hard gate enforced by the orchestrator and again by the
Execution agent. Port of lib/agents/planning.ts.
"""
from __future__ import annotations

import re
from typing import Any

from app.core import llm
from app.core.util import age_years, parse_dt
from app.repositories import care_plans, referrals
from app.schemas.clinical import ImageRead, RawPlan, ReferralRevisionModel, ValidationError, validate_details

from .base import CareXHealthAgent, skill
from .planning_rules import rule_based_plan

ITEM_CATEGORIES = ("MEDICATION", "INVESTIGATION", "FOLLOW_UP", "REFERRAL", "MONITORING", "DIET", "EXERCISE", "RESTRICTION", "CARE_INSTRUCTION", "RED_FLAG")

CATEGORY_ALIASES = {
    "MEDICATIONS": "MEDICATION", "MEDICINE": "MEDICATION", "DRUG": "MEDICATION",
    "INVESTIGATIONS": "INVESTIGATION", "TEST": "INVESTIGATION", "LAB": "INVESTIGATION", "LAB_TEST": "INVESTIGATION", "IMAGING": "INVESTIGATION",
    "FOLLOWUP": "FOLLOW_UP", "FOLLOW_UP_VISIT": "FOLLOW_UP", "APPOINTMENT": "FOLLOW_UP",
    "REFERRALS": "REFERRAL", "REHABILITATION": "REFERRAL", "REHAB": "REFERRAL", "THERAPY": "REFERRAL",
    "VITALS": "MONITORING", "VITAL_MONITORING": "MONITORING",
    "NUTRITION": "DIET", "ACTIVITY": "EXERCISE", "PHYSICAL_ACTIVITY": "EXERCISE",
    "RESTRICTIONS": "RESTRICTION", "PRECAUTION": "RESTRICTION",
    "INSTRUCTION": "CARE_INSTRUCTION", "CARE_INSTRUCTIONS": "CARE_INSTRUCTION", "WOUND_CARE": "CARE_INSTRUCTION",
    "REDFLAG": "RED_FLAG", "RED_FLAGS": "RED_FLAG", "WARNING": "RED_FLAG", "ALERT": "RED_FLAG",
}  # fmt: skip

# Required detail fields per structured category — used to detect items the model under-specified.
REQUIRED = {
    "MEDICATION": ["name", "timesPerDay", "durationDays"],
    "INVESTIGATION": ["test", "dayOffset"],
    "FOLLOW_UP": ["dayOffset"],
    "REFERRAL": ["referralType", "sessions"],
    "MONITORING": ["metric"],
    "RED_FLAG": ["metric", "action"],
}

# Orders (meds, tests, follow-ups, referrals) may only come from the doctor's own words
ORDER_CATEGORIES = {"MEDICATION", "INVESTIGATION", "FOLLOW_UP", "REFERRAL"}
ORDER_KEYWORDS = {
    "REFERRAL": r"refer|physio|therap|dietit|nutrition|counsel|psycholog|home (nursing|care|visit)|wound|specialist|rehab",
    "FOLLOW_UP": r"follow|review|revisit|see (me|you)|opd|clinic",
}
PRN = r"\b(prn|sos|as needed|when needed|if needed|if pain|for pain)\b"

SYSTEM = """You are the Care Planning & Coordination Agent of a hospital post-discharge platform.
You convert a doctor's natural-language discharge or decision note into a STRUCTURED care plan.
You decide WHAT care is required — you never book, choose specific providers, or make new diagnoses.

Rules:
- Every instruction the doctor wrote must appear as an item with source "DOCTOR". Never drop or alter doctor instructions.
- Add helpful, conservative supportive items (diet, exercise, restrictions, care instructions, red flags, monitoring) appropriate to the diagnosis with source "AI_SUGGESTED" and a short "rationale". The doctor will review and can remove them. NEVER add medications, investigations, follow-ups or referrals that the doctor did not write — orders come only from the doctor.
- Any need for external help (physiotherapy, dietitian, psychologist, cardiologist, home nursing, wound care, occupational therapy, etc.) is a REFERRAL item.
- Use these categories and detail shapes exactly:
  MEDICATION: {name, dose, timesPerDay (int), durationDays (int), route?, instructions?, asNeeded? (true for PRN/SOS medicines taken only when needed — they get no fixed schedule)}
  INVESTIGATION: {test, dayOffset (int days from discharge), instructions?}
  FOLLOW_UP: {specialty, withTreatingDoctor (bool), dayOffset (int), reason}
  REFERRAL: {referralType, reason, sessions (int), frequencyPerWeek (int), durationWeeks (int), preferredStartWithinDays (int), urgency: ROUTINE|PRIORITY|URGENT}
  MONITORING: {metric, timesPerDay (int), unit}
  RED_FLAG: {metric, operator: ">"|"<"|">="|"<="|"CONTAINS", threshold? (number), keywords? (string[] for SYMPTOM), unit?, action: NOTIFY_NURSE|NOTIFY_DOCTOR|EMERGENCY, severity: LOW|MEDIUM|HIGH|CRITICAL}
  DIET | EXERCISE | RESTRICTION | CARE_INSTRUCTION: {text}
- metric must be one of TEMPERATURE, SYSTOLIC_BP, DIASTOLIC_BP, HEART_RATE, SPO2, PAIN, BLOOD_GLUCOSE, WEIGHT, WEIGHT_GAIN, SYMPTOM. Temperature is in °F.
- A rule about a CHANGE in weight (e.g. "weight gain more than 2 kg") uses metric WEIGHT_GAIN with threshold = the change in kg. WEIGHT is only for absolute body weight.
- For amendments, use action "DISCONTINUE" (details.name = medication) to stop a medication and "MODIFY" to change one (include full new details).
- "title" is a concise human-readable line, e.g. "Medicine X — twice daily for 7 days".
- "action" is ADD unless stopping/changing a medication. "source" is exactly "DOCTOR" or "AI_SUGGESTED". "details" is always an OBJECT.
Return JSON: {"summary": string, "items": Item[]}

Example output for "Take Tab Cefuroxime 500mg twice daily for 7 days. Check CBC after 5 days. Physiotherapy three times a week for 4 weeks. Notify nurse if temperature exceeds 101°F.":
{"summary":"Post-operative plan with antibiotic course, day-5 CBC, physiotherapy referral and fever red flag.","items":[
{"category":"MEDICATION","action":"ADD","title":"Cefuroxime 500mg — twice daily for 7 days","source":"DOCTOR","details":{"name":"Cefuroxime","dose":"500mg","timesPerDay":2,"durationDays":7}},
{"category":"INVESTIGATION","action":"ADD","title":"CBC on day 5","source":"DOCTOR","details":{"test":"CBC","dayOffset":5}},
{"category":"REFERRAL","action":"ADD","title":"Physiotherapy — 12 sessions, 3/week for 4 weeks","source":"DOCTOR","details":{"referralType":"Physiotherapy","reason":"Post-operative mobility rehabilitation","sessions":12,"frequencyPerWeek":3,"durationWeeks":4,"preferredStartWithinDays":3,"urgency":"ROUTINE"}},
{"category":"RED_FLAG","action":"ADD","title":"Temperature > 101°F → notify nurse","source":"DOCTOR","details":{"metric":"TEMPERATURE","operator":">","threshold":101,"unit":"°F","action":"NOTIFY_NURSE","severity":"HIGH"}},
{"category":"EXERCISE","action":"ADD","title":"Ankle pumps 10 reps, 3 times daily","source":"AI_SUGGESTED","rationale":"Reduces DVT risk","details":{"text":"Ankle pumps 10 repetitions three times a day"}}]}"""

REVISE_SYSTEM = """You are the Care Planning & Coordination Agent. A specialist REJECTED a referral and gave a reason.
Revise the referral so it addresses the reason, and list any care-plan changes the referring doctor must make first
(e.g. the specialist needs an X-ray or blood test before starting → add an INVESTIGATION item; wants fewer sessions → change sessions).
Do not invent new diagnoses. Keep changes minimal and directly tied to the rejection reason.
The referral itself is revised in "referral" — NEVER put a REFERRAL item in carePlanChanges (that would create a duplicate referral).
Return JSON:
{"explanation": string (1-2 sentences for the doctor),
 "referral": {"referralType","reason","sessions","frequencyPerWeek","durationWeeks","preferredStartWithinDays","urgency":"ROUTINE|PRIORITY|URGENT","noteToSpecialist": string (what was changed, addressed to the specialist)},
 "carePlanChanges": [care-plan items using the same item format as care plans: {"category","action","title","source":"DOCTOR","details":{...}}]}
INVESTIGATION details: {test, dayOffset}. MEDICATION details: {name, dose, timesPerDay, durationDays}."""

READ_IMAGE = """You are reading a doctor's discharge note, prescription or clinical order from a photo or scan (it may be handwritten).
1. "transcript": transcribe exactly what is written, line by line.
2. "instructions": rewrite EVERY clinical instruction as a plain, complete English sentence, expanding standard shorthand:
   1-0-1 = twice daily (morning and night); 1-1-1 = three times daily; 1-0-0 = once daily in the morning; 0-0-1 = once daily at night;
   OD/QD = once daily; BD/BID = twice daily; TDS/TID = three times daily; QID = four times daily; HS = at bedtime; SOS/PRN = only when needed;
   AC = before food; PC = after food; "x 7d" / "x 7 days" = for 7 days; "Review in OPD after N" = follow up after N; Inv/Ix = investigation.
   Example: "Tab Cefuroxime 500mg 1-0-1 x 7 days" -> "Take Tab Cefuroxime 500mg twice daily for 7 days."
   Example: "Physio 3x/wk x 4 wks" -> "Physiotherapy required three times a week for 4 weeks."
3. "patientName": the patient's name written on the document, or "".
4. "unclear": anything you could not read confidently (empty list if none).
Never invent instructions that are not in the image. If the image is not a clinical document, return empty "instructions".
Return JSON {"transcript": string, "instructions": string[], "patientName": string, "unclear": string[]}"""

VISION_UNAVAILABLE = "Reading images needs a vision model (GROQ_VISION_MODEL, or OLLAMA_VISION_MODEL with Ollama running). Type the instructions instead."


def _blank(v: Any) -> bool:
    return v is None or v == ""


class PlanningAgent(CareXHealthAgent):
    key = "PLANNING"
    instructions = SYSTEM

    _catalogue: list[dict[str, Any]] | None = None

    async def catalogue(self) -> list[dict[str, Any]]:
        if self._catalogue is None:
            self._catalogue = (await self.mcp("test_center", "list_tests"))["tests"]
        return self._catalogue

    # ── normalisation & the invented-order filter ────────────────────────────────────────

    async def normalize_item(self, raw: dict[str, Any]) -> dict[str, Any] | None:
        """LLMs drift from the requested format; coerce rather than discard the whole plan."""
        key = re.sub(r"[\s-]+", "_", str(raw.get("category") or "").upper().strip())
        category = key if key in ITEM_CATEGORIES else CATEGORY_ALIASES.get(key)
        if not category:
            return None
        action_text = str(raw.get("action") or "").lower()
        action = "DISCONTINUE" if re.search(r"discontinu|stop|hold|cease", action_text) else "MODIFY" if re.search(r"modif|change|adjust|replace", action_text) else "ADD"
        source = "AI_SUGGESTED" if re.search(r"ai|suggest", str(raw.get("source") or ""), re.I) else "DOCTOR"
        title = str(raw.get("title") or "").strip()
        d = raw.get("details")
        details: dict[str, Any] = dict(d) if isinstance(d, dict) else {"text": str(d if d is not None else title)}
        if category in ("DIET", "EXERCISE", "RESTRICTION", "CARE_INSTRUCTION") and not details.get("text"):
            details["text"] = title
        if isinstance(details.get("metric"), str):
            details["metric"] = re.sub(r"[\s-]+", "_", details["metric"].upper())
        if isinstance(details.get("action"), str):
            details["action"] = re.sub(r"[\s-]+", "_", details["action"].upper())
        # Safety: an absolute-weight rule with a tiny threshold is really a weight-change rule (e.g. "gain > 2 kg")
        try:
            if category == "RED_FLAG" and details.get("metric") == "WEIGHT" and float(details.get("threshold")) < 20:  # type: ignore[arg-type]
                details["metric"] = "WEIGHT_GAIN"
        except (TypeError, ValueError):
            pass
        if isinstance(details.get("keywords"), str):
            details["keywords"] = [k.strip() for k in details["keywords"].split(",") if k.strip()]
        if category == "MEDICATION" and re.search(PRN, f"{title} {details.get('instructions') or ''} {details.get('frequency') or ''}", re.I):
            details["asNeeded"] = True

        # Repair under-specified structured items using the deterministic parser on the item's own text
        missing = [f for f in REQUIRED.get(category, []) if _blank(details.get(f))]
        if missing:
            text = ". ".join(x for x in [title, details["text"] if isinstance(details.get("text"), str) else ""] if x)
            repaired = next((i for i in rule_based_plan(text, "", suggestions=False, catalogue=await self.catalogue())["items"] if i["category"] == category), None)
            if repaired:
                details = {**repaired["details"], **{k: v for k, v in details.items() if not _blank(v)}}
        if not title:
            return None
        # Data contract: validated before it can become a database row
        try:
            details = validate_details(category, details, action)
        except ValidationError:
            return None
        return {"category": category, "action": action, "title": title, "source": source, "rationale": str(raw["rationale"]) if raw.get("rationale") else None, "details": details}

    @staticmethod
    def keep_order(item: dict[str, Any], note: str) -> bool:
        """AI cannot invent medical orders: drop AI-sourced orders and orders whose service is absent from the note."""
        if item["category"] not in ORDER_CATEGORIES:
            return True
        if item["source"] == "AI_SUGGESTED":
            return False
        if note and item["category"] == "REFERRAL":
            type_ = re.split(r"[\s/—-]+", str(item["details"].get("referralType") or item["title"]).lower())[0]
            return type_[:4] in note.lower() and bool(re.search(ORDER_KEYWORDS["REFERRAL"], note, re.I))
        if note and item["category"] == "FOLLOW_UP":
            return bool(re.search(ORDER_KEYWORDS["FOLLOW_UP"], note, re.I))
        return True

    async def parse_plan(self, v: Any, note: str = "") -> dict[str, Any]:
        raw = RawPlan.model_validate(v)
        normalized = [await self.normalize_item(i) for i in raw.items]
        items = [i for i in normalized if i and self.keep_order(i, note)]
        if not items:
            raise ValueError("No usable care-plan items in model output")
        return {"summary": raw.summary or f"Structured {len(items)} care-plan items for doctor review.", "items": items}

    # ── LLM structuring with deterministic fallback ──────────────────────────────────────

    async def structure(self, prompt: str, diagnosis: str, raw: str, suggestions: bool = True) -> dict[str, Any]:
        parsed: dict[str, Any] | None = None
        if self.llm is not None:
            data = await llm.run_json(self.llm, prompt, lambda v: v)
            if data is not None:
                try:
                    parsed = await self.parse_plan(data, raw)
                except (ValidationError, ValueError) as e:
                    await self.audit("LLM plan rejected by validation — using rule engine", detail=str(e)[:200], level="WARNING")
        if parsed:
            return {**parsed, "engine": llm.last_engine()}
        return {**rule_based_plan(raw, diagnosis, suggestions=suggestions, catalogue=await self.catalogue()), "engine": "rules"}

    @staticmethod
    def patient_brief(p: dict[str, Any]) -> str:
        return (
            f"Patient: {age_years(parse_dt(p['dateOfBirth']))}y {p['gender']}. Diagnosis: {p['diagnosis']}. Procedure: {p.get('procedure') or 'none'}. "
            f"Allergies: {p.get('allergies') or 'none known'}. Comorbidities: {p.get('comorbidities') or 'none'}."
        )

    async def patient(self, patient_id: str) -> dict[str, Any]:
        p = (await self.mcp("ehr", "get_patient_records", patient_id=patient_id))["patient"]
        if p is None:
            raise ValueError("Patient not found")
        return p

    async def active_items(self, patient_id: str) -> list[dict[str, Any]]:
        return (await self.mcp("ehr", "get_active_plan_items", patient_id=patient_id))["items"]

    # ── images ───────────────────────────────────────────────────────────────────────────

    async def read_attachments(self, patient_id: str, patient_name: str, attachments: list[dict[str, str]]) -> dict[str, Any]:
        reader = self.llm_agent("image reader", READ_IMAGE, vision=True)
        if reader is None or not llm.available(vision=True):
            raise ValueError(VISION_UNAVAILABLE)
        await self.audit(f"Reading {len(attachments)} attached image(s)", patient_id=patient_id, detail=", ".join(a["name"] for a in attachments))
        results = []
        for a in attachments:
            out = await llm.run_vision_json(reader, READ_IMAGE, [a["dataUrl"]], ImageRead.model_validate)
            if out is None:
                raise ValueError(f'Couldn\'t read "{a["name"]}". Make sure the photo is clear and well lit, or type the instructions.')
            results.append({**out.model_dump(), "name": a["name"], "dataUrl": a["dataUrl"]})
        lines = [line.strip() for r in results for line in r["instructions"] if line.strip()]
        if not lines:
            raise ValueError("No clinical instructions were found in the attached image(s).")
        # Safety: flag a document that appears to belong to someone else
        tokens = [t for t in patient_name.lower().split() if len(t) > 2]
        warnings = [
            f'⚠ The name on "{r["name"]}" ("{r["patientName"]}") does not match this patient — verify before approving.'
            for r in results
            if r.get("patientName") and not any(t in r["patientName"].lower() for t in tokens)
        ]
        unclear = [f'Unclear in "{r["name"]}": {u}' for r in results for u in (r.get("unclear") or [])]
        await self.audit(
            "Extracted instructions from image(s)",
            patient_id=patient_id,
            level="WARNING" if warnings else "SUCCESS",
            detail=f"{len(lines)} instruction(s){f', {len(unclear)} unclear' if unclear else ''}{' — patient name mismatch' if warnings else ''}",
        )
        return {"results": results, "lines": lines, "warnings": warnings, "unclear": unclear}

    async def store_sources(self, patient_id: str, doctor_id: str, plan_id: str, results: list[dict[str, Any]]) -> None:
        """Keeps the source images (clinician-only) alongside the plan they produced, for verification and audit."""
        for r in results:
            transcript = "\n".join(f"> {line}" for line in r["transcript"].split("\n"))
            extracted = "\n".join(f"- {line}" for line in r["instructions"])
            unclear = ("\n\n## Could not read confidently\n\n" + "\n".join(f"- {u}" for u in r["unclear"])) if r.get("unclear") else ""
            await self.mcp(
                "ehr",
                "store_document",
                patient_id=patient_id,
                type="SOURCE_NOTE",
                title=f"Source image — {r['name']}",
                content=f"# Source image — {r['name']}\n\n## Transcript\n\n{transcript}\n\n## Instructions extracted\n\n{extracted}{unclear}",
                data={"carePlanId": plan_id, "name": r["name"], "image": r["dataUrl"], "unclear": r.get("unclear") or []},
                created_by_id=doctor_id,
                engine=llm.last_engine(),
            )

    async def gather_input(self, patient_id: str, typed: str, attachments: list[dict[str, str]]) -> dict[str, Any]:
        patient = await self.patient(patient_id)
        if not attachments:
            return {"patient": patient, "text": typed, "raw": typed, "read": None}
        read = await self.read_attachments(patient_id, patient["user"]["name"], attachments)
        text = "\n".join(x for x in [typed.strip(), *read["lines"]] if x)
        prefix = f"{typed.strip()}\n\n" if typed.strip() else ""
        raw = f"{prefix}[Extracted from {len(attachments)} attached image(s)]\n" + "\n".join(read["lines"])
        return {"patient": patient, "text": text, "raw": raw, "read": read}

    @staticmethod
    def with_read_notes(summary: str, read: dict[str, Any] | None) -> str:
        if not read:
            return summary
        return " ".join([*read["warnings"], *[f"⚠ {u}" for u in read["unclear"]], summary])

    # ── skills ───────────────────────────────────────────────────────────────────────────

    @skill
    async def draft_care_plan(self, patient_id: str, doctor_id: str, instructions: str, attachments: list[dict[str, str]] | None = None) -> dict[str, Any]:
        """Phase 1: doctor's discharge instructions (typed and/or images) → structured DRAFT care plan."""
        g = await self.gather_input(patient_id, instructions, attachments or [])
        await self.audit("Received discharge instructions", patient_id=patient_id, detail=g["text"][:160])
        result = await self.structure(f'{self.patient_brief(g["patient"])}\n\nDoctor\'s discharge instructions:\n"""{g["text"]}"""', g["patient"]["diagnosis"], g["text"])
        result["summary"] = self.with_read_notes(result["summary"], g["read"])
        # Drop any earlier unapproved drafts
        care_plans.reject_initial_drafts(patient_id)
        plan = care_plans.create_draft(patient_id=patient_id, doctor_id=doctor_id, kind="INITIAL", raw=g["raw"], summary=result["summary"], engine=result["engine"], items=result["items"])
        if g["read"]:
            await self.store_sources(patient_id, doctor_id, plan.id, g["read"]["results"])
        ai = len([i for i in plan.items if i.source == "AI_SUGGESTED"])
        await self.audit(
            "Structured draft care plan created", patient_id=patient_id, level="SUCCESS", detail=f"{len(plan.items)} items ({ai} AI-suggested) via {result['engine']}. Awaiting doctor review."
        )
        return {"planId": plan.id}

    @skill
    async def draft_amendment(self, patient_id: str, doctor_id: str, decision: str, attachments: list[dict[str, str]] | None = None) -> dict[str, Any]:
        """Phase 7: doctor's decision (e.g. after reviewing a report) → structured care-plan amendment (DRAFT)."""
        g = await self.gather_input(patient_id, decision, attachments or [])
        current = await self.active_items(patient_id)
        await self.audit("Received doctor decision", patient_id=patient_id, detail=g["text"][:160])
        listing = "\n".join(f"- [{i['category']}] {i['title']}" for i in current) or "(none)"
        prompt = (
            f"{self.patient_brief(g['patient'])}\n\nCurrent active care plan items:\n{listing}\n\n"
            f'Doctor\'s new decision / order (create ONLY the changes it requires; do not repeat existing items; add no AI suggestions unless clearly needed for a new item):\n"""{g["text"]}"""'
        )
        result = await self.structure(prompt, g["patient"]["diagnosis"], g["text"], suggestions=False)
        result["summary"] = self.with_read_notes(result["summary"], g["read"])
        plan = care_plans.create_draft(patient_id=patient_id, doctor_id=doctor_id, kind="AMENDMENT", raw=g["raw"], summary=result["summary"], engine=result["engine"], items=result["items"])
        if g["read"]:
            await self.store_sources(patient_id, doctor_id, plan.id, g["read"]["results"])
        await self.audit("Care-plan amendment drafted", patient_id=patient_id, level="SUCCESS", detail=f"{len(plan.items)} change(s) via {result['engine']}. Awaiting approval.")
        return {"planId": plan.id}

    @skill
    async def create_amendment(self, patient_id: str, doctor_id: str, raw: str, items: list[dict[str, Any]], engine: str = "rules") -> dict[str, Any] | None:
        """Doctor-applied changes from an agent proposal → a DRAFT amendment (the orchestrator approves it on the doctor's behalf)."""
        if not items:
            return None
        plan = care_plans.create_draft(
            patient_id=patient_id, doctor_id=doctor_id, kind="AMENDMENT", raw=raw, summary=f"Changes requested to address a referral rejection ({len(items)} item(s)).", engine=engine, items=items
        )
        return {"planId": plan.id}

    @skill
    async def activate_plan(self, plan_id: str, doctor_id: str, doctor_name: str, base: str | None = None) -> dict[str, Any]:
        """Records the doctor's approval: DRAFT → ACTIVE (supersedes an earlier initial plan) and hands requirements off."""
        plan = care_plans.get(plan_id)
        if plan is None:
            raise ValueError("Care plan not found")
        if plan.status != "DRAFT":
            raise ValueError("Only draft plans can be approved")
        patient = await self.patient(plan.patient_id)
        if patient["doctorId"] != doctor_id:
            raise PermissionError("Only the treating doctor can approve this plan")
        from app.core.util import iso, now
        from app.repositories import monitoring, tasks

        if plan.kind == "INITIAL":
            care_plans.supersede_active(plan.patient_id)
            tasks.cancel_open_tasks(plan.patient_id)
            tasks.cancel_pending_doses(patient_id=plan.patient_id)
            monitoring.deactivate_all(plan.patient_id)
        care_plans.set_status(plan_id, "ACTIVE")
        await self.audit("Doctor approved care plan" if plan.kind == "INITIAL" else "Doctor approved care-plan amendment", patient_id=plan.patient_id, level="SUCCESS", agent="HUMAN")
        if plan.kind == "INITIAL":
            await self.mcp("ehr", "update_patient_record", patient_id=plan.patient_id, status="RECOVERING", discharge_date=patient.get("dischargeDate") or base or iso(now()))
        included = [i for i in plan.items if i.included]
        executable = len([i for i in included if i.category in ("MEDICATION", "INVESTIGATION", "FOLLOW_UP", "REFERRAL", "MONITORING")])
        flags = len([i for i in included if i.category == "RED_FLAG"])
        await self.audit(
            "Care requirements created and handed off", patient_id=plan.patient_id, detail=f"{executable} executable requirement(s) → Execution agent; {flags} red-flag rule(s) → Monitoring agent"
        )
        return {"planId": plan_id, "patientId": plan.patient_id, "kind": plan.kind, "version": plan.version, "doctorName": doctor_name}

    @skill
    async def revise_referral(self, referral_id: str) -> dict[str, Any]:
        """Reads the rejection reason and proposes a revised referral (+ care-plan changes). Nothing is saved."""
        ref = referrals.get(referral_id)
        if ref is None:
            raise ValueError("Referral not found")
        patient = await self.patient(ref.patient_id)
        current = {
            "referralType": ref.referral_type,
            "reason": ref.reason,
            "sessions": ref.sessions,
            "frequencyPerWeek": ref.frequency_per_week,
            "durationWeeks": ref.duration_weeks,
            "preferredStartWithinDays": ref.preferred_start_within_days,
            "urgency": ref.urgency,
        }
        items = await self.active_items(ref.patient_id)
        await self.audit("Analysing referral rejection", patient_id=ref.patient_id, detail=ref.decline_reason)
        import json

        listing = "\n".join(f"- [{i['category']}] {i['title']}" for i in items) or "(none)"
        prompt = (
            f"{self.patient_brief(patient)}\nCurrent active care plan:\n{listing}\n\nRejected referral: {json.dumps(current)}\n"
            f'Rejected by: {ref.declined_by_name or "specialist"}\nRejection reason: """{ref.decline_reason or "No reason given"}"""'
        )
        proposal: dict[str, Any] | None = None
        reviser = self.llm_agent("referral revision", REVISE_SYSTEM)
        data = await llm.run_json(reviser, prompt, ReferralRevisionModel.model_validate)
        if data is not None:
            r = data.referral

            def pos(x: Any, d: int) -> int:
                try:
                    v = float(x)
                    return int(v + 0.5) if v > 0 else d
                except (TypeError, ValueError):
                    return d

            urgency = str(r.get("urgency") or "").upper()
            changes = [await self.normalize_item(c) for c in data.carePlanChanges]
            proposal = {
                "explanation": data.explanation,
                "referral": {
                    "referralType": str(r.get("referralType") or current["referralType"]),
                    "reason": str(r.get("reason") or current["reason"]),
                    "sessions": pos(r.get("sessions"), current["sessions"]),
                    "frequencyPerWeek": pos(r.get("frequencyPerWeek"), current["frequencyPerWeek"]),
                    "durationWeeks": pos(r.get("durationWeeks"), current["durationWeeks"]),
                    "preferredStartWithinDays": pos(r.get("preferredStartWithinDays"), current["preferredStartWithinDays"]),
                    "urgency": urgency if urgency in ("ROUTINE", "PRIORITY", "URGENT") else current["urgency"],
                    "noteToSpecialist": str(r.get("noteToSpecialist") or f"Revised to address: {ref.decline_reason}"),
                },
                # The referral is updated in place by resend — a REFERRAL item here would spawn a duplicate referral.
                # Orders the specialist did not ask for are filtered like any other invented order.
                "carePlanChanges": [c for c in changes if c and c["category"] != "REFERRAL" and c["source"] == "DOCTOR"],
                "engine": llm.last_engine(),
            }
        if proposal is None:
            # Deterministic fallback: numbers in the reason adjust the schedule, named tests become investigations
            reason = ref.decline_reason or ""
            rev = {**current, "noteToSpecialist": f'Revised to address your feedback: "{reason}"'}
            per_week = re.search(r"(\d+|once|twice|thrice)\s*(?:times?\s*)?(?:a|per|/)\s*week", reason, re.I)
            if per_week:
                rev["frequencyPerWeek"] = {"once": 1, "twice": 2, "thrice": 3}.get(per_week.group(1).lower()) or int(per_week.group(1))
            sess = re.search(r"(\d+)\s*sessions?", reason, re.I)
            rev["sessions"] = int(sess.group(1)) if sess else rev["frequencyPerWeek"] * rev["durationWeeks"]
            later = re.search(r"(?:after|in|wait)\s+(\d+)\s*(days?|weeks?)", reason, re.I)
            if later:
                rev["preferredStartWithinDays"] = int(later.group(1)) * (7 if re.search(r"week", later.group(2), re.I) else 1)
            if re.search(r"urgent|asap|earlier|sooner", reason, re.I):
                rev["urgency"] = "URGENT"
            tests = [t for t in await self.catalogue() if any(a in reason.lower() for a in t["aliases"])]
            changes = [
                {"category": "INVESTIGATION", "action": "ADD", "title": f"{t['name']} on day 1", "source": "DOCTOR", "details": {"test": "X-ray" if t["code"] == "XRAY" else t["name"], "dayOffset": 1}}
                for t in tests
            ]
            added = f" and added {', '.join(c['title'] for c in changes)} to the care plan" if changes else ""
            proposal = {"explanation": f"Adjusted the referral to the specialist's feedback{added}. Review before resending.", "referral": rev, "carePlanChanges": changes, "engine": "rules"}
        await self.audit("Referral revision proposed", patient_id=ref.patient_id, level="SUCCESS", detail=f"{proposal['explanation']} ({proposal['engine']})")
        return proposal
