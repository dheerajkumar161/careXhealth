"""Retention housekeeping for operational tables.  `python scripts/housekeeping.py [--deliveries-days 90]`

Clinical records, observations and the audit log are NEVER deleted here — their retention is a policy/legal decision
(see SECURITY.md). Only ephemeral operational data is pruned.
"""
from __future__ import annotations

import argparse
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import delete  # noqa: E402

from app.core.db import init_db, session_scope  # noqa: E402
from app.core.util import now  # noqa: E402
from app.models import Delivery, LoginAttempt  # noqa: E402


def run(deliveries_days: int = 90) -> dict[str, int]:
    init_db()
    with session_scope() as s:
        d = s.execute(delete(Delivery).where(Delivery.status.in_(["SENT", "SKIPPED"]), Delivery.created_at < now() - timedelta(days=deliveries_days))).rowcount
        a = s.execute(delete(LoginAttempt).where(LoginAttempt.at < now() - timedelta(days=1))).rowcount
    return {"deliveries": d or 0, "loginAttempts": a or 0}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--deliveries-days", type=int, default=90)
    print(run(ap.parse_args().deliveries_days))
