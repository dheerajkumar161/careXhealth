"""Authentication: login, JWT claims, role / department / patient row-level restrictions."""
import jwt

from conftest import EMAILS, PASSWORD, Api, patient_id


def test_login_sets_cookie_and_jwt_claims(fresh):  # noqa: ANN001
    r = fresh.post("/api/auth/login", json={"email": EMAILS["doctor"], "password": PASSWORD})
    assert r.status_code == 200
    assert r.json()["redirect"] == "/doctor"
    assert "cb_session" in r.cookies
    claims = jwt.decode(r.json()["token"], options={"verify_signature": False})
    assert claims["role"] == "DOCTOR" and claims["department"] == "Orthopedics"
    assert {"user_id", "exp", "iat"} <= set(claims)
    # Cookie session works for /me
    me = fresh.get("/api/auth/me").json()
    assert me["user"]["email"] == EMAILS["doctor"] and me["ai"]["primary"] == "rules"


def test_invalid_credentials_and_unauthenticated(fresh):  # noqa: ANN001
    assert fresh.post("/api/auth/login", json={"email": EMAILS["doctor"], "password": "wrong"}).status_code == 401
    fresh.cookies.clear()
    r = fresh.get("/api/overview")
    assert r.status_code == 401 and r.json() == {"error": "Not authenticated"}
    assert fresh.get("/api/overview", headers={"Authorization": "Bearer not-a-jwt"}).status_code == 401


def test_expired_token_rejected(fresh):  # noqa: ANN001
    from datetime import UTC, datetime, timedelta

    token = jwt.encode({"user_id": "x", "role": "DOCTOR", "exp": datetime.now(UTC) - timedelta(minutes=1)}, "test-secret-test-secret-test-secret", algorithm="HS256")
    assert fresh.get("/api/overview", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_role_restrictions(api):  # noqa: ANN001
    patient, nurse, lab = api("patient"), api("nurse"), api("lab")
    assert patient.get("/api/patients").status_code == 403  # doctor/nurse only
    assert patient.get("/api/referrals").status_code == 403  # doctor only
    assert nurse.post("/api/care-plans/anything/approve").status_code == 403  # nurses cannot approve plans
    assert lab.get("/api/tests").status_code == 403


def test_department_restriction(api):  # noqa: ANN001
    doctor, lab = api("doctor"), api("lab")
    # /api/lab-reports is restricted to the Laboratory department
    assert doctor.post("/api/lab-reports", {"appointmentId": "x", "values": {}}).json()["error"].startswith("This action is restricted to the Laboratory")
    assert lab.post("/api/lab-reports", {"appointmentId": "missing", "values": {"hb": 10}}).status_code == 404


def test_patient_row_level_access(api):  # noqa: ANN001
    doctor, nurse2, specialist, patient = api("doctor"), api("nurse2"), api("specialist"), api("patient")
    pid = patient_id(doctor)
    assert doctor.get(f"/api/patients/{pid}").status_code == 200
    assert patient.get(f"/api/patients/{pid}").status_code == 200
    assert nurse2.get(f"/api/patients/{pid}").status_code == 403  # not the assigned nurse
    assert specialist.get(f"/api/patients/{pid}").status_code == 403  # not treating, no referral yet
    assert nurse2.post(f"/api/patients/{pid}/observations", {"type": "TEMPERATURE", "value": 99}).status_code == 403


def test_signup_normalizes_test_center_role(fresh):  # noqa: ANN001
    r = fresh.post(
        "/api/auth/signup",
        json={"role": "PROVIDER", "name": "Metro Labs", "email": "lab@metro.in", "password": "Password@123", "organization": "Metro Labs"},
    )
    assert r.status_code == 200, r.text
    claims = jwt.decode(r.json()["token"], options={"verify_signature": False})
    assert claims["role"] == "TEST_CENTER" and claims["department"] == "Laboratory"
    lab = Api(fresh, "lab@metro.in")
    assert lab.get("/api/overview").json()["isLab"] is True
