"""Speech-to-text benchmark: speed and accuracy on CPU.

Usage: python bench_stt.py <model_id> <lang ta|en> <audio_dir> [--limit N]
Accuracy: WER (word error rate) and CER (character error rate) after light normalisation.
Lower is better. For Tamil, CER is more meaningful: one wrong suffix makes the whole word "wrong".
"""
import argparse
import json
import re
import time
import unicodedata
from pathlib import Path

import jiwer
import numpy as np
import soundfile as sf
import torch

torch.set_num_threads(8)


def normalise(text: str) -> str:
    text = unicodedata.normalize("NFC", text.lower())
    # Drop punctuation but keep letters, digits and Tamil vowel signs (category M).
    text = "".join(ch if unicodedata.category(ch)[0] in "LNM" or ch.isspace() else " " for ch in text)
    return re.sub(r"\s+", " ", text).strip()


def load_audio(path: Path) -> np.ndarray:
    audio, sr = sf.read(path, dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    if sr != 16000:
        # Simple linear resample: good enough for a benchmark.
        n = int(len(audio) * 16000 / sr)
        audio = np.interp(np.linspace(0, len(audio), n, endpoint=False), np.arange(len(audio)), audio).astype("float32")
    return audio


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("model")
    ap.add_argument("lang")
    ap.add_argument("audio_dir")
    ap.add_argument("--limit", type=int, default=15)
    ap.add_argument("--refs", default=None, help="references.json (default: <audio_dir>/../references.json)")
    ap.add_argument("--out", default=None)
    ap.add_argument("--gen-config", default=None, help="base model to borrow generation_config from")
    ap.add_argument("--int8", action="store_true", help="dynamic int8 quantisation for CPU")
    ap.add_argument("--device", default="cpu")
    args = ap.parse_args()

    from transformers import WhisperForConditionalGeneration, WhisperProcessor

    audio_dir = Path(args.audio_dir)
    refs_path = Path(args.refs) if args.refs else audio_dir.parent / "references.json"
    refs = json.loads(refs_path.read_text(encoding="utf-8"))

    t0 = time.perf_counter()
    processor = WhisperProcessor.from_pretrained(args.model, local_files_only=True)
    model = WhisperForConditionalGeneration.from_pretrained(args.model, local_files_only=True, dtype=torch.float32)
    model.eval()
    if args.gen_config:
        # Older fine-tunes ship an outdated generation config; borrow the base model's
        # (it holds the language/task token tables that `language=` needs).
        from transformers import GenerationConfig

        model.generation_config = GenerationConfig.from_pretrained(args.gen_config, local_files_only=True)
    if args.int8:
        # Store linear-layer weights as 8-bit integers: smaller and usually faster on CPU.
        model = torch.ao.quantization.quantize_dynamic(model, {torch.nn.Linear}, dtype=torch.qint8)
    model.to(args.device)
    load_s = time.perf_counter() - t0
    print(f"{args.model}: loaded in {load_s:.1f} s", flush=True)

    files = sorted(audio_dir.glob("*.wav"))[: args.limit]
    hyps, gold, rows = [], [], []
    total_audio = total_time = 0.0
    for i, f in enumerate(files):
        audio = load_audio(f)
        dur = len(audio) / 16000
        feats = processor(audio, sampling_rate=16000, return_tensors="pt").input_features
        t = time.perf_counter()
        with torch.inference_mode():
            ids = model.generate(feats.to(args.device), language=args.lang, task="transcribe", max_new_tokens=220)
        took = time.perf_counter() - t
        text = processor.batch_decode(ids, skip_special_tokens=True)[0].strip()
        key = f"{audio_dir.name}/{f.name}"
        ref = refs.get(key, {}).get("text", "")
        if i > 0:  # first clip includes warm-up; leave it out of the speed figure
            total_audio += dur
            total_time += took
        rows.append({"file": f.name, "seconds_audio": round(dur, 1), "seconds_taken": round(took, 2), "hyp": text, "ref": ref})
        if ref:
            hyps.append(normalise(text))
            gold.append(normalise(ref))
        print(f"[{i + 1}/{len(files)}] {dur:4.1f}s audio -> {took:4.1f}s | {text[:90]}", flush=True)

    wer = jiwer.wer(gold, hyps) if gold else None
    cer = jiwer.cer(gold, hyps) if gold else None
    summary = {
        "model": args.model,
        "lang": args.lang,
        "clips": len(files),
        "load_seconds": round(load_s, 1),
        "avg_audio_seconds": round(total_audio / max(1, len(files) - 1), 1),
        "avg_seconds_per_clip": round(total_time / max(1, len(files) - 1), 2),
        "real_time_factor": round(total_time / total_audio, 2) if total_audio else None,
        "WER": round(wer, 3) if wer is not None else None,
        "CER": round(cer, 3) if cer is not None else None,
    }
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    out = Path(args.out or f"results/stt_{args.model.replace('/', '__')}_{args.lang}.json")
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
