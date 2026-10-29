"""CareXHealth agent base — a Microsoft Agent Framework agent.

Each of the five CareXHealth agents subclasses MAF's `BaseAgent` (the framework's extension point for custom
agents) and therefore satisfies `SupportsAgentRun`: it has an id/name/description, `run()` returns an
`AgentResponse`, it supports sessions, can be placed in MAF Workflows, exposed with `as_tool()`, etc.

How an agent works:
* Structured commands — a message whose text is `{"skill": ..., "args": {...}}` — run one of the agent's
  skills. Skills orchestrate deterministic domain logic and call hospital services through MCP tools.
* Reasoning (structuring notes, narratives, patient answers) is delegated to the agent's MAF chat `Agent`
  on the local Ollama model (`self.llm`, built by `core.llm`). Free-text messages go straight to it.
* When Ollama is unavailable the skills use their deterministic fallbacks; safety logic never uses the LLM.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from agent_framework import AgentResponse, BaseAgent, Content, Message

from app.core import llm
from app.core.util import dumps

from .mcp_client import HospitalServices

log = logging.getLogger("carexhealth.agents")

SkillFn = Callable[..., Awaitable[Any]]


class AgentError(Exception):
    """A business-rule refusal raised by an agent skill; the API maps `status` to the HTTP status code."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


def skill(fn: SkillFn) -> SkillFn:
    """Marks an agent method as a skill invocable via a structured command message."""
    fn.__carexhealth_skill__ = True  # type: ignore[attr-defined]
    return fn


class CareXHealthAgent(BaseAgent):
    key: str = ""
    instructions: str = ""

    def __init__(self, *, services: HospitalServices, name: str, description: str) -> None:
        super().__init__(id=f"carexhealth-{self.key.lower()}", name=name, description=description)
        self.services = services
        self._skills: dict[str, SkillFn] = {
            attr: getattr(self, attr) for attr in dir(type(self)) if getattr(getattr(type(self), attr, None), "__carexhealth_skill__", False)
        }
        self._llm_cache: dict[str, tuple[tuple[Any, ...], llm.LLMAgent | None]] = {}
        self.peers: dict[str, CareXHealthAgent] = {}

    async def ask(self, agent_key: str, skill_name: str, **args: Any) -> Any:
        """Agent-to-agent collaboration — always through the peer's MAF `run()` entry point."""
        return await self.peers[agent_key].invoke(skill_name, **args)

    # ── MAF agent protocol ────────────────────────────────────────────────────────────────

    @property
    def skills(self) -> list[str]:
        return sorted(self._skills)

    def llm_agent(self, purpose: str = "default", instructions: str | None = None, *, vision: bool = False) -> llm.LLMAgent | None:
        """MAF chat Agents (Groq → Ollama chain) for one reasoning purpose (rebuilt if the LLM configuration changes)."""
        cache_key = llm.config_key(vision)
        cached = self._llm_cache.get(purpose)
        if cached is None or cached[0] != cache_key:
            name = f"{self.name} · {purpose}" if purpose != "default" else (self.name or self.key)
            cached = (cache_key, llm.build_llm_agent(name, instructions or self.instructions, vision=vision))
            self._llm_cache[purpose] = cached
        return cached[1]

    @property
    def llm(self) -> llm.LLMAgent | None:
        """This agent's primary reasoning model."""
        return self.llm_agent()

    async def run(  # type: ignore[override]
        self,
        messages: Any = None,
        *,
        stream: bool = False,
        session: Any = None,
        function_invocation_kwargs: Any = None,
        client_kwargs: Any = None,
        **_: Any,
    ) -> AgentResponse:
        if stream:
            raise NotImplementedError(f"{self.name} does not stream; call run(stream=False)")
        text = _last_text(messages)
        command = _parse_command(text)
        if command is None:
            return await self._converse(messages, session)
        name, args = command
        if name not in self._skills:
            raise ValueError(f"{self.name} has no skill '{name}'. Available: {', '.join(self.skills)}")
        result = await self._skills[name](**args)
        return AgentResponse(
            messages=[Message(role="assistant", contents=[Content.from_text(dumps(result) if result is not None else "ok")], author_name=self.name)],
            agent_id=self.id,
            value=result,
        )

    async def _converse(self, messages: Any, session: Any) -> AgentResponse:
        chain = self.llm.live() if self.llm is not None else []
        for _, agent in chain:
            try:
                return await agent.run(messages, session=session)
            except Exception:  # noqa: BLE001 — try the next provider
                log.warning("%s: provider failed in conversation", self.name, exc_info=True)
        msg = f"{self.name}: no language model is available; structured skills still work: {', '.join(self.skills)}"
        return AgentResponse(messages=[Message(role="assistant", contents=[Content.from_text(msg)], author_name=self.name)], agent_id=self.id)

    async def invoke(self, skill_name: str, **args: Any) -> Any:
        """Run one skill through the MAF `run()` entry point and return its structured value."""
        command = Message(role="user", contents=[Content.from_text(json.dumps({"skill": skill_name, "args": args}, default=str))])
        return (await self.run(command)).value

    # ── helpers shared by the agents ─────────────────────────────────────────────────────

    async def mcp(self, service: str, tool: str, **kwargs: Any) -> dict[str, Any]:
        return await self.services.call(service, tool, **kwargs)

    async def audit(self, action: str, *, patient_id: str | None = None, detail: str | None = None, level: str = "INFO", agent: str | None = None) -> None:
        """Every agent/service/human action goes to the AgentEvent audit trail via the EHR MCP server."""
        await self.services.call("ehr", "create_audit_event", agent=agent or self.key, action=action, patient_id=patient_id, detail=detail, level=level)

    async def notify(self, audience: str, patient_id: str, type_: str, title: str, body: str, link: str | None = None) -> bool:
        tool = {"PATIENT": "notify_patient", "DOCTOR": "notify_doctor", "NURSE": "notify_nurse"}[audience]
        return bool((await self.services.call("notification", tool, patient_id=patient_id, type=type_, title=title, body=body, link=link)).get("delivered"))

    async def notify_user(self, user_id: str, type_: str, title: str, body: str, link: str | None = None) -> None:
        await self.services.call("notification", "create_in_app_notification", user_id=user_id, type=type_, title=title, body=body, link=link)

    async def notify_provider(self, provider_id: str, type_: str, title: str, body: str) -> bool:
        return bool((await self.services.call("notification", "notify_provider", provider_id=provider_id, type=type_, title=title, body=body)).get("delivered"))


def _last_text(messages: Any) -> str:
    if messages is None:
        return ""
    if isinstance(messages, str):
        return messages
    if isinstance(messages, Message):
        return messages.text or ""
    if isinstance(messages, (list, tuple)) and messages:
        return _last_text(messages[-1])
    return str(messages)


def _parse_command(text: str) -> tuple[str, dict[str, Any]] | None:
    t = text.strip()
    if not t.startswith("{"):
        return None
    try:
        data = json.loads(t)
    except ValueError:
        return None
    if isinstance(data, dict) and isinstance(data.get("skill"), str):
        return data["skill"], dict(data.get("args") or {})
    return None
