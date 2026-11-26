"""Produces the answer for a question: retrieval + Gemini, with backend checks (Phase 3).

Flow for one question:
  1. Search the knowledge base (Phase 2). Short follow-ups are also searched together with the
     previous question, so "what about the penalty?" still finds the right Act.
  2. No relevant evidence -> fixed "not available" answer. Gemini is NOT called (Decision 9).
  3. Gemini gets ONLY the numbered evidence and must reply in a fixed JSON shape.
  4. The backend checks the reply: source numbers must exist, unknown [n] markers are removed,
     and an "answered" reply with no valid source becomes "insufficient_evidence" (Decision 9).
  5. Citations are built by the backend from document metadata, renumbered 1..n in the order the
     answer uses them. Gemini never writes citation text (Decision 10).

Without GEMINI_API_KEY the service returns a clearly marked placeholder answer, so the app still runs.
"""

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Callable, Protocol

from app.errors import ApiError
from app.services.citation_service import build_citation
from app.services.session_service import StoredMessage
from app.utils.retry import PermanentServiceError, TemporaryServiceError

log = logging.getLogger("civi.answer")


@dataclass
class AnswerResult:
    answer: str
    status: str  # "answered" | "insufficient_evidence" | "out_of_scope"
    citations: list[dict] = field(default_factory=list)
    spoken_summary: str | None = None
    placeholder: bool = False


class JsonModel(Protocol):
    """Anything that can answer like GeminiClient.generate_json (tests use a fake)."""

    def generate_json(self, system_instruction: str, turns: list[tuple[str, str]], schema: dict) -> dict: ...


# ---------- fixed texts ----------

_TEMPORARY_ANSWER = {
    "en": (
        '[Temporary API response] CIVI received your question: "{q}". '
        "Gemini is not connected yet (GEMINI_API_KEY is missing in backend/.env)."
    ),
    "ta": (
        '[தற்காலிக பதில்] உங்கள் கேள்வி பெறப்பட்டது: "{q}". '
        "Gemini இன்னும் இணைக்கப்படவில்லை (backend/.env-இல் GEMINI_API_KEY இல்லை)."
    ),
}

NOT_AVAILABLE = {
    "en": (
        "Verified information is not available in the current knowledge base. "
        "Please rephrase your question, or ask about co-operative society registration, "
        "membership, elections, meetings, audit or management."
    ),
    "ta": (
        "சரிபார்க்கப்பட்ட தகவல் தற்போதைய அறிவுத் தளத்தில் இல்லை. "
        "உங்கள் கேள்வியை வேறு விதமாகக் கேளுங்கள், அல்லது கூட்டுறவுச் சங்கங்களின் பதிவு, உறுப்பினர், "
        "தேர்தல், கூட்டங்கள், தணிக்கை அல்லது நிர்வாகம் பற்றிக் கேளுங்கள்."
    ),
}

OUT_OF_SCOPE = {
    "en": (
        "I can only help with questions about co-operative societies: their governance, rules and "
        "legal requirements. Please ask a question on that topic."
    ),
    "ta": (
        "கூட்டுறவுச் சங்கங்களின் நிர்வாகம், விதிகள் மற்றும் சட்டத் தேவைகள் பற்றிய கேள்விகளுக்கு மட்டுமே "
        "என்னால் உதவ முடியும். அந்தத் தலைப்பில் ஒரு கேள்வியைக் கேளுங்கள்."
    ),
}

_LANGUAGE_NAME = {"en": "English", "ta": "Tamil"}

SYSTEM_INSTRUCTION = """You are CIVI, a legal-information assistant for co-operative societies in India \
(mainly Tamil Nadu). You explain what the documents in the knowledge base say.

GROUNDING RULES (most important):
1. Use ONLY the numbered SOURCES given with the latest question. Never use general knowledge, your memory \
of the law, or earlier answers in the conversation as a source of legal facts.
2. Put the source number right after each statement it supports, like "... within fifteen days [2]." \
Use only numbers that appear in SOURCES.
3. Never invent sections, rules, fees, amounts, time limits, forms, schemes or procedures. If a detail \
is not in the sources, say that it is not available in the knowledge base.
4. If the sources do not contain enough information to answer the question, set status \
"insufficient_evidence".
5. If the question is not about co-operative societies, their governance, or the law in these sources \
(for example weather, sports, films, general knowledge, coding, personal matters), set status "out_of_scope".
6. Earlier conversation turns are only for understanding follow-up questions such as "what about that \
section?" or "and for members?".
7. Each source shows its document, validity and date. Prefer current documents. If a source's validity \
is "unknown" or "superseded", or sources disagree, say clearly that the text may have been amended and \
should be checked with the Registrar of Co-operative Societies.
8. Users are in Tamil Nadu. Unless the question is about multi-state co-operative societies, base the \
answer on Tamil Nadu sources when they answer the question. If you also use the Multi-State \
Co-operative Societies Act, say that it applies only to multi-state societies.
9. Explain the law; do not decide a person's specific case. When the user describes their own dispute, \
add one short line suggesting they confirm with the Registrar of Co-operative Societies or a lawyer.

ANSWER STYLE (status "answered"):
- Write the answer in {language}.{tamil_note}
- Start with a direct answer in one or two sentences. Then, only where useful: a simple explanation, \
the important legal requirements, step-by-step procedure, and a short practical example. Skip parts \
that do not apply. Use short paragraphs or "- " bullet points. Plain text only: no tables, no "#" \
headings, no "**" bold markers (the app shows the text as it is).
- In the written answer, write Act, section and rule numbers exactly as in the sources, with digits \
(e.g. "Section 136-D", "பிரிவு 20(2)"). Only the spoken summary spells numbers as words.
- Keep the original legal term and explain it in simple words, e.g. "Quorum: the minimum number of \
members who must be present for the meeting to be valid".
- Do not add a list of sources at the end; the app shows the sources separately.

SPOKEN SUMMARY: two or three short sentences in {language} that will be read aloud. Say only things \
that are already in the answer. No source numbers, no brackets, no lists, no symbols. Write every \
number as words ("section thirty-four", "fifteen days").{tamil_spoken_note}

USED SOURCES: the numbers of the sources the answer relies on.

For status "insufficient_evidence" or "out_of_scope", answer and spoken_summary may be empty \
and used_sources must be empty."""

_TAMIL_NOTE = (
    " Use simple, clear modern Tamil. The first time a legal term appears, also give the English term "
    'in brackets, e.g. "கோரம் (Quorum)". Keep Act and section names recognisable.'
)
_TAMIL_SPOKEN_NOTE = ' In Tamil write numbers as Tamil words, e.g. "பிரிவு முப்பத்து நான்கு".'

ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["answered", "insufficient_evidence", "out_of_scope"]},
        "answer": {"type": "string"},
        "spoken_summary": {"type": "string"},
        "used_sources": {"type": "array", "items": {"type": "integer"}},
    },
    "required": ["status", "answer", "spoken_summary", "used_sources"],
}

# [3]  or  [1, 2]  or  [1,2,3]
_MARKER = re.compile(r"\s?\[(\d{1,2}(?:\s*,\s*\d{1,2})*)\]")
# A short question after an earlier one is probably a follow-up ("what about members?").
FOLLOW_UP_MAX_WORDS = 12
# Answers shorter than this are spoken in full, so no separate summary (API_CONTRACT: spoken_summary).
SPOKEN_SUMMARY_MIN_ANSWER_CHARS = 300
_MAX_HISTORY_CHARS = 1500


class AnswerService:
    def __init__(
        self,
        retrieval_provider: Callable[[], object] | None = None,
        llm: JsonModel | None = None,
        top_k: int = 5,
        history_messages: int = 6,
    ):
        # retrieval_provider is called lazily so the placeholder mode never loads the knowledge base.
        self._retrieval_provider = retrieval_provider
        self._llm = llm
        self.top_k = top_k
        self.history_messages = history_messages

    @property
    def configured(self) -> bool:
        return self._llm is not None and self._retrieval_provider is not None

    def answer(self, question: str, language: str, history: list[StoredMessage]) -> AnswerResult:
        if not self.configured:
            return AnswerResult(answer=_TEMPORARY_ANSWER[language].format(q=question), status="answered",
                                placeholder=True)

        started = time.perf_counter()
        evidence = self._retrieve(question, language, history)
        if not evidence:
            log.info("answer: no relevant evidence (%.1f s)", time.perf_counter() - started)
            return AnswerResult(answer=NOT_AVAILABLE[language], status="insufficient_evidence")

        turns = self._history_turns(history) + [("user", _question_turn(question, evidence))]
        system = SYSTEM_INSTRUCTION.format(
            language=_LANGUAGE_NAME[language],
            tamil_note=_TAMIL_NOTE if language == "ta" else "",
            tamil_spoken_note=_TAMIL_SPOKEN_NOTE if language == "ta" else "",
        )
        try:
            reply = self._llm.generate_json(system, turns, ANSWER_SCHEMA)
        except TemporaryServiceError as exc:
            raise ApiError(502, "upstream_error",
                           "The answer service is busy right now. Please try again in a minute.") from exc
        except PermanentServiceError as exc:
            if "quota_exceeded" in str(exc).lower() or "resource_exhausted" in str(exc).lower():
                raise ApiError(503, "service_unavailable",
                               "Today's free Gemini limit has been reached. Please try again later.") from exc
            raise ApiError(502, "upstream_error", f"The answer service failed: {exc}") from exc

        result = check_reply(reply, evidence, language)
        log.info("answer: %s with %d citation(s) (%.1f s)", result.status, len(result.citations),
                 time.perf_counter() - started)
        return result

    # ---------- steps ----------

    def _retrieve(self, question: str, language: str, history: list[StoredMessage]) -> list:
        retrieval = self._retrieval_provider()
        found = {e.chunk_id: e for e in retrieval.search(question, language=language).evidence}

        previous = _previous_user_question(history)
        if previous and len(question.split()) <= FOLLOW_UP_MAX_WORDS:
            for e in retrieval.search(f"{previous}\n{question}", language=language).evidence:
                if e.chunk_id not in found or e.score > found[e.chunk_id].score:
                    found[e.chunk_id] = e

        evidence = sorted(found.values(), key=lambda e: e.score, reverse=True)[: self.top_k]
        for number, e in enumerate(evidence, start=1):
            e.citation = build_citation(number, e.metadata, language)
        return evidence

    def _history_turns(self, history: list[StoredMessage]) -> list[tuple[str, str]]:
        turns = []
        for message in history[-self.history_messages:]:
            text = _MARKER.sub("", message.text)[:_MAX_HISTORY_CHARS]
            turns.append(("user" if message.role == "user" else "model", text))
        # The conversation sent to Gemini should start with the user.
        while turns and turns[0][0] != "user":
            turns.pop(0)
        return turns


def _previous_user_question(history: list[StoredMessage]) -> str | None:
    for message in reversed(history):
        if message.role == "user":
            return message.text
    return None


def _question_turn(question: str, evidence: list) -> str:
    blocks = []
    for e in evidence:
        m = e.metadata
        details = " | ".join(
            part
            for part in (
                f"Document: {m.get('document_title', '')}",
                f"Authority: {m['issuing_authority']}" if m.get("issuing_authority") else "",
                f"Jurisdiction: {m['jurisdiction']}" if m.get("jurisdiction") else "",
                f"Validity: {m.get('validity') or 'unknown'}",
                f"Published: {m['published_on']}" if m.get("published_on") else "",
                f"Chapter: {m['chapter']}" if m.get("chapter") else "",
            )
            if part
        )
        blocks.append(f"[{e.citation['number']}] {e.citation['label'].split('] ', 1)[-1]}\n{details}\nText:\n{e.text}")
    return "SOURCES:\n\n" + "\n\n".join(blocks) + f"\n\nQUESTION:\n{question}"


# ---------- backend checks (Decision 9) ----------


def check_reply(reply: dict, evidence: list, language: str) -> AnswerResult:
    """Validate Gemini's JSON against the evidence and build the final, citation-checked answer."""
    status = reply.get("status")
    if status == "out_of_scope":
        return AnswerResult(answer=OUT_OF_SCOPE[language], status="out_of_scope")
    if status != "answered":
        return AnswerResult(answer=NOT_AVAILABLE[language], status="insufficient_evidence")

    answer = str(reply.get("answer") or "").strip()
    by_number = {e.citation["number"]: e for e in evidence}

    # Sources actually used: markers in the text (in order) plus the declared list; unknown numbers dropped.
    order: list[int] = []
    for match in _MARKER.finditer(answer):
        for n in _numbers(match.group(1)):
            if n in by_number and n not in order:
                order.append(n)
    for n in reply.get("used_sources") or []:
        if isinstance(n, int) and n in by_number and n not in order:
            order.append(n)

    if not answer or not order:
        log.warning("answer rejected: status 'answered' without a valid source")
        return AnswerResult(answer=NOT_AVAILABLE[language], status="insufficient_evidence")

    renumber = {old: new for new, old in enumerate(order, start=1)}

    def rewrite(match: re.Match) -> str:
        kept = [renumber[n] for n in _numbers(match.group(1)) if n in renumber]
        if not kept:
            return ""  # a number that isn't a real source: remove the marker
        return " " * match.group(0).startswith(" ") + "".join(f"[{n}]" for n in kept)

    answer = _MARKER.sub(rewrite, answer).strip()
    citations = [build_citation(renumber[old], by_number[old].metadata, language) for old in order]

    spoken = _MARKER.sub("", str(reply.get("spoken_summary") or "")).strip()
    if len(answer) < SPOKEN_SUMMARY_MIN_ANSWER_CHARS or not spoken:
        spoken = None

    return AnswerResult(answer=answer, status="answered", citations=citations, spoken_summary=spoken)


def _numbers(text: str) -> list[int]:
    return [int(n) for n in re.findall(r"\d{1,2}", text)]
