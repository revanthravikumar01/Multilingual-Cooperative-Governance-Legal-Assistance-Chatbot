"""Request and response bodies for POST /api/v1/chat."""

from pydantic import BaseModel, Field

from app.models.common import AnswerStatus, Language


class Citation(BaseModel):
    """A source reference built by the backend from document metadata (Decision 10).

    Gemini never writes these. They come only from retrieved chunks.
    """

    number: int
    label: str  # Compact text Flutter shows, e.g. "[1] TN Co-op Societies Act, Section 2, Page 4"
    document_id: str
    document_title: str
    issuing_authority: str | None = None
    chapter: str | None = None
    section: str | None = None
    subsection: str | None = None
    page: int | None = None
    published_on: str | None = None


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=5000)
    language: Language = "en"
    # Optional so the current Flutter app keeps working; a new session is created if missing.
    session_id: str | None = Field(default=None, min_length=1, max_length=64)


class ChatResponse(BaseModel):
    session_id: str
    answer: str
    status: AnswerStatus
    citations: list[Citation] = []
    spoken_summary: str | None = None
    user_message_seq: int
    assistant_message_seq: int
    # True until RAG + Gemini replace the temporary answer (Phases 2–3).
    placeholder: bool = True
