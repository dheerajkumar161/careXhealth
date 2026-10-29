"""Referrals, nurse release decisions, nurses, notifications, overview, agents."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, or_, select

from app.agents.base import AgentError
from app.agents.orchestrator import orchestrator
from app.auth.deps import require_role, require_user
from app.auth.security import SessionUser
from app.core import llm
from app.core.db import session_scope
from app.core.i18n import normalize_language
from app.core.util import parse_json
from app.models import Appointment, Document, Notification, Patient, Provider, Referral, User
from app.repositories import referrals as referral_repo
from app.scheduler.jobs import run_full_cycle
from app.schemas.api import NotificationUpdate, TranslateIn, ReferralDecision, ReferralResend, ReleaseDecision
from app.services import records, translation

router = APIRouter(tags=["coordination"])


# ── referrals ──


@router.get("/api/referrals")
def referral_hub(user: SessionUser = Depends(require_role("DOCTOR"))) -> dict:
    """Doctor's referral hub: requests sent TO them (as a specialist) and referrals they sent FOR their patients."""
    with session_scope() as s:
        me = s.scalars(select(Provider).where(Provider.user_id == user.id)).first()
        incoming = list(s.scalars(select(Referral).where(or_(Referral.provider_id == me.id, Referral.declined_provider_ids.contains(me.id))).order_by(Referral.updated_at.desc())).unique()) if me else []
        my_patients = select(Patient.id).where(Patient.doctor_id == user.id)
        outgoing = list(s.scalars(select(Referral).where(Referral.patient_id.in_(my_patients)).order_by(Referral.updated_at.desc())).unique())
        q = select(Provider).where(Provider.accepts_referrals.is_(True), Provider.type != "TEST_CENTER")
        if me:
            q = q.where(Provider.id != me.id)
        specialists = list(s.scalars(q.order_by(Provider.name)))
        ref_ids = [r.id for r in incoming + outgoing]
        appts = list(s.scalars(select(Appointment).where(Appointment.referral_id.in_(ref_ids)).order_by(Appointment.starts_at)).unique()) if ref_ids else []
        doc_ids = [r.package_document_id for r in incoming + outgoing if r.package_document_id]
        docs = {d.id: {"id": d.id, "title": d.title, "content": d.content, "createdAt": d.to_dict()["createdAt"]} for d in s.scalars(select(Document).where(Document.id.in_(doc_ids))).unique()} if doc_ids else {}
        patients = {p.id: p for p in s.scalars(select(Patient).where(Patient.id.in_({r.patient_id for r in incoming + outgoing}))).unique()} if ref_ids else {}

        def patient_view(pid: str) -> dict:
            p = patients[pid]
            return {**p.to_dict(), "user": {"name": p.user.name, "phone": p.user.phone}, "doctor": {"name": p.doctor.name, "title": p.doctor.title}}

        def base(r: Referral, mine_only: bool) -> dict:
            return {
                **r.to_dict(),
                "timeline": parse_json(r.timeline, []),
                "package": docs.get(r.package_document_id or ""),
                "patient": patient_view(r.patient_id),
                "appointments": [a.to_dict() for a in appts if a.referral_id == r.id and (not mine_only or a.provider_id == me.id)],  # type: ignore[union-attr]
            }

        return {
            "incoming": [{**base(r, True), "rejectedByMe": r.provider_id != me.id} for r in incoming],  # type: ignore[union-attr]
            "outgoing": [{**base(r, False), "provider": {**r.provider.to_dict(), "user": {"name": r.provider.user.name} if r.provider.user else None} if r.provider else None} for r in outgoing],
            "specialists": [{"id": p.id, "name": p.name, "organization": p.organization, "specialties": p.specialties, "type": p.type, "userId": p.user_id, "hasPortal": bool(p.user_id)} for p in specialists],
        }


@router.patch("/api/referrals/{referral_id}")
async def referral_decision(referral_id: str, body: ReferralDecision, user: SessionUser = Depends(require_role("DOCTOR"))) -> dict:
    """The receiving (specialist) doctor accepts or rejects a referral request. Rejection requires a reason."""
    with session_scope() as s:
        me = s.scalars(select(Provider.id).where(Provider.user_id == user.id)).first()
    ref = referral_repo.get(referral_id)
    if ref is None or not me or ref.provider_id != me:
        raise HTTPException(404, "Referral request not found")
    note = (body.note or "").strip() or None
    if body.action == "DECLINE" and (not note or len(note) < 5):
        raise HTTPException(400, "Please explain why you are rejecting, so the referring doctor can revise the request")
    await orchestrator.execution.invoke("respond_to_referral", referral_id=referral_id, decision=body.action, note=note)
    return {"ok": True}


def _own_referral(referral_id: str, user: SessionUser) -> Referral:
    ref = referral_repo.get(referral_id)
    if ref is None:
        raise HTTPException(404, "Referral not found")
    with session_scope() as s:
        if s.get(Patient, ref.patient_id).doctor_id != user.id:  # type: ignore[union-attr]
            raise HTTPException(404, "Referral not found")
    return ref


@router.post("/api/referrals/{referral_id}/revise")
async def revise(referral_id: str, user: SessionUser = Depends(require_role("DOCTOR"))) -> dict:
    """Referring doctor asks the Planning agent to auto-revise a rejected referral. Returns a proposal only — nothing is saved."""
    ref = _own_referral(referral_id, user)
    if ref.status != "DECLINED":
        raise HTTPException(409, "Only rejected referrals can be auto-revised")
    return {"proposal": await orchestrator.planning.invoke("revise_referral", referral_id=referral_id)}


@router.post("/api/referrals/{referral_id}/resend")
async def resend(referral_id: str, body: ReferralResend, user: SessionUser = Depends(require_role("DOCTOR"))) -> dict:
    """Referring doctor applies revisions (their own or the agent's) — care-plan changes first, then the referral is re-routed."""
    ref = _own_referral(referral_id, user)
    if ref.status not in ("DECLINED", "CREATED"):
        raise HTTPException(409, f"This referral is {ref.status.lower()} and cannot be resent")
    if body.providerId:
        with session_scope() as s:
            p = s.get(Provider, body.providerId)
            if p is None or p.type == "TEST_CENTER" or p.user_id == user.id:
                raise HTTPException(400, "Choose a valid specialist")
    # The referral itself is revised by resend; never create a second referral from the change list
    changes = [{**c.model_dump(), "source": "DOCTOR"} for c in body.carePlanChanges if c.category != "REFERRAL"]
    engine = body.engine
    return await orchestrator.apply_referral_revision(referral_id, ref.patient_id, user.id, user.name, body.referral.model_dump(), changes, engine, body.providerId or None)


# ── nurse release ──


@router.patch("/api/nurse-release/{request_id}")
async def release_decision(request_id: str, body: ReleaseDecision, user: SessionUser = Depends(require_role("DOCTOR", "NURSE"))) -> dict:
    """Doctor approves (assigning the next nurse) or rejects; the requesting nurse may cancel while pending."""
    try:
        if body.action == "CANCEL":
            if user.role != "NURSE":
                raise HTTPException(403, "Only the requesting nurse can withdraw a request")
            await orchestrator.intelligence.invoke("cancel_release", request_id=request_id, nurse_id=user.id)
        elif body.action in ("ACCEPT", "DECLINE"):
            if user.role != "NURSE":
                raise HTTPException(403, "Only the incoming nurse can respond to a handoff")
            await orchestrator.intelligence.invoke("respond_handoff", request_id=request_id, nurse_id=user.id, decision=body.action, note=body.note)
        else:
            if user.role != "DOCTOR":
                raise HTTPException(403, "Only the treating doctor can decide on a release request")
            await orchestrator.intelligence.invoke("decide_release", request_id=request_id, doctor_id=user.id, decision=body.action, to_nurse_id=body.toNurseId, note=body.note)
    except AgentError as e:
        raise HTTPException(e.status, str(e)) from e
    return {"ok": True}


@router.get("/api/nurses")
def nurses(user: SessionUser = Depends(require_role("DOCTOR", "NURSE"))) -> dict:
    """Nurses with their current patient load — used when assigning or suggesting the next nurse."""
    with session_scope() as s:
        load = dict(s.execute(select(Patient.nurse_id, func.count()).where(Patient.status != "COMPLETED", Patient.nurse_id.is_not(None)).group_by(Patient.nurse_id)).all())
        rows = s.scalars(select(User).where(User.role == "NURSE").order_by(User.name))
        return {"nurses": [{"id": n.id, "name": n.name, "title": n.title, "load": load.get(n.id, 0)} for n in rows]}


# ── notifications ──


@router.get("/api/notifications")
async def notifications(user: SessionUser = Depends(require_user)) -> dict:
    with session_scope() as s:
        items = [n.to_dict() for n in s.scalars(select(Notification).where(Notification.user_id == user.id).order_by(Notification.created_at.desc()).limit(40))]
        unread = s.scalar(select(func.count()).select_from(Notification).where(Notification.user_id == user.id, Notification.read.is_(False))) or 0
        lang = normalize_language(s.get(User, user.id).language)  # type: ignore[union-attr]
    if lang != "en" and items:  # shown in the viewer's own language (cached, one batched model call for new strings)
        texts = [t for n in items for t in (n["title"], n["body"])]
        out, _ = await translation.translate_many(texts, lang)
        for i, n in enumerate(items):
            n["title"], n["body"] = out[2 * i], out[2 * i + 1]
    return {"items": items, "unread": unread}


_translate_calls: dict[str, list[float]] = {}


def _translate_budget(user_id: str, per_minute: int = 40) -> None:
    """Cheap in-memory guard so one session cannot drain the LLM quota through the translate endpoint."""
    import time

    t = time.monotonic()
    calls = [c for c in _translate_calls.get(user_id, []) if t - c < 60]
    if len(calls) >= per_minute:
        raise HTTPException(429, "Too many translation requests — try again in a minute", headers={"Retry-After": "30"})
    calls.append(t)
    _translate_calls[user_id] = calls


@router.post("/api/translate")
async def translate(body: TranslateIn, user: SessionUser = Depends(require_user)) -> dict:
    """Translate display strings into the caller's language (or `lang`). Used for dynamic plan/appointment text and UI labels."""
    _translate_budget(user.id)
    with session_scope() as s:
        lang = normalize_language(body.lang or s.get(User, user.id).language)  # type: ignore[union-attr]
    texts, ok = await translation.translate_many(body.texts, lang)
    return {"texts": texts, "language": lang, "translated": ok}


@router.post("/api/notifications")
def mark_read(body: NotificationUpdate, user: SessionUser = Depends(require_user)) -> dict:
    with session_scope() as s:
        q = select(Notification).where(Notification.user_id == user.id)
        if body.all:
            q = q.where(Notification.read.is_(False))
        elif body.id:
            q = q.where(Notification.id == body.id)
        else:
            return {"ok": True}
        for n in s.scalars(q):
            n.read = True
    return {"ok": True}


# ── overview & agents ──


@router.get("/api/overview")
async def overview(user: SessionUser = Depends(require_user)) -> dict:
    """Role-specific dashboard payload — each role only ever receives its own scoped data."""
    if user.role == "DOCTOR":
        return records.doctor_overview(user)
    if user.role == "NURSE":
        return records.nurse_overview(user)
    if user.role in ("PATIENT", "CAREGIVER"):
        return records.patient_overview(user)
    data = records.provider_overview(user)
    panels: dict[str, dict] = {}
    for a in data["appointments"]:
        q = a.pop("panelQuery", None)
        if q is not None and q not in panels:
            panels[q] = (await orchestrator.services.call("test_center", "get_test_details", name=q))["test"]
        a["panel"] = panels.get(q) if q is not None else None
    return data


@router.post("/api/agents/cycle")
async def agent_cycle(user: SessionUser = Depends(require_role("DOCTOR", "NURSE"))) -> dict:
    return await run_full_cycle()


@router.get("/api/agents")
def agents(user: SessionUser = Depends(require_user)) -> dict:
    """The five Microsoft Agent Framework agents, their skills and the hospital MCP servers they use."""
    return {
        "framework": "Microsoft Agent Framework",
        "agents": [{"id": a.id, "key": a.key, "name": a.name, "description": a.description, "skills": a.skills} for a in orchestrator.agents.values()],
        "mcpServers": {name: [f.name for f in tool.functions] for name, tool in orchestrator.services.tools.items()},
        "llm": llm.llm_status(),
    }
