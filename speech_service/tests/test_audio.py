"""Fast checks of the speech service's own logic (no models needed).

Run:  speech_service\\.venv\\Scripts\\python.exe -m pytest speech_service\\tests -q
"""

import io
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from civi_speech.audio import KIOSK_RATE, louder, read_wav, speech_contrast, to_kiosk_wav  # noqa: E402
from civi_speech.tts_tamil import _chunks, _cross_fade, _trim_silence  # noqa: E402

RATE = 16_000


def _speech_like(seconds: float = 2.0) -> np.ndarray:
    """Bursts of tone separated by quiet gaps, like syllables."""
    t = np.arange(int(RATE * seconds)) / RATE
    envelope = (np.sin(2 * np.pi * 3 * t) > 0.2).astype("float32")
    return (0.2 * np.sin(2 * np.pi * 220 * t) * envelope + 0.001 * np.random.randn(len(t))).astype("float32")


def test_speech_has_contrast_noise_does_not():
    _, speech = speech_contrast(_speech_like())
    _, noise = speech_contrast((0.01 * np.random.randn(RATE * 2)).astype("float32"))
    _, quiet_speech = speech_contrast(_speech_like() * 0.005)  # very quiet but still speech-like
    assert speech > 1.4 and quiet_speech > 1.4
    assert noise < 1.2


def test_silence_has_no_level():
    level, _ = speech_contrast(np.zeros(RATE * 2, dtype="float32"))
    assert level < 0.0003


def test_louder_only_raises_quiet_audio():
    quiet = np.full(10, 0.01, dtype="float32")
    loud = np.full(10, 0.8, dtype="float32")
    assert np.isclose(np.abs(louder(quiet)).max(), 0.5)
    assert np.array_equal(louder(loud), loud)


def test_kiosk_wav_format():
    data = to_kiosk_wav(np.sin(np.linspace(0, 100, 24_000)).astype("float32"), 24_000)
    info = sf.info(io.BytesIO(data))
    assert (info.samplerate, info.channels, info.subtype) == (KIOSK_RATE, 1, "PCM_16")
    audio, rate = read_wav(data)
    assert rate == KIOSK_RATE and abs(len(audio) - KIOSK_RATE) <= 1


def test_trim_silence_keeps_only_the_voice():
    rate = 24_000
    voice = (0.3 * np.sin(np.linspace(0, 2000, rate))).astype("float32")
    padded = np.concatenate([np.zeros(rate // 2, "float32"), voice, np.zeros(rate, "float32")])
    trimmed = _trim_silence(padded, rate)
    assert abs(len(trimmed) - len(voice)) < rate * 0.01


def test_long_text_is_split_into_sentences():
    text = "முதல் வாக்கியம். இரண்டாவது வாக்கியம்! மூன்றாவது?"
    assert _chunks(text, max_bytes=60) == ["முதல் வாக்கியம்.", "இரண்டாவது வாக்கியம்!", "மூன்றாவது?"]
    assert _chunks(text, max_bytes=10_000) == [text]


def test_cross_fade_joins_smoothly():
    a, b = np.ones(10_000, "float32"), np.ones(10_000, "float32")
    joined = _cross_fade([a, b])
    assert len(joined) == 20_000 - int(0.15 * 24_000)
    assert np.allclose(joined, 1.0)
