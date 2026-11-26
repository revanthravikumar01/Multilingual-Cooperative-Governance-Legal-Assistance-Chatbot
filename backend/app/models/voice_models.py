"""Response bodies for the /api/v1/voice endpoints (Phase 4)."""

from pydantic import BaseModel

from app.models.chat_models import Citation
from app.models.common import AnswerStatus


class AudioLinks(BaseModel):
    summary_url: str  # short spoken version (played automatically, Decision 23)
    full_url: str  # the whole answer (Confirm button, Decision 24)


class VoiceQueryResponse(BaseModel):
    session_id: str
    status: AnswerStatus  # "stt_failed" when the speech could not be recognised (Decision 17)
    transcript: str  # what the user said ("" when stt_failed)
    answer: str
    citations: list[Citation] = []
    spoken_summary: str | None = None
    user_message_seq: int | None = None  # None when stt_failed (no question was recognised)
    assistant_message_seq: int
    audio: AudioLinks
    placeholder: bool = False
