"""Backend settings, read once from environment variables (.env).

API keys for Gemini and Sarvam will be added here in later phases.
They must stay on the backend and never go into Flutter or ESP32 code.
"""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"Environment variable {name} must be a whole number, got {value!r}") from exc


@dataclass(frozen=True)
class Settings:
    allowed_origins: list[str]
    session_ttl_minutes: int
    max_session_messages: int


def load_settings() -> Settings:
    origins = os.getenv("CIVI_ALLOWED_ORIGINS", "*")
    return Settings(
        allowed_origins=[o.strip() for o in origins.split(",") if o.strip()],
        session_ttl_minutes=_int_env("CIVI_SESSION_TTL_MINUTES", 30),
        max_session_messages=_int_env("CIVI_MAX_SESSION_MESSAGES", 40),
    )


settings = load_settings()
