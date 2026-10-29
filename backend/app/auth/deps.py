"""FastAPI auth dependencies: require_user / require_role / require_department / patient row-level access."""
from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select

from app.core.db import session_scope
from app.models import Appointment, CaregiverAccess, Patient, Provider, Referral, User

from .security import SESSION_COOKIE, SessionUser, verify_session

PARTNER_ROLES = ("PROVIDER", "TEST_CENTER")


def _token(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.cookies.get(SESSION_COOKIE)


def require_user(request: Request) -> SessionUser:
    user = verify_session(_token(request))
    if user is None:
        raise HTTPException(401, "Not authenticated")
    # A valid token can outlive its account (e.g. after a database reset) — treat it as signed out
    with session_scope() as s:
        row = s.get(User, user.id)
        if row is None or row.token_version != user.tv:
            raise HTTPException(401, "Session expired — please sign in again")
    return user


def require_role(*roles: str) -> Callable[..., SessionUser]:
    def dep(user: SessionUser = Depends(require_user)) -> SessionUser:
        if roles and user.role not in roles:
            raise HTTPException(403, "You do not have access to this resource")
        return user

    return dep


def require_department(*departments: str) -> Callable[..., SessionUser]:
    """Department-scoped authorization (JWT `department` claim)."""
    wanted = {d.lower() for d in departments}

    def dep(user: SessionUser = Depends(require_user)) -> SessionUser:
        if (user.department or "").lower() not in wanted:
            raise HTTPException(403, f"This action is restricted to the {', '.join(departments)} department")
        return user

    return dep


def can_access_patient(user: SessionUser, patient_id: str) -> bool:
    """Row-level access: may this user see this patient's record? (unchanged from the legacy app)"""
    with session_scope() as s:
        p = s.get(Patient, patient_id)
        if p is None:
            return False
        if user.role == "PATIENT":
            return p.user_id == user.id
        if user.role == "CAREGIVER":
            return s.scalars(select(CaregiverAccess.id).where(CaregiverAccess.patient_id == patient_id, CaregiverAccess.caregiver_id == user.id, CaregiverAccess.status == "ACTIVE")).first() is not None
        if user.role == "DOCTOR":
            return p.doctor_id == user.id
        if user.role == "NURSE":
            return p.nurse_id == user.id
        if user.role in PARTNER_ROLES:
            provider = s.scalars(select(Provider).where(Provider.user_id == user.id)).first()
            if provider is None:
                return False
            link = s.scalars(select(Referral.id).where(Referral.patient_id == patient_id, Referral.provider_id == provider.id, Referral.status.not_in(["DECLINED", "CANCELLED"]))).first()
            if link:
                return True
            return s.scalars(select(Appointment.id).where(Appointment.patient_id == patient_id, Appointment.provider_id == provider.id)).first() is not None
    return False


def require_patient_access(user: SessionUser, patient_id: str) -> None:
    if not can_access_patient(user, patient_id):
        raise HTTPException(403, "You do not have access to this patient")


def provider_for(user: SessionUser) -> Provider:
    with session_scope() as s:
        p = s.scalars(select(Provider).where(Provider.user_id == user.id)).first()
    if p is None:
        raise HTTPException(403, "No provider profile linked to this account")
    return p
