"""Planning agent: rule fallback, draft status, LLM path via MAF, invented-order filter, images, approval gate."""
import asyncio
from functools import partial

import pytest

from conftest import NOTE, draft_and_approve, patient_id
from fake_llm import FakeChatClient, as_json

from app.core import llm


@pytest.fixture
def fake_llm(monkeypatch):  # noqa: ANN001, ANN201
    """Install a scripted MAF chat client; yields a setter for the reply function."""
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "force_rule_engine", False)
    holder = {"reply": lambda s, u, img: "", "clients": []}

    def factory(model: str) -> FakeChatClient:
        c = FakeChatClient(lambda s, u, img: holder["reply"](s, u, img), model=model)
        holder["clients"].append(c)
        return c

    llm.set_chat_client_factory(factory)
    yield holder
    llm.set_chat_client_factory(None)


def test_rule_based_draft(api):  # noqa: ANN001
    doctor = api("doctor")
    pid = patient_id(doctor)
    plan = doctor.post(f"/api/patients/{pid}/care-plans", {"instructions": NOTE}).json()["plan"]
    assert plan["status"] == "DRAFT" and plan["engine"] == "rules"
    cats = [i["category"] for i in plan["items"]]
    assert cats.count("MEDICATION") == 2 and "INVESTIGATION" in cats and "FOLLOW_UP" in cats and "REFERRAL" in cats and "RED_FLAG" in cats
    # Draft → nothing executed yet
    rec = doctor.get(f"/api/patients/{pid}").json()
    assert rec["tasks"] == [] and rec["doses"] == [] and rec["appointments"] == []


def test_too_short_note_rejected(api):  # noqa: ANN001
    doctor = api("doctor")
    r = doctor.post(f"/api/patients/{patient_id(doctor)}/care-plans", {"instructions": "rest"})
    assert r.status_code == 400


def test_llm_plan_with_invented_orders_filtered(api, fake_llm):  # noqa: ANN001
    note = "Take Tab Cefuroxime 500mg twice daily for 7 days. Avoid strenuous activity."
    fake_llm["reply"] = lambda s, u, img: as_json(
        {
            "summary": "Antibiotic course.",
            "items": [
                {"category": "MEDICATION", "action": "ADD", "title": "Cefuroxime 500mg — twice daily for 7 days", "source": "DOCTOR", "details": {"name": "Cefuroxime", "dose": "500mg", "timesPerDay": 2, "durationDays": 7}},
                # Invented orders the doctor never wrote — must be dropped
                {"category": "MEDICATION", "title": "Vitamin D 1000 IU daily", "source": "AI_SUGGESTED", "details": {"name": "Vitamin D", "timesPerDay": 1, "durationDays": 30}},
                {"category": "REFERRAL", "title": "Cardiology review", "source": "DOCTOR", "details": {"referralType": "Cardiology", "sessions": 1}},
                {"category": "FOLLOW_UP", "title": "Follow-up in 1 week", "source": "DOCTOR", "details": {"dayOffset": 7}},
                {"category": "INVESTIGATION", "title": "Lipid profile", "source": "AI_SUGGESTED", "details": {"test": "Lipid", "dayOffset": 3}},
                # Allowed AI suggestion (non-order) and an under-specified item repaired by the rule parser
                {"category": "EXERCISE", "title": "Ankle pumps", "source": "AI_SUGGESTED", "rationale": "DVT", "details": {"text": "Ankle pumps 10x"}},
                {"category": "restrictions", "title": "Avoid strenuous activity", "source": "DOCTOR", "details": "Avoid strenuous activity"},
            ],
        }
    )
    doctor = api("doctor")
    plan = doctor.post(f"/api/patients/{patient_id(doctor)}/care-plans", {"instructions": note}).json()["plan"]
    assert plan["engine"] == "groq"
    titles = {(i["category"], i["source"]) for i in plan["items"]}
    assert ("MEDICATION", "DOCTOR") in titles and ("EXERCISE", "AI_SUGGESTED") in titles and ("RESTRICTION", "DOCTOR") in titles
    names = [i["title"] for i in plan["items"]]
    assert not any(n.startswith(("Vitamin D", "Cardiology", "Follow-up", "Lipid")) for n in names), names
    # The structuring call went through a MAF Agent with the planning instructions and JSON mode
    call = fake_llm["clients"][0].calls[0]
    assert "Care Planning & Coordination Agent" in call["system"] and call["options"]["response_format"] == {"type": "json_object"}


def test_llm_invalid_output_falls_back_to_rules(api, fake_llm):  # noqa: ANN001
    fake_llm["reply"] = lambda s, u, img: "I'm sorry, I can't produce JSON today."
    doctor = api("doctor")
    plan = doctor.post(f"/api/patients/{patient_id(doctor)}/care-plans", {"instructions": NOTE}).json()["plan"]
    assert plan["engine"] == "rules" and len(plan["items"]) >= 10


def test_whole_chain_unreachable_falls_back_to_rules(api, monkeypatch):  # noqa: ANN001
    from app.core.config import get_settings

    s = get_settings()
    monkeypatch.setattr(s, "force_rule_engine", False)
    monkeypatch.setattr(s, "groq_api_key", "gsk_invalid")
    monkeypatch.setattr(s, "groq_base_url", "http://127.0.0.1:9/openai/v1")  # nothing listens here
    monkeypatch.setattr(s, "groq_fallback_model", "qwen/qwen3-32b")
    monkeypatch.setattr(s, "ollama_model", "qwen2.5:3b")
    monkeypatch.setattr(s, "ollama_base_url", "http://127.0.0.1:9")
    llm._probe.update(at=0.0, ok=False)
    doctor = api("doctor")
    plan = doctor.post(f"/api/patients/{patient_id(doctor)}/care-plans", {"instructions": NOTE}).json()["plan"]
    assert plan["engine"] == "rules"
    ai = doctor.get("/api/auth/me").json()["ai"]
    assert ai["primary"] == "groq" and ai["chain"] == ["groq:openai/gpt-oss-120b", "groq:qwen/qwen3-32b", "rules"]  # Ollama skipped: down
    llm._probe.update(at=0.0, ok=False)


def test_groq_failure_falls_back_to_ollama(api, monkeypatch):  # noqa: ANN001
    """Provider chain order: the first provider errors, the next one answers and is recorded as the engine."""
    from fake_llm import FakeChatClient

    from app.core.config import get_settings

    s = get_settings()
    monkeypatch.setattr(s, "force_rule_engine", False)
    monkeypatch.setattr(s, "groq_api_key", "gsk_test")
    monkeypatch.setattr(s, "ollama_model", "qwen2.5:3b")
    monkeypatch.setattr(llm, "_ollama_up", lambda: True)

    def boom(system: str, user: str, img: bool) -> str:
        raise RuntimeError("Groq 503")

    ok = '{"summary": "x", "items": [{"category": "RESTRICTION", "title": "Avoid strenuous activity", "source": "DOCTOR", "details": {"text": "Avoid strenuous activity"}}]}'
    monkeypatch.setattr(llm, "_client", lambda p: FakeChatClient(boom if p.engine == "groq" else (lambda s_, u, i: ok), model=p.model))
    doctor = api("doctor")
    plan = doctor.post(f"/api/patients/{patient_id(doctor)}/care-plans", {"instructions": "Avoid strenuous activity for six weeks."}).json()["plan"]
    assert plan["engine"] == "ollama" and plan["items"][0]["title"] == "Avoid strenuous activity"


IMG = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg=="


def test_prescription_image_without_vision_model_is_422(api):  # noqa: ANN001
    doctor = api("doctor")
    r = doctor.post(f"/api/patients/{patient_id(doctor)}/care-plans", {"instructions": "", "attachments": [{"name": "rx.png", "dataUrl": IMG}]})
    assert r.status_code == 422 and "vision model" in r.json()["error"]


def test_prescription_image_with_vision_model(api, fake_llm, monkeypatch):  # noqa: ANN001
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "ollama_vision_model", "llama3.2-vision")

    def reply(system: str, user: str, has_image: bool) -> str:
        if has_image:
            return as_json({"transcript": "Tab Cefuroxime 500mg 1-0-1 x 7d", "instructions": ["Take Tab Cefuroxime 500mg twice daily for 7 days."], "patientName": "Ravi Kumar", "unclear": ["signature"]})
        return "not json"  # structuring falls back to rules on the extracted text

    fake_llm["reply"] = reply
    doctor = api("doctor")
    pid = patient_id(doctor)
    plan = doctor.post(f"/api/patients/{pid}/care-plans", {"instructions": "", "attachments": [{"name": "rx.png", "dataUrl": IMG}]}).json()["plan"]
    assert any(i["category"] == "MEDICATION" and "Cefuroxime" in i["title"] for i in plan["items"])
    assert "does not match this patient" in plan["summary"] and "Unclear" in plan["summary"]
    docs = doctor.get(f"/api/patients/{pid}").json()["documents"]
    src = next(d for d in docs if d["type"] == "SOURCE_NOTE")
    assert "image" not in src["data"]  # stripped from dashboard payloads
    assert doctor.get(f"/api/documents/{src['id']}/image").json()["dataUrl"] == IMG


def test_execution_blocked_before_approval(api):  # noqa: ANN001
    from app.agents.orchestrator import orchestrator

    doctor = api("doctor")
    pid = patient_id(doctor)
    plan = doctor.post(f"/api/patients/{pid}/care-plans", {"instructions": NOTE}).json()["plan"]
    portal = doctor.c.portal  # run in the app's event loop (where the MCP connections live)
    with pytest.raises(PermissionError, match="not been approved"):
        portal.call(partial(orchestrator.execution.invoke, "execute_plan", plan_id=plan["id"]))
    rec = doctor.get(f"/api/patients/{pid}").json()
    assert rec["tasks"] == [] and rec["doses"] == []
    assert any(e["action"] == "Refused to execute unapproved care plan" and e["level"] == "CRITICAL" for e in rec["events"])


def test_approval_rules(api):  # noqa: ANN001
    doctor, specialist = api("doctor"), api("specialist")
    pid = patient_id(doctor)
    plan = doctor.post(f"/api/patients/{pid}/care-plans", {"instructions": NOTE}).json()["plan"]
    assert specialist.post(f"/api/care-plans/{plan['id']}/approve").status_code == 403  # not the treating doctor
    assert doctor.post(f"/api/care-plans/{plan['id']}/approve").status_code == 200
    assert doctor.post(f"/api/care-plans/{plan['id']}/approve").status_code == 409  # already processed
    assert doctor.patch(f"/api/care-plans/{plan['id']}", {"status": "REJECTED"}).status_code == 409  # only drafts editable


def test_doctor_edits_draft_before_approval(api):  # noqa: ANN001
    doctor = api("doctor")
    pid = patient_id(doctor)
    plan = doctor.post(f"/api/patients/{pid}/care-plans", {"instructions": NOTE}).json()["plan"]
    items = [{**i, "included": i["category"] != "REFERRAL"} for i in plan["items"] if i["source"] == "DOCTOR"]
    items.append({"category": "DIET", "title": "Soft diet for 3 days", "details": {"text": "Soft diet"}})
    edited = doctor.patch(f"/api/care-plans/{plan['id']}", {"items": items}).json()["plan"]
    assert len(edited["items"]) == len(items) and edited["items"][-1]["title"] == "Soft diet for 3 days"
    doctor.post(f"/api/care-plans/{plan['id']}/approve")
    rec = doctor.get(f"/api/patients/{pid}").json()
    assert rec["referrals"] == []  # excluded item was not executed


def test_agents_are_maf_agents(api):  # noqa: ANN001
    from agent_framework import AgentResponse, BaseAgent, Content, Message, SupportsAgentRun

    from app.agents.orchestrator import orchestrator

    for a in orchestrator.agents.values():
        assert isinstance(a, BaseAgent) and isinstance(a, SupportsAgentRun)
    msg = Message(role="user", contents=[Content.from_text('{"skill": "deactivate_rule", "args": {"patient_id": "p", "care_plan_id": "c", "description": "d"}}')])
    resp = api("doctor").c.portal.call(orchestrator.monitoring.run, msg)
    assert isinstance(resp, AgentResponse) and resp.value is False and resp.agent_id == "carexhealth-monitoring"
    # Free text without an LLM → graceful message, not an error
    resp = asyncio.run(orchestrator.planning.run("hello"))
    assert "no language model is available" in resp.text


def test_full_draft_approve_flow_keeps_safety_net_rules(api):  # noqa: ANN001
    pid, _ = draft_and_approve(api("doctor"))
    rules = api("nurse").get(f"/api/patients/{pid}").json()["rules"]
    descriptions = {r["description"] for r in rules}
    assert "SpO₂ < 90% (safety net)" in descriptions and "Pain score ≥ 8/10 (safety net)" in descriptions
