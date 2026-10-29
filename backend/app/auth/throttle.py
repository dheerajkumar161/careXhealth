"""DB-backed login throttling: too many failures for an email OR an IP within the window → 429 until it expires."""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import delete, func, select

from app.core.config import get_settings
from app.core.db import session_scope
from app.core.util import now
from app.models import LoginAttempt


def _window_start():  # noqa: ANN202
    return now() - timedelta(minutes=get_settings().login_lockout_minutes)


def locked_for(email: str, ip: str | None) -> int:
    """Minutes remaining on a lockout (0 when the caller may try)."""
    cfg = get_settings()
    with session_scope() as s:
        for col, val in ((LoginAttempt.email, email), (LoginAttempt.ip, ip)):
            if val is None:
                continue
            times = list(s.scalars(select(LoginAttempt.at).where(col == val, LoginAttempt.at >= _window_start()).order_by(LoginAttempt.at)))
            # per-IP limit is looser than per-email so one shared NAT does not lock everyone out
            limit = cfg.login_max_attempts if col is LoginAttempt.email else cfg.login_max_attempts * 4
            if len(times) >= limit:
                unlock = times[-limit] + timedelta(minutes=cfg.login_lockout_minutes)
                return max(int((unlock - now()).total_seconds() // 60) + 1, 1)
    return 0


def record_failure(email: str, ip: str | None) -> None:
    with session_scope() as s:
        s.add(LoginAttempt(email=email, ip=ip))
        s.execute(delete(LoginAttempt).where(LoginAttempt.at < now() - timedelta(days=1)))


def clear(email: str) -> None:
    with session_scope() as s:
        s.execute(delete(LoginAttempt).where(LoginAttempt.email == email))


def failure_count(email: str) -> int:
    with session_scope() as s:
        return s.scalar(select(func.count()).select_from(LoginAttempt).where(LoginAttempt.email == email, LoginAttempt.at >= _window_start())) or 0
