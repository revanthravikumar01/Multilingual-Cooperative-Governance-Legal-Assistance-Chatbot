"""Speech-to-text on the CPU (Decision 38).

Tamil:   AI4Bharat IndicConformer 600M (MIT). ~1 s per question, 3.0% character errors in our test.
English: OpenAI Whisper small (Apache-2.0). ~2 s per question, 6.6% word errors in our test.

Both run on the CPU so the 4 GB GPU stays free for the Tamil voice (IndicF5 needs ~2.9 GB).
"""

import importlib.util
import logging
import threading
from pathlib import Path

import numpy as np
import torch
from huggingface_hub import snapshot_download

from civi_speech.audio import resample
from civi_speech.config import settings

log = logging.getLogger("civi.stt")
STT_RATE = 16_000


class TamilRecognizer:
    def __init__(self, model_id: str, decoding: str = "rnnt"):
        repo = Path(snapshot_download(model_id))
        # The model's own loader (model_onnx.py) builds ONNX sessions + a TorchScript preprocessor.
        spec = importlib.util.spec_from_file_location("indic_conformer_onnx", repo / "model_onnx.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.model = module.IndicASRModel(module.IndicASRConfig(ts_folder=str(repo), FRAME_DURATION_MS=0.08))
        self.decoding = decoding
        self._lock = threading.Lock()

    def transcribe(self, audio: np.ndarray) -> str:
        wav = torch.from_numpy(np.ascontiguousarray(audio, dtype="float32")).unsqueeze(0)
        with self._lock, torch.inference_mode():
            return str(self.model(wav, "ta", self.decoding)).strip()


class EnglishRecognizer:
    def __init__(self, model_id: str):
        from transformers import WhisperForConditionalGeneration, WhisperProcessor

        self.processor = WhisperProcessor.from_pretrained(model_id)
        self.model = WhisperForConditionalGeneration.from_pretrained(model_id, dtype=torch.float32).to("cpu").eval()
        self._lock = threading.Lock()

    def transcribe(self, audio: np.ndarray) -> str:
        features = self.processor(audio, sampling_rate=STT_RATE, return_tensors="pt").input_features
        with self._lock, torch.inference_mode():
            ids = self.model.generate(features, language="en", task="transcribe", max_new_tokens=220)
        return self.processor.batch_decode(ids, skip_special_tokens=True)[0].strip()


class Recognizers:
    """Loads both recognizers once and picks one by language."""

    def __init__(self):
        self.tamil = TamilRecognizer(settings.tamil_stt_model, settings.tamil_stt_decoding)
        self.english = EnglishRecognizer(settings.english_stt_model)

    def transcribe(self, audio: np.ndarray, rate: int, language: str) -> str:
        audio = resample(audio, rate, STT_RATE)
        recognizer = self.tamil if language == "ta" else self.english
        return recognizer.transcribe(audio)
