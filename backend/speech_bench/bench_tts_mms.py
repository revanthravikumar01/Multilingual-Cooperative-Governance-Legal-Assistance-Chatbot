"""Text-to-speech benchmark for Meta MMS-TTS (VITS) on CPU.

Usage: python bench_tts_mms.py <out_dir>
Writes one WAV per sentence so you can listen, and a JSON with timings.
"""
import json
import sys
import time
from pathlib import Path

import numpy as np
import soundfile as sf
import torch

torch.set_num_threads(8)

SENTENCES = {
    "ta": [
        "உங்கள் கேள்விக்கான பதில் தமிழ்நாடு கூட்டுறவுச் சங்கங்கள் சட்டத்தில் உள்ளது.",
        "மேலும் விவரங்களுக்கு, திரையில் காட்டப்பட்டுள்ள மேற்கோள்களைப் பார்க்கவும்.",
        "மன்னிக்கவும், இந்தக் கேள்விக்கு அறிவுத் தளத்தில் போதுமான தகவல் இல்லை.",
        "இது பிரிவு முப்பத்து நான்கு, உட்பிரிவு இரண்டில் கூறப்பட்டுள்ளது.",
        "இது பிரிவு 34(2) இல் கூறப்பட்டுள்ளது.",  # digits: does the voice read them?
    ],
    "en": [
        "The answer to your question is in the Tamil Nadu Co-operative Societies Act.",
        "For more details, please see the citations shown on the screen.",
        "Sorry, the knowledge base does not have enough information to answer this question.",
        "This is stated in section thirty four, sub-section two.",
        "This is stated in Section 34(2).",
    ],
}
MODELS = {"ta": "facebook/mms-tts-tam", "en": "facebook/mms-tts-eng"}


def main():
    from transformers import AutoTokenizer, VitsModel

    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    results = []
    for lang, model_id in MODELS.items():
        t0 = time.perf_counter()
        tok = AutoTokenizer.from_pretrained(model_id, local_files_only=True)
        model = VitsModel.from_pretrained(model_id, local_files_only=True).eval()
        load_s = time.perf_counter() - t0
        print(f"{model_id}: loaded in {load_s:.1f} s", flush=True)
        for i, text in enumerate(SENTENCES[lang]):
            inputs = tok(text, return_tensors="pt")
            torch.manual_seed(0)
            t = time.perf_counter()
            with torch.inference_mode():
                wav = model(**inputs).waveform[0].numpy()
            took = time.perf_counter() - t
            sr = model.config.sampling_rate
            dur = len(wav) / sr
            name = f"mms_{lang}_{i + 1}.wav"
            sf.write(out / name, (wav / max(1e-6, np.abs(wav).max()) * 0.9).astype("float32"), sr, subtype="PCM_16")
            results.append({"model": model_id, "lang": lang, "file": name, "text": text, "chars": len(text),
                            "seconds_audio": round(dur, 1), "seconds_taken": round(took, 2), "sample_rate": sr,
                            "load_seconds": round(load_s, 1)})
            print(f"  {name}: {len(text)} chars -> {dur:.1f}s audio in {took:.2f}s", flush=True)
    (out / "tts_results.json").write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
