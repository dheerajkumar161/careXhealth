"""/api/stream — Server-Sent Events: pushes new notifications/alerts to the signed-in user within ~2 s.

Notifications are written by other processes (MCP servers, scheduler), so the stream watches the database rather than an
in-process bus. The browser falls back to polling if the stream is unavailable.
"""
from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select

from app.auth.deps import require_user
from app.auth.security import SessionUser
from app.core.db import session_scope
from app.models import Notification

router = APIRouter(tags=["stream"])
POLL_SECONDS = 2.0
HEARTBEAT_SECONDS = 15.0


def snapshot(user_id: str) -> tuple[int, str | None, int]:
    """(total notifications, newest id, unread) — cheap change detector."""
    with session_scope() as s:
        total = s.scalar(select(func.count()).select_from(Notification).where(Notification.user_id == user_id)) or 0
        newest = s.scalars(select(Notification.id).where(Notification.user_id == user_id).order_by(Notification.created_at.desc(), Notification.id.desc()).limit(1)).first()
        unread = s.scalar(select(func.count()).select_from(Notification).where(Notification.user_id == user_id, Notification.read.is_(False))) or 0
    return total, newest, unread


def new_since(user_id: str, last_id: str | None) -> list[dict]:
    with session_scope() as s:
        rows = list(s.scalars(select(Notification).where(Notification.user_id == user_id).order_by(Notification.created_at.desc()).limit(10)))
    out = []
    for n in rows:
        if n.id == last_id:
            break
        out.append({"id": n.id, "type": n.type, "title": n.title, "link": n.link})
    return out


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@router.get("/api/stream")
async def stream(request: Request, maxSeconds: float = 3600, user: SessionUser = Depends(require_user)) -> StreamingResponse:  # noqa: N803
    async def gen() -> AsyncIterator[str]:
        total, newest, unread = await asyncio.to_thread(snapshot, user.id)
        yield _sse("ready", {"unread": unread})
        waited = since_beat = 0.0
        while waited < min(maxSeconds, 3600):
            if await request.is_disconnected():
                return
            await asyncio.sleep(POLL_SECONDS)
            waited += POLL_SECONDS
            since_beat += POLL_SECONDS
            t2, n2, u2 = await asyncio.to_thread(snapshot, user.id)
            if (t2, n2, u2) != (total, newest, unread):
                fresh = await asyncio.to_thread(new_since, user.id, newest) if n2 != newest else []
                total, newest, unread = t2, n2, u2
                yield _sse("notification", {"unread": u2, "items": fresh})
                since_beat = 0
            elif since_beat >= HEARTBEAT_SECONDS:
                since_beat = 0
                yield ": keep-alive\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"})
