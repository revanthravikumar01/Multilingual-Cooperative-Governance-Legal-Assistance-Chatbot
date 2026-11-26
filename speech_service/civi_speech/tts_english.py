"""English text-to-speech with the voice built into Windows (System.Speech, e.g. Microsoft Zira).

Free, offline, no licence issues, and works on any Windows laptop. It runs through PowerShell, so no
extra Python packages (or DLLs that Smart App Control might block) are needed. The text is passed on
standard input, never inside the command line, so it can't change the command.
"""

import os
import subprocess
import tempfile
import threading
from pathlib import Path

import numpy as np

from civi_speech.audio import read_wav
from civi_speech.config import settings

_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = [System.Text.Encoding]::UTF8
Add-Type -AssemblyName System.Speech
$text = [Console]::In.ReadToEnd()
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
try { $synth.SelectVoice($env:CIVI_VOICE) } catch { }
$synth.Rate = [int]$env:CIVI_RATE
$format = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(16000, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono)
$synth.SetOutputToWaveFile($env:CIVI_OUT, $format)
$synth.Speak($text)
$synth.Dispose()
"""


class EnglishVoice:
    def __init__(self):
        self._lock = threading.Lock()
        # Fail early if Windows speech isn't available.
        self.synthesize("Ready.")

    def synthesize(self, text: str) -> tuple[np.ndarray, int]:
        with self._lock, tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "speech.wav"
            env = dict(os.environ)
            env.update({
                "CIVI_VOICE": settings.english_voice,
                "CIVI_RATE": str(settings.english_voice_rate),
                "CIVI_OUT": str(out),
            })
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", _SCRIPT],
                input=text.encode("utf-8"),
                capture_output=True,
                env=env,
                timeout=120,
            )
            if result.returncode != 0 or not out.exists():
                raise RuntimeError(f"Windows speech failed: {result.stderr.decode(errors='replace')[:300]}")
            return read_wav(out.read_bytes())
