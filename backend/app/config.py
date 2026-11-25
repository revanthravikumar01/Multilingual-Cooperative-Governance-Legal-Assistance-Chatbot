"""Backend settings, read once from environment variables (.env).

API keys for Gemini and Sarvam will be added here in later phases.
They must stay on the backend and never go into Flutter or ESP32 code.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path

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


def _float_env(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    try:
        return float(value)
    except ValueError as exc:
        raise ValueError(f"Environment variable {name} must be a number, got {value!r}") from exc


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


# backend/ folder: knowledge_base/ lives next to main.py
BACKEND_DIR = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Settings:
    allowed_origins: list[str]
    session_ttl_minutes: int
    max_session_messages: int

    # Knowledge base (Phase 2)
    knowledge_base_dir: Path
    embedding_model: str
    max_upload_mb: int
    chunk_max_chars: int
    chunk_overlap_chars: int
    # Minimum cosine similarity (0–1) for a chunk to count as relevant evidence. Tune with real questions.
    relevance_threshold: float
    # Threshold for Tamil text searched directly. bge-m3 matches Tamil to English well, so it equals
    # relevance_threshold; raise it if you switch to a weaker multilingual model.
    tamil_query_threshold: float
    retrieval_candidates: int  # how many chunks to fetch from ChromaDB before reranking
    retrieval_top_k: int  # how many chunks to keep as final evidence
    # Allow document uploads from other devices on the local Wi-Fi (not only this laptop).
    admin_allow_lan: bool

    # Sarvam AI. repr=False keeps the key out of logs and error messages.
    sarvam_api_key: str = field(default="", repr=False)
    sarvam_translate_model: str = "mayura:v1"
    sarvam_timeout_seconds: float = 15.0

    @property
    def uploads_dir(self) -> Path:
        return self.knowledge_base_dir / "uploads"

    @property
    def chroma_dir(self) -> Path:
        return self.knowledge_base_dir / "chroma_db"

    @property
    def registry_path(self) -> Path:
        return self.knowledge_base_dir / "documents.json"


def load_settings() -> Settings:
    origins = os.getenv("CIVI_ALLOWED_ORIGINS", "*")
    kb_dir = os.getenv("CIVI_KNOWLEDGE_BASE_DIR", "").strip()
    return Settings(
        allowed_origins=[o.strip() for o in origins.split(",") if o.strip()],
        session_ttl_minutes=_int_env("CIVI_SESSION_TTL_MINUTES", 30),
        max_session_messages=_int_env("CIVI_MAX_SESSION_MESSAGES", 40),
        knowledge_base_dir=Path(kb_dir) if kb_dir else BACKEND_DIR / "knowledge_base",
        embedding_model=os.getenv(
            "CIVI_EMBEDDING_MODEL", "BAAI/bge-m3"
        ),
        max_upload_mb=_int_env("CIVI_MAX_UPLOAD_MB", 50),
        chunk_max_chars=_int_env("CIVI_CHUNK_MAX_CHARS", 1200),
        chunk_overlap_chars=_int_env("CIVI_CHUNK_OVERLAP_CHARS", 200),
        relevance_threshold=_float_env("CIVI_RELEVANCE_THRESHOLD", 0.52),
        tamil_query_threshold=_float_env("CIVI_TAMIL_QUERY_THRESHOLD", 0.52),
        retrieval_candidates=_int_env("CIVI_RETRIEVAL_CANDIDATES", 30),
        retrieval_top_k=_int_env("CIVI_RETRIEVAL_TOP_K", 5),
        admin_allow_lan=_bool_env("CIVI_ADMIN_ALLOW_LAN", False),
        sarvam_api_key=os.getenv("SARVAM_API_KEY", "").strip(),
        sarvam_translate_model=os.getenv("CIVI_SARVAM_TRANSLATE_MODEL", "mayura:v1"),
        sarvam_timeout_seconds=_float_env("CIVI_SARVAM_TIMEOUT_SECONDS", 15.0),
    )


settings = load_settings()
