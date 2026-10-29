"""Architecture guards: MAF agents, MCP boundaries, no Groq, deterministic monitoring."""
import ast
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]


def _imports(path: Path) -> set[str]:
    mods: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            mods |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods.add(node.module)
    return mods


def test_agents_never_import_hospital_service_code():
    for f in (BACKEND / "app" / "agents").glob("*.py"):
        assert not any(m.startswith("mcp_servers") for m in _imports(f)), f.name


def test_monitoring_agent_has_no_llm_dependency():
    mods = _imports(BACKEND / "app" / "agents" / "monitoring_agent.py")
    assert "app.core.llm" not in mods and not any("llm" in m for m in mods)


def test_mcp_servers_have_no_llm():
    for f in (BACKEND / "mcp_servers").rglob("*.py"):
        mods = _imports(f)
        assert not any(m.startswith(("agent_framework", "app.core.llm", "ollama")) for m in mods), f


def test_llm_calls_are_centralised():
    """Only core/llm.py creates model clients (Groq via MAF's OpenAI-compatible client, Ollama via MAF's Ollama client)."""
    clients = ("agent_framework.ollama", "agent_framework_ollama", "ollama", "agent_framework.openai", "agent_framework_openai", "openai", "groq")
    for f in list((BACKEND / "app").rglob("*.py")) + list((BACKEND / "mcp_servers").rglob("*.py")):
        if f.name in ("llm.py", "config.py"):  # the gateway, and the settings holding the default Groq URL
            continue
        assert not any(m.startswith(clients) for m in _imports(f)), f
        assert "api.groq.com" not in f.read_text(encoding="utf-8"), f


def test_mcp_servers_expose_required_tools(app_client):  # noqa: ANN001
    from app.agents.orchestrator import orchestrator

    tools = {name: {f.name for f in t.functions} for name, t in orchestrator.services.tools.items()}
    assert {"find_available_slots", "hold_slot", "book_slot", "cancel_booking", "reschedule_booking", "create_recurring_booking"} <= tools["scheduling"]
    assert {"find_provider", "find_providers_by_specialty", "check_provider_availability"} <= tools["provider_directory"]
    assert {"list_tests", "get_test_details", "find_available_slots", "book_test"} <= tools["test_center"]
    assert {"notify_patient", "notify_nurse", "notify_doctor", "notify_provider", "create_in_app_notification"} <= tools["notification"]
    assert {"get_patient_context", "get_patient_records", "store_document", "get_documents", "create_audit_event"} <= tools["ehr"]


def test_agents_endpoint(api):  # noqa: ANN001
    data = api("doctor").get("/api/agents").json()
    assert data["framework"] == "Microsoft Agent Framework"
    assert [a["key"] for a in data["agents"]] == ["PLANNING", "EXECUTION", "MONITORING", "COMMUNICATION", "INTELLIGENCE"]
    assert set(data["mcpServers"]) == {"scheduling", "provider_directory", "test_center", "notification", "ehr"}


def test_provider_availability_tool(api):  # noqa: ANN001
    from functools import partial

    from app.agents.orchestrator import orchestrator
    from app.core.util import iso, now

    doctor = api("doctor")
    pid = doctor.get("/api/patients").json()["patients"][0]["id"]  # noqa: F841
    physio = doctor.c.portal.call(partial(orchestrator.services.call, "provider_directory", "find_providers_by_specialty", specialty="physio"))["providers"][0]
    res = doctor.c.portal.call(partial(orchestrator.services.call, "provider_directory", "check_provider_availability", provider_id=physio["id"], from_date=iso(now()), sessions=6, per_week=3))
    assert res["available"] is True and len(res["slots"]) == 6
