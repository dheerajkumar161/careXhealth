"""Monitoring rules, observations and alerts (Monitoring agent state)."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select, update

from app.core.db import session_scope
from app.core.util import dumps, now, parse_json
from app.models import Alert, MonitoringRule, Observation


# ── rules ──
def create_rule(**fields: Any) -> MonitoringRule:
    with session_scope() as s:
        r = MonitoringRule(**fields)
        s.add(r)
        s.flush()
        return r


def active_rules(patient_id: str, metric: str | None = None) -> list[MonitoringRule]:
    with session_scope() as s:
        q = select(MonitoringRule).where(MonitoringRule.patient_id == patient_id, MonitoringRule.active.is_(True))
        if metric:
            q = q.where(MonitoringRule.metric == metric)
        return list(s.scalars(q.order_by(MonitoringRule.created_at)))


def deactivate_all(patient_id: str) -> None:
    with session_scope() as s:
        s.execute(update(MonitoringRule).where(MonitoringRule.patient_id == patient_id).values(active=False))


def deactivate_matching(patient_id: str, care_plan_id: str, description: str) -> int:
    with session_scope() as s:
        res = s.execute(
            update(MonitoringRule)
            .where(MonitoringRule.patient_id == patient_id, MonitoringRule.care_plan_id == care_plan_id, MonitoringRule.description == description, MonitoringRule.active.is_(True))
            .values(active=False)
        )
        return res.rowcount or 0


# ── observations ──
def create_observation(**fields: Any) -> Observation:
    with session_scope() as s:
        o = Observation(**fields)
        s.add(o)
        s.flush()
        s.refresh(o)
        return o


def get_observation(obs_id: str) -> Observation | None:
    with session_scope() as s:
        return s.get(Observation, obs_id)


def flag_observation(obs_id: str) -> None:
    with session_scope() as s:
        o = s.get(Observation, obs_id)
        if o:
            o.flagged = True


def prior_weights(patient_id: str, exclude_id: str, since: datetime, before: datetime) -> list[float]:
    with session_scope() as s:
        rows = s.scalars(
            select(Observation.value).where(Observation.patient_id == patient_id, Observation.type == "WEIGHT", Observation.id != exclude_id, Observation.recorded_at >= since, Observation.recorded_at < before)
        )
        return [v for v in rows if v is not None]


# ── alerts ──
def open_duplicate(patient_id: str, dedupe_key: str) -> Alert | None:
    with session_scope() as s:
        return s.scalars(
            select(Alert).where(Alert.patient_id == patient_id, Alert.dedupe_key == dedupe_key, Alert.status != "RESOLVED", Alert.created_at >= now() - timedelta(hours=12))
        ).first()


def create_alert(**fields: Any) -> Alert:
    with session_scope() as s:
        a = Alert(**fields)
        s.add(a)
        s.flush()
        return a


def get_alert(alert_id: str) -> Alert | None:
    with session_scope() as s:
        return s.get(Alert, alert_id)


def append_history(alert_id: str, event: str, by: str | None = None, **extra: Any) -> Alert:
    with session_scope() as s:
        a = s.get(Alert, alert_id)
        assert a is not None
        history = parse_json(a.history, [])
        entry: dict[str, Any] = {"at": now().astimezone().isoformat(timespec="milliseconds"), "event": event}
        if by is not None:
            entry["by"] = by
        history.append(entry)
        a.history = dumps(history)
        for k, v in extra.items():
            setattr(a, k, v)
        s.flush()
        return a


def open_severities(patient_id: str) -> list[str]:
    with session_scope() as s:
        return list(s.scalars(select(Alert.severity).where(Alert.patient_id == patient_id, Alert.status != "RESOLVED")))


def overdue_for_escalation(t: datetime) -> list[Alert]:
    with session_scope() as s:
        return list(s.scalars(select(Alert).where(Alert.status.in_(["OPEN", "ESCALATED"]), Alert.acknowledged_at.is_(None), Alert.escalate_after < t)))


def reassign_open(patient_id: str, from_user_id: str, to_user_id: str, escalate_after: datetime) -> int:
    with session_scope() as s:
        res = s.execute(
            update(Alert).where(Alert.patient_id == patient_id, Alert.assigned_to_id == from_user_id, Alert.status != "RESOLVED").values(assigned_to_id=to_user_id, escalate_after=escalate_after)
        )
        return res.rowcount or 0
