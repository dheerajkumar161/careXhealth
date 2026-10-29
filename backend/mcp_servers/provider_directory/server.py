"""Provider Directory MCP server — finds suitable providers for a requirement (port of lib/services/providerDirectory.ts)."""
from __future__ import annotations

from mcp_servers.common import create_server, ok

from sqlalchemy import select

from app.core.db import session_scope
from app.core.util import parse_dt
from app.models import Provider
from mcp_servers.scheduling import service as scheduling

mcp = create_server("carexhealth-provider-directory", "Hospital Provider Directory: specialty matching, provider lookup and availability checks.")

SYNONYMS: dict[str, list[str]] = {
    "physiotherapy": ["physio", "physiotherapy", "physical therapy", "rehabilitation", "rehab", "mobility"],
    "cardiology": ["cardio", "cardiology", "heart", "cardiac"],
    "dietetics": ["diet", "dietitian", "dietician", "nutrition", "nutritionist", "dietetics"],
    "psychology": ["psych", "psychology", "counselling", "counseling", "mental health"],
    "occupational therapy": ["occupational"],
    "speech therapy": ["speech", "swallow"],
    "wound care": ["wound", "dressing", "suture"],
    "home nursing": ["home nursing", "home care", "home visit", "nursing visit"],
    "orthopedics": ["ortho", "orthopedic", "orthopaedic", "bone", "joint"],
    "endocrinology": ["endocrin", "diabetes", "thyroid"],
    "pulmonology": ["pulmo", "lung", "respiratory"],
    "laboratory": ["lab", "blood test", "pathology", "diagnostic"],
    "radiology": ["x-ray", "xray", "mri", "ct scan", "ultrasound", "scan", "imaging"],
    "general medicine": ["general", "physician", "internal medicine"],
}


def normalize(text: str) -> str:
    s = text.lower()
    for key, words in SYNONYMS.items():
        if s == key or any(w in s for w in words):
            return key
    return s.strip()


@mcp.tool()
def normalize_specialty(specialty: str) -> dict:
    """Map free text (e.g. 'physio') to the directory's canonical specialty key."""
    return ok(specialty=normalize(specialty))


@mcp.tool()
def find_providers_by_specialty(specialty: str, exclude: list[str] | None = None, types: list[str] | None = None) -> dict:
    """Providers accepting referrals for a specialty, best match first, then by rating."""
    key = normalize(specialty)
    with session_scope() as s:
        q = select(Provider).where(Provider.accepts_referrals.is_(True))
        if types:
            q = q.where(Provider.type.in_(types))
        scored = []
        for p in s.scalars(q).all():
            if exclude and p.id in exclude:
                continue
            specs = [x.strip().lower() for x in p.specialties.split(",")]
            score = 2 if key in specs else 1 if any(x in key or key in x for x in specs) else 0
            if score:
                scored.append((score, p))
        scored.sort(key=lambda t: (-t[0], -t[1].rating))
        return ok(providers=[p.to_dict() for _, p in scored])


@mcp.tool()
def find_provider(provider_id: str | None = None, user_id: str | None = None) -> dict:
    """Look up one provider by id or by its linked portal user (e.g. the treating doctor's OPD listing)."""
    with session_scope() as s:
        p = s.get(Provider, provider_id) if provider_id else s.scalars(select(Provider).where(Provider.user_id == user_id)).first() if user_id else None
        if p is None:
            return ok(provider=None)
        d = p.to_dict()
        d["portalRole"] = p.user.role if p.user else None
        return ok(provider=d)


@mcp.tool()
def check_provider_availability(provider_id: str, from_date: str, sessions: int = 1, per_week: int = 1, not_before: str | None = None) -> dict:
    """Whether the provider has capacity for `sessions` appointments from `from_date` (single slot or recurring series)."""
    with session_scope() as s:
        start, nb = parse_dt(from_date), parse_dt(not_before) if not_before else None
        slots = scheduling.find_series_slots(s, provider_id, start, sessions, per_week, nb) if sessions > 1 else scheduling.find_slots(s, provider_id, start, 1, 14, nb)
    return ok(available=len(slots) >= sessions, slots=[scheduling.slot_dict(x) for x in slots])


if __name__ == "__main__":
    mcp.run("stdio")
