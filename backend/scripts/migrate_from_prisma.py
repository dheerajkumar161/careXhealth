"""One-off data migration: copy an existing Prisma SQLite database (prisma/carexhealth.db) into the SQLAlchemy schema.

    python scripts/migrate_from_prisma.py [path/to/prisma.db]

Prisma stored DateTime as epoch milliseconds and booleans as 0/1; table/column names were PascalCase/camelCase.
Legacy role PROVIDER for test-center logins becomes TEST_CENTER (role normalization); departments are derived.
The target database is wiped first.
"""
from __future__ import annotations

import re
import sqlite3
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import Boolean, DateTime  # noqa: E402

from app.core.db import Base, get_engine  # noqa: E402
from scripts.seed import reset  # noqa: E402

TABLES = {  # prisma model → SQLAlchemy table (insert order respects foreign keys)
    "User": "users",
    "Provider": "providers",
    "Patient": "patients",
    "CarePlan": "care_plans",
    "CarePlanItem": "care_plan_items",
    "CareTask": "care_tasks",
    "MedicationDose": "medication_doses",
    "Referral": "referrals",
    "Appointment": "appointments",
    "MonitoringRule": "monitoring_rules",
    "Observation": "observations",
    "Alert": "alerts",
    "Document": "documents",
    "Notification": "notifications",
    "AgentEvent": "agent_events",
    "ChatMessage": "chat_messages",
    "NurseReleaseRequest": "nurse_release_requests",
}


EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
LOCAL_OFFSET = datetime.now().astimezone().utcoffset() or timedelta(0)


def snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z0-9])", "_", name).lower().replace("value_2", "value2")


def migrate(src: Path) -> dict[str, int]:
    reset()
    con = sqlite3.connect(src)
    con.row_factory = sqlite3.Row
    counts: dict[str, int] = {}
    meta = {t.name: t for t in Base.metadata.sorted_tables}
    with get_engine().begin() as conn:
        for model, table_name in TABLES.items():
            table = meta[table_name]
            rows = con.execute(f'SELECT * FROM "{model}"').fetchall()  # noqa: S608 (fixed table names)
            out = []
            for r in rows:
                rec = {}
                for key in r.keys():  # noqa: SIM118
                    col = table.c.get(snake(key))
                    if col is None:
                        continue
                    v = r[key]
                    if v is not None and isinstance(col.type, DateTime):
                        # epoch ms → naive local time (arithmetic, so pre-1970 dates of birth work on Windows too)
                        utc = EPOCH + timedelta(milliseconds=v) if isinstance(v, (int, float)) else datetime.fromisoformat(str(v).replace("Z", "+00:00"))
                        v = (utc + LOCAL_OFFSET).replace(tzinfo=None)
                    elif v is not None and isinstance(col.type, Boolean):
                        v = bool(v)
                    rec[col.name] = v
                if table_name == "users":
                    if rec.get("role") == "PROVIDER":
                        rec["role"] = "TEST_CENTER"
                    rec.setdefault("department", {"NURSE": "Nursing", "TEST_CENTER": "Laboratory"}.get(rec["role"]))
                out.append(rec)
            if out:
                conn.execute(table.insert(), out)
            counts[model] = len(out)
        # Doctors' department = their first listed specialty in the provider directory; patients inherit their doctor's
        users, providers, patients = meta["users"], meta["providers"], meta["patients"]
        for uid, specs in conn.execute(providers.select().with_only_columns(providers.c.user_id, providers.c.specialties).where(providers.c.type == "DOCTOR")):
            conn.execute(users.update().where(users.c.id == uid, users.c.department.is_(None)).values(department=specs.split(",")[0].strip().title()))
        for puid, did in conn.execute(patients.select().with_only_columns(patients.c.user_id, patients.c.doctor_id)):
            dept = conn.execute(users.select().with_only_columns(users.c.department).where(users.c.id == did)).scalar()
            conn.execute(users.update().where(users.c.id == puid, users.c.department.is_(None)).values(department=dept))
    return counts


if __name__ == "__main__":
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[2] / "prisma" / "carexhealth.db"
    for model, n in migrate(source).items():
        print(f"{model:<22} {n}")
