"""/api/audit and /api/admin — the audit trail (admins: everything; doctors: their own patients) and a read-only user directory."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from app.auth.deps import require_role
from app.auth.security import SessionUser
from app.core.db import session_scope
from app.models import AuditLog, Patient, User

router = APIRouter(tags=["admin"])


@router.get("/api/audit")
def audit_trail(limit: int = 100, action: str | None = None, patientId: str | None = None, actorId: str | None = None, user: SessionUser = Depends(require_role("ADMIN", "DOCTOR"))) -> dict:  # noqa: N803
    with session_scope() as s:
        q = select(AuditLog).order_by(AuditLog.at.desc(), AuditLog.id.desc()).limit(min(max(limit, 1), 500))
        if action:
            q = q.where(AuditLog.action == action)
        if actorId:
            q = q.where(AuditLog.actor_id == actorId)
        if patientId:
            q = q.where(AuditLog.patient_id == patientId)
        if user.role == "DOCTOR":
            mine = list(s.scalars(select(Patient.id).where(Patient.doctor_id == user.id)))
            q = q.where((AuditLog.patient_id.in_(mine)) | (AuditLog.actor_id == user.id))
        rows = [r.to_dict() for r in s.scalars(q)]
        names = {u.id: u.name for u in s.scalars(select(User).where(User.id.in_({r["actorId"] for r in rows if r["actorId"]})))} if rows else {}
    for r in rows:
        r["actorName"] = names.get(r["actorId"]) if r["actorId"] else None
    return {"entries": rows}


@router.get("/api/admin/users")
def users(user: SessionUser = Depends(require_role("ADMIN"))) -> dict:
    with session_scope() as s:
        rows = [{"id": u.id, "name": u.name, "email": u.email, "role": u.role, "department": u.department, "language": u.language, "createdAt": u.created_at.isoformat()} for u in s.scalars(select(User).order_by(User.created_at))]
    return {"users": rows}


@router.post("/api/admin/users/{user_id}/revoke-sessions")
def revoke_sessions(user_id: str, admin: SessionUser = Depends(require_role("ADMIN"))) -> dict:
    """Sign a user out everywhere (e.g. lost device)."""
    from app.services.audit import audit

    with session_scope() as s:
        u = s.get(User, user_id)
        if u is None:
            raise HTTPException(404, "User not found")
        u.token_version += 1
    audit("SESSIONS_REVOKED", admin, entity_type="User", entity_id=user_id)
    return {"ok": True}
