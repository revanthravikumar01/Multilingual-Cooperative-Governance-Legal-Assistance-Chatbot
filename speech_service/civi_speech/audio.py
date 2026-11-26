"""Small audio helpers: read/write 16-bit mono WAV and resample. Only numpy + soundfile."""

import io

import numpy as np
import soundfile as sf

KIOSK_RATE = 16_000  # the ESP32 records and plays 16 kHz, 16-bit, mono (Decision 20, API_CONTRACT)


def read_wav(data: bytes) -> tuple[np.ndarray, int]:
    """WAV bytes -> (float32 mono samples in [-1, 1], sample rate)."""
    audio, rate = sf.read(io.BytesIO(data), dtype="float32", always_2d=True)
    return audio.mean(axis=1), rate


def resample(audio: np.ndarray, rate: int, target: int) -> np.ndarray:
    """Band-limited enough for speech: linear interpolation after a light low-pass when downsampling."""
    if rate == target or len(audio) == 0:
        return audio.astype("float32")
    if target < rate:
        # Moving-average low-pass to reduce aliasing before dropping samples.
        width = max(1, int(round(rate / target)))
        if width > 1:
            audio = np.convolve(audio, np.ones(width) / width, mode="same")
    n = int(round(len(audio) * target / rate))
    positions = np.linspace(0, len(audio) - 1, n)
    return np.interp(positions, np.arange(len(audio)), audio).astype("float32")


def to_kiosk_wav(audio: np.ndarray, rate: int, peak: float = 0.9) -> bytes:
    """Float samples at any rate -> 16 kHz, 16-bit, mono WAV bytes, normalised to `peak`."""
    audio = resample(np.asarray(audio, dtype="float32"), rate, KIOSK_RATE)
    loudest = float(np.abs(audio).max()) if len(audio) else 0.0
    if loudest > 0:
        audio = audio / loudest * peak
    buffer = io.BytesIO()
    sf.write(buffer, audio, KIOSK_RATE, format="WAV", subtype="PCM_16")
    return buffer.getvalue()


def silence_wav(seconds: float = 0.3) -> bytes:
    buffer = io.BytesIO()
    sf.write(buffer, np.zeros(int(KIOSK_RATE * seconds), dtype="float32"), KIOSK_RATE, format="WAV", subtype="PCM_16")
    return buffer.getvalue()


def speech_contrast(audio: np.ndarray) -> tuple[float, float]:
    """(level, contrast) over 30 ms frames.

    level    = loudness (RMS) of the loudest 10% of frames.
    contrast = level / median frame loudness. Speech has loud syllables and quiet gaps (measured 1.8–5),
               steady noise or hum does not (~1.0–1.1). Loudness alone can't tell them apart: some real
               recordings are as quiet as background noise.
    """
    frame = 480
    if len(audio) < frame * 5:
        return 0.0, 1.0
    usable = len(audio) // frame * frame
    rms = np.sqrt(np.mean(np.square(audio[:usable].reshape(-1, frame)), axis=1)) + 1e-7
    ordered = np.sort(rms)
    level = float(ordered[-max(1, len(rms) // 10):].mean())
    return level, level / float(np.median(ordered))


def louder(audio: np.ndarray, target_peak: float = 0.5) -> np.ndarray:
    """Raise very quiet recordings so the recognizers get a normal level (never makes audio quieter)."""
    peak = float(np.abs(audio).max()) if len(audio) else 0.0
    if 0 < peak < target_peak:
        return (audio * min(target_peak / peak, 50.0)).astype("float32")
    return audio
