"""Scheduled job bodies — the legacy `runAgentCycle()` decomposed into independent persistent jobs.

Referenced by import path (`app.scheduler.jobs:<name>`) so the persistent job store can rehydrate them after a restart.
All jobs share one lock, replacing the legacy `running` guard so cycle steps never interleave.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

log = logging.getLogger("carexhealth.scheduler")
_cycle_lock = asyncio.Lock()


async def _run(name: str) -> Any:
    from app.agents.orchestrator import orchestrator

    async with _cycle_lock:
        try:
            result = await getattr(orchestrator, name)()
            log.debug("[job] %s → %s", name, result)
            return result
        except Exception:
            log.exception("[job] %s failed", name)
            return None


async def send_due_dose_reminders() -> Any:
    return await _run("send_due_dose_reminders")


async def mark_overdue_doses() -> Any:
    return await _run("mark_overdue_doses")


async def check_missed_appointments() -> Any:
    return await _run("check_missed_appointments")


async def check_adherence() -> Any:
    return await _run("check_adherence")


async def escalate_unacknowledged_alerts() -> Any:
    return await _run("escalate_unacknowledged_alerts")


async def deliver_notifications() -> Any:
    """Send due email/SMS copies of notifications (retries with backoff; independent of the agent cycle lock)."""
    from app.services import delivery

    try:
        return await delivery.process_due_async()
    except Exception:
        log.exception("[job] deliver_notifications failed")
        return None


async def run_full_cycle() -> dict[str, Any]:
    """On-demand cycle ("Agents live"): the MAF cycle workflow, serialized with the scheduled jobs."""
    from app.agents.orchestrator import orchestrator

    async with _cycle_lock:
        return await orchestrator.run_agent_cycle()


JOBS = ["send_due_dose_reminders", "mark_overdue_doses", "check_missed_appointments", "check_adherence", "escalate_unacknowledged_alerts", "deliver_notifications"]
