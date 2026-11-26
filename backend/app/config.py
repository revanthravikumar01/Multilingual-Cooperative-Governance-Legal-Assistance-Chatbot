"""Backend settings, read once from environment variables (.env).

API keys (GEMINI_API_KEY, SARVAM_API_KEY) are read from backend/.env.
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
    # Jurisdiction preferred in search when a question names none ("tamil_nadu"; empty = no preference).
    default_jurisdiction: str = "tamil_nadu"

    # Sarvam AI. repr=False keeps the key out of logs and error messages.
    sarvam_api_key: str = field(default="", repr=False)
    sarvam_translate_model: str = "mayura:v1"
    sarvam_timeout_seconds: float = 15.0

    # Google Gemini (Phase 3). Without a key, /chat returns a clearly marked placeholder answer.
    gemini_api_key: str = field(default="", repr=False)
    gemini_model: str = "gemini-3.5-flash-lite"
    gemini_thinking_level: str = "low"
    gemini_max_output_tokens: int = 4096
    gemini_timeout_seconds: float = 60.0
    gemini_api_revision: str = "2026-05-20"
    # Earlier messages sent to Gemini for follow-up questions (Decision 11).
    chat_history_messages: int = 6

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
        default_jurisdiction=os.getenv("CIVI_DEFAULT_JURISDICTION", "tamil_nadu").strip(),
        sarvam_api_key=os.getenv("SARVAM_API_KEY", "").strip(),
        sarvam_translate_model=os.getenv("CIVI_SARVAM_TRANSLATE_MODEL", "mayura:v1"),
        sarvam_timeout_seconds=_float_env("CIVI_SARVAM_TIMEOUT_SECONDS", 15.0),
        gemini_api_key=os.getenv("GEMINI_API_KEY", "").strip(),
        gemini_model=os.getenv("CIVI_GEMINI_MODEL", "gemini-3.5-flash-lite").strip(),
        gemini_thinking_level=os.getenv("CIVI_GEMINI_THINKING_LEVEL", "low").strip(),
        gemini_max_output_tokens=_int_env("CIVI_GEMINI_MAX_OUTPUT_TOKENS", 4096),
        gemini_timeout_seconds=_float_env("CIVI_GEMINI_TIMEOUT_SECONDS", 60.0),
        gemini_api_revision=os.getenv("CIVI_GEMINI_API_REVISION", "2026-05-20").strip(),
        chat_history_messages=_int_env("CIVI_CHAT_HISTORY_MESSAGES", 6),
    )


settings = load_settings()
