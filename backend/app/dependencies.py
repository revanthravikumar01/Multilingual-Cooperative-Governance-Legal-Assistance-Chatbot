"""Shared objects that endpoints receive through FastAPI's `Depends`.

Tests replace these with fresh copies using `app.dependency_overrides`.
"""

from app.config import settings
from app.services.session_service import SessionService

_session_service = SessionService(
    ttl_minutes=settings.session_ttl_minutes,
    max_messages=settings.max_session_messages,
)


def get_session_service() -> SessionService:
    return _session_service
