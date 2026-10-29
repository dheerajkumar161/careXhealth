# CareXHealth API + agents + MCP servers + scheduler (one container: the MCP servers are stdio child processes)
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
# xhtml2pdf needs cairo/pango-free build deps only for some wheels; keep the image small but able to build them
RUN apt-get update && apt-get install -y --no-install-recommends build-essential libffi-dev && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt && pip install "psycopg[binary]>=3.2"
COPY . .
RUN useradd --create-home --uid 10001 carexhealth && mkdir -p /data && chown -R carexhealth /app /data
USER carexhealth
ENV HOST=0.0.0.0 PORT=8000 ENVIRONMENT=production DATABASE_URL=sqlite:////data/carexhealth.db LOG_JSON=true FORWARDED_ALLOW_IPS=*
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/ready', timeout=4).status == 200 else 1)"
CMD ["python", "main.py"]
