"""LLM gateway — every model call goes through Microsoft Agent Framework, via one provider chain:

    Groq primary model  →  Groq fallback model  →  local Ollama  →  None (caller uses its deterministic rules)

Groq is reached with MAF's OpenAI-compatible chat-completions client; Ollama with MAF's `OllamaChatClient`.
`build_llm_agent()` returns an `LLMAgent` holding one MAF `Agent` per provider; the `run_*` helpers try them
in order and return validated data, or `None` when every provider is unavailable / failing / returns unusable
output. `last_engine()` tells the caller which provider answered ("groq" | "ollama").
Clinical safety decisions (red-flag evaluation, escalation) never call this module.
"""
from __future__ import annotations

import asyncio
import contextvars
import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeVar

import httpx
from agent_framework import Agent, Content, Message

from .config import get_settings
from .metrics import LLM_CALLS, LLM_FALLBACK, LLM_LATENCY
from .util import extract_json

log = logging.getLogger("carexhealth.llm")
T = TypeVar("T")

_THINK = re.compile(r"<think>[\s\S]*?</think>")
_last_engine: contextvars.ContextVar[str] = contextvars.ContextVar("carexhealth_llm_engine", default="rules")

# Overridable for tests: a factory returning any MAF chat client replaces the real provider chain.
_client_factory: Callable[[str], Any] | None = None
_probe: dict[str, Any] = {"at": 0.0, "ok": False}


def set_chat_client_factory(factory: Callable[[str], Any] | None) -> None:
    global _client_factory
    _client_factory = factory
    _probe.update(at=0.0, ok=False)


@dataclass(frozen=True)
class Provider:
    engine: str  # "groq" | "ollama"
    model: str
    json_format: Any  # how this client expresses JSON mode


def _ollama_up() -> bool:
    """Ollama answers (cached for 30 s so a stopped server costs nothing per call)."""
    if time.monotonic() - _probe["at"] > 30:
        try:
            _probe["ok"] = httpx.get(f"{get_settings().ollama_base_url.rstrip('/')}/api/tags", timeout=2.0).status_code == 200
        except httpx.HTTPError:
            _probe["ok"] = False
        _probe["at"] = time.monotonic()
    return bool(_probe["ok"])


def providers(vision: bool = False, *, check_ollama: bool = True) -> list[Provider]:
    s = get_settings()
    if s.force_rule_engine:
        return []
    if _client_factory is not None:
        return [Provider("groq", "test-model", {"type": "json_object"})]
    out: list[Provider] = []
    if s.groq_api_key.strip():
        models = [s.groq_vision_model] if vision else [s.groq_model, s.groq_fallback_model]
        for m in dict.fromkeys(m.strip() for m in models if m and m.strip()):
            out.append(Provider("groq", m, {"type": "json_object"}))
    local = (s.ollama_vision_model if vision else s.ollama_model).strip()
    if local and (not check_ollama or _ollama_up()):
        out.append(Provider("ollama", local, "json"))
    return out


def configured(vision: bool = False) -> bool:
    return bool(providers(vision, check_ollama=False))


def available(vision: bool = False) -> bool:
    return bool(providers(vision))


def config_key(vision: bool = False) -> tuple[Any, ...]:
    """Agents rebuild their LLM agents when this changes (e.g. tests switching providers)."""
    return (_client_factory, tuple(providers(vision, check_ollama=False)))


def last_engine() -> str:
    """The provider that produced the most recent successful answer in this task."""
    return _last_engine.get()


def llm_status() -> dict[str, Any]:
    chain = providers()
    first = chain[0] if chain else None
    return {
        "configured": configured(),
        "available": bool(chain),
        "primary": first.engine if first else "rules",
        "model": first.model if first else None,
        "chain": [f"{p.engine}:{p.model}" for p in chain] + ["rules"],
        "visionModel": next((p.model for p in providers(True)), None),
    }


def _client(p: Provider) -> Any:
    if _client_factory is not None:
        return _client_factory(p.model)
    s = get_settings()
    if p.engine == "groq":
        from agent_framework.openai import OpenAIChatCompletionClient

        return OpenAIChatCompletionClient(model=p.model, api_key=s.groq_api_key, base_url=s.groq_base_url)
    from agent_framework.ollama import OllamaChatClient

    return OllamaChatClient(host=s.ollama_base_url, model=p.model)


class LLMAgent:
    """One MAF `Agent` per provider in the chain, sharing the same name and instructions."""

    def __init__(self, name: str, instructions: str | None, vision: bool) -> None:
        self.name = name
        self.vision = vision
        self.chain: list[tuple[Provider, Agent]] = [
            (p, Agent(client=_client(p), instructions=instructions, name=name, default_options={"temperature": 0.2})) for p in providers(vision, check_ollama=False)
        ]

    def live(self) -> list[tuple[Provider, Agent]]:
        """Skip Ollama when its server is down (Groq failures are discovered per call)."""
        return [(p, a) for p, a in self.chain if p.engine != "ollama" or _ollama_up()]


def build_llm_agent(name: str, instructions: str, *, vision: bool = False, tools: list[Any] | None = None) -> LLMAgent | None:
    """The reasoning model for an agent purpose, or None if no provider is configured.

    Vision agents carry their instructions in the user turn instead (several vision models reject a system
    message alongside images)."""
    if not configured(vision):
        return None
    del tools  # deterministic skills call the MCP tools; the LLM only reasons over provided context
    return LLMAgent(name, None if vision else instructions, vision)


def _retry_delay(err: Exception) -> float | None:
    """Groq 429s say 'Please try again in 2.28s' — wait that long once if it is short."""
    msg = str(err)
    if "429" not in msg and "rate limit" not in msg.lower():
        return None
    m = re.search(r"try again in ([\d.]+)(ms|s)", msg)
    if not m:
        return 3.0
    secs = float(m.group(1)) / (1000 if m.group(2) == "ms" else 1)
    return secs + 0.25 if secs <= 20 else None


async def _ask[T](llm_agent: LLMAgent | None, messages: Any, options: dict[str, Any], validate: Callable[[str], T], timeout: float | None = None) -> T | None:
    if llm_agent is None:
        return None
    for provider, agent in llm_agent.live():
        opts = {**options, "response_format": provider.json_format} if options.get("response_format") else dict(options)
        for attempt in range(2):
            started = time.monotonic()
            try:
                resp = await asyncio.wait_for(agent.run(messages, options=opts), timeout or get_settings().llm_timeout_seconds)
                text = _THINK.sub("", resp.text or "").strip()
                if not text:
                    raise ValueError("empty response")
                value = validate(text)
                _last_engine.set(provider.engine)
                LLM_CALLS.labels(provider.engine, "ok").inc()
                LLM_LATENCY.labels(provider.engine).observe(time.monotonic() - started)
                return value
            except Exception as e:  # noqa: BLE001 — fall through to the next provider, then to the rule engine
                LLM_CALLS.labels(provider.engine, "failed").inc()
                wait = _retry_delay(e) if attempt == 0 else None
                log.warning("[llm] %s via %s/%s failed%s: %s", llm_agent.name, provider.engine, provider.model, f", retrying in {wait:.1f}s" if wait else "", str(e)[:200])
                if not wait:
                    break
                await asyncio.sleep(wait)
    LLM_FALLBACK.inc()
    return None


async def run_json[T](agent: LLMAgent | None, prompt: str, validate: Callable[[Any], T]) -> T | None:
    """Structured generation: JSON mode + caller-side validation (Pydantic / domain filters)."""
    return await _ask(agent, prompt + "\nRespond with valid JSON only.", {"response_format": True}, lambda t: validate(extract_json(t)))


async def run_text(agent: LLMAgent | None, prompt: str) -> str | None:
    return await _ask(agent, prompt, {}, lambda t: t)


async def run_vision_json[T](agent: LLMAgent | None, instructions: str, images: list[str], validate: Callable[[Any], T]) -> T | None:
    """Reads images (data URLs) with the vision chain (instructions travel in the user turn)."""
    if not images:
        return None
    contents: list[Any] = [Content.from_text(instructions + "\nRespond with valid JSON only.")]
    for url in images:
        media = url[5 : url.index(";")] if url.startswith("data:") and ";" in url else "image/jpeg"
        contents.append(Content.from_uri(uri=url, media_type=media))
    msg = [Message(role="user", contents=contents)]
    return await _ask(agent, msg, {"response_format": True, "temperature": 0.1}, lambda t: validate(extract_json(t)), timeout=max(get_settings().llm_timeout_seconds, 120))
