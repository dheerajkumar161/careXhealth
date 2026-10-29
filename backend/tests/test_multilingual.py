"""Multilingual: a user's Settings language drives patient plans, assistant replies, notifications and /api/translate."""
import json

from conftest import draft_and_approve
from test_planning import fake_llm  # noqa: F401  (fixture)


def _translator(system: str, user: str, img: bool) -> str:
    if "medical translator" in system:
        return json.dumps({"translations": [f"[hi] {t}" for t in json.loads(user.split("\nRespond")[0])]})
    if "patient-facing assistant" in system:
        assert "Reply entirely in Hindi" in system
        return "[hi] answer"
    return ""


def _plan_doc(patient, pid):  # noqa: ANN001, ANN202
    docs = patient.get("/api/auth/me")  # touch auth
    assert docs.status_code == 200
    rec = patient.get(f"/api/patients/{pid}").json()
    return next(d for d in rec["documents"] if d["type"] == "PATIENT_INSTRUCTIONS")


def test_english_without_model_falls_back_and_flags(api):  # noqa: ANN001
    patient = api("patient")
    assert patient.patch("/api/auth/profile", {"language": "hi"}).status_code == 200
    pid, _ = draft_and_approve(api("doctor"))
    doc = _plan_doc(patient, pid)
    assert doc["data"]["language"] == "hi" and doc["data"]["translated"] is False
    assert "Your Recovery Plan" in doc["content"]  # honest English fallback, not garbage
    r = patient.post("/api/translate", {"texts": ["Hello"]}).json()
    assert r["texts"] == ["Hello"] and r["translated"] is False and r["language"] == "hi"


def test_plan_chat_and_notifications_follow_user_language(api, fake_llm):  # noqa: ANN001, F811
    fake_llm["reply"] = _translator
    patient, doctor = api("patient"), api("doctor")
    pid, _ = draft_and_approve(doctor)
    assert "Your Recovery Plan" in _plan_doc(patient, pid)["content"]  # still English

    # changing language in Settings re-renders the existing plan
    assert patient.patch("/api/auth/profile", {"language": "hi"}).status_code == 200
    doc = _plan_doc(patient, pid)
    assert doc["content"].startswith("[hi] ") and doc["data"]["translated"] is True and doc["title"].startswith("[hi]")

    # assistant replies in the chosen language
    reply = patient.post(f"/api/patients/{pid}/chat", {"message": "What medicines do I take?"}).json()
    assert "[hi] answer" in json.dumps(reply)

    # notifications are shown translated, and switching back to English shows the originals
    items = patient.get("/api/notifications").json()["items"]
    assert items and all(i["title"].startswith("[hi] ") for i in items)
    patient.patch("/api/auth/profile", {"language": "en"})
    assert not any(i["title"].startswith("[hi] ") for i in patient.get("/api/notifications").json()["items"])

    # cache: second identical request makes no new model call
    patient.patch("/api/auth/profile", {"language": "hi"})
    calls = sum(len(c.calls) for c in fake_llm["clients"])
    patient.get("/api/notifications")
    assert sum(len(c.calls) for c in fake_llm["clients"]) == calls


def test_translate_limits(api):  # noqa: ANN001
    doctor = api("doctor")
    assert doctor.post("/api/translate", {"texts": ["x" * 9000]}).status_code == 400
    assert doctor.post("/api/translate", {"texts": ["a"], "lang": "fr"}).json()["language"] == "fr"
