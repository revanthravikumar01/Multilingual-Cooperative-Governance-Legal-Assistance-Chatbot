"""Speech service settings (environment variables, all optional)."""

import os
from dataclasses import dataclass
from pathlib import Path

SERVICE_DIR = Path(__file__).resolve().parents[1]


def _float(name: str, default: float) -> float:
    value = os.getenv(name, "").strip()
    return float(value) if value else default


def _int(name: str, default: int) -> int:
    value = os.getenv(name, "").strip()
    return int(value) if value else default


@dataclass(frozen=True)
class Settings:
    # Speech-to-text (CPU)
    tamil_stt_model: str = os.getenv("CIVI_TAMIL_STT_MODEL", "ai4bharat/indic-conformer-600m-multilingual")
    tamil_stt_decoding: str = os.getenv("CIVI_TAMIL_STT_DECODING", "rnnt")  # rnnt (more accurate) or ctc (faster)
    english_stt_model: str = os.getenv("CIVI_ENGLISH_STT_MODEL", "openai/whisper-small")
    # A recording counts as "nothing said" if it is digital silence (level below min_speech_level) or has
    # no speech-like loud/quiet contrast (speech measured 1.8–5, steady noise ~1.05).
    min_speech_level: float = _float("CIVI_MIN_SPEECH_LEVEL", 0.0003)
    min_speech_contrast: float = _float("CIVI_MIN_SPEECH_CONTRAST", 1.4)
    max_audio_seconds: float = _float("CIVI_MAX_AUDIO_SECONDS", 62)

    # Tamil text-to-speech: IndicF5 on the GPU (Decision 38)
    tamil_tts_model: str = os.getenv("CIVI_TAMIL_TTS_MODEL", "ai4bharat/IndicF5")
    tamil_tts_steps: int = _int("CIVI_TAMIL_TTS_STEPS", 16)  # 16 = ~4 s/sentence on an RTX 3050; 32 = clearer, 2x slower
    tamil_tts_device: str = os.getenv("CIVI_TAMIL_TTS_DEVICE", "auto")  # auto | cuda | cpu (cpu is ~1-2 min/sentence)
    # Reference voice: voices/tamil_reference.wav + .txt if present, else AI4Bharat's sample voice.
    voices_dir: Path = SERVICE_DIR / "voices"

    # English text-to-speech: Windows built-in voice
    english_voice: str = os.getenv("CIVI_ENGLISH_VOICE", "Microsoft Zira Desktop")
    english_voice_rate: int = _int("CIVI_ENGLISH_VOICE_RATE", 0)  # -10 (slow) .. 10 (fast)

    max_tts_chars: int = _int("CIVI_MAX_TTS_CHARS", 3000)


settings = Settings()
