"""Central configuration (env vars / backend/.env). Every process — API, scheduler, MCP servers — reads the same settings."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    database_url: str = f"sqlite:///{(BACKEND_DIR / 'carexhealth.db').as_posix()}"
    auth_secret: str = "change-me-to-a-long-random-string-at-least-32-chars"
    session_hours: int = 12

    # --- LLM chain: Groq (primary → fallback model) → local Ollama → deterministic rule engine ---
    groq_api_key: str = ""
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_model: str = "openai/gpt-oss-120b"
    groq_fallback_model: str = ""  # second Groq model tried if the primary call fails
    groq_vision_model: str = ""  # vision-capable Groq model for photos/scans of notes
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = ""  # local fallback, e.g. "qwen2.5:3b" — intentionally not hard-coded
    ollama_vision_model: str = ""  # optional local vision fallback, e.g. "llama3.2-vision"
    llm_timeout_seconds: float = 90.0
    force_rule_engine: bool = False

    # --- Monitoring / scheduler ---
    escalation_minutes: int = 15
    escalation_ladder: str = ""  # e.g. "15,10": nurse→doctor after 15 min, doctor→on-call after 10 min
    agent_cycle_seconds: int = 60
    scheduler_enabled: bool = True

    # --- Production hardening ---
    environment: str = "development"  # "production" enables the startup safety checks and secure cookies
    cookie_secure: bool | None = None  # None → secure when environment == "production"
    login_max_attempts: int = 5
    login_lockout_minutes: int = 15
    password_min_length: int = 10
    max_upload_mb: int = 8
    log_json: bool = False
    metrics_token: str = ""  # if set, /metrics requires "Authorization: Bearer <token>"; otherwise only loopback callers or admins
    hsts: bool | None = None  # None → enabled in production

    # --- Outbound delivery (all off until configured) ---
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_starttls: bool = True
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from: str = ""  # SMS sender number, or "whatsapp:+14155238886" for WhatsApp
    quiet_hours_start: int = 22  # local hour; non-urgent messages wait until quiet hours end
    quiet_hours_end: int = 7
    delivery_max_attempts: int = 5

    # Relaxes time windows so the whole journey can be demoed in one sitting. Never enable in production.
    demo_mode: bool = False
    signup_invite_code: str = ""
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    @property
    def secure_cookies(self) -> bool:
        return self.is_production if self.cookie_secure is None else self.cookie_secure

    def validate_for_startup(self) -> None:
        """Refuse to boot a production instance with unsafe settings."""
        if not self.is_production:
            return
        problems: list[str] = []
        if self.auth_secret.startswith("change-me") or len(self.auth_secret) < 32:
            problems.append("AUTH_SECRET must be a unique random string of at least 32 characters")
        if self.demo_mode:
            problems.append("DEMO_MODE must be false in production")
        if "*" in self.cors_origins:
            problems.append("CORS_ORIGINS must not contain '*'")
        if problems:
            raise RuntimeError("Unsafe production configuration: " + "; ".join(problems))

    def ladder_minutes(self, level: int, severity: str = "MEDIUM") -> int:
        """Minutes an alert may sit at `level` (1 = nurse, 2 = doctor) before escalating. ESCALATION_LADDER="15,10" sets per-step
        timers; otherwise ESCALATION_MINUTES applies to every step. CRITICAL alerts use a third of the time."""
        steps = [int(x) for x in self.escalation_ladder.replace(" ", "").split(",") if x.isdigit() and int(x) > 0]
        base = (steps[min(level - 1, len(steps) - 1)] if steps else self.escalation_min)
        return max(round(base / 3), 1) if severity == "CRITICAL" else base

    @property
    def escalation_min(self) -> int:
        return max(self.escalation_minutes or 15, 1)


@lru_cache
def get_settings() -> Settings:
    return Settings()
