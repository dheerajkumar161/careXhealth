"""AGENT 2 — Care Execution & Scheduling (Microsoft Agent Framework agent).

Execute → Book → Track. Takes the APPROVED care plan and makes the activities happen by orchestrating the
hospital services over MCP (Scheduling, Provider Directory, Test Center, Notification, EHR).
It does not judge whether the patient is getting worse (that is the Monitoring agent).
Port of lib/agents/execution.ts.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any

from app.core.util import add_days, dumps, fmt, fmt_day, fmt_time, iso, now, parse_dt, parse_json, start_of_day
from app.repositories import care_plans, people, referrals, tasks

from .base import CareXHealthAgent, skill

DOSE_TIMES: dict[int, list[tuple[int, int]]] = {1: [(9, 0)], 2: [(8, 0), (20, 0)], 3: [(8, 0), (14, 0), (20, 0)], 4: [(6, 0), (12, 0), (18, 0), (22, 0)]}
REFERRAL_PROVIDER_TYPES = ["DOCTOR", "THERAPIST", "SPECIALIST", "HOME_CARE", "COUNSELLOR", "DIETITIAN"]
PRN = r"\b(prn|sos|as needed|when needed|if needed|if pain|for pain)\b"


def _n(v: Any, default: float) -> float:
    """JS `Number(v) || default`."""
    try:
        x = float(v)
        return x if x and x == x else default
    except (TypeError, ValueError):
        return default


def referral_title(referral_type: str, sessions: int, frequency_per_week: int, duration_weeks: int) -> str:
    base = f"{referral_type} — {sessions} session{'s' if sessions > 1 else ''}"
    return base + (f", {frequency_per_week}/week for {duration_weeks} week{'s' if duration_weeks > 1 else ''}" if sessions > 1 else "")


class ExecutionAgent(CareXHealthAgent):
    key = "EXECUTION"
    instructions = (
        "You are the Care Execution & Scheduling Agent of a hospital post-discharge platform. You execute APPROVED care plans "
        "by booking tests, follow-ups and referral sessions through the hospital's scheduling, provider-directory and test-center "
        "services, and you track attendance. You never change clinical orders."
    )

    # ── plan execution (hard approval gate) ──────────────────────────────────────────────

    @skill
    async def execute_plan(self, plan_id: str, base: str | None = None, not_before: str | None = None) -> dict[str, Any]:
        plan = care_plans.get(plan_id)
        if plan is None:
            raise ValueError("Care plan not found")
        # Safety gate: an agent may never execute a plan the doctor has not approved.
        if plan.status != "ACTIVE" or plan.approved_at is None:
            await self.audit("Refused to execute unapproved care plan", patient_id=plan.patient_id, level="CRITICAL", detail=f"Plan v{plan.version} is {plan.status}")
            raise PermissionError("Care plan has not been approved by the doctor")
        b = parse_dt(base) or now()
        nb = parse_dt(not_before)
        patient_id = plan.patient_id
        await self.audit("Picked up approved care requirements", patient_id=patient_id, detail=f"Plan v{plan.version} ({plan.kind.lower()})")
        for item in [i for i in plan.items if i.included]:
            d = parse_json(item.details, {})
            try:
                if item.category == "MEDICATION":
                    if item.action in ("DISCONTINUE", "MODIFY"):
                        await self.discontinue_medication(patient_id, str(d.get("name") or item.title))
                    if item.action != "DISCONTINUE":
                        await self.schedule_medication(plan_id, item.id, patient_id, d, item.title, b, nb)
                elif item.category == "INVESTIGATION":
                    await self.schedule_investigation(plan_id, item.id, patient_id, d, b, nb)
                elif item.category == "FOLLOW_UP":
                    await self.schedule_follow_up(plan_id, item.id, patient_id, plan.doctor_id, d, b, nb)
                elif item.category == "REFERRAL":
                    await self.create_referral(plan_id, item.id, patient_id, d, item.title, b, nb)
                elif item.category == "MONITORING":
                    tasks.create_task(patient_id=patient_id, care_plan_id=plan_id, item_id=item.id, type="MONITORING", title=item.title, status="IN_PROGRESS", meta=d)
            except Exception as e:  # noqa: BLE001 — one failed requirement must not stop the rest
                await self.audit(f"Failed to execute: {item.title}", patient_id=patient_id, level="WARNING", detail=str(e))
        await self.audit("Execution workflow initiated for all requirements", patient_id=patient_id, level="SUCCESS")
        return {"planId": plan_id}

    async def schedule_medication(self, plan_id: str, item_id: str, patient_id: str, d: dict[str, Any], title: str, base: datetime, not_before: datetime | None) -> None:
        times_per_day = int(min(max(_n(d.get("timesPerDay"), 1), 1), 4))
        days = int(min(max(_n(d.get("durationDays"), 7), 1), 180))
        name = str(d.get("name") or title)
        dose_label = f" {d['dose']}" if d.get("dose") else ""
        # As-needed (PRN / SOS) medicines get no fixed dose times — no reminders, and skipping them is not non-adherence
        if d.get("asNeeded") is True or re.search(PRN, f"{title} {d.get('instructions') or ''} {d.get('frequency') or ''}", re.I):
            tasks.create_task(
                patient_id=patient_id, care_plan_id=plan_id, item_id=item_id, type="MEDICATION", title=f"{name}{dose_label} (as needed)", status="IN_PROGRESS",
                due_date=add_days(start_of_day(base), days), meta={**d, "asNeeded": True, "durationDays": days},
            )  # fmt: skip
            await self.audit(f"As-needed medication recorded: {name}", patient_id=patient_id, detail="No fixed schedule or reminders — taken only when required")
            return
        lower = not_before or base
        task = tasks.create_task(
            patient_id=patient_id, care_plan_id=plan_id, item_id=item_id, type="MEDICATION", title=f"{name}{dose_label}", status="IN_PROGRESS",
            due_date=add_days(start_of_day(base), days), meta={**d, "timesPerDay": times_per_day, "durationDays": days},
        )  # fmt: skip
        # If today's slots have mostly passed, the course starts with the next available dose and still delivers the full count.
        total = times_per_day * days
        doses: list[datetime] = []
        day = start_of_day(base)
        while len(doses) < total:
            for h, m in DOSE_TIMES[times_per_day]:
                t = day.replace(hour=h, minute=m)
                if t >= lower - timedelta(hours=1) and len(doses) < total:
                    doses.append(t)
            day = add_days(day, 1)
        tasks.create_doses(patient_id, task.id, name, str(d["dose"]) if d.get("dose") else None, doses)
        tasks.update_task(task.id, due_date=doses[-1])
        at = ", ".join(f"{h:02d}:{m:02d}" for h, m in DOSE_TIMES[times_per_day])
        await self.audit(f"Medication schedule generated: {name}", patient_id=patient_id, level="SUCCESS", detail=f"{total} doses at {at} for {days} days. Reminders enabled.")

    async def discontinue_medication(self, patient_id: str, name: str) -> None:
        key = name.lower().split(" ")[0]
        matches = [t for t in tasks.active_medication_tasks(patient_id) if key in t.title.lower()]
        for t in matches:
            tasks.cancel_pending_doses(task_id=t.id)
            tasks.update_task(t.id, status="CANCELLED")
        await self.audit(
            f"Medication discontinued: {name}", patient_id=patient_id, level="SUCCESS" if matches else "WARNING", detail=f"{len(matches)} active schedule(s) cancelled" if matches else "No active schedule matched"
        )

    async def schedule_investigation(self, plan_id: str, item_id: str, patient_id: str, d: dict[str, Any], base: datetime, not_before: datetime | None) -> None:
        panel = (await self.mcp("test_center", "get_test_details", name=str(d.get("test") or "Investigation")))["test"]
        target = add_days(start_of_day(base), _n(d.get("dayOffset"), 1))
        title = f"{panel['name']}{' (' + panel['code'] + ')' if panel['code'] != 'CUSTOM' else ''}"
        task = tasks.create_task(
            patient_id=patient_id, care_plan_id=plan_id, item_id=item_id, type="INVESTIGATION", title=title, status="PENDING", due_date=target,
            meta={**d, "testCode": panel["code"], "testName": panel["name"]},
        )  # fmt: skip
        await self.audit(f"Investigation task created: {panel['name']}", patient_id=patient_id, detail=f"Target day {d.get('dayOffset', 1)} → querying Test Center service")
        for center in (await self.mcp("test_center", "find_test_centers"))["centers"]:
            slots = (await self.mcp("test_center", "find_available_slots", center_id=center["id"], from_date=iso(target), count=1, horizon_days=7, not_before=iso(not_before or now())))["slots"]
            if not slots:
                continue
            slot = slots[0]
            await self.mcp("test_center", "book_test", patient_id=patient_id, center_id=center["id"], start=slot["start"], end=slot["end"], test_name=panel["name"], task_id=task.id)
            start = parse_dt(slot["start"])
            tasks.update_task(task.id, status="SCHEDULED", due_date=start)
            await self.audit(f"Test Center booked {panel['name']}", patient_id=patient_id, level="SUCCESS", detail=f"{center['organization']} — {fmt(start)}", agent="SERVICE")
            prep = panel.get("prep") or (str(d["instructions"]) if d.get("instructions") else "No special preparation needed.")
            await self.notify("PATIENT", patient_id, "APPOINTMENT", f"{panel['name']} booked", f"{fmt(start)} at {center['organization']}, {center['location']}. {prep}")
            await self.notify_provider(center["id"], "APPOINTMENT", f"New test booking: {panel['name']}", f"Scheduled for {fmt(start)}.")
            return
        tasks.update_task(task.id, status="FAILED")
        await self.audit(f"No test-center slot found for {panel['name']}", patient_id=patient_id, level="WARNING")
        await self.notify("NURSE", patient_id, "SYSTEM", "Manual booking needed", f"No test center slot was available for {panel['name']}.")

    async def schedule_follow_up(self, plan_id: str, item_id: str, patient_id: str, doctor_id: str, d: dict[str, Any], base: datetime, not_before: datetime | None) -> None:
        target = add_days(start_of_day(base), _n(d.get("dayOffset"), 14))
        treating = (await self.mcp("provider_directory", "find_provider", user_id=doctor_id))["provider"]
        doctor = people.get_user(doctor_id)
        spec = str(d.get("specialty") or "").strip()
        spec_key = (await self.mcp("provider_directory", "normalize_specialty", specialty=spec))["specialty"] if spec else ""
        use_treating = d.get("withTreatingDoctor") is not False or not spec or bool(treating and spec_key in treating["specialties"])
        if use_treating and treating:
            candidates = [treating]
        else:
            candidates = (await self.mcp("provider_directory", "find_providers_by_specialty", specialty=spec, types=["DOCTOR", "SPECIALIST"]))["providers"]
        if treating and all(c["id"] != treating["id"] for c in candidates):
            candidates.append(treating)
        title = f"Follow-up consultation — {spec}" if spec and not use_treating else f"Follow-up consultation — {doctor.name if doctor else 'treating doctor'}"
        task = tasks.create_task(patient_id=patient_id, care_plan_id=plan_id, item_id=item_id, type="FOLLOW_UP", title=title, status="PENDING", due_date=target, meta=d)
        await self.audit("Follow-up task created", patient_id=patient_id, detail=f"Requesting availability from Scheduling service around {fmt_day(target)}")
        for provider in candidates:
            slots = (await self.mcp("scheduling", "find_available_slots", provider_id=provider["id"], from_date=iso(target), count=1, horizon_days=10, not_before=iso(not_before or now())))["slots"]
            if not slots:
                continue
            slot = slots[0]
            await self.mcp("scheduling", "book_slot", patient_id=patient_id, provider_id=provider["id"], start=slot["start"], end=slot["end"], kind="FOLLOW_UP", title=title, task_id=task.id)
            start = parse_dt(slot["start"])
            tasks.update_task(task.id, status="SCHEDULED", due_date=start)
            await self.audit("Scheduling service booked follow-up", patient_id=patient_id, level="SUCCESS", detail=f"{provider['name']} — {fmt(start)}", agent="SERVICE")
            await self.notify("PATIENT", patient_id, "APPOINTMENT", "Follow-up appointment booked", f"{provider['name']}, {fmt(start)} at {provider['organization']}.")
            await self.notify("DOCTOR", patient_id, "APPOINTMENT", "Follow-up booked", f"Patient follow-up on {fmt(start)}.")
            return
        tasks.update_task(task.id, status="FAILED")
        await self.audit("No follow-up slot available", patient_id=patient_id, level="WARNING")

    # ── referrals ────────────────────────────────────────────────────────────────────────

    async def create_referral(self, plan_id: str, item_id: str, patient_id: str, d: dict[str, Any], title: str, base: datetime, not_before: datetime | None) -> None:
        sessions = int(max(_n(d.get("sessions"), 1), 1))
        task = tasks.create_task(
            patient_id=patient_id, care_plan_id=plan_id, item_id=item_id, type="REFERRAL", title=title, status="PENDING",
            due_date=add_days(base, _n(d.get("preferredStartWithinDays"), 7)), meta=d,
        )  # fmt: skip
        ref = referrals.create(
            patient_id=patient_id,
            task_id=task.id,
            referral_type=str(d.get("referralType") or "Specialist"),
            reason=str(d.get("reason") or title),
            urgency=str(d.get("urgency") or "ROUTINE"),
            sessions=sessions,
            frequency_per_week=int(max(_n(d.get("frequencyPerWeek"), 1), 1)),
            duration_weeks=int(max(_n(d.get("durationWeeks"), 1), 1)),
            preferred_start_within_days=int(_n(d.get("preferredStartWithinDays"), 7)),
            timeline=dumps([{"status": "CREATED", "at": iso(now()), "note": "Referral requirement received from care plan"}]),
        )
        await self.audit(f"Referral created: {ref.referral_type}", patient_id=patient_id, detail=f"{sessions} session(s) — searching Provider Directory")
        await self.route_referral(ref.id, iso(base), iso(not_before) if not_before else None)

    @skill
    async def route_referral(self, referral_id: str, base: str | None = None, not_before: str | None = None, preferred_provider_id: str | None = None) -> bool:
        """Find a receiving doctor/provider → hold slots → have the package built → route the request."""
        ref = referrals.get(referral_id)
        if ref is None:
            raise ValueError("Referral not found")
        b, nb = parse_dt(base) or now(), parse_dt(not_before) or now()
        patient = (await self.mcp("ehr", "get_patient_records", patient_id=ref.patient_id))["patient"]
        own = (await self.mcp("provider_directory", "find_provider", user_id=patient["doctorId"]))["provider"]
        exclude = [x for x in ref.declined_provider_ids.split(",") if x] + ([own["id"]] if own else [])
        if preferred_provider_id:
            p = (await self.mcp("provider_directory", "find_provider", provider_id=preferred_provider_id))["provider"]
            providers = [p] if p else []
        else:
            providers = (await self.mcp("provider_directory", "find_providers_by_specialty", specialty=ref.referral_type, exclude=exclude, types=REFERRAL_PROVIDER_TYPES))["providers"]
        start = add_days(start_of_day(b), 0 if ref.urgency == "URGENT" else 1)

        for provider in providers:
            if ref.sessions > 1:
                slots = (await self.mcp("scheduling", "find_series_slots", provider_id=provider["id"], from_date=iso(start), sessions=ref.sessions, per_week=ref.frequency_per_week, not_before=iso(nb)))["slots"]
            else:
                slots = (await self.mcp("scheduling", "find_available_slots", provider_id=provider["id"], from_date=iso(start), count=1, horizon_days=14, not_before=iso(nb)))["slots"]
            if len(slots) < ref.sessions:
                continue
            first = parse_dt(slots[0]["start"])
            await self.audit(f"Provider Directory matched {provider['name']}", patient_id=ref.patient_id, detail=f"{provider['organization']} · {ref.sessions} slot(s) held from {fmt(first)}", agent="SERVICE")
            await self.mcp(
                "scheduling", "create_recurring_booking", patient_id=ref.patient_id, provider_id=provider["id"], slots=slots,
                kind="THERAPY" if ref.sessions > 1 else "SPECIALIST", title_prefix=ref.referral_type, referral_id=ref.id, task_id=ref.task_id, tentative=True,
            )  # fmt: skip
            referrals.update(ref.id, provider_id=provider["id"])

            # Clinical Intelligence → summary; Communication & Documentation → package
            summary = await self.ask("INTELLIGENCE", "referral_clinical_summary", referral_id=ref.id)
            doc = await self.ask("COMMUNICATION", "build_referral_package", referral_id=ref.id, clinical_summary=summary)
            note = f"{'Revised request (v' + str(ref.revision + 1) + ')' if ref.revision else 'Referral request'} sent to {provider['name']}"
            referrals.push_timeline(ref.id, "SENT", note, package_document_id=doc["id"])
            if ref.task_id:
                tasks.update_task(ref.task_id, status="IN_PROGRESS")
            has_portal = await self.notify_provider(
                provider["id"],
                "REFERRAL",
                f"{'Revised referral request' if ref.revision else 'New referral request'}: {ref.referral_type}",
                f"{ref.reason}. {ref.sessions} session(s) proposed from {fmt(first)}. Review the patient details and accept or reject.",
            )
            await self.audit(
                "Routing service delivered referral request", patient_id=ref.patient_id, level="SUCCESS",
                detail=f"{provider['name']} — referral requests inbox" if has_portal else f"{provider['name']} — secure e-mail (off-platform)", agent="SERVICE",
            )  # fmt: skip
            if not has_portal:
                await self.respond_to_referral(ref.id, "ACCEPT", "Confirmed by provider office (off-platform)", ref.revision > 0)
            return True

        referrals.push_timeline(ref.id, "CREATED", "Selected specialist has no capacity for this schedule" if preferred_provider_id else "No available specialist found — choose one and resend")
        if ref.task_id:
            tasks.update_task(ref.task_id, status="FAILED")
        await self.audit(f"No specialist available for {ref.referral_type}", patient_id=ref.patient_id, level="WARNING")
        await self.notify(
            "DOCTOR", ref.patient_id, "REFERRAL", "Referral needs attention",
            f"No {ref.referral_type} specialist with capacity was found. Open Referrals to choose one and resend.", f"/doctor/referrals?focus={ref.id}",
        )  # fmt: skip
        return False

    @skill
    async def respond_to_referral(self, referral_id: str, decision: str, note: str | None = None, refresh_patient_plan: bool = True) -> None:
        ref = referrals.get(referral_id)
        if ref is None:
            raise ValueError("Referral not found")
        if ref.status != "SENT":
            raise ValueError(f"Referral is {ref.status.lower()}, not awaiting a response")
        provider_name = ref.provider.name if ref.provider else None
        if decision == "DECLINE":
            # Goes back to the referring doctor with the reason — they revise and resend (manually or via the agent)
            await self.mcp("scheduling", "cancel_booking", referral_id=referral_id, statuses=["TENTATIVE"])
            declined = list(dict.fromkeys([x for x in ref.declined_provider_ids.split(",") if x] + ([ref.provider_id] if ref.provider_id else [])))
            referrals.push_timeline(
                referral_id, "DECLINED", f"{provider_name or 'Specialist'} rejected: {note}",
                declined_provider_ids=",".join(declined), decline_reason=note, declined_by_name=provider_name, provider_id=None,
            )  # fmt: skip
            if ref.task_id:
                tasks.update_task(ref.task_id, status="PENDING")
            await self.audit("Referral rejected — returned to referring doctor", patient_id=ref.patient_id, level="WARNING", detail=f"{provider_name}: {note}")
            await self.notify(
                "DOCTOR", ref.patient_id, "REFERRAL", f"Referral rejected: {ref.referral_type}",
                f'{provider_name}: "{note}". Edit & resend, or let the agent auto-revise it.', f"/doctor/referrals?focus={ref.id}",
            )  # fmt: skip
            return
        referrals.push_timeline(referral_id, "ACCEPTED", note or f"{provider_name} accepted the referral", provider_notes=note)
        appts = (await self.mcp("scheduling", "confirm_bookings", referral_id=referral_id))["appointments"]
        referrals.push_timeline(referral_id, "SCHEDULED", f"{len(appts)} appointment(s) confirmed")
        first = parse_dt(appts[0]["startsAt"]) if appts else None
        if ref.task_id:
            tasks.update_task(ref.task_id, status="SCHEDULED", due_date=first)
        first_label = fmt(first) if first else "—"
        await self.audit(f"{ref.referral_type} schedule confirmed", patient_id=ref.patient_id, level="SUCCESS", detail=f"{len(appts)} session(s), first on {first_label}")
        await self.notify("PATIENT", ref.patient_id, "APPOINTMENT", f"{ref.referral_type} scheduled", f"{len(appts)} session(s) with {provider_name}. First: {first_label}.")
        await self.notify(
            "DOCTOR", ref.patient_id, "REFERRAL", f"Referral accepted: {ref.referral_type}", f"{provider_name} accepted. {len(appts)} session(s) scheduled.", f"/doctor/referrals?focus={ref.id}"
        )
        if refresh_patient_plan:
            await self.ask("COMMUNICATION", "generate_patient_instructions", patient_id=ref.patient_id)

    @skill
    async def resend_referral(self, referral_id: str, revision: dict[str, Any], provider_id: str | None = None) -> bool:
        """Referring doctor resubmits a rejected (or unrouted) referral with revised details."""
        ref = referrals.get(referral_id)
        if ref is None:
            raise ValueError("Referral not found")
        if ref.status not in ("DECLINED", "CREATED"):
            raise ValueError(f"Referral is {ref.status.lower()} — only rejected or unrouted referrals can be resent")
        await self.mcp("scheduling", "cancel_booking", referral_id=referral_id, statuses=["TENTATIVE"])
        declined = [x for x in ref.declined_provider_ids.split(",") if x and x != provider_id]
        sessions = max(int(revision.get("sessions") or 1), 1)
        per_week = max(int(revision.get("frequencyPerWeek") or 1), 1)
        weeks = max(int(revision.get("durationWeeks") or 1), 1)
        referrals.update(
            referral_id,
            referral_type=revision["referralType"],
            reason=revision["reason"],
            sessions=sessions,
            frequency_per_week=per_week,
            duration_weeks=weeks,
            preferred_start_within_days=max(int(revision.get("preferredStartWithinDays") or 1), 0),
            urgency=revision["urgency"],
            note_to_specialist=revision.get("noteToSpecialist") or None,
            declined_provider_ids=",".join(declined),
            revision=ref.revision + 1,
        )
        # Keep the care plan in step with the revised referral
        if ref.task_id:
            task = tasks.get_task(ref.task_id)
            details = {
                "referralType": revision["referralType"], "reason": revision["reason"], "sessions": sessions, "frequencyPerWeek": per_week,
                "durationWeeks": weeks, "preferredStartWithinDays": revision.get("preferredStartWithinDays"), "urgency": revision["urgency"],
            }  # fmt: skip
            title = referral_title(revision["referralType"], sessions, per_week, weeks)
            tasks.update_task(ref.task_id, title=title, meta=details)
            if task and task.item_id:
                care_plans.update_item(task.item_id, title=title, details=details)
        note = revision.get("noteToSpecialist")
        referrals.push_timeline(referral_id, "RESUBMITTED", f"Revised by referring doctor: {note}" if note else "Revised by referring doctor")
        await self.audit(f"Referral revised and resubmitted (v{ref.revision + 2})", patient_id=ref.patient_id, detail=note)
        return await self.route_referral(referral_id, iso(now()), None, provider_id)

    @skill
    async def cancel_plan_item(self, item_id: str, reason: str, doctor_name: str) -> dict[str, Any]:
        """Doctor removes an item from an ACTIVE plan → cancel everything the agents set in motion for it."""
        item = care_plans.get_item(item_id)
        if item is None:
            raise ValueError("Care plan item not found")
        patient_id = item.care_plan.patient_id
        cancelled: list[str] = []
        for task in tasks.tasks_for_item(item_id):
            n = tasks.cancel_pending_doses(task_id=task.id)
            if n:
                cancelled.append(f"{n} pending dose(s)")
            appts = (await self.mcp("scheduling", "cancel_booking", task_id=task.id, statuses=["BOOKED", "TENTATIVE"]))["cancelled"]
            if appts:
                cancelled.append(f"{len(appts)} appointment(s)")
                for provider_id in dict.fromkeys(a["providerId"] for a in appts):
                    await self.notify_provider(provider_id, "APPOINTMENT", "Booking cancelled by referring doctor", f"{task.title} — {reason}")
            ref = referrals.by_task(task.id)
            if ref and ref.status not in ("COMPLETED", "CANCELLED"):
                referrals.push_timeline(ref.id, "CANCELLED", f"Cancelled by {doctor_name}: {reason}")
                cancelled.append("referral")
            if task.status not in ("COMPLETED", "CANCELLED"):
                tasks.update_task(task.id, status="CANCELLED")
        if item.category == "RED_FLAG":
            if await self.ask("MONITORING", "deactivate_rule", patient_id=patient_id, care_plan_id=item.care_plan_id, description=item.title):
                cancelled.append("monitoring rule")
        care_plans.update_item(item_id, included=False)
        await self.audit(f'{doctor_name} removed "{item.title}" from the active plan', patient_id=patient_id, detail=reason, agent="HUMAN")
        await self.audit("Cancelled downstream activity for removed item", patient_id=patient_id, level="SUCCESS", detail=", ".join(cancelled) if cancelled else "Nothing was scheduled for this item")
        await self.notify("PATIENT", patient_id, "CARE_PLAN", "Your care plan was updated", f"Your doctor removed: {item.title}.")
        await self.ask("COMMUNICATION", "generate_patient_instructions", patient_id=patient_id)
        return {"cancelled": cancelled}

    # ── tracking ─────────────────────────────────────────────────────────────────────────

    @skill
    async def record_dose(self, dose_id: str, status: str, note: str | None = None) -> dict[str, Any]:
        dose = tasks.record_dose(dose_id, status, note)
        await self.audit(
            f"Dose {status.lower()}: {dose.medication}", patient_id=dose.patient_id, level="SUCCESS" if status == "TAKEN" else "WARNING",
            detail=f"Scheduled {fmt(dose.scheduled_at)}{' — ' + note if note else ''}",
        )  # fmt: skip
        return dose.to_dict()

    @skill
    async def complete_appointment(self, appointment_id: str, notes: str | None = None) -> dict[str, Any]:
        appt = (await self.mcp("scheduling", "complete_booking", appointment_id=appointment_id, notes=notes))["appointment"]
        await self.audit(f"Completed: {appt['title']}", patient_id=appt["patientId"], level="SUCCESS", detail=notes)
        if appt.get("referralId"):
            ref = referrals.get(appt["referralId"])
            assert ref is not None
            done = len((await self.mcp("scheduling", "list_appointments", referral_id=ref.id, statuses=["COMPLETED"]))["appointments"])
            if done >= ref.sessions:
                referrals.push_timeline(ref.id, "COMPLETED", f"All {ref.sessions} session(s) completed")
                if ref.task_id:
                    tasks.update_task(ref.task_id, status="COMPLETED")
                await self.notify("DOCTOR", ref.patient_id, "REFERRAL", f"{ref.referral_type} completed", f"All {ref.sessions} session(s) completed.", f"/doctor/referrals?focus={ref.id}")
            elif ref.status == "SCHEDULED":
                referrals.push_timeline(ref.id, "IN_TREATMENT", "Treatment started")
                if ref.task_id:
                    tasks.update_task(ref.task_id, status="IN_PROGRESS")
        elif appt.get("taskId"):
            tasks.update_task(appt["taskId"], status="AWAITING_RESULT" if appt["kind"] == "TEST" else "COMPLETED")
        return appt

    @skill
    async def miss_appointment(self, appointment_id: str, reason: str = "Patient did not attend") -> dict[str, Any]:
        """Missed session → find replacement slot → update schedule; Monitoring agent is informed."""
        res = await self.mcp("scheduling", "reschedule_booking", appointment_id=appointment_id, reason=reason)
        appt, replacement = res["appointment"], res["replacement"]
        await self.audit(f"Missed: {appt['title']}", patient_id=appt["patientId"], level="WARNING", detail=reason)
        if replacement:
            when = fmt(parse_dt(replacement["startsAt"]))
            await self.audit("Scheduling service found replacement slot", patient_id=appt["patientId"], level="SUCCESS", detail=f"{appt['provider']['name']} — {when}", agent="SERVICE")
            await self.notify("PATIENT", appt["patientId"], "APPOINTMENT", "Missed appointment rescheduled", f"{appt['title']} has been moved to {when}.")
            await self.notify_provider(appt["providerId"], "APPOINTMENT", "Session rescheduled", f"{appt['title']} moved to {when}.")
        else:
            await self.audit("No replacement slot available", patient_id=appt["patientId"], level="WARNING")
        await self.ask("MONITORING", "on_missed_appointment", appointment_id=appt["id"])
        await self.ask("COMMUNICATION", "generate_patient_instructions", patient_id=appt["patientId"])
        return appt

    # ── background (scheduled) skills ────────────────────────────────────────────────────

    @skill
    async def sweep_doses(self, at: str | None = None) -> list[str]:
        """Mark doses not recorded 2 h after their time as missed and close finished medication courses."""
        t = parse_dt(at) or now()
        overdue = tasks.overdue_doses(t - timedelta(hours=2))
        for d in overdue:
            tasks.mark_dose(d.id, "MISSED")
            await self.audit(f"Dose not recorded — marked missed: {d.medication}", patient_id=d.patient_id, level="WARNING", detail=fmt(d.scheduled_at))
        tasks.complete_finished_courses()
        return list(dict.fromkeys(d.patient_id for d in overdue))

    @skill
    async def dispatch_reminders(self, at: str | None = None) -> int:
        """Send reminders for doses due within the next 30 minutes."""
        t = parse_dt(at) or now()
        due = tasks.doses_due_for_reminder(t)
        for d in due:
            await self.notify("PATIENT", d.patient_id, "REMINDER", f"Time for {d.medication}", f"{d.dose + ' — ' if d.dose else ''}scheduled at {fmt_time(d.scheduled_at)}. Tap to mark as taken.")
            tasks.mark_reminded(d.id)
        return len(due)

    @skill
    async def sweep_appointments(self) -> int:
        """Booked appointments left unconfirmed 24 h after their end time are treated as missed."""
        stale = (await self.mcp("scheduling", "find_unconfirmed_appointments", older_than_hours=24))["appointmentIds"]
        for appointment_id in stale:
            await self.miss_appointment(appointment_id, "Attendance not confirmed within 24 hours")
        return len(stale)
