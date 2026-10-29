"""Phase 1: throttling, audit trail, password change/session revocation, profile + language, ADMIN role, headers."""
from __future__ import annotations

from conftest import EMAILS, PASSWORD


def _login(client, email, password=PASSWORD):
    return client.post("/api/auth/login", json={"email": email, "password": password})


def test_security_headers_and_request_id(fresh):
    r = fresh.get("/api/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["x-request-id"]


def test_login_lockout_after_repeated_failures(fresh):
    email = EMAILS["specialist"]
    for _ in range(5):
        assert _login(fresh, email, "wrong-password1").status_code == 401
    locked = _login(fresh, email)
    assert locked.status_code == 429 and "Retry-After" in locked.headers
    from app.auth import throttle

    throttle.clear(email)
    assert _login(fresh, email).status_code == 200


def test_change_password_revokes_other_sessions(fresh, app_client):
    from fastapi.testclient import TestClient

    from app.main import app

    email = EMAILS["nurse2"]
    a = TestClient(app)
    b = TestClient(app)
    assert _login(a, email).status_code == 200 and _login(b, email).status_code == 200
    bad = a.post("/api/auth/change-password", json={"currentPassword": "nope-nope-1", "newPassword": "Brand-new-pass-9"})
    assert bad.status_code == 400
    weak = a.post("/api/auth/change-password", json={"currentPassword": PASSWORD, "newPassword": "short"})
    assert weak.status_code == 400
    ok = a.post("/api/auth/change-password", json={"currentPassword": PASSWORD, "newPassword": "Brand-new-pass-9"})
    assert ok.status_code == 200
    assert a.get("/api/auth/me").status_code == 200  # this device gets a fresh session
    assert b.get("/api/auth/me").status_code == 401  # the other device is signed out
    assert _login(TestClient(app), email, "Brand-new-pass-9").status_code == 200
    # restore for other tests
    c = TestClient(app)
    _login(c, email, "Brand-new-pass-9")
    assert c.post("/api/auth/change-password", json={"currentPassword": "Brand-new-pass-9", "newPassword": PASSWORD}).status_code == 200


def test_every_role_can_update_profile_and_language(fresh, api):
    for who, extra in (("doctor", {}), ("nurse", {}), ("patient", {"emergencyContact": "Sunita 99999"}), ("lab", {"location": "New Road"})):
        c = api(who)
        r = c.patch("/api/auth/profile", json={"phone": "+91 90000 12345", "address": "1 Test Street", "language": "hi", **extra})
        assert r.status_code == 200, (who, r.text)
        u = r.json()["user"]
        assert u["phone"] == "+91 90000 12345" and u["language"] == "hi"
        me = c.get("/api/auth/me").json()
        assert me["user"]["language"] == "hi" and any(x["code"] == "ta" for x in me["languages"])
    assert api("doctor").patch("/api/auth/profile", json={"language": "xx"}).status_code == 400
    assert api("patient").patch("/api/auth/profile", json={"emergencyContact": "Sunita 99999"}).json()["user"]["patientProfile"]["emergencyContact"] == "Sunita 99999"
    for who in ("doctor", "nurse", "patient", "lab"):  # reset language for other tests
        api(who).patch("/api/auth/profile", json={"language": "en"})


def test_admin_audit_and_directory(fresh, api):
    admin = api("admin")
    entries = admin.get("/api/audit").json()["entries"]
    assert any(e["action"] == "LOGIN" for e in entries)
    assert len(admin.get("/api/admin/users").json()["users"]) >= 6
    assert api("patient").get("/api/audit").status_code == 403
    assert api("patient").get("/api/admin/users").status_code == 403


def test_production_startup_guard():
    import pytest

    from app.core.config import Settings

    with pytest.raises(RuntimeError):
        Settings(environment="production", auth_secret="change-me-to-a-long-random-string-at-least-32-chars", demo_mode=False).validate_for_startup()
    with pytest.raises(RuntimeError):
        Settings(environment="production", auth_secret="x" * 40, demo_mode=True).validate_for_startup()
    Settings(environment="production", auth_secret="x" * 40, demo_mode=False, cors_origins="https://app.example.com").validate_for_startup()
    assert Settings(environment="production").secure_cookies is True


def test_legacy_database_is_stamped_and_upgraded(tmp_path):
    """A DB created before migrations existed (create_all, no alembic_version) upgrades in place without data loss."""
    import sqlite3

    from app.core import db

    url = f"sqlite:///{(tmp_path / 'legacy.db').as_posix()}"
    from app.core.config import get_settings

    old = get_settings().database_url
    get_settings().database_url = url
    db.reset_engine()
    try:
        from alembic import command
        from alembic.config import Config

        cfg = Config(str(db.Path(db.__file__).resolve().parents[2] / "alembic.ini"))
        cfg.set_main_option("script_location", str(db.Path(db.__file__).resolve().parents[2] / "alembic"))
        command.upgrade(cfg, "0001")
        con = sqlite3.connect(tmp_path / "legacy.db")
        con.execute("DROP TABLE alembic_version")
        con.execute("INSERT INTO users (id,email,password_hash,name,role,created_at) VALUES ('u1','a@b.c','x','A','NURSE','2024-01-01')")
        con.commit()
        con.close()
        db.init_db()
        con = sqlite3.connect(tmp_path / "legacy.db")
        assert con.execute("SELECT language, token_version FROM users WHERE id='u1'").fetchone() == ("en", 0)
        assert con.execute("SELECT version_num FROM alembic_version").fetchone()[0] >= "0002"
        con.close()
    finally:
        get_settings().database_url = old
        db.reset_engine()


def test_escalation_ladder_steps():
    from app.core.config import Settings

    s = Settings(escalation_minutes=15, escalation_ladder="")
    assert s.ladder_minutes(1) == 15 and s.ladder_minutes(2) == 15 and s.ladder_minutes(1, "CRITICAL") == 5
    s = Settings(escalation_ladder="20,8")
    assert (s.ladder_minutes(1), s.ladder_minutes(2), s.ladder_minutes(3)) == (20, 8, 8) and s.ladder_minutes(2, "CRITICAL") == 3
