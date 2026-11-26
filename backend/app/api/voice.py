"""Voice endpoints for the ESP32 (Phase 4; Decisions 13, 14, 17, 20–24, 36, 38).

POST /voice/query                         WAV question in -> recognised text + answer + audio links
GET  /voice/audio/{session_id}/{seq}      the spoken answer as WAV (?variant=summary|full)

The ESP32 records 16 kHz 16-bit mono audio (≤ 60 s) and streams it here with chunked HTTP.
The question and answer are stored in the session, so Flutter shows them by polling
GET /sessions/{id}/messages (Decision 21). Audio is made by the local speech service.
"""

import hashlib
import io
import logging
import wave

from fastapi import APIRouter, BackgroundTasks, Depends, Header, Query, Request, Response
from fastapi.concurrency import run_in_threadpool

from app.dependencies import get_answer_service, get_audio_cache, get_session_service, get_speech_client
from app.errors import ApiError
from app.models.voice_models import AudioLinks, VoiceQueryResponse
from app.services.answer_service import AnswerService
from app.services.session_service import SessionService, StoredMessage
from app.services.speech_client import AudioCache, SpeechClient
from app.services.speech_text import prepare_for_speech
from app.utils.retry import PermanentServiceError, TemporaryServiceError

router = APIRouter(prefix="/voice", tags=["voice"])
log = logging.getLogger("civi.voice")

SAMPLE_RATE = 16_000
MAX_SECONDS = 60  # Decision 20
# 60 s of 16 kHz 16-bit mono is 1,920,000 bytes; allow a little for the header and rounding.
MAX_UPLOAD_BYTES = SAMPLE_RATE * 2 * (MAX_SECONDS + 2) + 1024

REPEAT_PROMPT = {
    "en": (
        "Sorry, I could not hear your question clearly. Please press the microphone button and ask "
        "again in English, or type your question."
    ),
    "ta": (
        "மன்னிக்கவும், உங்கள் கேள்வியைத் தெளிவாகக் கேட்க முடியவில்லை. மைக் பொத்தானை அழுத்தி மீண்டும் "
        "தமிழில் கேளுங்கள், அல்லது உங்கள் கேள்வியைத் தட்டச்சு செய்யுங்கள்."
    ),
}


@router.post("/query", response_model=VoiceQueryResponse)
async def voice_query(
    request: Request,
    background: BackgroundTasks,
    session_id: str = Header(alias="X-Session-Id", min_length=1, max_length=64),
    sessions: SessionService = Depends(get_session_service),
    answers: AnswerService = Depends(get_answer_service),
    speech: SpeechClient = Depends(get_speech_client),
    cache: AudioCache = Depends(get_audio_cache),
) -> VoiceQueryResponse:
    language = sessions.get(session_id).language
    wav = await _read_limited(request)
    _check_wav(wav)
    # The rest takes seconds (speech recognition, Gemini): run it in a worker thread so the
    # backend keeps answering other requests (Flutter polling, audio downloads) meanwhile.
    return await run_in_threadpool(_answer_voice, wav, session_id, language, background, sessions, answers,
                                   speech, cache)


def _answer_voice(wav: bytes, session_id: str, language: str, background: BackgroundTasks,
                  sessions: SessionService, answers: AnswerService, speech: SpeechClient,
                  cache: AudioCache) -> VoiceQueryResponse:
    sessions.touch(session_id, language)

    # 1. Speech -> text
    try:
        transcript = speech.transcribe(wav, language)
    except TemporaryServiceError as exc:
        raise _speech_unavailable() from exc
    except PermanentServiceError as exc:
        raise ApiError(502, "upstream_error", f"Speech recognition failed: {exc}") from exc

    # 2. Nothing recognised -> ask the user to repeat (Decision 17). The prompt is shown and spoken.
    if not transcript.speech_detected or len(transcript.text) < 2:
        message = sessions.add_message(session_id, "assistant", REPEAT_PROMPT[language], "voice", status="stt_failed")
        _pregenerate(background, cache, speech, message, language)
        return VoiceQueryResponse(
            session_id=session_id,
            status="stt_failed",
            transcript="",
            answer=message.text,
            assistant_message_seq=message.seq,
            audio=_links(session_id, message.seq),
        )

    # 3. Recognised text -> answer, exactly like a typed question (Decision 21: no confirmation step).
    history = sessions.recent_history(session_id)
    user_message = sessions.add_message(session_id, "user", transcript.text, "voice")
    result = answers.answer(transcript.text, language, history)
    message = sessions.add_message(
        session_id, "assistant", result.answer, "voice",
        status=result.status, citations=result.citations, spoken_summary=result.spoken_summary,
    )
    # 4. Start making the short spoken version now, so it's ready when the ESP32 asks for it.
    _pregenerate(background, cache, speech, message, language)

    return VoiceQueryResponse(
        session_id=session_id,
        status=result.status,
        transcript=transcript.text,
        answer=result.answer,
        citations=result.citations,
        spoken_summary=result.spoken_summary,
        user_message_seq=user_message.seq,
        assistant_message_seq=message.seq,
        audio=_links(session_id, message.seq),
        placeholder=result.placeholder,
    )


@router.get("/audio/{session_id}/{seq}")
def voice_audio(
    session_id: str,
    seq: int,
    variant: str = Query("summary", pattern="^(summary|full)$"),
    sessions: SessionService = Depends(get_session_service),
    speech: SpeechClient = Depends(get_speech_client),
    cache: AudioCache = Depends(get_audio_cache),
) -> Response:
    """The spoken version of an assistant message, typed or voice (Decision 14: in visually
    challenged mode typed answers are spoken too). Does not refresh the session timer."""
    session = sessions.get(session_id)
    message = next((m for m in sessions.messages_after(session_id, seq - 1) if m.seq == seq), None)
    if message is None or message.role != "assistant":
        raise ApiError(404, "message_not_found", "No answer with that number in this session.")
    text = spoken_text(message, variant)
    try:
        wav = _synthesize(cache, speech, text, session.language)
    except TemporaryServiceError as exc:
        raise _speech_unavailable() from exc
    except PermanentServiceError as exc:
        raise ApiError(502, "upstream_error", f"Speech generation failed: {exc}") from exc
    return Response(content=wav, media_type="audio/wav", headers={"Cache-Control": "no-store"})


# ---------- helpers ----------


def spoken_text(message: StoredMessage, variant: str) -> str:
    """Summary = the short spoken version if there is one (Decision 23), else the whole answer."""
    if variant == "summary" and message.status == "answered" and message.spoken_summary:
        return message.spoken_summary
    return message.text


def _synthesize(cache: AudioCache, speech: SpeechClient, text: str, language: str) -> bytes:
    speakable = prepare_for_speech(text, language)
    key = (language, hashlib.sha256(speakable.encode("utf-8")).hexdigest())
    return cache.get_or_create(key, lambda: speech.synthesize(speakable, language))


def _pregenerate(background: BackgroundTasks, cache: AudioCache, speech: SpeechClient,
                 message: StoredMessage, language: str) -> None:
    def run() -> None:
        try:
            _synthesize(cache, speech, spoken_text(message, "summary"), language)
        except Exception as exc:  # the ESP32's own request will report the problem
            log.warning("Could not pre-generate audio for message %s: %s", message.seq, exc)

    background.add_task(run)


def _links(session_id: str, seq: int) -> AudioLinks:
    base = f"/api/v1/voice/audio/{session_id}/{seq}"
    return AudioLinks(summary_url=f"{base}?variant=summary", full_url=f"{base}?variant=full")


async def _read_limited(request: Request) -> bytes:
    """Read the (possibly chunked) upload, refusing anything longer than 60 s of audio."""
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_UPLOAD_BYTES:
            raise ApiError(413, "payload_too_large", f"Recordings may be at most {MAX_SECONDS} seconds.")
        chunks.append(chunk)
    if not size:
        raise ApiError(400, "invalid_audio", "The request has no audio.")
    return b"".join(chunks)


def _check_wav(data: bytes) -> None:
    try:
        with wave.open(io.BytesIO(data)) as wav:
            channels, width, rate, frames = wav.getnchannels(), wav.getsampwidth(), wav.getframerate(), wav.getnframes()
    except (wave.Error, EOFError) as exc:
        raise ApiError(400, "invalid_audio", f"Audio must be a WAV file: {exc}") from exc
    if (channels, width, rate) != (1, 2, SAMPLE_RATE):
        raise ApiError(
            400, "invalid_audio",
            f"Audio must be 16 kHz, 16-bit, mono WAV (got {rate} Hz, {width * 8}-bit, {channels} channel(s)).",
        )
    if frames / SAMPLE_RATE > MAX_SECONDS + 1:
        raise ApiError(413, "payload_too_large", f"Recordings may be at most {MAX_SECONDS} seconds.")


def _speech_unavailable() -> ApiError:
    return ApiError(503, "speech_unavailable",
                    "The speech service is not running or is still starting. Please try again shortly.")
