"""Structured logging with per-request IDs and PHI-safe redaction (emails, bearer tokens, long digit runs)."""
from __future__ import annotations

import contextvars
import json
import logging
import re
import sys
from datetime import UTC, datetime

request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)
client_ip_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("client_ip", default=None)

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_BEARER = re.compile(r"(?i)bearer\s+[\w.\-]+")
_DIGITS = re.compile(r"\b\d{8,}\b")


def redact(text: str) -> str:
    text = _BEARER.sub("Bearer [redacted]", text)
    text = _EMAIL.sub("[email]", text)
    return _DIGITS.sub("[number]", text)


class _Redact(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(record.getMessage())
        record.args = ()
        return True


class _Json(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        out = {"ts": datetime.now(UTC).isoformat(timespec="milliseconds"), "level": record.levelname, "logger": record.name, "msg": record.getMessage(), "request_id": request_id_var.get()}
        if record.exc_info:
            out["exc"] = self.formatException(record.exc_info)
        return json.dumps(out)


def setup_logging(json_logs: bool = False) -> None:
    handler = logging.StreamHandler(sys.stderr)
    handler.addFilter(_Redact())
    handler.setFormatter(_Json() if json_logs else logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s"))
    root = logging.getLogger()
    for h in list(root.handlers):
        if getattr(h, "_carexhealth", False):
            root.removeHandler(h)
    handler._carexhealth = True  # type: ignore[attr-defined]
    root.addHandler(handler)
    if root.level == logging.WARNING:
        root.setLevel(logging.INFO)
