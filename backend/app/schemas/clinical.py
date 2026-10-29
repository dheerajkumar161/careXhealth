"""Clinical data contracts. LLM structured output is validated against these before it becomes database rows."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

Category = Literal["MEDICATION", "INVESTIGATION", "FOLLOW_UP", "REFERRAL", "MONITORING", "DIET", "EXERCISE", "RESTRICTION", "CARE_INSTRUCTION", "RED_FLAG"]
ItemAction = Literal["ADD", "DISCONTINUE", "MODIFY"]
Urgency = Literal["ROUTINE", "PRIORITY", "URGENT"]


class _Details(BaseModel):
    model_config = ConfigDict(extra="allow")


class MedicationInstruction(_Details):
    name: str
    dose: str | None = ""
    timesPerDay: int | None = None  # noqa: N815
    durationDays: int | None = None  # noqa: N815
    route: str | None = None
    instructions: str | None = None
    asNeeded: bool | None = None  # noqa: N815


class InvestigationInstruction(_Details):
    test: str
    dayOffset: int = 1  # noqa: N815
    instructions: str | None = None


class FollowUpInstruction(_Details):
    specialty: str | None = ""
    withTreatingDoctor: bool | None = True  # noqa: N815
    dayOffset: int = 14  # noqa: N815
    reason: str | None = None


class ReferralInstruction(_Details):
    referralType: str  # noqa: N815
    reason: str | None = None
    sessions: int = Field(1, ge=1)
    frequencyPerWeek: int = Field(1, ge=1)  # noqa: N815
    durationWeeks: int = Field(1, ge=1)  # noqa: N815
    preferredStartWithinDays: int = Field(7, ge=0)  # noqa: N815
    urgency: Urgency = "ROUTINE"

    @field_validator("urgency", mode="before")
    @classmethod
    def _urgency(cls, v: Any) -> Any:
        return str(v).upper() if v else "ROUTINE"


class MonitoringInstruction(_Details):
    metric: str
    timesPerDay: int | None = 1  # noqa: N815
    unit: str | None = None


class RedFlagInstruction(_Details):
    metric: str
    operator: Literal[">", "<", ">=", "<=", "CONTAINS"] = ">"
    threshold: float | None = None
    keywords: list[str] | None = None
    unit: str | None = None
    action: Literal["NOTIFY_NURSE", "NOTIFY_DOCTOR", "EMERGENCY"] = "NOTIFY_NURSE"
    severity: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"] = "HIGH"


class TextInstruction(_Details):
    text: str


DETAIL_SCHEMAS: dict[str, type[BaseModel]] = {
    "MEDICATION": MedicationInstruction,
    "INVESTIGATION": InvestigationInstruction,
    "FOLLOW_UP": FollowUpInstruction,
    "REFERRAL": ReferralInstruction,
    "MONITORING": MonitoringInstruction,
    "RED_FLAG": RedFlagInstruction,
    "DIET": TextInstruction,
    "EXERCISE": TextInstruction,
    "RESTRICTION": TextInstruction,
    "CARE_INSTRUCTION": TextInstruction,
}


def validate_details(category: str, details: dict[str, Any], action: str = "ADD") -> dict[str, Any]:
    """Coerce/validate an item's details. A DISCONTINUE only needs the medication name."""
    if category == "MEDICATION" and action == "DISCONTINUE":
        return MedicationInstruction.model_validate({"name": details.get("name", ""), **details}).model_dump(exclude_none=True)
    schema = DETAIL_SCHEMAS[category]
    return schema.model_validate(details).model_dump(exclude_none=True)


class CarePlanItem(BaseModel):
    """A structured care-plan line as produced by the Planning agent (doctor-reviewable)."""

    category: Category
    action: ItemAction = "ADD"
    title: str = Field(min_length=1)
    source: Literal["DOCTOR", "AI_SUGGESTED"] = "DOCTOR"
    rationale: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class RawPlan(BaseModel):
    """What the LLM must return when structuring a note."""

    summary: str = ""
    items: list[dict[str, Any]] = Field(min_length=1)


class ReferralRevisionModel(BaseModel):
    explanation: str = ""
    referral: dict[str, Any]
    carePlanChanges: list[dict[str, Any]] = Field(default_factory=list)  # noqa: N815


class ImageRead(BaseModel):
    transcript: str = ""
    instructions: list[str] = Field(default_factory=list)
    patientName: str | None = ""  # noqa: N815
    unclear: list[str] | None = Field(default_factory=list)


class PatientContext(BaseModel):
    """Longitudinal context served by the EHR MCP server (dates are ISO strings)."""

    model_config = ConfigDict(extra="allow")
    patient: dict[str, Any]
    items: list[dict[str, Any]]
    doses: list[dict[str, Any]]
    appointments: list[dict[str, Any]]
    referrals: list[dict[str, Any]]
    observations: list[dict[str, Any]]
    alerts: list[dict[str, Any]]
    labs: list[dict[str, Any]]
    tasks: list[dict[str, Any]]
    adherence: int | None = None
    latestVitals: dict[str, Any] = Field(default_factory=dict)  # noqa: N815
    now: str


__all__ = ["ValidationError"]
