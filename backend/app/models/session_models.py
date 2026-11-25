"""Request and response bodies for the /api/v1/sessions endpoints."""

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.chat_models import Citation
from app.models.common import AnswerStatus, Language, MessageSource


class CreateSessionRequest(BaseModel):
    language: Language
    kiosk_id: str | None = Field(default=None, min_length=1, max_length=64)


class SessionResponse(BaseModel):
    session_id: str
    language: Language
    kiosk_id: str | None
    created_at: datetime
    expires_at: datetime


class MessageOut(BaseModel):
    seq: int
    role: str  # "user" or "assistant"
    text: str
    source: MessageSource
    status: AnswerStatus | None = None
    citations: list[Citation] = []
    spoken_summary: str | None = None
    created_at: datetime


class MessagesResponse(BaseModel):
    session_id: str
    messages: list[MessageOut]
