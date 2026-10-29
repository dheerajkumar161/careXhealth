"""Test harness: a throw-away SQLite DB, the real FastAPI app, the real stdio MCP servers and the real MAF agents.

The LLM is off by default (FORCE_RULE_ENGINE) so every test exercises the deterministic paths; LLM-path tests
install a fake MAF chat client (tests/fake_llm.py) — no network, no Ollama required.
"""
from __future__ import annotations

import os
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

_tmp = Path(tempfile.mkdtemp(prefix="carexhealth-test-"))
os.environ.update(
    DATABASE_URL=f"sqlite:///{(_tmp / 'test.db').as_posix()}",
    AUTH_SECRET="test-secret-test-secret-test-secret",
    FORCE_RULE_ENGINE="true",
    OLLAMA_MODEL="",
    GROQ_API_KEY="",  # never call the real Groq API from tests
    SCHEDULER_ENABLED="false",
    DEMO_MODE="true",
    ESCALATION_MINUTES="15",
)

from fastapi.testclient import TestClient  # noqa: E402

PASSWORD = "Password@123"
EMAILS = {
    "doctor": "ananya.rao@carexhealth.health",
    "nurse": "priya.nair@carexhealth.health",
    "nurse2": "rahul.verma@carexhealth.health",
    "patient": "arjun.sharma@example.com",
    "specialist": "kavya.menon@carexhealth.health",
    "lab": "reports@citydiagnostics.in",
    "admin": "admin@carexhealth.health",
}

NOTE = (
    "Patient underwent right total knee replacement. Take Tab Cefuroxime 500mg twice daily for 7 days. "
    "Take Tab Paracetamol 650mg three times daily for 5 days. Check CBC after 5 days. Follow up after 2 weeks. "
    "Physiotherapy required three times a week for 4 weeks. Avoid strenuous activity. Notify nurse if temperature exceeds 101°F."
)


@pytest.fixture(scope="session")
def app_client() -> Iterator[TestClient]:
    from scripts.seed import seed

    seed()
    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture
def fresh(app_client: TestClient) -> TestClient:
    """Re-seed the database (MCP servers keep running; they open a session per call)."""
    from scripts.seed import seed

    seed()
    app_client.cookies.clear()
    return app_client


class Api:
    """A logged-in client for one role (Bearer token, so several roles can act in one test)."""

    def __init__(self, client: TestClient, email: str) -> None:
        self.c = client
        r = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
        assert r.status_code == 200, r.text
        self.token = r.json()["token"]
        client.cookies.clear()

    def _h(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    def get(self, url: str, **kw):  # noqa: ANN003, ANN201
        return self.c.get(url, headers=self._h(), **kw)

    def post(self, url: str, json=None, **kw):  # noqa: ANN001, ANN003, ANN201
        return self.c.post(url, json=json, headers=self._h(), **kw)

    def patch(self, url: str, json=None, **kw):  # noqa: ANN001, ANN003, ANN201
        return self.c.patch(url, json=json, headers=self._h(), **kw)

    def delete(self, url: str, json=None, **kw):  # noqa: ANN001, ANN003, ANN201
        return self.c.request("DELETE", url, json=json, headers=self._h(), **kw)


@pytest.fixture
def api(fresh: TestClient):  # noqa: ANN201
    def login(role: str) -> Api:
        return Api(fresh, EMAILS[role])

    return login


def patient_id(api_doctor: Api) -> str:
    return api_doctor.get("/api/patients").json()["patients"][0]["id"]


def draft_and_approve(doctor: Api, note: str = NOTE) -> tuple[str, dict]:
    pid = patient_id(doctor)
    r = doctor.post(f"/api/patients/{pid}/care-plans", {"instructions": note})
    assert r.status_code == 200, r.text
    plan = r.json()["plan"]
    r = doctor.post(f"/api/care-plans/{plan['id']}/approve")
    assert r.status_code == 200, r.text
    return pid, r.json()["plan"]
