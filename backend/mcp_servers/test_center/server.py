"""Test Center MCP server — test catalogue, reference ranges, test-center lookup and test booking."""
from __future__ import annotations

from mcp_servers.common import create_server, ok

from sqlalchemy import select

from app.core.db import session_scope
from app.core.util import parse_dt
from app.models import Provider
from mcp_servers.scheduling import service as scheduling
from mcp_servers.test_center.catalogue import TEST_CATALOGUE, flag_values, resolve_test

mcp = create_server("carexhealth-test-center", "Hospital Test Center: test catalogue, reference-range flagging, test-center slots and test bookings.")


@mcp.tool()
def list_tests() -> dict:
    """The full test catalogue with aliases, preparation notes and reference ranges."""
    return ok(tests=TEST_CATALOGUE)


@mcp.tool()
def get_test_details(name: str) -> dict:
    """Resolve free text (e.g. 'CBC', 'kidney function') to a catalogue panel; unknown tests return code CUSTOM."""
    return ok(test=resolve_test(name))


@mcp.tool()
def flag_results(test_name: str, values: dict[str, float]) -> dict:
    """Deterministically flag result values against the panel's reference and critical ranges."""
    panel = resolve_test(test_name)
    return ok(test=panel, flags=flag_values(panel, values))


@mcp.tool()
def find_test_centers(exclude: list[str] | None = None) -> dict:
    """Test centers, best rated first."""
    with session_scope() as s:
        q = select(Provider).where(Provider.type == "TEST_CENTER")
        if exclude:
            q = q.where(Provider.id.not_in(exclude))
        return ok(centers=[p.to_dict() for p in s.scalars(q.order_by(Provider.rating.desc())).all()])


@mcp.tool()
def find_available_slots(center_id: str, from_date: str, count: int = 1, horizon_days: int = 7, not_before: str | None = None) -> dict:
    """Free sample-collection slots at a test center."""
    with session_scope() as s:
        slots = scheduling.find_slots(s, center_id, parse_dt(from_date), count, horizon_days, parse_dt(not_before) if not_before else None)
    return ok(slots=[scheduling.slot_dict(x) for x in slots])


@mcp.tool()
def book_test(patient_id: str, center_id: str, start: str, end: str, test_name: str, task_id: str | None = None) -> dict:
    """Book a test at a test center (appointment kind TEST)."""
    with session_scope() as s:
        a = scheduling.book(s, patient_id=patient_id, provider_id=center_id, start=parse_dt(start), end=parse_dt(end), kind="TEST", title=test_name, task_id=task_id)
        s.flush()
        s.refresh(a)
        d = a.to_dict()
        d["provider"] = a.provider.to_dict()
        return ok(appointment=d)


if __name__ == "__main__":
    mcp.run("stdio")
