"""Notification MCP server — in-app notifications with deep links (stand-in for SMS/push/email gateways).
Port of lib/services/notification.ts."""
from __future__ import annotations

from mcp_servers.common import create_server, ok

from app.core.db import session_scope
from app.models import Notification, Patient, Provider

mcp = create_server("carexhealth-notification", "Hospital Notification & Routing Service: delivers notifications to patients, nurses, doctors and providers.")

CLINICIAN_TAB = {"ALERT": "monitoring", "DOCUMENT": "documents", "APPOINTMENT": "execution", "REFERRAL": "execution", "CARE_PLAN": "plan", "REMINDER": "execution"}
PATIENT_PAGE = {
    "REMINDER": "/patient",
    "ALERT": "/patient",
    "APPOINTMENT": "/patient/appointments",
    "REFERRAL": "/patient/appointments",
    "DOCUMENT": "/patient/documents",
    "CARE_PLAN": "/patient/plan",
}


def _tab_link(base: str, type_: str) -> str:
    return f"{base}?tab={CLINICIAN_TAB[type_]}" if type_ in CLINICIAN_TAB else base


def doctor_patient_link(patient_id: str, type_: str = "", extra: str = "") -> str:
    return _tab_link(f"/doctor/patients/{patient_id}", type_) + extra


def nurse_patient_link(patient_id: str, type_: str = "", extra: str = "") -> str:
    return _tab_link(f"/nurse/patients/{patient_id}", type_) + extra


def _create(s, user_id: str, type: str, title: str, body: str, link: str | None) -> str:  # noqa: A002, ANN001
    n = Notification(user_id=user_id, type=type, title=title, body=body, link=link)
    s.add(n)
    s.flush()
    return n.id


@mcp.tool()
def create_in_app_notification(user_id: str, type: str, title: str, body: str, link: str | None = None) -> dict:  # noqa: A002
    """Deliver an in-app notification to one user."""
    with session_scope() as s:
        return ok(notificationId=_create(s, user_id, type, title, body, link))


@mcp.tool()
def notify_patient(patient_id: str, type: str, title: str, body: str, link: str | None = None) -> dict:  # noqa: A002
    """Notify the patient (deep link defaults to the matching patient page)."""
    with session_scope() as s:
        p = s.get(Patient, patient_id)
        if not p:
            return ok(delivered=False)
        _create(s, p.user_id, type, title, body, link or PATIENT_PAGE.get(type, "/patient"))
        return ok(delivered=True)


@mcp.tool()
def notify_doctor(patient_id: str, type: str, title: str, body: str, link: str | None = None) -> dict:  # noqa: A002
    """Notify the patient's treating doctor."""
    with session_scope() as s:
        p = s.get(Patient, patient_id)
        if not p:
            return ok(delivered=False)
        _create(s, p.doctor_id, type, title, body, link or doctor_patient_link(patient_id, type))
        return ok(delivered=True)


@mcp.tool()
def notify_nurse(patient_id: str, type: str, title: str, body: str, link: str | None = None) -> dict:  # noqa: A002
    """Notify the patient's assigned nurse (no-op if none is assigned)."""
    with session_scope() as s:
        p = s.get(Patient, patient_id)
        if not p or not p.nurse_id:
            return ok(delivered=False)
        _create(s, p.nurse_id, type, title, body, link or nurse_patient_link(patient_id, type))
        return ok(delivered=True)


@mcp.tool()
def notify_provider(provider_id: str, type: str, title: str, body: str) -> dict:  # noqa: A002
    """Routing service: deliver to a provider's portal inbox. delivered=false means the provider has no portal login."""
    with session_scope() as s:
        p = s.get(Provider, provider_id)
        if not p or not p.user_id:
            return ok(delivered=False)
        role = p.user.role if p.user else None
        # Specialist doctors: referral inbox. Test centers: tests list, or their schedule for booking changes.
        link = "/doctor/referrals?tab=incoming" if role == "DOCTOR" else "/provider/schedule" if type == "APPOINTMENT" and p.type != "TEST_CENTER" else "/provider"
        _create(s, p.user_id, type, title, body, link)
        return ok(delivered=True)


@mcp.tool()
def patient_link(patient_id: str, audience: str, type: str = "", extra: str = "") -> dict:  # noqa: A002
    """Deep link into a patient's workspace for a DOCTOR or NURSE audience."""
    return ok(link=doctor_patient_link(patient_id, type, extra) if audience == "DOCTOR" else nurse_patient_link(patient_id, type, extra))


if __name__ == "__main__":
    mcp.run("stdio")
