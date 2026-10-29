"""Consistent database backup + retention.  `python scripts/backup.py [--dir backups] [--keep 14]`

SQLite: uses the online backup API (safe while the API is running, WAL-aware).
Postgres: runs `pg_dump` (must be installed) into the same directory.
"""
from __future__ import annotations

import argparse
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.engine import make_url  # noqa: E402

from app.core.config import get_settings  # noqa: E402


def backup(out_dir: Path) -> Path:
    url = make_url(get_settings().database_url)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    if url.get_backend_name() == "sqlite":
        target = out_dir / f"carexhealth-{stamp}.db"
        src = sqlite3.connect(url.database)
        dst = sqlite3.connect(target)
        with dst:
            src.backup(dst)
        src.close()
        dst.close()
        return target
    if shutil.which("pg_dump") is None:
        raise SystemExit("pg_dump not found on PATH")
    target = out_dir / f"carexhealth-{stamp}.sql"
    dsn = url.set(drivername="postgresql").render_as_string(hide_password=False)
    subprocess.run(["pg_dump", "--no-owner", "--format=plain", "--file", str(target), dsn], check=True)
    return target


def prune(out_dir: Path, keep: int) -> list[Path]:
    files = sorted(out_dir.glob("carexhealth-*"), key=lambda p: p.stat().st_mtime, reverse=True)
    old = files[keep:]
    for f in old:
        f.unlink()
    return old


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="backups")
    ap.add_argument("--keep", type=int, default=14, help="number of most recent backups to keep")
    a = ap.parse_args()
    path = backup(Path(a.dir))
    removed = prune(Path(a.dir), a.keep)
    print(f"backup written: {path} (pruned {len(removed)} old)")
