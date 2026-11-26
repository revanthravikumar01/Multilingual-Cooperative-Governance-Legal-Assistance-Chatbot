"""CIVI speech service: a small local server the main backend calls (Decision 38).

  GET  /health                 which engines are loaded
  POST /stt?language=ta|en     body: WAV audio      -> {"transcript", "speech_detected", "seconds", "took"}
  POST /tts                    {"text", "language"} -> 16 kHz 16-bit mono WAV

Run it only on 127.0.0.1: it has no authentication and is meant for the backend on the same laptop.
Models load in the background after start; /health shows when they are ready (first start ~1 minute).
"""

import logging
import os
import threading
import time
from typing import Literal

# Models are downloaded by setup_speech.py. Don't check Hugging Face for updates at every start:
# on a slow connection those checks took over a minute. Set HF_HUB_OFFLINE=0 to allow downloads.
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

from fastapi import FastAPI, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

from civi_speech.audio import louder, read_wav, speech_contrast, to_kiosk_wav
from civi_speech.config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("civi.speech")

MAX_UPLOAD_BYTES = 8 * 1024 * 1024

app = FastAPI(title="CIVI speech service", version="1.0")

_engines: dict = {}
_status: dict[str, str] = {"stt": "loading", "tts_ta": "loading", "tts_en": "loading"}


def _load(name: str, factory) -> None:
    started = time.perf_counter()
    try:
        _engines[name] = factory()
        _status[name] = "ready"
        log.info("%s ready in %.1f s", name, time.perf_counter() - started)
    except Exception as exc:  # keep the other engines usable
        _status[name] = f"failed: {type(exc).__name__}: {exc}"
        log.exception("%s failed to load", name)


def _load_all() -> None:
    from civi_speech.stt import Recognizers
    from civi_speech.tts_english import EnglishVoice
    from civi_speech.tts_tamil import TamilVoice

    _load("tts_en", EnglishVoice)
    _load("stt", Recognizers)
    _load("tts_ta", TamilVoice)


@app.on_event("startup")
def _start_loading() -> None:
    threading.Thread(target=_load_all, name="load-models", daemon=True).start()


def _engine(name: str):
    if name not in _engines:
        state = _status.get(name, "missing")
        raise HTTPException(503, f"Speech engine '{name}' is not ready ({state}).")
    return _engines[name]


@app.get("/health")
def health() -> dict:
    tamil = _engines.get("tts_ta")
    return {
        "status": "ok" if all(s == "ready" for s in _status.values()) else "starting_or_degraded",
        "engines": _status,
        "tamil_voice": getattr(tamil, "voice_name", None),
        "tamil_voice_device": getattr(tamil, "device", None),
    }


@app.post("/stt")
async def speech_to_text(request: Request, language: Literal["ta", "en"] = Query(...)) -> dict:
    data = await request.body()
    if not data:
        raise HTTPException(400, "Empty audio.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Audio is too large.")
    try:
        audio, rate = read_wav(data)
    except Exception as exc:
        raise HTTPException(400, f"Not a readable WAV file: {exc}") from exc
    seconds = len(audio) / rate if rate else 0.0
    if seconds > settings.max_audio_seconds:
        raise HTTPException(413, f"Audio is longer than {settings.max_audio_seconds:.0f} s.")

    level, contrast = speech_contrast(audio)
    if level < settings.min_speech_level or contrast < settings.min_speech_contrast:
        # Silence or steady noise: don't let the model invent words from it.
        log.info("stt %s: no speech (level %.4f, contrast %.2f)", language, level, contrast)
        return {"transcript": "", "speech_detected": False, "seconds": round(seconds, 2), "took": 0.0}

    recognizers = _engine("stt")
    started = time.perf_counter()
    transcript = recognizers.transcribe(louder(audio), rate, language)
    took = time.perf_counter() - started
    log.info("stt %s: %.1f s audio -> %d chars in %.2f s", language, seconds, len(transcript), took)
    return {"transcript": transcript, "speech_detected": True, "seconds": round(seconds, 2), "took": round(took, 2)}


class TtsRequest(BaseModel):
    text: str = Field(min_length=1)
    language: Literal["ta", "en"]


@app.post("/tts")
def text_to_speech(body: TtsRequest) -> Response:
    text = body.text.strip()
    if not text:
        raise HTTPException(400, "Empty text.")
    if len(text) > settings.max_tts_chars:
        raise HTTPException(413, f"Text is longer than {settings.max_tts_chars} characters.")
    voice = _engine("tts_ta" if body.language == "ta" else "tts_en")
    started = time.perf_counter()
    audio, rate = voice.synthesize(text)
    wav = to_kiosk_wav(audio, rate)
    log.info("tts %s: %d chars -> %.1f s audio in %.1f s", body.language, len(text), len(audio) / rate,
             time.perf_counter() - started)
    return Response(content=wav, media_type="audio/wav")
