"""Central APScheduler configuration — persistent jobs in SQLite (table `apscheduler_jobs`).

* Fixed job ids + replace_existing → restarts update rather than duplicate jobs; next run times survive restarts.
* coalesce + max_instances=1 → a backlog after downtime runs once, never concurrently.
* An exclusive lock file → only one process (e.g. one of several uvicorn workers) runs the scheduler.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import IO, Any

from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core.config import BACKEND_DIR, get_settings

from .jobs import JOBS

log = logging.getLogger("carexhealth.scheduler")

# Seconds between runs per job; the dose / escalation jobs follow AGENT_CYCLE_SECONDS like the legacy loop.
_lock_handle: IO[Any] | None = None


def _acquire_singleton_lock(path: Path) -> bool:
    global _lock_handle
    handle = open(path, "a+")  # noqa: SIM115 — held for the process lifetime
    try:
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return False
    _lock_handle = handle
    return True


def _release_singleton_lock() -> None:
    global _lock_handle
    if _lock_handle is None:
        return
    try:
        if os.name == "nt":
            import msvcrt

            _lock_handle.seek(0)
            msvcrt.locking(_lock_handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(_lock_handle.fileno(), fcntl.LOCK_UN)
    finally:
        _lock_handle.close()
        _lock_handle = None


def build_scheduler(database_url: str | None = None) -> AsyncIOScheduler:
    url = database_url or get_settings().database_url
    return AsyncIOScheduler(
        jobstores={"default": SQLAlchemyJobStore(url=url, tablename="apscheduler_jobs")},
        job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 300},
    )


def register_jobs(scheduler: AsyncIOScheduler, interval_seconds: int | None = None) -> None:
    seconds = max(interval_seconds or get_settings().agent_cycle_seconds or 60, 15)
    for name in JOBS:
        existing = scheduler.get_job(name)
        if existing is not None and getattr(existing.trigger, "interval", None) is not None and existing.trigger.interval.total_seconds() == seconds:
            continue  # persisted job with the same cadence — keep its next_run_time across the restart
        scheduler.add_job(f"app.scheduler.jobs:{name}", "interval", seconds=seconds, id=name, name=name, replace_existing=True)


_scheduler: AsyncIOScheduler | None = None


def start_scheduler() -> AsyncIOScheduler | None:
    global _scheduler
    if not get_settings().scheduler_enabled:
        log.info("Scheduler disabled (SCHEDULER_ENABLED=false)")
        return None
    if not _acquire_singleton_lock(BACKEND_DIR / ".scheduler.lock"):
        log.info("Scheduler already running in another process — not starting a second one")
        return None
    _scheduler = build_scheduler()
    _scheduler.start()
    register_jobs(_scheduler)
    log.info("APScheduler started with %d persistent jobs", len(_scheduler.get_jobs()))
    return _scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
    _release_singleton_lock()
