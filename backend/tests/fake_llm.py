"""A scripted Microsoft Agent Framework chat client: lets tests drive the LLM paths without Ollama."""
from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from agent_framework import BaseChatClient, ChatResponse, Message


class FakeChatClient(BaseChatClient):
    """`reply(system, user_text, has_image) -> str` decides the model output for each call."""

    def __init__(self, reply: Callable[[str, str, bool], str], model: str = "fake-model") -> None:
        super().__init__()
        self.model = model
        self.reply = reply
        self.calls: list[dict[str, Any]] = []

    async def _respond(self, messages: list[Message], options: Any) -> ChatResponse:
        system = (options or {}).get("instructions") or ""
        user = messages[-1]
        has_image = any(getattr(c, "type", "") in ("data", "uri") for c in user.contents)
        text = self.reply(system, user.text or "", has_image)
        self.calls.append({"system": system, "user": user.text, "image": has_image, "options": dict(options or {})})
        return ChatResponse(messages=[Message(role="assistant", contents=[text])])

    def _inner_get_response(self, *, messages, stream, options, **kwargs):  # noqa: ANN001, ANN003, ANN202
        if stream:
            raise NotImplementedError
        return self._respond(list(messages), options)


def as_json(obj: Any) -> str:
    return json.dumps(obj)
