"""Shared bootstrap for the hospital-service MCP servers.

Each service runs as its own stdio MCP server process (`python -m mcp_servers.<service>.server`), owns its
deterministic service logic, and persists through SQLAlchemy into the shared SQLite database.
MCP servers contain NO LLM reasoning.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from mcp.server.fastmcp import FastMCP  # noqa: E402

from app.core.db import init_db  # noqa: E402


def create_server(name: str, instructions: str) -> FastMCP:
    logging.basicConfig(level=logging.WARNING, stream=sys.stderr)
    init_db()
    return FastMCP(name, instructions=instructions, log_level="WARNING")


def ok(**kw: Any) -> dict[str, Any]:
    """MCP tools always return an object (lists get split into separate contents by the SDK)."""
    return kw
