"""Request/response contracts for the REST API (ports of the zod schemas in the Next.js route handlers)."""
from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.auth.security import check_password_policy
from app.core.i18n import LANGUAGES

from .clinical import Category, ItemAction, Urgency

MAX_IMAGE_BYTES = 6 * 1024 * 1024
DATA_URL = re.compile(r"^data:image/(png|jpe?g|webp|gif);base64,[A-Za-z0-9+/=]+$")


class Login(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)
    role: Literal["DOCTOR", "NURSE", "PATIENT", "PROVIDER", "TEST_CENTER", "ADMIN"] | None = None


class Signup(BaseModel):
    role: Literal["DOCTOR", "NURSE", "PROVIDER", "TEST_CENTER"]
    name: str = Field(min_length=2)
    email: EmailStr
    password: str = Field(min_length=8)
    phone: str | None = None
    title: str | None = None
    language: str | None = None
    specialty: str | None = None
    organization: str | None = None
    location: str | None = None
    department: str | None = None
    acceptsReferrals: bool = True  # noqa: N815
    inviteCode: str | None = None  # noqa: N815

    @field_validator("password")
    @classmethod
    def _pw(cls, v: str) -> str:
        return check_password_policy(v)


class ChangePassword(BaseModel):
    currentPassword: str = Field(min_length=1, max_length=200)  # noqa: N815
    newPassword: str = Field(min_length=8, max_length=200)  # noqa: N815

    @field_validator("newPassword")
    @classmethod
    def _pw(cls, v: str) -> str:
        return check_password_policy(v)


class ApproveIn(BaseModel):
    """Written reasons for overriding blocking safety findings, keyed by finding code."""

    overrides: dict[str, str] = Field(default_factory=dict, max_length=20)


class TranslateIn(BaseModel):
    texts: list[str] = Field(max_length=80)
    lang: str | None = None

    @field_validator("texts")
    @classmethod
    def _size(cls, v: list[str]) -> list[str]:
        if sum(len(t) for t in v) > 20000 or any(len(t) > 8000 for t in v):
            raise ValueError("Too much text to translate at once")
        return v


class ProfileUpdate(BaseModel):
    """Self-service profile edit. Role/email/department are not editable here."""

    name: str | None = Field(None, min_length=2, max_length=120)
    phone: str | None = Field(None, max_length=40)
    title: str | None = Field(None, max_length=120)
    address: str | None = Field(None, max_length=300)
    language: str | None = None
    notifyEmail: bool | None = None  # noqa: N815
    notifySms: bool | None = None  # noqa: N815
    # patient-only
    emergencyContact: str | None = Field(None, max_length=200)  # noqa: N815
    # provider / test-center / doctor directory profile
    organization: str | None = Field(None, max_length=160)
    location: str | None = Field(None, max_length=200)

    @field_validator("language")
    @classmethod
    def _lang(cls, v: str | None) -> str | None:
        if v is not None and v.lower().split("-")[0] not in LANGUAGES:
            raise ValueError("Unsupported language")
        return v and v.lower().split("-")[0]


class Attachment(BaseModel):
    name: str = Field("image", max_length=200)
    dataUrl: str  # noqa: N815

    @field_validator("dataUrl")
    @classmethod
    def _image(cls, v: str) -> str:
        if not DATA_URL.match(v):
            raise ValueError("Attachments must be PNG, JPEG, WebP or GIF images")
        if len(v) * 3 / 4 > MAX_IMAGE_BYTES:
            raise ValueError("Each image must be under 6 MB")
        return v


class CarePlanCreate(BaseModel):
    instructions: str = Field("", max_length=10_000)
    kind: Literal["INITIAL", "AMENDMENT"] = "INITIAL"
    attachments: list[Attachment] = Field(default_factory=list, max_length=4)


class CarePlanItemIn(BaseModel):
    id: str | None = None
    category: Category
    action: ItemAction = "ADD"
    title: str = Field(min_length=2)
    details: dict[str, Any] = Field(default_factory=dict)
    included: bool = True
    source: Literal["DOCTOR", "AI_SUGGESTED"] = "DOCTOR"
    rationale: str | None = None


class CarePlanUpdate(BaseModel):
    items: list[CarePlanItemIn] | None = None
    status: Literal["REJECTED"] | None = None


class CarePlanResponse(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str
    status: str
    kind: str
    version: int
    items: list[dict[str, Any]]


class ItemRemoval(BaseModel):
    reason: str = Field(min_length=3)


class ObservationCreate(BaseModel):
    type: Literal["TEMPERATURE", "BP", "HEART_RATE", "SPO2", "PAIN", "BLOOD_GLUCOSE", "WEIGHT", "SYMPTOM", "NURSE_NOTE"]
    value: float | None = None
    value2: float | None = None
    text: str | None = Field(None, max_length=1000)


class AlertAction(BaseModel):
    action: Literal["ACKNOWLEDGE", "RESOLVE", "ESCALATE"]
    note: str | None = Field(None, max_length=1000)


class AlertResponse(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str
    patientId: str  # noqa: N815
    category: str
    severity: str
    title: str
    message: str
    status: str
    escalationLevel: int  # noqa: N815


class AppointmentAction(BaseModel):
    action: Literal["COMPLETE", "MISS"]
    notes: str | None = Field(None, max_length=1000)


class LabResult(BaseModel):
    values: dict[str, float] = Field(default_factory=dict)
    findings: str | None = Field(None, max_length=4000)


class LabReportCreate(LabResult):
    appointmentId: str  # noqa: N815


class DoseAction(BaseModel):
    status: Literal["TAKEN", "SKIPPED"]
    note: str | None = Field(None, max_length=300)


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=1000)


class IntelligenceRequest(BaseModel):
    kind: Literal["HANDOFF", "SUMMARY"]


class ReleaseRequestIn(BaseModel):
    reason: str = Field(min_length=5, max_length=1000)
    suggestedNurseId: str | None = None  # noqa: N815

    @field_validator("reason", mode="before")
    @classmethod
    def _strip(cls, v: Any) -> Any:
        return v.strip() if isinstance(v, str) else v


class ReleaseDecision(BaseModel):
    action: Literal["APPROVE", "REJECT", "CANCEL", "ACCEPT", "DECLINE"]
    toNurseId: str | None = None  # noqa: N815
    note: str | None = Field(None, max_length=1000)


class NurseAssign(BaseModel):
    nurseId: str = Field(min_length=1)  # noqa: N815
    reason: str = Field(min_length=3, max_length=1000)


class PatientCreate(BaseModel):
    name: str = Field(min_length=2)
    email: EmailStr
    phone: str | None = None
    password: str = Field(min_length=8)
    language: str | None = None
    dateOfBirth: str  # noqa: N815
    gender: str
    diagnosis: str = Field(min_length=2)
    procedure: str | None = None
    allergies: str | None = None
    comorbidities: str | None = None
    nurseId: str | None = None  # noqa: N815
    admissionDate: str | None = None  # noqa: N815

    @field_validator("password")
    @classmethod
    def _pw(cls, v: str) -> str:
        return check_password_policy(v)


class ReferralDecision(BaseModel):
    action: Literal["ACCEPT", "DECLINE"]
    note: str | None = Field(None, max_length=1000)


class ReferralRevisionIn(BaseModel):
    referralType: str = Field(min_length=2)  # noqa: N815
    reason: str = Field(min_length=3)
    sessions: int = Field(ge=1, le=60)
    frequencyPerWeek: int = Field(ge=1, le=7)  # noqa: N815
    durationWeeks: int = Field(ge=1, le=52)  # noqa: N815
    preferredStartWithinDays: int = Field(ge=0, le=90)  # noqa: N815
    urgency: Urgency
    noteToSpecialist: str | None = Field(None, max_length=1000)  # noqa: N815


class PlanChangeIn(BaseModel):
    category: Category
    action: ItemAction = "ADD"
    title: str = Field(min_length=2)
    details: dict[str, Any] = Field(default_factory=dict)


class ReferralResponse(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str
    referralType: str  # noqa: N815
    status: str
    sessions: int
    timeline: list[dict[str, Any]]


class ReferralResend(BaseModel):
    referral: ReferralRevisionIn
    providerId: str | None = None  # noqa: N815
    carePlanChanges: list[PlanChangeIn] = Field(default_factory=list)  # noqa: N815
    engine: Literal["groq", "ollama", "rules"] = "rules"


class NotificationUpdate(BaseModel):
    id: str | None = None
    all: bool | None = None


class AgentEventResponse(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str
    agent: str
    action: str
    detail: str | None = None
    level: str
    createdAt: str  # noqa: N815
