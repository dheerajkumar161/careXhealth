"""Entry point: `python main.py` (or `uvicorn app.main:app`). HOST / PORT env vars override the loopback default."""
import os

import uvicorn

from app.core.config import get_settings  # noqa: F401
from app.main import app  # noqa: F401

if __name__ == "__main__":
    uvicorn.run("app.main:app", host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", "8000")), reload=False, proxy_headers=True, forwarded_allow_ips=os.environ.get("FORWARDED_ALLOW_IPS", "127.0.0.1"))
