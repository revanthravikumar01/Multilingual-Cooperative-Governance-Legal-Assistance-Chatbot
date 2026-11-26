"""Tamil text-to-speech with AI4Bharat IndicF5 (MIT), on the GPU (Decision 38).

Measured on the kiosk laptop (RTX 3050 4 GB): ~4 s per sentence with 16 steps and bf16 inside the
transformer, ~2.9 GB GPU memory. This file holds a minimal copy of IndicF5's inference loop so that
only the model code is imported, not its training tools (which pull in packages Windows Smart App
Control blocks). The model code itself comes from the `f5_tts` package installed from AI4Bharat's
IndicF5 repository.

IndicF5 speaks in the voice of a short reference recording + its exact transcript:
  voices/tamil_reference.wav + voices/tamil_reference.txt  (record with the speaker's consent)
If those files are missing, AI4Bharat's sample voice from the model repository is used.
"""

import logging
import re
import sys
import threading
import types
from pathlib import Path

import numpy as np
import soundfile as sf
import torch
from huggingface_hub import hf_hub_download, snapshot_download
from safetensors.torch import load_file

from civi_speech.audio import resample
from civi_speech.config import settings

log = logging.getLogger("civi.tts.tamil")

# Model constants from IndicF5 (f5_tts/infer/utils_infer.py)
TARGET_RATE = 24_000
HOP_LENGTH = 256
TARGET_RMS = 0.1
CROSS_FADE_SECONDS = 0.15
CFG_STRENGTH = 2.0
SWAY_SAMPLING = -1.0
DIT_CONFIG = dict(dim=1024, depth=22, heads=16, ff_mult=2, text_dim=512, conv_layers=4)

# AI4Bharat's sample voice (inside the gated model repo) and its transcript from the model card.
SAMPLE_VOICE = "prompts/PAN_F_HAPPY_00001.wav"
SAMPLE_TEXT = "ਭਹੰਪੀ ਵਿੱਚ ਸਮਾਰਕਾਂ ਦੇ ਭਵਨ ਨਿਰਮਾਣ ਕਲਾ ਦੇ ਵੇਰਵੇ ਗੁੰਝਲਦਾਰ ਅਤੇ ਹੈਰਾਨ ਕਰਨ ਵਾਲੇ ਹਨ, ਜੋ ਮੈਨੂੰ ਖੁਸ਼ ਕਰਦੇ  ਹਨ।"


def _import_f5_model_code():
    """Import IndicF5's model classes without its training module (wandb, datasets, ...)."""
    if "f5_tts.model.trainer" not in sys.modules:
        trainer = types.ModuleType("f5_tts.model.trainer")
        trainer.Trainer = None
        sys.modules["f5_tts.model.trainer"] = trainer
    from f5_tts.model.backbones.dit import DiT
    from f5_tts.model.cfm import CFM
    from f5_tts.model.utils import convert_char_to_pinyin, get_tokenizer

    return DiT, CFM, convert_char_to_pinyin, get_tokenizer


class TamilVoice:
    def __init__(self):
        DiT, CFM, self._to_tokens, get_tokenizer = _import_f5_model_code()
        from vocos import Vocos

        if settings.tamil_tts_device == "auto":
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            self.device = settings.tamil_tts_device
        if self.device == "cpu":
            log.warning("No GPU: Tamil speech will take 1-2 minutes per sentence.")

        repo = Path(snapshot_download(settings.tamil_tts_model, allow_patterns=["*.json", "*.txt", "*.safetensors", "prompts/*"]))

        # Vocoder: turns mel spectrograms into sound (charactr/vocos-mel-24khz, MIT).
        vocos_config = hf_hub_download("charactr/vocos-mel-24khz", "config.yaml")
        vocos_weights = hf_hub_download("charactr/vocos-mel-24khz", "pytorch_model.bin")
        self.vocoder = Vocos.from_hparams(vocos_config)
        self.vocoder.load_state_dict(torch.load(vocos_weights, map_location="cpu", weights_only=True))
        self.vocoder = self.vocoder.eval().to(self.device)

        vocab_map, vocab_size = get_tokenizer(str(repo / "checkpoints" / "vocab.txt"), "custom")
        model = CFM(
            transformer=DiT(**DIT_CONFIG, text_num_embeds=vocab_size, mel_dim=100),
            mel_spec_kwargs=dict(n_fft=1024, hop_length=HOP_LENGTH, win_length=1024, n_mel_channels=100,
                                 target_sample_rate=TARGET_RATE, mel_spec_type="vocos"),
            odeint_kwargs=dict(method="euler"),
            vocab_char_map=vocab_map,
        )
        state = load_file(str(repo / "model.safetensors"), device="cpu")
        weights = {k[len("ema_model."):].replace("_orig_mod.", ""): v for k, v in state.items() if k.startswith("ema_model.")}
        missing, _ = model.load_state_dict(weights, strict=False)
        if missing:
            raise RuntimeError(f"IndicF5 weights are incomplete ({len(missing)} missing)")
        self.model = model.eval().to(self.device)

        if self.device == "cuda":
            # bf16 inside the transformer only: 4x faster; fp16 gives noise, bf16 breaks the FFT.
            original = self.model.transformer.forward

            def forward_bf16(*args, **kwargs):
                with torch.autocast("cuda", dtype=torch.bfloat16):
                    return original(*args, **kwargs).float()

            self.model.transformer.forward = forward_bf16

        self.ref_audio, self.ref_text, self.voice_name = self._load_reference(repo)
        self._lock = threading.Lock()

    def _load_reference(self, repo: Path) -> tuple[torch.Tensor, str, str]:
        custom_wav = settings.voices_dir / "tamil_reference.wav"
        custom_txt = settings.voices_dir / "tamil_reference.txt"
        if custom_wav.exists() and custom_txt.exists():
            path, text, name = custom_wav, custom_txt.read_text(encoding="utf-8").strip(), "team voice"
        else:
            path, text, name = repo / SAMPLE_VOICE, SAMPLE_TEXT, "AI4Bharat sample voice"
        audio, rate = sf.read(str(path), dtype="float32", always_2d=True)
        audio = audio.mean(axis=1)
        audio = audio[: int(rate * 12)]  # IndicF5 works best with a reference under ~12 s
        audio = resample(audio, rate, TARGET_RATE)
        # Same preparation as IndicF5's own code: trim silence at both ends, then add a 50 ms pause.
        # Without it, the reference's last word leaks into the start of every generated sentence.
        audio = np.concatenate([_trim_silence(audio, TARGET_RATE), np.zeros(int(0.05 * TARGET_RATE), "float32")])
        tensor = torch.from_numpy(audio).unsqueeze(0)
        rms = torch.sqrt(torch.mean(torch.square(tensor)))
        if rms < TARGET_RMS:
            tensor = tensor * TARGET_RMS / rms
        # IndicF5 expects the reference text to end with ". " (a clear sentence end before the new text).
        text = text.rstrip()
        text = text + " " if text.endswith(".") else text + ". "
        log.info("Tamil voice: %s", name)
        return tensor.to(self.device), text, name

    def synthesize(self, text: str) -> tuple[np.ndarray, int]:
        """Tamil text -> (float32 samples, 24000). Long text is spoken in sentence chunks."""
        ref_frames = self.ref_audio.shape[-1] // HOP_LENGTH
        ref_bytes = len(self.ref_text.encode("utf-8"))
        ref_seconds = self.ref_audio.shape[-1] / TARGET_RATE
        # Same chunk size rule as IndicF5: keep reference + chunk under ~25 s of audio.
        max_bytes = max(60, int(ref_bytes / ref_seconds * (25 - ref_seconds)))
        waves = []
        with self._lock, torch.inference_mode():
            for chunk in _chunks(text, max_bytes):
                tokens = self._to_tokens([self.ref_text + chunk])
                duration = ref_frames + int(ref_frames / ref_bytes * len(chunk.encode("utf-8")))
                generated, _ = self.model.sample(
                    cond=self.ref_audio,
                    text=tokens,
                    duration=duration,
                    steps=settings.tamil_tts_steps,
                    cfg_strength=CFG_STRENGTH,
                    sway_sampling_coef=SWAY_SAMPLING,
                )
                mel = generated.to(torch.float32)[:, ref_frames:, :].permute(0, 2, 1)
                waves.append(self.vocoder.decode(mel).squeeze().cpu().numpy())
        return _cross_fade(waves), TARGET_RATE


def _trim_silence(audio: np.ndarray, rate: int, threshold_db: float = -42.0) -> np.ndarray:
    """Cut leading/trailing parts quieter than `threshold_db` (1 ms steps, like pydub in IndicF5)."""
    step = max(1, rate // 1000)
    usable = len(audio) // step * step
    if usable == 0:
        return audio
    rms = np.sqrt(np.mean(np.square(audio[:usable].reshape(-1, step)), axis=1)) + 1e-9
    loud = np.nonzero(20 * np.log10(rms) > threshold_db)[0]
    if len(loud) == 0:
        return audio
    return audio[loud[0] * step:(loud[-1] + 1) * step]


def _chunks(text: str, max_bytes: int) -> list[str]:
    sentences = re.split(r"(?<=[;:,.!?।])\s+", text.strip())
    chunks, current = [], ""
    for sentence in sentences:
        if current and len((current + " " + sentence).encode("utf-8")) > max_bytes:
            chunks.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        chunks.append(current)
    return chunks


def _cross_fade(waves: list[np.ndarray]) -> np.ndarray:
    if not waves:
        return np.zeros(0, dtype="float32")
    result = waves[0]
    fade = int(CROSS_FADE_SECONDS * TARGET_RATE)
    for wave in waves[1:]:
        n = min(fade, len(result), len(wave))
        if n <= 0:
            result = np.concatenate([result, wave])
            continue
        ramp = np.linspace(0, 1, n, dtype="float32")
        overlap = result[-n:] * (1 - ramp) + wave[:n] * ramp
        result = np.concatenate([result[:-n], overlap, wave[n:]])
    return result.astype("float32")
