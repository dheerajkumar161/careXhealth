"""Users, patient chat and nurse-release requests."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select, update

from app.core.db import session_scope
from app.models import ChatMessage, NurseReleaseRequest, User


def get_user(user_id: str) -> User | None:
    with session_scope() as s:
        return s.get(User, user_id)


# ── chat ──
def add_chat(patient_id: str, role: str, content: str) -> ChatMessage:
    with session_scope() as s:
        m = ChatMessage(patient_id=patient_id, role=role, content=content)
        s.add(m)
        s.flush()
        return m


def recent_chat(patient_id: str, limit: int = 8) -> list[ChatMessage]:
    with session_scope() as s:
        return list(s.scalars(select(ChatMessage).where(ChatMessage.patient_id == patient_id).order_by(ChatMessage.created_at.desc()).limit(limit)))


# ── nurse release ──
def pending_release(patient_id: str) -> NurseReleaseRequest | None:
    with session_scope() as s:
        return s.scalars(select(NurseReleaseRequest).where(NurseReleaseRequest.patient_id == patient_id, NurseReleaseRequest.status.in_(["PENDING", "AWAITING_NURSE"]))).first()


def get_release(request_id: str) -> NurseReleaseRequest | None:
    with session_scope() as s:
        return s.get(NurseReleaseRequest, request_id)


def create_release(**fields: Any) -> NurseReleaseRequest:
    with session_scope() as s:
        r = NurseReleaseRequest(**fields)
        s.add(r)
        s.flush()
        return r


def update_release(request_id: str, **fields: Any) -> None:
    with session_scope() as s:
        r = s.get(NurseReleaseRequest, request_id)
        if r:
            for k, v in fields.items():
                setattr(r, k, v)


def cancel_pending_releases(patient_id: str, note: str, at: Any) -> None:
    with session_scope() as s:
        s.execute(update(NurseReleaseRequest).where(NurseReleaseRequest.patient_id == patient_id, NurseReleaseRequest.status.in_(["PENDING", "AWAITING_NURSE"])).values(status="CANCELLED", decision_note=note, decided_at=at))
