"""Outbound delivery of notifications over email (SMTP) and SMS/WhatsApp (Twilio-style REST), with retry/backoff,
quiet hours for non-urgent messages, per-user opt-out and delivery status. Every channel stays off until configured.

`process_due()` (scheduler job `deliver_notifications`) first queues copies of any new notifications, then sends what is due.
"""
from __future__ import annotations

import asyncio
import logging
import smtplib
from datetime import datetime, timedelta
from email.message import EmailMessage
from typing import Protocol

import httpx
from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import session_scope
from app.core.util import now
from app.models import Delivery, Notification, User

log = logging.getLogger("carexhealth.delivery")
URGENT_TYPES = {"ALERT"}


class Provider(Protocol):
    channel: str

    def send(self, to: str, subject: str, body: str) -> None: ...


class SmtpEmail:
    channel = "EMAIL"

    def send(self, to: str, subject: str, body: str) -> None:
        c = get_settings()
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = c.smtp_from or c.smtp_user, to, subject
        msg.set_content(body)
        with smtplib.SMTP(c.smtp_host, c.smtp_port, timeout=20) as smtp:
            if c.smtp_starttls:
                smtp.starttls()
            if c.smtp_user:
                smtp.login(c.smtp_user, c.smtp_password)
            smtp.send_message(msg)


class TwilioSms:
    channel = "SMS"

    def send(self, to: str, subject: str, body: str) -> None:
        c = get_settings()
        sender = c.twilio_from
        dest = f"whatsapp:{to}" if sender.startswith("whatsapp:") else to
        r = httpx.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{c.twilio_account_sid}/Messages.json",
            auth=(c.twilio_account_sid, c.twilio_auth_token), data={"From": sender, "To": dest, "Body": f"{subject}\n{body}"[:1500]}, timeout=20,
        )
        r.raise_for_status()


_override: dict[str, Provider] | None = None


def set_providers(providers: dict[str, Provider] | None) -> None:
    """Tests inject fakes."""
    global _override
    _override = providers


def providers() -> dict[str, Provider]:
    if _override is not None:
        return _override
    c, out = get_settings(), {}
    if c.smtp_host:
        out["EMAIL"] = SmtpEmail()
    if c.twilio_account_sid and c.twilio_auth_token and c.twilio_from:
        out["SMS"] = TwilioSms()
    return out


def in_quiet_hours(t: datetime) -> bool:
    c = get_settings()
    s, e = c.quiet_hours_start, c.quiet_hours_end
    return (s <= t.hour or t.hour < e) if s > e else (s <= t.hour < e)


def _after_quiet(t: datetime) -> datetime:
    end = t.replace(hour=get_settings().quiet_hours_end, minute=0, second=0, microsecond=0)
    return end if end > t else end + timedelta(days=1)


def enqueue(s, notification: Notification) -> int:  # noqa: ANN001
    """Create pending deliveries for the channels that are configured and that the recipient has not opted out of."""
    user = s.get(User, notification.user_id)
    if user is None:
        return 0
    chans = providers()
    urgent = notification.type in URGENT_TYPES
    n = 0
    for channel, ok in (("EMAIL", user.email and user.notify_email), ("SMS", user.phone and user.notify_sms)):
        if channel in chans and ok:
            due = now() if urgent or not in_quiet_hours(now()) else _after_quiet(now())
            s.add(Delivery(notification_id=notification.id, user_id=user.id, channel=channel, urgent=urgent, next_attempt_at=due))
            n += 1
    return n


def _backoff(attempts: int) -> timedelta:
    return timedelta(minutes=min(2**attempts, 60))


def enqueue_new(limit: int = 200) -> int:
    """Queue email/SMS copies for notifications written by any process (MCP servers, API) since the last pass."""
    n = 0
    with session_scope() as s:
        for note in s.scalars(select(Notification).where(Notification.dispatched.is_(False)).order_by(Notification.created_at).limit(limit)):
            n += enqueue(s, note)
            note.dispatched = True
    return n


def process_due(limit: int = 50) -> dict[str, int]:
    """Send everything that is due. Failures are retried with exponential backoff, then marked FAILED (dead letter)."""
    cfg, prov, stats = get_settings(), providers(), {"sent": 0, "retry": 0, "failed": 0, "skipped": 0}
    enqueue_new()
    with session_scope() as s:
        due = list(s.scalars(select(Delivery).where(Delivery.status == "PENDING", Delivery.next_attempt_at <= now()).order_by(Delivery.next_attempt_at).limit(limit)))
        for d in due:
            provider = prov.get(d.channel)
            n, u = s.get(Notification, d.notification_id), s.get(User, d.user_id)
            if provider is None or n is None or u is None:
                d.status, d.last_error = "SKIPPED", "channel not configured"
                stats["skipped"] += 1
                continue
            if not d.urgent and in_quiet_hours(now()):
                d.next_attempt_at = _after_quiet(now())
                continue
            to = u.email if d.channel == "EMAIL" else u.phone
            d.attempts += 1
            try:
                provider.send(to or "", f"CareXHealth: {n.title}", n.body)
                d.status, d.sent_at, d.last_error = "SENT", now(), None
                stats["sent"] += 1
            except Exception as e:  # noqa: BLE001 — provider/network errors are retried
                d.last_error = str(e)[:300]
                if d.attempts >= cfg.delivery_max_attempts:
                    d.status = "FAILED"
                    stats["failed"] += 1
                    log.error("delivery %s dead-lettered after %d attempts", d.id, d.attempts)
                else:
                    d.next_attempt_at = now() + _backoff(d.attempts)
                    stats["retry"] += 1
    return stats


async def process_due_async() -> dict[str, int]:
    return await asyncio.to_thread(process_due)
