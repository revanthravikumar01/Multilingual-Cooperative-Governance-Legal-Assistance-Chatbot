"""Shared objects that endpoints receive through FastAPI's `Depends`.

Tests replace these with fresh copies using `app.dependency_overrides`.
The knowledge-base objects are created on first use, so the server starts
quickly and chat keeps working even if the knowledge base can't load.
"""

import ipaddress
import threading

from fastapi import Request

from app.config import settings
from app.errors import ApiError
from app.services.session_service import SessionService

_session_service = SessionService(
    ttl_minutes=settings.session_ttl_minutes,
    max_messages=settings.max_session_messages,
)

_kb_lock = threading.Lock()
_kb: dict = {}


def get_session_service() -> SessionService:
    return _session_service


def _knowledge_base() -> dict:
    with _kb_lock:
        if not _kb:
            from app.services.document_service import DocumentRegistry, DocumentService
            from app.services.embedding_service import SentenceTransformerEmbedder
            from app.services.retrieval_service import RetrievalService
            from app.services.vector_store import VectorStore

            try:
                store = VectorStore(settings.chroma_dir, embedding_model=settings.embedding_model)
            except Exception as exc:
                raise ApiError(503, "service_unavailable", f"Knowledge base could not start: {exc}") from exc
            embedder = SentenceTransformerEmbedder(settings.embedding_model)
            _kb["documents"] = DocumentService(
                registry=DocumentRegistry(settings.registry_path),
                uploads_dir=settings.uploads_dir,
                store=store,
                embedder=embedder,
                max_upload_mb=settings.max_upload_mb,
                chunk_max_chars=settings.chunk_max_chars,
                chunk_overlap_chars=settings.chunk_overlap_chars,
            )
            _kb["retrieval"] = RetrievalService(
                store=store,
                embedder=embedder,
                relevance_threshold=settings.relevance_threshold,
                tamil_query_threshold=settings.tamil_query_threshold,
                candidates=settings.retrieval_candidates,
                top_k=settings.retrieval_top_k,
                translator=_tamil_to_english(),
                default_jurisdiction=settings.default_jurisdiction or None,
            )
        return _kb


def _tamil_to_english():
    """Translates Tamil questions to English before searching: Sarvam if its key is set,
    otherwise Gemini (free tier), otherwise None (search the Tamil text only)."""
    if not settings.sarvam_api_key:
        gemini = _gemini_client()
        return gemini.translate_question if gemini else None
    from app.services.sarvam_service import SarvamClient

    client = SarvamClient(
        settings.sarvam_api_key,
        translate_model=settings.sarvam_translate_model,
        timeout_seconds=settings.sarvam_timeout_seconds,
    )
    return lambda text: client.translate(text, source="ta", target="en")


def get_document_service():
    return _knowledge_base()["documents"]


def get_retrieval_service():
    return _knowledge_base()["retrieval"]


_answer_lock = threading.Lock()
_answer_service = None
_gemini_lock = threading.Lock()
_gemini = None


def _gemini_client():
    """One shared Gemini client, or None if GEMINI_API_KEY is not set."""
    global _gemini
    if not settings.gemini_api_key:
        return None
    with _gemini_lock:
        if _gemini is None:
            from app.services.gemini_service import GeminiClient

            _gemini = GeminiClient(
                settings.gemini_api_key,
                model=settings.gemini_model,
                timeout_seconds=settings.gemini_timeout_seconds,
                thinking_level=settings.gemini_thinking_level,
                max_output_tokens=settings.gemini_max_output_tokens,
                api_revision=settings.gemini_api_revision,
            )
        return _gemini


def get_answer_service():
    """Retrieval + Gemini. Without GEMINI_API_KEY it gives placeholder answers and never loads the
    knowledge base, so the app still runs on a laptop without a key."""
    global _answer_service
    with _answer_lock:
        if _answer_service is None:
            from app.services.answer_service import AnswerService

            llm = _gemini_client()
            if llm:
                _answer_service = AnswerService(
                    retrieval_provider=get_retrieval_service,
                    llm=llm,
                    top_k=settings.retrieval_top_k,
                    history_messages=settings.chat_history_messages,
                )
            else:
                _answer_service = AnswerService()
        return _answer_service


def is_trusted_host(host: str | None, allow_lan: bool) -> bool:
    try:
        ip = ipaddress.ip_address(host or "")
    except ValueError:
        return False
    return ip.is_loopback or (allow_lan and ip.is_private)


def require_trusted_client(request: Request) -> None:
    """Decision 30: no admin login in V1, so admin endpoints only accept requests from
    this laptop (or the private Wi-Fi network if CIVI_ADMIN_ALLOW_LAN=true)."""
    host = request.client.host if request.client else None
    if not is_trusted_host(host, settings.admin_allow_lan):
        raise ApiError(403, "forbidden", "Document management is only allowed from the backend laptop.")


_speech_lock = threading.Lock()
_speech: dict = {}


def get_speech_client():
    """Client for the local speech service (speech_service/). Created once."""
    with _speech_lock:
        if "client" not in _speech:
            from app.services.speech_client import SpeechClient

            _speech["client"] = SpeechClient(settings.speech_service_url, settings.speech_timeout_seconds)
        return _speech["client"]


def get_audio_cache():
    with _speech_lock:
        if "cache" not in _speech:
            from app.services.speech_client import AudioCache

            _speech["cache"] = AudioCache()
        return _speech["cache"]
