"""Create (or reset) an administrator account — the only way to get an ADMIN, since sign-up never offers that role.

    python scripts/create_admin.py --email admin@hospital.org --name "Hospital Admin"
The password is read from the CADMIN_PASSWORD environment variable, or prompted for (hidden).
"""
from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.auth.security import check_password_policy, hash_password  # noqa: E402
from app.core.db import init_db, session_scope  # noqa: E402
from app.models import User  # noqa: E402


def create_admin(email: str, name: str, password: str) -> str:
    check_password_policy(password)
    init_db()
    email = email.lower().strip()
    with session_scope() as s:
        user = s.scalars(select(User).where(User.email == email)).first()
        if user is None:
            s.add(User(email=email, name=name, role="ADMIN", department="Administration", title="System Administrator", password_hash=hash_password(password)))
            return "created"
        if user.role != "ADMIN":
            raise SystemExit(f"{email} exists with role {user.role}; refusing to change its role")
        user.password_hash, user.token_version = hash_password(password), user.token_version + 1  # also signs out old sessions
        return "password reset"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--email", required=True)
    ap.add_argument("--name", default="Administrator")
    a = ap.parse_args()
    pw = os.environ.get("CADMIN_PASSWORD") or getpass.getpass("Password: ")
    print(f"admin {a.email}: {create_admin(a.email, a.name, pw)}")
