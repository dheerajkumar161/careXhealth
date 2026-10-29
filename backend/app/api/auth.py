"""/api/auth — login (throttled), logout, me, profile, change-password, signup (JWT in an httpOnly cookie; also returned for Bearer clients)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select

from app.agents.orchestrator import orchestrator
from app.auth import throttle
from app.auth.deps import _token, require_user
from app.auth.security import SESSION_COOKIE, SessionUser, hash_password, sign_session, verify_password, verify_session
from app.core import llm
from app.core.config import get_settings
from app.core.constants import ROLE_HOME
from app.core.db import session_scope
from app.core.i18n import language_list, normalize_language
from app.core.logging import client_ip_var
from app.core.metrics import LOGIN_FAILURES
from app.models import Document, Patient, Provider, User
from app.schemas.api import ChangePassword, Login, ProfileUpdate, Signup
from app.services.audit import audit

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _session_user(user: User) -> SessionUser:
    return SessionUser(id=user.id, role=user.role, department=user.department, name=user.name, email=user.email, tv=user.token_version)


def _session_response(response: Response, user: User) -> dict:
    token = sign_session(_session_user(user))
    response.set_cookie(SESSION_COOKIE, token, httponly=True, samesite="lax", secure=get_settings().secure_cookies, path="/", max_age=get_settings().session_hours * 3600)
    return {"ok": True, "redirect": ROLE_HOME.get(user.role, "/login"), "token": token}


@router.post("/login")
def login(body: Login, request: Request, response: Response) -> dict:
    email = body.email.lower().strip()
    ip = client_ip_var.get() or (request.client.host if request.client else None)
    wait = throttle.locked_for(email, ip)
    if wait:
        audit("LOGIN_LOCKED", detail=email)
        raise HTTPException(429, f"Too many failed attempts. Try again in {wait} minute(s).", headers={"Retry-After": str(wait * 60)})
    with session_scope() as s:
        user = s.scalars(select(User).where(User.email == email)).first()
    if user is None or not verify_password(body.password, user.password_hash):
        throttle.record_failure(email, ip)
        LOGIN_FAILURES.inc()
        audit("LOGIN_FAILED", detail=email, actor_id=user.id if user else None)
        raise HTTPException(401, "Invalid email or password")
    if body.role and not (user.role == body.role or {user.role, body.role} <= {"PROVIDER", "TEST_CENTER"}):
        raise HTTPException(403, f"This account is not registered as a {body.role.lower()}")
    throttle.clear(email)
    audit("LOGIN", _session_user(user))
    return _session_response(response, user)


@router.post("/logout")
def logout(request: Request, response: Response) -> dict:
    who = verify_session(_token(request))
    if who:
        audit("LOGOUT", who)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


def user_payload(u: User, s) -> dict:  # noqa: ANN001
    profile = u.provider_profile
    out = {
        "id": u.id, "name": u.name, "email": u.email, "role": u.role, "department": u.department, "title": u.title, "phone": u.phone,
        "address": u.address, "language": normalize_language(u.language), "notifyEmail": u.notify_email, "notifySms": u.notify_sms,
        "providerProfile": {"organization": profile.organization, "type": profile.type, "location": profile.location} if profile else None,
        "patientProfile": None,
    }  # fmt: skip
    if u.role == "PATIENT":
        p = s.scalars(select(Patient).where(Patient.user_id == u.id)).first()
        if p:
            out["patientProfile"] = {"id": p.id, "mrn": p.mrn, "emergencyContact": p.emergency_contact, "address": p.address}
    return out


@router.get("/me")
def me(session: SessionUser = Depends(require_user)) -> dict:
    with session_scope() as s:
        u = s.get(User, session.id)
        assert u is not None
        user = user_payload(u, s)
    return {"user": user, "ai": llm.llm_status(), "demoMode": get_settings().demo_mode, "languages": language_list()}


@router.patch("/profile")
async def update_profile(body: ProfileUpdate, session: SessionUser = Depends(require_user)) -> dict:
    """Every role edits their own details; email, role and department are not self-editable."""
    if body.name is not None and not body.name.strip():
        raise HTTPException(400, "Name cannot be empty")
    changed: list[str] = []
    with session_scope() as s:
        u = s.get(User, session.id)
        assert u is not None
        for field in ("name", "phone", "title", "address"):
            v = getattr(body, field)
            if v is not None and (v.strip() or None) != getattr(u, field):
                setattr(u, field, v.strip() or None)
                changed.append(field)
        for flag, col in (("notifyEmail", "notify_email"), ("notifySms", "notify_sms")):
            v = getattr(body, flag)
            if v is not None and v != getattr(u, col):
                setattr(u, col, v)
                changed.append(flag)
        if body.language is not None and body.language != u.language:
            u.language = body.language
            changed.append("language")
        if u.role == "PATIENT":
            p = s.scalars(select(Patient).where(Patient.user_id == u.id)).first()
            if p:
                if body.emergencyContact is not None:
                    p.emergency_contact = body.emergencyContact.strip() or None
                    changed.append("emergencyContact")
                if body.address is not None:
                    p.address = body.address.strip() or None
        prov = u.provider_profile
        if prov is not None:
            if body.organization is not None and body.organization.strip():
                prov.organization = body.organization.strip()
                if prov.type == "TEST_CENTER":
                    prov.name = prov.organization
                changed.append("organization")
            if body.location is not None:
                prov.location = body.location.strip() or "—"
                changed.append("location")
            if "name" in changed and prov.type == "DOCTOR":
                prov.name = u.name
            if "phone" in changed:
                prov.phone = u.phone
        s.flush()
        user = user_payload(u, s)
        sess = _session_user(u)
    audit("PROFILE_UPDATE", sess, entity_type="User", entity_id=sess.id, detail=",".join(changed))
    if "language" in changed and sess.role == "PATIENT" and user["patientProfile"]:
        # Re-render the patient's recovery plan in the newly chosen language (only if one has been published).
        pid = user["patientProfile"]["id"]
        with session_scope() as s:
            has_plan = s.scalars(select(Document.id).where(Document.patient_id == pid, Document.type == "PATIENT_INSTRUCTIONS")).first() is not None
        if has_plan:
            await orchestrator.communication.invoke("generate_patient_instructions", patient_id=pid)
    return {"user": user}


@router.post("/change-password")
def change_password(body: ChangePassword, response: Response, session: SessionUser = Depends(require_user)) -> dict:
    """Any role. Bumps the user's token version, which signs out every other device; this device gets a fresh session."""
    with session_scope() as s:
        u = s.get(User, session.id)
        assert u is not None
        if not verify_password(body.currentPassword, u.password_hash):
            audit("PASSWORD_CHANGE_FAILED", session)
            raise HTTPException(400, "Current password is incorrect")
        if verify_password(body.newPassword, u.password_hash):
            raise HTTPException(400, "New password must be different from the current one")
        u.password_hash = hash_password(body.newPassword)
        u.token_version += 1
        s.flush()
        result = _session_response(response, u)
    audit("PASSWORD_CHANGE", session)
    return {**result, "message": "Password updated. Other devices have been signed out."}


@router.post("/signup")
async def signup(body: Signup, response: Response) -> dict:
    """Self-registration for clinicians, test centers and care partners. Patients are registered by their doctor."""
    code = get_settings().signup_invite_code
    if code and body.inviteCode != code:
        raise HTTPException(403, "Invalid hospital invite code")
    if body.role == "DOCTOR" and not (body.specialty or "").strip():
        raise HTTPException(400, "Select your specialty")
    if body.role in ("PROVIDER", "TEST_CENTER") and not (body.organization or "").strip():
        raise HTTPException(400, "Enter the test center name")
    email = body.email.lower().strip()
    with session_scope() as s:
        if s.scalars(select(User).where(User.email == email)).first():
            raise HTTPException(409, "An account with this email already exists — sign in instead")
    # The legacy sign-up form's "test center" option used role PROVIDER; it is normalized to TEST_CENTER.
    role = "TEST_CENTER" if body.role == "PROVIDER" else body.role
    specialty_key = (await orchestrator.services.call("provider_directory", "normalize_specialty", specialty=body.specialty))["specialty"] if role == "DOCTOR" else ""
    department = body.department or (specialty_key.title() if role == "DOCTOR" else "Nursing" if role == "NURSE" else "Laboratory")
    title = body.title or (body.specialty if role == "DOCTOR" else "Staff Nurse" if role == "NURSE" else "Test Center")
    with session_scope() as s:
        user = User(email=email, name=body.name.strip(), language=normalize_language(body.language), role=role, department=department, phone=body.phone or None, title=title, password_hash=hash_password(body.password))
        s.add(user)
        s.flush()
        if role == "DOCTOR":
            therapy = specialty_key in ("physiotherapy", "occupational therapy", "speech therapy")
            s.add(
                Provider(
                    user_id=user.id, name=user.name, organization=(body.organization or "").strip() or "CareXHealth Hospital", type="DOCTOR",
                    specialties=",".join(dict.fromkeys([specialty_key, body.specialty.strip().lower()])),  # type: ignore[union-attr]
                    location=(body.location or "").strip() or "—", phone=body.phone or None, accepts_referrals=body.acceptsReferrals,
                    work_start_hour=9, work_end_hour=17, slot_minutes=45 if therapy else 30, work_days="1,2,3,4,5,6",
                )
            )  # fmt: skip
        if role == "TEST_CENTER":
            org = body.organization.strip()  # type: ignore[union-attr]
            s.add(
                Provider(
                    user_id=user.id, name=org, organization=org, type="TEST_CENTER", specialties="laboratory,pathology,radiology", location=(body.location or "").strip() or "—",
                    phone=body.phone or None, work_start_hour=7, work_end_hour=19, slot_minutes=15, work_days="0,1,2,3,4,5,6",
                )
            )  # fmt: skip
    audit("SIGNUP", _session_user(user), detail=role)
    return _session_response(response, user)
