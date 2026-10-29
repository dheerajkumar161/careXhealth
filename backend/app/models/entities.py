"""SQLAlchemy models — 1:1 port of prisma/schema.prisma (same entities, columns and string vocabularies).

Only addition: `User.department` (JWT claim used for department-scoped authorization).
JSON payload columns stay serialized strings, exactly as with Prisma.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, inspect
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.core.util import camel, iso, new_id, now


class Serializable:
    """Column values → camelCase dict with ISO datetimes (the shape the frontend already consumes)."""

    def to_dict(self, *, exclude: tuple[str, ...] = ()) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for attr in inspect(self).mapper.column_attrs:
            if attr.key in exclude:
                continue
            v = getattr(self, attr.key)
            out[camel(attr.key)] = iso(v) if isinstance(v, datetime) else v
        return out


def _id() -> Mapped[str]:
    return mapped_column(String, primary_key=True, default=new_id)


# ─────────────────────────── Identity & access ───────────────────────────


class User(Base, Serializable):
    __tablename__ = "users"
    id: Mapped[str] = _id()
    email: Mapped[str] = mapped_column(String, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String)
    name: Mapped[str] = mapped_column(String)
    role: Mapped[str] = mapped_column(String)  # DOCTOR | NURSE | PATIENT | TEST_CENTER | PROVIDER
    department: Mapped[str | None] = mapped_column(String, nullable=True)  # e.g. Orthopedics, Laboratory
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    phone: Mapped[str | None] = mapped_column(String, nullable=True)
    address: Mapped[str | None] = mapped_column(String, nullable=True)
    language: Mapped[str] = mapped_column(String, default="en", server_default="en")  # preferred language (ISO 639-1)
    notify_email: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")  # outbound channel opt-outs
    notify_sms: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    token_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")  # bump to revoke all sessions
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    provider_profile: Mapped[Provider | None] = relationship(back_populates="user", uselist=False)

    def lite(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "email": self.email, "phone": self.phone, "title": self.title}


# ─────────────────────────── Hospital / EHR data ───────────────────────────


class Patient(Base, Serializable):
    __tablename__ = "patients"
    id: Mapped[str] = _id()
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    mrn: Mapped[str] = mapped_column(String, unique=True)
    date_of_birth: Mapped[datetime] = mapped_column(DateTime)
    gender: Mapped[str] = mapped_column(String)
    blood_group: Mapped[str | None] = mapped_column(String, nullable=True)
    diagnosis: Mapped[str] = mapped_column(String)
    procedure: Mapped[str | None] = mapped_column(String, nullable=True)
    allergies: Mapped[str | None] = mapped_column(String, nullable=True)
    comorbidities: Mapped[str | None] = mapped_column(String, nullable=True)
    admission_date: Mapped[datetime] = mapped_column(DateTime)
    discharge_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String, default="ADMITTED")  # ADMITTED | DISCHARGED | RECOVERING | COMPLETED
    risk_level: Mapped[str] = mapped_column(String, default="LOW")
    risk_score: Mapped[int] = mapped_column(Integer, default=0, server_default="0")  # 0–100, see services/risk.py
    risk_factors: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON [{points,label}]
    address: Mapped[str | None] = mapped_column(String, nullable=True)
    emergency_contact: Mapped[str | None] = mapped_column(String, nullable=True)
    doctor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    nurse_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    user: Mapped[User] = relationship(foreign_keys=[user_id], lazy="joined")
    doctor: Mapped[User] = relationship(foreign_keys=[doctor_id], lazy="joined")
    nurse: Mapped[User | None] = relationship(foreign_keys=[nurse_id], lazy="joined")


# ─────────────────────────── Agent 1: Care Planning ───────────────────────────


class CarePlan(Base, Serializable):
    __tablename__ = "care_plans"
    id: Mapped[str] = _id()
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id", ondelete="CASCADE"), index=True)
    doctor_id: Mapped[str] = mapped_column(String)
    kind: Mapped[str] = mapped_column(String, default="INITIAL")  # INITIAL | AMENDMENT
    status: Mapped[str] = mapped_column(String, default="DRAFT")  # DRAFT | ACTIVE | REJECTED | SUPERSEDED | COMPLETED
    version: Mapped[int] = mapped_column(Integer, default=1)
    raw_instructions: Mapped[str] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    engine: Mapped[str | None] = mapped_column(String, nullable=True)  # ollama | rules
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)

    items: Mapped[list[CarePlanItem]] = relationship(back_populates="care_plan", order_by="CarePlanItem.sort_order", cascade="all, delete-orphan", lazy="selectin")


class CarePlanItem(Base, Serializable):
    __tablename__ = "care_plan_items"
    id: Mapped[str] = _id()
    care_plan_id: Mapped[str] = mapped_column(ForeignKey("care_plans.id", ondelete="CASCADE"), index=True)
    category: Mapped[str] = mapped_column(String)
    action: Mapped[str] = mapped_column(String, default="ADD")  # ADD | DISCONTINUE | MODIFY
    title: Mapped[str] = mapped_column(Text)
    details: Mapped[str] = mapped_column(Text, default="{}")  # JSON
    source: Mapped[str] = mapped_column(String, default="DOCTOR")  # DOCTOR | AI_SUGGESTED
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    included: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    care_plan: Mapped[CarePlan] = relationship(back_populates="items")


# ─────────────────────────── Agent 2: Execution & Scheduling ───────────────────────────


class CareTask(Base, Serializable):
    __tablename__ = "care_tasks"
    id: Mapped[str] = _id()
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id", ondelete="CASCADE"), index=True)
    care_plan_id: Mapped[str] = mapped_column(ForeignKey("care_plans.id", ondelete="CASCADE"))
    item_id: Mapped[str | None] = mapped_column(ForeignKey("care_plan_items.id", ondelete="SET NULL"), nullable=True)
    type: Mapped[str] = mapped_column(String)  # MEDICATION | INVESTIGATION | FOLLOW_UP | REFERRAL | MONITORING
    title: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String, default="PENDING")
    due_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    meta: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)


class MedicationDose(Base, Serializable):
    __tablename__ = "medication_doses"
    id: Mapped[str] = _id()
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id", ondelete="CASCADE"), index=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("care_tasks.id", ondelete="CASCADE"), index=True)
    medication: Mapped[str] = mapped_column(String)
    dose: Mapped[str | None] = mapped_column(String, nullable=True)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    status: Mapped[str] = mapped_column(String, default="PENDING")  # PENDING | TAKEN | SKIPPED | MISSED | CANCELLED
    recorded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reminder_sent: Mapped[bool] = mapped_column(Boolean, default=False)


class Provider(Base, Serializable):
    """Hospital provider directory (owned by the Provider Directory MCP service)."""

    __tablename__ = "providers"
    id: Mapped[str] = _id()
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), unique=True, nullable=True)
    name: Mapped[str] = mapped_column(String)
    organization: Mapped[str] = mapped_column(String)
    type: Mapped[str] = mapped_column(String)  # DOCTOR | THERAPIST | TEST_CENTER | SPECIALIST | HOME_CARE | COUNSELLOR | DIETITIAN
    specialties: Mapped[str] = mapped_column(Text)
    location: Mapped[str] = mapped_column(String)
    phone: Mapped[str | None] = mapped_column(String, nullable=True)
    rating: Mapped[float] = mapped_column(Float, default=4.5)
    work_start_hour: Mapped[int] = mapped_column(Integer, default=9)
    work_end_hour: Mapped[int] = mapped_column(Integer, default=17)
    slot_minutes: Mapped[int] = mapped_column(Integer, default=45)
    work_days: Mapped[str] = mapped_column(String, default="1,2,3,4,5")  # 0=Sun
    accepts_referrals: Mapped[bool] = mapped_column(Boolean, default=True)

    user: Mapped[User | None] = relationship(back_populates="provider_profile")


class Appointment(Base, Serializable):
    __tablename__ = "appointments"
    id: Mapped[str] = _id()
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id", ondelete="CASCADE"), index=True)
    task_id: Mapped[str | None] = mapped_column(ForeignKey("care_tasks.id", ondelete="SET NULL"), nullable=True)
    provider_id: Mapped[str] = mapped_column(ForeignKey("providers.id"), index=True)
    referral_id: Mapped[str | None] = mapped_column(ForeignKey("referrals.id", ondelete="SET NULL"), nullable=True)
    kind: Mapped[str] = mapped_column(String)  # FOLLOW_UP | TEST | THERAPY | SPECIALIST
    title: Mapped[str] = mapped_column(Text)
    starts_at: Mapped[datetime] = mapped_column(DateTime)
    ends_at: Mapped[datetime] = mapped_column(DateTime)
    location: Mapped[str | None] = mapped_column(String, nullable=True)
    sequence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String, default="BOOKED")  # TENTATIVE | BOOKED | COMPLETED | MISSED | CANCELLED | RESCHEDULED
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    rescheduled_from_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    provider: Mapped[Provider] = relationship(lazy="joined")


class Referral(Base, Serializable):
    __tablename__ = "referrals"
    id: Mapped[str] = _id()
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id", ondelete="CASCADE"), index=True)
    task_id: Mapped[str | None] = mapped_column(ForeignKey("care_tasks.id", ondelete="SET NULL"), unique=True, nullable=True)
    referral_type: Mapped[str] = mapped_column(String)
    reason: Mapped[str] = mapped_column(Text)
    urgency: Mapped[str] = mapped_column(String, default="ROUTINE")
    sessions: Mapped[int] = mapped_column(Integer, default=1)
    frequency_per_week: Mapped[int] = mapped_column(Integer, default=1)
    duration_weeks: Mapped[int] = mapped_column(Integer, default=1)
    preferred_start_within_days: Mapped[int] = mapped_column(Integer, default=7)
    status: Mapped[str] = mapped_column(String, default="CREATED")
    provider_id: Mapped[str | None] = mapped_column(ForeignKey("providers.id"), nullable=True)
    declined_provider_ids: Mapped[str] = mapped_column(Text, default="")
    decline_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    declined_by_name: Mapped[str | None] = mapped_column(String, nullable=True)
    note_to_specialist: Mapped[str | None] = mapped_column(Text, nullable=True)
    revision: Mapped[int] = mapped_column(Integer, default=0)
    package_document_id: Mapped[str | None] = mapped_column(String, nullable=True)
    provider_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    timeline: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)

    provider: Mapped[Provider | None] = relationship(lazy="joined")


# ─────────────────────────── Agent 3: Monitoring & Escalation ───────────────────────────


class Observation(Base, Serializable):
    __tablename__ = "observations"
    id: Mapped[str] = _id()
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String)
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    value2: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit: Mapped[str | None] = mapped_column(String, nullable=True)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String, default="PATIENT")
    recorded_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    flagged: Mapped[bool] = mapped_column(Boolean, default=False)

    recorded_by: Mapped[User | None] = relationship(lazy="joined")


class MonitoringRule(Base, Serializable):
    __tablename__ = "monitoring_rules"
    id: Mapped[str] = _id()
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id", ondelete="CASCADE"), index=True)
    care_plan_id: Mapped[str | None] = mapped_column(String, nullable=True)
    metric: Mapped[str] = mapped_column(String)
    operator: Mapped[str] = mapped_column(String)  # > | >= | < | <= | CONTAINS | COUNT_GTE
    threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    keywords: Mapped[str | None] = mapped_column(Text, nullable=True)
    window_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    action: Mapped[str] = mapped_column(String, default="NOTIFY_NURSE")
    severity: Mapped[str] = mapped_column(String, default="MEDIUM")
    description: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String, default="DOCTOR")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Alert(Base, Serializable):
    __tablename__ = "alerts"
    id: Mapped[str] = _id()
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id", ondelete="CASCADE"), index=True)
    rule_id: Mapped[str | None] = mapped_column(ForeignKey("monitoring_rules.id", ondelete="SET NULL"), nullable=True)
    category: Mapped[str] = mapped_column(String)
    severity: Mapped[str] = mapped_column(String)
    title: Mapped[str] = mapped_column(Text)
    message: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String, default="OPEN")  # OPEN | ACKNOWLEDGED | ESCALATED | RESOLVED
    escalation_level: Mapped[int] = mapped_column(Integer, default=1)
    assigned_to_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    dedupe_key: Mapped[str | None] = mapped_column(String, nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    acknowledged_by_id: Mapped[str | None] = mapped_column(String, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)
    escalate_after: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    history: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    assigned_to: Mapped[User | None] = relationship(lazy="joined")


# ─────────────────────────── Agents 4 & 5: Documents, Communication, Intelligence ───────────────────────────


class Document(Base, Serializable):
    __tablename__ = "documents"
    id: Mapped[str] = _id()
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id", ondelete="CASCADE"), index=True)
    task_id: Mapped[str | None] = mapped_column(ForeignKey("care_tasks.id", ondelete="SET NULL"), nullable=True)
    type: Mapped[str] = mapped_column(String)
    title: Mapped[str] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text)  # markdown
    data: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    visible_to_patient: Mapped[bool] = mapped_column(Boolean, default=False)
    shared_with_provider_id: Mapped[str | None] = mapped_column(String, nullable=True)
    review_status: Mapped[str | None] = mapped_column(String, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    engine: Mapped[str | None] = mapped_column(String, nullable=True)
    created_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    created_by: Mapped[User | None] = relationship(lazy="joined")


class Notification(Base, Serializable):
    __tablename__ = "notifications"
    id: Mapped[str] = _id()
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String)
    title: Mapped[str] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text)
    link: Mapped[str | None] = mapped_column(String, nullable=True)
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    dispatched: Mapped[bool] = mapped_column(Boolean, default=False, server_default="1")  # email/SMS copies queued (old rows: already handled)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class AgentEvent(Base, Serializable):
    __tablename__ = "agent_events"
    id: Mapped[str] = _id()
    patient_id: Mapped[str | None] = mapped_column(ForeignKey("patients.id", ondelete="CASCADE"), nullable=True, index=True)
    agent: Mapped[str] = mapped_column(String)  # PLANNING | EXECUTION | MONITORING | COMMUNICATION | INTELLIGENCE | SERVICE | HUMAN
    action: Mapped[str] = mapped_column(Text)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    level: Mapped[str] = mapped_column(String, default="INFO")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class ChatMessage(Base, Serializable):
    __tablename__ = "chat_messages"
    id: Mapped[str] = _id()
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String)  # user | assistant
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class NurseReleaseRequest(Base, Serializable):
    """A nurse asks to be released from a patient; the treating doctor approves and assigns the next nurse."""

    __tablename__ = "nurse_release_requests"
    id: Mapped[str] = _id()
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id", ondelete="CASCADE"), index=True)
    from_nurse_id: Mapped[str] = mapped_column(String)
    suggested_nurse_id: Mapped[str | None] = mapped_column(String, nullable=True)
    to_nurse_id: Mapped[str | None] = mapped_column(String, nullable=True)
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String, default="PENDING")
    kind: Mapped[str] = mapped_column(String, default="REQUEST")
    handoff_document_id: Mapped[str | None] = mapped_column(String, nullable=True)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_by_id: Mapped[str | None] = mapped_column(String, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


# ─────────────────────────── Security ───────────────────────────


class AuditLog(Base, Serializable):
    """Append-only trail of security- and PHI-relevant actions (never updated or deleted by the app)."""

    __tablename__ = "audit_logs"
    id: Mapped[str] = _id()
    at: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)
    actor_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    actor_role: Mapped[str | None] = mapped_column(String, nullable=True)
    action: Mapped[str] = mapped_column(String, index=True)  # e.g. LOGIN, PLAN_APPROVE, RECORD_VIEW
    entity_type: Mapped[str | None] = mapped_column(String, nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    patient_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip: Mapped[str | None] = mapped_column(String, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String, nullable=True)


class LoginAttempt(Base, Serializable):
    """Failed-login ledger backing the rate limiter / lockout (DB-backed so it survives restarts)."""

    __tablename__ = "login_attempts"
    id: Mapped[str] = _id()
    at: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)
    email: Mapped[str] = mapped_column(String, index=True)
    ip: Mapped[str | None] = mapped_column(String, nullable=True, index=True)


# ─────────────────────────── Localisation ───────────────────────────


class TranslationCache(Base, Serializable):
    """Translations of recurring strings (UI labels, notification templates, plan items) so each is paid for once."""

    __tablename__ = "translation_cache"
    __table_args__ = (UniqueConstraint("lang", "source_hash", name="uq_translation_lang_hash"),)
    id: Mapped[str] = _id()
    lang: Mapped[str] = mapped_column(String, index=True)
    source_hash: Mapped[str] = mapped_column(String)
    source: Mapped[str] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text)
    engine: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


# ─────────────────────────── Caregiver access (patient-granted, revocable) ───────────────────────────


class CaregiverAccess(Base, Serializable):
    """A family member/caregiver the PATIENT has invited to view their recovery (read-only)."""

    __tablename__ = "caregiver_access"
    id: Mapped[str] = _id()
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id", ondelete="CASCADE"), index=True)
    caregiver_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    invite_email: Mapped[str] = mapped_column(String)
    invite_name: Mapped[str | None] = mapped_column(String, nullable=True)
    token_hash: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    status: Mapped[str] = mapped_column(String, default="INVITED")  # INVITED | ACTIVE | REVOKED
    expires_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


# ─────────────────────────── Outbound delivery (email / SMS) ───────────────────────────


class Delivery(Base, Serializable):
    """One outbound message (email or SMS) for a notification; retried with backoff, then dead-lettered (FAILED)."""

    __tablename__ = "deliveries"
    id: Mapped[str] = _id()
    notification_id: Mapped[str] = mapped_column(ForeignKey("notifications.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    channel: Mapped[str] = mapped_column(String)  # EMAIL | SMS
    status: Mapped[str] = mapped_column(String, default="PENDING", index=True)  # PENDING | SENT | FAILED | SKIPPED
    urgent: Mapped[bool] = mapped_column(Boolean, default=False)  # urgent messages ignore quiet hours
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
