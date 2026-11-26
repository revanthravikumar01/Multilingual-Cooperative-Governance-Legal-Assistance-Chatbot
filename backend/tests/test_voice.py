"""Phase 4: voice endpoints, speech-service client and text-for-speech. No models, no network."""

import io
import json
import wave

import httpx
import pytest

from app.dependencies import get_audio_cache, get_speech_client
from app.services.speech_client import AudioCache, SpeechClient, Transcript
from app.services.speech_text import english_number, prepare_for_speech, tamil_number
from app.utils.retry import PermanentServiceError, TemporaryServiceError
from tests.test_answer_service import _service

API = "/api/v1"


def make_wav(seconds: float = 1.0, rate: int = 16_000, channels: int = 1, width: int = 2) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(width)
        w.setframerate(rate)
        w.writeframes(b"\x00\x01" * int(rate * seconds) * channels * (width // 2 or 1))
    return buffer.getvalue()


class FakeSpeech:
    def __init__(self, transcript="When is the general body meeting held?", detected=True, error=None):
        self.transcript = transcript
        self.detected = detected
        self.error = error
        self.spoken: list[tuple[str, str]] = []

    def transcribe(self, wav, language):
        if self.error:
            raise self.error
        return Transcript(self.transcript, self.detected, 1.0)

    def synthesize(self, text, language):
        if self.error:
            raise self.error
        self.spoken.append((text, language))
        return b"RIFF-fake-" + text.encode("utf-8")[:20]


@pytest.fixture
def speech():
    return FakeSpeech()


@pytest.fixture
def voice_client(client, speech, answers):
    client.app.dependency_overrides[get_speech_client] = lambda: speech
    cache = AudioCache()
    client.app.dependency_overrides[get_audio_cache] = lambda: cache
    reply = {"status": "answered", "answer": "It is held every year under Section 34(2) [1].",
             "spoken_summary": "", "used_sources": [1]}
    fake, _, _ = _service(reply)
    answers.__dict__.update(fake.__dict__)
    return client


def _session(client, language="en") -> str:
    return client.post(f"{API}/sessions", json={"language": language}).json()["session_id"]


def _ask(client, sid, wav=None):
    return client.post(f"{API}/voice/query", content=wav or make_wav(),
                       headers={"X-Session-Id": sid, "Content-Type": "audio/wav"})


# ---------- /voice/query ----------


def test_voice_question_is_answered_and_shown_in_session(voice_client, speech):
    sid = _session(voice_client)
    response = _ask(voice_client, sid)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "answered"
    assert body["transcript"] == "When is the general body meeting held?"
    assert body["citations"][0]["section"] == "34"
    assert body["audio"]["summary_url"] == f"/api/v1/voice/audio/{sid}/2?variant=summary"
    # Flutter sees both messages by polling (Decision 21).
    messages = voice_client.get(f"{API}/sessions/{sid}/messages").json()["messages"]
    assert [(m["role"], m["source"]) for m in messages] == [("user", "voice"), ("assistant", "voice")]
    # The short spoken version was prepared in the background, already speakable.
    assert speech.spoken == [("It is held every year under Section thirty-four, sub-section two.", "en")]


def test_unrecognised_speech_asks_to_repeat(voice_client, speech):
    speech.detected, speech.transcript = False, ""
    sid = _session(voice_client, "ta")
    body = _ask(voice_client, sid).json()
    assert body["status"] == "stt_failed"
    assert body["transcript"] == "" and body["user_message_seq"] is None
    assert "மீண்டும்" in body["answer"]
    messages = voice_client.get(f"{API}/sessions/{sid}/messages").json()["messages"]
    assert [(m["role"], m["status"]) for m in messages] == [("assistant", "stt_failed")]


@pytest.mark.parametrize(
    "wav, status",
    [
        (make_wav(rate=44_100), 400),
        (make_wav(channels=2), 400),
        (b"not a wav file at all", 400),
        (make_wav(seconds=63), 413),
    ],
)
def test_bad_audio_is_rejected(voice_client, wav, status):
    sid = _session(voice_client)
    response = _ask(voice_client, sid, wav)
    assert response.status_code == status
    assert response.json()["error"]["code"] in {"invalid_audio", "payload_too_large"}


def test_voice_needs_a_live_session(voice_client):
    assert _ask(voice_client, "missing").status_code == 404
    response = voice_client.post(f"{API}/voice/query", content=make_wav())
    assert response.status_code == 400  # X-Session-Id header missing


def test_speech_service_down_gives_503(voice_client, speech):
    speech.error = TemporaryServiceError("connection refused")
    response = _ask(voice_client, _session(voice_client))
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "speech_unavailable"


# ---------- /voice/audio ----------


def test_audio_for_typed_answer_and_cache(voice_client, speech):
    sid = _session(voice_client)
    voice_client.post(f"{API}/chat", json={"message": "When?", "language": "en", "session_id": sid})
    first = voice_client.get(f"{API}/voice/audio/{sid}/2?variant=full")
    again = voice_client.get(f"{API}/voice/audio/{sid}/2?variant=summary")  # no summary -> same text
    assert first.status_code == again.status_code == 200
    assert first.headers["content-type"] == "audio/wav"
    assert first.content == again.content
    assert len(speech.spoken) == 1  # generated once, then served from the cache


def test_audio_errors(voice_client):
    sid = _session(voice_client)
    voice_client.post(f"{API}/chat", json={"message": "When?", "language": "en", "session_id": sid})
    assert voice_client.get(f"{API}/voice/audio/{sid}/1").json()["error"]["code"] == "message_not_found"  # user msg
    assert voice_client.get(f"{API}/voice/audio/{sid}/9").status_code == 404
    assert voice_client.get(f"{API}/voice/audio/{sid}/2?variant=loud").status_code == 400
    assert voice_client.get(f"{API}/voice/audio/nope/2").status_code == 404


# ---------- SpeechClient ----------


def _speech_client(handler):
    return SpeechClient("http://speech.test", http=httpx.Client(transport=httpx.MockTransport(handler)),
                        retry_delays=(0,))


def test_speech_client_shapes():
    seen = []

    def handler(request):
        seen.append(request)
        if request.url.path == "/stt":
            return httpx.Response(200, json={"transcript": " வணக்கம் ", "speech_detected": True, "seconds": 1.5})
        return httpx.Response(200, content=b"RIFFwav", headers={"content-type": "audio/wav"})

    client = _speech_client(handler)
    assert client.transcribe(b"wav", "ta") == Transcript("வணக்கம்", True, 1.5)
    assert client.synthesize("hello", "en") == b"RIFFwav"
    assert seen[0].url.params["language"] == "ta"
    assert json.loads(seen[1].content) == {"text": "hello", "language": "en"}


def test_speech_client_errors():
    with pytest.raises(TemporaryServiceError):  # still loading models
        _speech_client(lambda r: httpx.Response(503, json={"detail": "loading"})).synthesize("x", "en")
    with pytest.raises(PermanentServiceError):
        _speech_client(lambda r: httpx.Response(413, json={"detail": "too long"})).synthesize("x", "en")

    def refuse(request):
        raise httpx.ConnectError("refused")

    with pytest.raises(TemporaryServiceError):
        _speech_client(refuse).transcribe(b"wav", "en")


def test_audio_cache_limits_size():
    cache = AudioCache(max_items=2)
    for i in range(3):
        cache.get_or_create(("k", i), lambda i=i: bytes([i]))
    assert cache.get(("k", 0)) is None and cache.get(("k", 2)) == b"\x02"


# ---------- text for speech ----------


@pytest.mark.parametrize("n, en, ta", [
    (7, "seven", "ஏழு"),
    (19, "nineteen", "பத்தொன்பது"),
    (34, "thirty-four", "முப்பத்து நான்கு"),
    (136, "one hundred and thirty-six", "நூற்று முப்பத்து ஆறு"),
    (1983, "one thousand nine hundred and eighty-three", "ஆயிரத்து தொள்ளாயிரத்து எண்பத்து மூன்று"),
    (5000, "five thousand", "ஐந்தாயிரம்"),
    (150000, "one lakh fifty thousand", "ஒரு லட்சத்து ஐம்பது ஆயிரம்"),
])
def test_number_words(n, en, ta):
    assert english_number(n) == en
    assert tamil_number(n) == ta


def test_prepare_for_speech_english():
    text = ("Meetings are yearly under Section 34(2)(a) [1].\n"
            "- Section 136-D: a deposit of Rs. 5,000 for 2 years [2, 3].\n"
            "- **Note**: the TN Co-operative Societies Act, 1983 applies to 5% of members")
    assert prepare_for_speech(text, "en") == (
        "Meetings are yearly under Section thirty-four, sub-section two, clause a. "
        "Section one hundred and thirty-six D: a deposit of five thousand rupees for two years. "
        "Note: the TN Co-operative Societies Act, nineteen eighty-three applies to five per cent of members."
    )


def test_prepare_for_speech_tamil():
    assert prepare_for_speech("இது பிரிவு 20(2) இல் உள்ளது [1]. ரூ. 5000 வைப்பு.", "ta") == (
        "இது பிரிவு இருபது, உட்பிரிவு இரண்டு இல் உள்ளது. ஐந்தாயிரம் ரூபாய் வைப்பு."
    )
