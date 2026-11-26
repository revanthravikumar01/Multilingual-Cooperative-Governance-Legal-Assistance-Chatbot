"""Phase 3: grounded answers. Gemini and the knowledge base are replaced by fakes (no key, no network)."""

import json

import httpx
import pytest

from app.errors import ApiError
from app.services.answer_service import (
    ANSWER_SCHEMA,
    NOT_AVAILABLE,
    OUT_OF_SCOPE,
    AnswerService,
)
from app.services.gemini_service import INTERACTIONS_URL, GeminiClient
from app.services.retrieval_service import Evidence, RetrievalResult
from app.services.session_service import StoredMessage
from app.utils.retry import PermanentServiceError, TemporaryServiceError

API = "/api/v1"


def _evidence(n: int, section: str, text: str, score: float = 0.8) -> Evidence:
    return Evidence(
        chunk_id=f"chunk-{section}",
        text=text,
        metadata={
            "document_id": "tn-act",
            "document_title": "Tamil Nadu Co-operative Societies Act, 1983",
            "citation_name": "TN Co-operative Societies Act, 1983",
            "jurisdiction": "tamil_nadu",
            "doc_type": "act",
            "validity": "current",
            "section": section,
            "page_start": 10 + n,
            "page_end": 10 + n,
        },
        similarity=score,
        score=score,
    )


class FakeRetrieval:
    def __init__(self, evidence_by_query=None, default=None):
        self.evidence_by_query = evidence_by_query or {}
        self.default = default if default is not None else []
        self.queries: list[str] = []

    def search(self, query, language="en", **_):
        self.queries.append(query)
        evidence = [
            Evidence(e.chunk_id, e.text, dict(e.metadata), e.similarity, e.score)
            for e in self.evidence_by_query.get(query, self.default)
        ]
        return RetrievalResult(sufficient=bool(evidence), evidence=evidence)


class FakeLLM:
    def __init__(self, reply=None, error=None):
        self.reply = reply
        self.error = error
        self.calls: list[dict] = []

    def generate_json(self, system_instruction, turns, schema):
        self.calls.append({"system": system_instruction, "turns": turns, "schema": schema})
        if self.error:
            raise self.error
        return self.reply


EVIDENCE = [
    _evidence(1, "34", "Section 34. A general body meeting shall be held once a year."),
    _evidence(2, "35", "Section 35. Notice of fourteen days shall be given."),
    _evidence(3, "36", "Section 36. The quorum shall be one-fifth of members."),
]


def _service(reply=None, error=None, evidence=EVIDENCE, by_query=None):
    retrieval = FakeRetrieval(by_query, default=evidence)
    llm = FakeLLM(reply, error)
    return AnswerService(lambda: retrieval, llm, top_k=5, history_messages=6), retrieval, llm


LONG = "A general body meeting must be held every year [1]. " * 8


# ---------- placeholder mode ----------


def test_without_key_gives_placeholder_and_never_searches():
    service = AnswerService()
    result = service.answer("What is quorum?", "en", [])
    assert result.placeholder is True
    assert result.status == "answered"


# ---------- grounding checks (Decision 9) ----------


def test_no_evidence_means_no_gemini_call():
    service, _, llm = _service(evidence=[])
    result = service.answer("Who won the cricket match?", "en", [])
    assert result.status == "insufficient_evidence"
    assert result.answer == NOT_AVAILABLE["en"]
    assert result.citations == []
    assert llm.calls == []


def test_answered_reply_gets_backend_citations_renumbered():
    reply = {
        "status": "answered",
        "answer": "The quorum is one-fifth of members [3]. Notice is fourteen days [2].",
        "spoken_summary": "",
        "used_sources": [3, 2],
    }
    service, _, _ = _service(reply)
    result = service.answer("What is the quorum?", "en", [])
    assert result.status == "answered"
    # Renumbered in order of use: old 3 -> 1, old 2 -> 2.
    assert result.answer == "The quorum is one-fifth of members [1]. Notice is fourteen days [2]."
    assert [c["number"] for c in result.citations] == [1, 2]
    assert [c["section"] for c in result.citations] == ["36", "35"]
    assert result.citations[0]["label"] == "[1] TN Co-operative Societies Act, 1983, Section 36, Page 13"
    assert result.spoken_summary is None  # short answer: spoken in full


def test_invented_source_numbers_are_removed():
    reply = {
        "status": "answered",
        "answer": "Meetings are yearly [1]. The fee is Rs 500 [9]. See also [1, 7].",
        "spoken_summary": "",
        "used_sources": [1, 9],
    }
    service, _, _ = _service(reply)
    result = service.answer("Meetings?", "en", [])
    assert "[9]" not in result.answer and "[7]" not in result.answer
    assert result.answer == "Meetings are yearly [1]. The fee is Rs 500. See also [1]."
    assert [c["section"] for c in result.citations] == ["34"]


def test_answered_without_any_valid_source_is_rejected():
    reply = {"status": "answered", "answer": "Yes, you can do that.", "spoken_summary": "", "used_sources": [8]}
    service, _, _ = _service(reply)
    result = service.answer("Can I do that?", "en", [])
    assert result.status == "insufficient_evidence"
    assert result.answer == NOT_AVAILABLE["en"]
    assert result.citations == []


def test_gemini_out_of_scope_uses_fixed_text():
    reply = {"status": "out_of_scope", "answer": "Here is the weather...", "spoken_summary": "", "used_sources": []}
    service, _, _ = _service(reply)
    result = service.answer("Weather tomorrow?", "ta", [])
    assert result.status == "out_of_scope"
    assert result.answer == OUT_OF_SCOPE["ta"]


def test_gemini_insufficient_uses_fixed_text():
    reply = {"status": "insufficient_evidence", "answer": "I think...", "spoken_summary": "", "used_sources": []}
    service, _, _ = _service(reply)
    result = service.answer("What is the stamp duty?", "en", [])
    assert result.status == "insufficient_evidence"
    assert result.answer == NOT_AVAILABLE["en"]


def test_spoken_summary_for_long_answers_without_markers():
    reply = {"status": "answered", "answer": LONG, "spoken_summary": "Meetings are held every year [1].",
             "used_sources": [1]}
    service, _, _ = _service(reply)
    result = service.answer("When are meetings held?", "en", [])
    assert result.spoken_summary == "Meetings are held every year."


# ---------- prompt contents ----------


def test_prompt_contains_only_numbered_evidence_and_language():
    reply = {"status": "answered", "answer": "Yearly [1].", "spoken_summary": "", "used_sources": [1]}
    service, _, llm = _service(reply)
    service.answer("பொதுக்குழு எப்போது?", "ta", [])
    call = llm.calls[0]
    assert "Tamil" in call["system"] and "கோரம் (Quorum)" in call["system"]
    last_role, last_text = call["turns"][-1]
    assert last_role == "user"
    assert "[1] TN Co-operative Societies Act, 1983, பிரிவு 34" in last_text
    assert "Validity: current" in last_text
    assert last_text.rstrip().endswith("பொதுக்குழு எப்போது?")
    assert call["schema"] == ANSWER_SCHEMA


def test_history_is_sent_and_follow_up_searches_with_previous_question():
    history = [
        StoredMessage(1, "user", "What is the quorum for a general body meeting?", "text", None),
        StoredMessage(2, "assistant", "One-fifth of members [1].", "text", None, status="answered"),
    ]
    reply = {"status": "answered", "answer": "Fourteen days [2].", "spoken_summary": "", "used_sources": [2]}
    service, retrieval, llm = _service(reply)
    service.answer("And the notice period?", "en", history)
    assert retrieval.queries == [
        "And the notice period?",
        "What is the quorum for a general body meeting?\nAnd the notice period?",
    ]
    turns = llm.calls[0]["turns"]
    assert turns[0] == ("user", "What is the quorum for a general body meeting?")
    assert turns[1] == ("model", "One-fifth of members.")  # old markers removed


def test_long_new_question_is_not_merged_with_history():
    history = [StoredMessage(1, "user", "What is quorum?", "text", None)]
    reply = {"status": "answered", "answer": "Yearly [1].", "spoken_summary": "", "used_sources": [1]}
    service, retrieval, _ = _service(reply)
    long_question = "Please explain in detail how the annual general body meeting of a primary co-operative society is called"
    service.answer(long_question, "en", history)
    assert retrieval.queries == [long_question]


# ---------- Gemini failures ----------


def test_temporary_gemini_failure_becomes_502():
    service, _, _ = _service(error=TemporaryServiceError("HTTP 503"))
    with pytest.raises(ApiError) as info:
        service.answer("Meetings?", "en", [])
    assert info.value.status_code == 502 and info.value.code == "upstream_error"


def test_daily_quota_becomes_503():
    service, _, _ = _service(error=PermanentServiceError("HTTP 429 quota_exceeded: daily limit"))
    with pytest.raises(ApiError) as info:
        service.answer("Meetings?", "en", [])
    assert info.value.status_code == 503


# ---------- GeminiClient (HTTP shape) ----------


def _client(handler, delays=(0, 0)):
    http = httpx.Client(transport=httpx.MockTransport(handler))
    return GeminiClient("test-key", model="gemini-test", http=http, retry_delays=delays)


def _ok(payload: dict) -> dict:
    return {
        "id": "x",
        "status": "completed",
        "steps": [
            {"type": "thought", "content": [{"type": "text", "text": "thinking..."}]},
            {"type": "model_output", "content": [{"type": "text", "text": json.dumps(payload)}]},
        ],
    }


def test_gemini_client_request_and_reply_shape():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["headers"] = request.headers
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=_ok({"status": "answered"}))

    data = _client(handler).generate_json("SYSTEM", [("user", "hi"), ("model", "hello"), ("user", "q")], {"type": "object"})
    assert data == {"status": "answered"}
    assert seen["url"] == INTERACTIONS_URL
    assert seen["headers"]["x-goog-api-key"] == "test-key"
    body = seen["body"]
    assert body["model"] == "gemini-test"
    assert body["store"] is False
    assert body["system_instruction"] == "SYSTEM"
    assert [s["type"] for s in body["input"]] == ["user_input", "model_output", "user_input"]
    assert body["response_format"]["mime_type"] == "application/json"
    assert "temperature" not in json.dumps(body)


def test_gemini_client_retries_rate_limit_then_succeeds():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, json={"error": {"code": "rate_limit_exceeded", "message": "slow down"}})
        return httpx.Response(200, json=_ok({"ok": True}))

    assert _client(handler).generate_json("S", [("user", "q")], {}) == {"ok": True}
    assert calls["n"] == 2


def test_gemini_client_does_not_retry_daily_quota_or_bad_key():
    for status, code in ((429, "quota_exceeded"), (401, "authentication")):
        calls = {"n": 0}

        def handler(request, status=status, code=code):
            calls["n"] += 1
            return httpx.Response(status, json={"error": {"code": code, "message": "no"}})

        with pytest.raises(PermanentServiceError):
            _client(handler).generate_json("S", [("user", "q")], {})
        assert calls["n"] == 1


def test_gemini_client_rejects_incomplete_or_non_json_replies():
    incomplete = {"status": "incomplete", "steps": []}
    not_json = {"status": "completed", "steps": [{"type": "model_output", "content": [{"type": "text", "text": "hello"}]}]}
    for body in (incomplete, not_json):
        with pytest.raises(PermanentServiceError):
            _client(lambda r, body=body: httpx.Response(200, json=body)).generate_json("S", [("user", "q")], {})


# ---------- /chat end to end with fakes ----------


def test_chat_endpoint_returns_citations(client, answers):
    reply = {"status": "answered", "answer": "Held yearly [1].", "spoken_summary": "", "used_sources": [1]}
    service, _, _ = _service(reply)
    answers.__dict__.update(service.__dict__)  # turn the fixture's placeholder service into the fake one
    body = client.post(f"{API}/chat", json={"message": "When is the meeting?", "language": "en"}).json()
    assert body["status"] == "answered"
    assert body["placeholder"] is False
    assert body["citations"][0]["label"].startswith("[1] TN Co-operative Societies Act, 1983, Section 34")
    messages = client.get(f"{API}/sessions/{body['session_id']}/messages").json()["messages"]
    assert messages[1]["citations"][0]["section"] == "34"


def test_chat_endpoint_reports_gemini_failure(client, answers):
    service, _, _ = _service(error=TemporaryServiceError("down"))
    answers.__dict__.update(service.__dict__)
    response = client.post(f"{API}/chat", json={"message": "When is the meeting?", "language": "en"})
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "upstream_error"


def test_gemini_translates_tamil_question_quickly():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=_ok({"english": "How to become a member of a co-operative society?"}))

    english = _client(handler).translate_question("கூட்டுறவு உறுப்பினராக எப்படி ஆவது?")
    assert english == "How to become a member of a co-operative society?"
    assert seen["body"]["generation_config"]["thinking_level"] == "minimal"
    assert seen["body"]["input"][0]["content"][0]["text"] == "கூட்டுறவு உறுப்பினராக எப்படி ஆவது?"


def test_empty_translation_is_an_error():
    client = _client(lambda r: httpx.Response(200, json=_ok({"english": "  "})))
    with pytest.raises(PermanentServiceError):
        client.translate_question("கேள்வி")
