"""Append-only audit trail. Failures to write an audit row never break the request, but are logged."""
from __future__ import annotations

import logging
from typing import Any

from app.auth.security import SessionUser
from app.core.db import session_scope
from app.core.logging import client_ip_var, request_id_var
from app.models import AuditLog

log = logging.getLogger("carexhealth.audit")


def audit(
    action: str,
    actor: SessionUser | None = None,
    *,
    entity_type: str | None = None,
    entity_id: str | None = None,
    patient_id: str | None = None,
    detail: str | None = None,
    actor_id: str | None = None,
) -> None:
    try:
        with session_scope() as s:
            s.add(
                AuditLog(
                    actor_id=actor.id if actor else actor_id, actor_role=actor.role if actor else None, action=action, entity_type=entity_type,
                    entity_id=entity_id, patient_id=patient_id, detail=(detail or None) and detail[:500], ip=client_ip_var.get(), request_id=request_id_var.get(),
                )
            )  # fmt: skip
    except Exception:  # noqa: BLE001
        log.exception("audit write failed for %s", action)


def audit_rows(*, limit: int = 100, actor_id: str | None = None, action: str | None = None, patient_id: str | None = None) -> list[dict[str, Any]]:
    from sqlalchemy import select

    with session_scope() as s:
        q = select(AuditLog).order_by(AuditLog.at.desc(), AuditLog.id.desc()).limit(min(max(limit, 1), 500))
        if actor_id:
            q = q.where(AuditLog.actor_id == actor_id)
        if action:
            q = q.where(AuditLog.action == action)
        if patient_id:
            q = q.where(AuditLog.patient_id == patient_id)
        return [r.to_dict() for r in s.scalars(q)]
