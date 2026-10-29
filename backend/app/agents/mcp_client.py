"""MCP client side of the hospital services.

Agents reach hospital services ONLY through these Microsoft Agent Framework `MCPStdioTool` connections —
one stdio MCP server process per service. Nothing in `app.agents` imports a service implementation.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from typing import Any

from agent_framework import FunctionTool, MCPStdioTool

from app.core.config import BACKEND_DIR, get_settings

log = logging.getLogger("carexhealth.mcp")

SERVICES: dict[str, str] = {
    "scheduling": "mcp_servers.scheduling.server",
    "provider_directory": "mcp_servers.provider_directory.server",
    "test_center": "mcp_servers.test_center.server",
    "notification": "mcp_servers.notification.server",
    "ehr": "mcp_servers.ehr.server",
}


class MCPCallError(RuntimeError):
    pass


class HospitalServices:
    """Connections to the five hospital-service MCP servers."""

    def __init__(self) -> None:
        self.tools: dict[str, MCPStdioTool] = {}
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        async with self._lock:
            if self.tools:
                return
            env = {**os.environ, "DATABASE_URL": get_settings().database_url, "PYTHONPATH": str(BACKEND_DIR), "PYTHONIOENCODING": "utf-8"}
            tools = {
                name: MCPStdioTool(
                    name=name,
                    command=sys.executable,
                    args=["-m", module],
                    env=env,
                    load_prompts=False,
                    request_timeout=60,
                    description=f"CareXHealth hospital {name.replace('_', ' ')} service",
                )
                for name, module in SERVICES.items()
            }
            await asyncio.gather(*(t.connect() for t in tools.values()))
            self.tools = tools
            log.info("Connected to %d hospital MCP servers: %s", len(tools), ", ".join(tools))

    async def close(self) -> None:
        for t in self.tools.values():
            try:
                await t.close()
            except Exception:  # noqa: BLE001
                log.debug("MCP close failed", exc_info=True)
        self.tools = {}

    def functions(self, service: str, names: list[str] | None = None) -> list[FunctionTool]:
        """MCP tools as MAF FunctionTools (for handing a read-only subset to an LLM agent)."""
        fns = self.tools[service].functions
        return [f for f in fns if names is None or f.name in names]

    async def call(self, service: str, tool: str, **kwargs: Any) -> dict[str, Any]:
        if not self.tools:
            await self.connect()
        args = {k: v for k, v in kwargs.items() if v is not None}
        try:
            result = await self.tools[service].call_tool(tool, **args)
        except Exception as e:  # noqa: BLE001
            raise MCPCallError(f"{service}.{tool} failed: {e}") from e
        texts = [c.text for c in result if getattr(c, "text", None)] if isinstance(result, list) else [str(result)]
        if not texts:
            return {}
        try:
            data = json.loads(texts[0])
        except ValueError as e:
            raise MCPCallError(f"{service}.{tool} returned non-JSON: {texts[0][:200]}") from e
        if isinstance(data, dict) and data.get("isError"):
            raise MCPCallError(f"{service}.{tool}: {data}")
        return data


services = HospitalServices()
