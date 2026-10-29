"""Starts the API on a fresh, seeded, throw-away database with the LLM off — used by the Playwright suite."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
tmp = Path(tempfile.mkdtemp(prefix="carexhealth-e2e-"))
os.environ.update(
    DATABASE_URL=f"sqlite:///{(tmp / 'e2e.db').as_posix()}", AUTH_SECRET="e2e-secret-e2e-secret-e2e-secret-1234", FORCE_RULE_ENGINE="true",
    GROQ_API_KEY="", OLLAMA_MODEL="", DEMO_MODE="true", SCHEDULER_ENABLED="false",
)  # fmt: skip

from scripts.seed import seed  # noqa: E402

seed()

import uvicorn  # noqa: E402

uvicorn.run("app.main:app", host="127.0.0.1", port=8000)
