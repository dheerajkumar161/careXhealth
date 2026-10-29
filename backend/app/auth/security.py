"""JWT sessions (user_id + role + department + expiry) and bcrypt password hashing."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from app.core.config import get_settings

SESSION_COOKIE = "cb_session"
ALGORITHM = "HS256"


@dataclass(frozen=True)
class SessionUser:
    id: str
    role: str
    department: str | None
    name: str
    email: str
    tv: int = 0  # token_version claim; a password change bumps the user's version and revokes older sessions


def _secret() -> str:
    s = get_settings().auth_secret
    if not s or len(s) < 16:
        raise RuntimeError("AUTH_SECRET is missing or too short")
    return s


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=10)).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except ValueError:
        return False


def check_password_policy(password: str) -> str:
    """Raises ValueError (→ HTTP 400) unless the password meets the policy; returns it unchanged."""
    n = get_settings().password_min_length
    if len(password) < n:
        raise ValueError(f"Password must be at least {n} characters")
    if not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
        raise ValueError("Password must contain at least one letter and one number")
    return password


def sign_session(user: SessionUser) -> str:
    t = datetime.now(UTC)
    payload = {
        "user_id": user.id,
        "role": user.role,
        "department": user.department,
        "name": user.name,
        "email": user.email,
        "tv": user.tv,
        "iat": t,
        "exp": t + timedelta(hours=get_settings().session_hours),
    }
    return jwt.encode(payload, _secret(), algorithm=ALGORITHM)


def verify_session(token: str | None) -> SessionUser | None:
    if not token:
        return None
    try:
        p = jwt.decode(token, _secret(), algorithms=[ALGORITHM], options={"require": ["exp", "user_id", "role"]})
    except jwt.PyJWTError:
        return None
    return SessionUser(id=str(p["user_id"]), role=str(p["role"]), department=p.get("department"), name=str(p.get("name", "")), email=str(p.get("email", "")), tv=int(p.get("tv", 0)))
