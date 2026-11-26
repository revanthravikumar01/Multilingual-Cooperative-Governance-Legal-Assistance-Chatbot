"""IndicF5 text-to-speech benchmark on CPU, loading the model without torch.compile.

Usage: python bench_tts_f5.py <out_dir> [--nfe 32 16 ...]
Writes one WAV per sentence (24 kHz) plus results JSON.
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import stubs  # noqa: E402

stubs.install()

import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402
import torch  # noqa: E402
from huggingface_hub import snapshot_download  # noqa: E402
from safetensors.torch import load_file  # noqa: E402

torch.set_num_threads(8)

import torchaudio  # noqa: E402


def _load_with_soundfile(path, *args, **kwargs):
    # torchaudio 2.9+ needs torchcodec + FFmpeg for load(); soundfile is enough for WAV.
    data, sr = sf.read(str(path), dtype="float32", always_2d=True)
    return torch.from_numpy(data.T.copy()), sr


torchaudio.load = _load_with_soundfile

from f5_tts.infer.utils_infer import infer_process, load_model, load_vocoder, preprocess_ref_audio_text  # noqa: E402
from f5_tts.model import DiT  # noqa: E402

SENTENCES = [
    "உங்கள் கேள்விக்கான பதில் தமிழ்நாடு கூட்டுறவுச் சங்கங்கள் சட்டத்தில் உள்ளது.",
    "மேலும் விவரங்களுக்கு, திரையில் காட்டப்பட்டுள்ள மேற்கோள்களைப் பார்க்கவும்.",
    "மன்னிக்கவும், இந்தக் கேள்விக்கு அறிவுத் தளத்தில் போதுமான தகவல் இல்லை.",
    "இது பிரிவு முப்பத்து நான்கு, உட்பிரிவு இரண்டில் கூறப்பட்டுள்ளது.",
    "இது பிரிவு 34(2) இல் கூறப்பட்டுள்ளது.",
]
# AI4Bharat's own sample voice and its transcript (from the model card).
REF_AUDIO = "prompts/PAN_F_HAPPY_00001.wav"
REF_TEXT = "ਭਹੰਪੀ ਵਿੱਚ ਸਮਾਰਕਾਂ ਦੇ ਭਵਨ ਨਿਰਮਾਣ ਕਲਾ ਦੇ ਵੇਰਵੇ ਗੁੰਝਲਦਾਰ ਅਤੇ ਹੈਰਾਨ ਕਰਨ ਵਾਲੇ ਹਨ, ਜੋ ਮੈਨੂੰ ਖੁਸ਼ ਕਰਦੇ  ਹਨ।"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out_dir")
    ap.add_argument("--nfe", type=int, nargs="+", default=[32], help="denoising steps (fewer = faster, rougher)")
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    ap.add_argument("--prefix", default="f5")
    ap.add_argument("--dtype", default="float32", choices=["float32", "float16", "bfloat16"])
    args = ap.parse_args()
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    # Training/eval files were skipped on download, so point at the cached snapshot folder directly.
    repo = next((Path.home() / ".cache/huggingface/hub/models--ai4bharat--IndicF5/snapshots").iterdir())
    t0 = time.perf_counter()
    vocoder = load_vocoder(vocoder_name="vocos", is_local=False, device=args.device)
    model = load_model(
        DiT,
        dict(dim=1024, depth=22, heads=16, ff_mult=2, text_dim=512, conv_layers=4),
        mel_spec_type="vocos",
        vocab_file=str(repo / "checkpoints" / "vocab.txt"),
        device=args.device,
    )
    state = load_file(str(repo / "model.safetensors"), device=args.device)
    cleaned = {}
    for key, value in state.items():
        if not key.startswith("ema_model."):
            continue  # vocoder weights come from load_vocoder
        cleaned[key[len("ema_model."):].replace("_orig_mod.", "")] = value
    missing, unexpected = model.load_state_dict(cleaned, strict=False)
    print(f"weights: {len(cleaned)} loaded, {len(missing)} missing, {len(unexpected)} unexpected", flush=True)
    if missing:
        print("  missing e.g.", missing[:3], flush=True)
    model.eval()
    if args.dtype != "float32":
        # Reduced precision only inside the transformer; mel spectrogram (FFT) and vocoder stay float32.
        low = getattr(torch, args.dtype)
        original_forward = model.transformer.forward

        def forward_low_precision(*a, **k):
            with torch.autocast(args.device, dtype=low):
                return original_forward(*a, **k).float()

        model.transformer.forward = forward_low_precision
    load_s = time.perf_counter() - t0
    print(f"loaded in {load_s:.1f} s", flush=True)

    ref_audio, ref_text = preprocess_ref_audio_text(str(repo / REF_AUDIO), REF_TEXT, show_info=lambda *a: None)

    results = []
    for nfe in args.nfe:
        for i, text in enumerate(SENTENCES):
            t = time.perf_counter()
            with torch.inference_mode():
                wav, sr, _ = infer_process(ref_audio, ref_text, text, model, vocoder, mel_spec_type="vocos",
                                           nfe_step=nfe, device=args.device, show_info=lambda *a: None)
            took = time.perf_counter() - t
            wav = np.asarray(wav, dtype="float32")
            dur = len(wav) / sr
            name = f"{args.prefix}_nfe{nfe}_ta_{i + 1}.wav"
            sf.write(out / name, wav / max(1e-6, np.abs(wav).max()) * 0.9, sr, subtype="PCM_16")
            results.append({"nfe": nfe, "file": name, "text": text, "chars": len(text), "seconds_audio": round(dur, 1),
                            "seconds_taken": round(took, 2), "load_seconds": round(load_s, 1)})
            print(f"  nfe={nfe} {name}: {len(text)} chars -> {dur:.1f}s audio in {took:.1f}s", flush=True)
    (out / f"{args.prefix}_results.json").write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
