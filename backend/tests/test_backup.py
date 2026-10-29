"""Backup produces a restorable copy; housekeeping prunes only operational tables."""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))


def test_sqlite_backup_is_restorable_and_pruned(fresh, tmp_path):  # noqa: ANN001
    import backup

    first = backup.backup(tmp_path)
    con = sqlite3.connect(first)
    assert con.execute("select count(*) from users").fetchone()[0] >= 6
    assert con.execute("select count(*) from alembic_version").fetchone()[0] == 1
    con.close()
    for i in range(3):
        (tmp_path / f"carexhealth-2000010{i}-000000.db").write_bytes(b"x")
    assert len(backup.prune(tmp_path, keep=2)) == 2 and len(list(tmp_path.glob("carexhealth-*"))) == 2


def test_housekeeping_keeps_clinical_data(fresh):  # noqa: ANN001
    import housekeeping
    from app.core.db import session_scope
    from app.models import AuditLog, User
    from sqlalchemy import func, select

    with session_scope() as s:
        users = s.scalar(select(func.count()).select_from(User))
    housekeeping.run(0)
    with session_scope() as s:
        assert s.scalar(select(func.count()).select_from(User)) == users
        assert s.scalar(select(func.count()).select_from(AuditLog)) >= 0


def test_create_admin_script(fresh):  # noqa: ANN001
    import pytest

    import create_admin

    assert create_admin.create_admin("ops@hospital.org", "Ops", "Strong-pass-2026") == "created"
    assert fresh.post("/api/auth/login", json={"email": "ops@hospital.org", "password": "Strong-pass-2026", "role": "ADMIN"}).json()["redirect"] == "/admin"
    assert create_admin.create_admin("ops@hospital.org", "Ops", "Another-pass-2026") == "password reset"
    with pytest.raises(ValueError):
        create_admin.create_admin("weak@hospital.org", "Weak", "short")
    with pytest.raises(SystemExit):
        create_admin.create_admin("ananya.rao@carexhealth.health", "x", "Strong-pass-2026")
