"""/api/caregivers — a patient invites family/caregivers to a read-only view of their recovery, and can revoke at any time."""
from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select

from app.auth.deps import require_role
from app.auth.security import SessionUser, check_password_policy, hash_password, verify_password
from app.core.db import session_scope
from app.core.i18n import normalize_language
from app.core.util import now
from app.models import CaregiverAccess, Patient, User
from app.services.audit import audit

router = APIRouter(tags=["caregivers"])
INVITE_DAYS = 7


class InviteIn(BaseModel):
    email: EmailStr
    name: str | None = Field(None, max_length=120)


class AcceptIn(BaseModel):
    token: str = Field(min_length=10, max_length=200)
    name: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=8, max_length=200)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _patient_id(user: SessionUser) -> str:
    with session_scope() as s:
        pid = s.scalars(select(Patient.id).where(Patient.user_id == user.id)).first()
    if not pid:
        raise HTTPException(404, "No patient record linked to this account")
    return pid


@router.get("/api/caregivers")
def list_caregivers(user: SessionUser = Depends(require_role("PATIENT"))) -> dict:
    pid = _patient_id(user)
    with session_scope() as s:
        rows = [
            {"id": c.id, "email": c.invite_email, "name": c.invite_name, "status": c.status, "createdAt": c.created_at.isoformat(), "acceptedAt": c.accepted_at.isoformat() if c.accepted_at else None}
            for c in s.scalars(select(CaregiverAccess).where(CaregiverAccess.patient_id == pid, CaregiverAccess.status != "REVOKED").order_by(CaregiverAccess.created_at.desc()))
        ]
    return {"caregivers": rows}


@router.post("/api/caregivers")
def invite(body: InviteIn, user: SessionUser = Depends(require_role("PATIENT"))) -> dict:
    """Returns a one-time sign-up link (valid 7 days) for the patient to share; the secret is never stored in clear."""
    pid = _patient_id(user)
    email = body.email.lower().strip()
    token = secrets.token_urlsafe(24)
    with session_scope() as s:
        if s.scalars(select(CaregiverAccess.id).where(CaregiverAccess.patient_id == pid, CaregiverAccess.invite_email == email, CaregiverAccess.status != "REVOKED")).first():
            raise HTTPException(409, "This person already has access or a pending invite")
        c = CaregiverAccess(patient_id=pid, invite_email=email, invite_name=body.name, token_hash=_hash(token), expires_at=now() + timedelta(days=INVITE_DAYS))
        s.add(c)
        s.flush()
        cid = c.id
    audit("CAREGIVER_INVITED", user, entity_type="CaregiverAccess", entity_id=cid, patient_id=pid, detail=email)
    return {"id": cid, "link": f"/join?token={token}", "expiresInDays": INVITE_DAYS}


@router.delete("/api/caregivers/{access_id}")
def revoke(access_id: str, user: SessionUser = Depends(require_role("PATIENT"))) -> dict:
    pid = _patient_id(user)
    with session_scope() as s:
        c = s.get(CaregiverAccess, access_id)
        if c is None or c.patient_id != pid:
            raise HTTPException(404, "Not found")
        c.status, c.token_hash = "REVOKED", None
        if c.caregiver_id:  # sign the caregiver out so access ends immediately
            u = s.get(User, c.caregiver_id)
            if u is not None:
                u.token_version += 1
    audit("CAREGIVER_REVOKED", user, entity_type="CaregiverAccess", entity_id=access_id, patient_id=pid)
    return {"ok": True}


@router.post("/api/auth/accept-invite")
def accept(body: AcceptIn, response: Response) -> dict:
    """Caregiver creates (or re-uses) their CAREGIVER account using the invite link."""
    from app.api.auth import _session_response

    with session_scope() as s:
        c = s.scalars(select(CaregiverAccess).where(CaregiverAccess.token_hash == _hash(body.token), CaregiverAccess.status == "INVITED")).first()
        if c is None or c.expires_at < now():
            raise HTTPException(400, "This invite link is invalid or has expired — ask the patient for a new one")
        user = s.scalars(select(User).where(User.email == c.invite_email)).first()
        if user is None:
            check_password_policy(body.password)
            patient = s.get(Patient, c.patient_id)
            patient_user = s.get(User, patient.user_id) if patient else None
            user = User(
                email=c.invite_email, name=body.name.strip(), role="CAREGIVER", department="Family", title="Caregiver", password_hash=hash_password(body.password),
                language=normalize_language(patient_user.language if patient_user else None),
            )  # fmt: skip
            s.add(user)
            s.flush()
        elif user.role != "CAREGIVER" or not verify_password(body.password, user.password_hash):
            raise HTTPException(400, "An account with this email already exists — use that account's password, or a different email")
        c.caregiver_id, c.status, c.accepted_at, c.token_hash = user.id, "ACTIVE", now(), None
        pid, cid = c.patient_id, c.id
        s.flush()
        result = _session_response(response, user)
    audit("CAREGIVER_ACCEPTED", actor_id=user.id, entity_type="CaregiverAccess", entity_id=cid, patient_id=pid)
    return result
