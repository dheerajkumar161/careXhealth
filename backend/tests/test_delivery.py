"""Outbound email/SMS: opt-outs, quiet hours, retry with backoff, dead-lettering, status."""
from datetime import timedelta

import pytest
from sqlalchemy import select

from conftest import draft_and_approve

from app.core.config import get_settings
from app.core.db import session_scope
from app.core.util import now
from app.models import Delivery
from app.services import delivery


class Fake:
    def __init__(self, channel, fail=0):
        self.channel, self.fail, self.sent = channel, fail, []

    def send(self, to, subject, body):
        if self.fail:
            self.fail -= 1
            raise RuntimeError("provider down")
        self.sent.append((to, subject, body))


@pytest.fixture
def fakes():
    f = {"EMAIL": Fake("EMAIL"), "SMS": Fake("SMS")}
    delivery.set_providers(f)
    yield f
    delivery.set_providers(None)


def rows():
    with session_scope() as s:
        return list(s.scalars(select(Delivery).order_by(Delivery.created_at)))


def test_notifications_are_emailed_and_texted(api, fakes):  # noqa: ANN001
    draft_and_approve(api("doctor"))
    stats = delivery.process_due()
    assert {d.channel for d in rows()} == {"EMAIL", "SMS"}
    assert stats["sent"] > 0 and fakes["EMAIL"].sent and fakes["SMS"].sent
    assert all(d.status == "SENT" for d in rows() if d.next_attempt_at <= now())
    assert any(to == "arjun.sharma@example.com" for to, _, _ in fakes["EMAIL"].sent)


def test_opt_out_is_respected(api, fakes):  # noqa: ANN001
    patient = api("patient")
    assert patient.patch("/api/auth/profile", {"notifyEmail": False, "notifySms": False}).json()["user"]["notifyEmail"] is False
    draft_and_approve(api("doctor"))
    delivery.process_due()
    with session_scope() as s:
        from app.models import Patient

        uid = s.scalars(select(Patient.user_id)).first()
        assert not [d for d in s.scalars(select(Delivery)) if d.user_id == uid]


def test_retry_backoff_then_dead_letter(api, fakes, monkeypatch):  # noqa: ANN001
    fakes["EMAIL"].fail = 99
    monkeypatch.setattr(get_settings(), "delivery_max_attempts", 2)
    draft_and_approve(api("doctor"))
    delivery.process_due()
    failing = [d for d in rows() if d.channel == "EMAIL"]
    assert failing and all(d.status == "PENDING" and d.attempts == 1 and d.next_attempt_at > now() for d in failing)
    with session_scope() as s:  # make them due again
        for d in s.scalars(select(Delivery)):
            d.next_attempt_at = now() - timedelta(minutes=1)
    stats = delivery.process_due()
    assert stats["failed"] > 0 and all(d.status == "FAILED" and d.last_error for d in rows() if d.channel == "EMAIL")


def test_quiet_hours_defer_non_urgent(monkeypatch):
    monkeypatch.setattr(get_settings(), "quiet_hours_start", 22)
    monkeypatch.setattr(get_settings(), "quiet_hours_end", 7)
    from datetime import datetime

    assert delivery.in_quiet_hours(datetime(2026, 1, 1, 23, 0)) and delivery.in_quiet_hours(datetime(2026, 1, 1, 3, 0))
    assert not delivery.in_quiet_hours(datetime(2026, 1, 1, 12, 0))
    assert delivery._after_quiet(datetime(2026, 1, 1, 23, 0)) == datetime(2026, 1, 2, 7, 0)
    assert delivery._after_quiet(datetime(2026, 1, 1, 3, 0)) == datetime(2026, 1, 1, 7, 0)


def test_no_channels_configured_creates_nothing(api):  # noqa: ANN001
    delivery.set_providers(None)
    draft_and_approve(api("doctor"))
    delivery.process_due()
    assert rows() == []
