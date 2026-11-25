"""Produces the answer for a question.

Phase 1: returns a clearly labelled temporary answer.
Phases 2–3 replace the body of `answer_question` with RAG retrieval + Gemini.
The endpoints don't need to change when that happens.
"""

from dataclasses import dataclass, field

from app.services.session_service import StoredMessage


@dataclass
class AnswerResult:
    answer: str
    status: str  # "answered" | "insufficient_evidence" | "out_of_scope"
    citations: list[dict] = field(default_factory=list)
    spoken_summary: str | None = None
    placeholder: bool = False


_TEMPORARY_ANSWER = {
    "en": (
        '[Temporary API response] CIVI received your question: "{q}". '
        "The knowledge base and Gemini are not connected yet."
    ),
    "ta": (
        '[தற்காலிக பதில்] உங்கள் கேள்வி பெறப்பட்டது: "{q}". '
        "அறிவுத் தளமும் Gemini-யும் இன்னும் இணைக்கப்படவில்லை."
    ),
}


def answer_question(question: str, language: str, history: list[StoredMessage]) -> AnswerResult:
    # `history` is unused for now; Phase 3 passes it to Gemini for follow-up questions.
    return AnswerResult(
        answer=_TEMPORARY_ANSWER[language].format(q=question),
        status="answered",
        placeholder=True,
    )
