"""IndicConformer 600M speech-to-text benchmark (ONNX on CPU), same metrics as bench_stt.py.

Usage: python bench_stt_ic.py <audio_dir> [--decoding ctc rnnt] [--limit N] [--tag name]
"""
import argparse
import importlib.util
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import jiwer  # noqa: E402
import torch  # noqa: E402
from huggingface_hub import snapshot_download  # noqa: E402

from bench_stt import load_audio, normalise  # noqa: E402

torch.set_num_threads(8)


def load_model():
    repo = snapshot_download("ai4bharat/indic-conformer-600m-multilingual", local_files_only=True)
    spec = importlib.util.spec_from_file_location("ic_model_onnx", Path(repo) / "model_onnx.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.IndicASRModel(mod.IndicASRConfig(ts_folder=repo, FRAME_DURATION_MS=0.08))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("audio_dir")
    ap.add_argument("--decoding", nargs="+", default=["ctc", "rnnt"])
    ap.add_argument("--limit", type=int, default=15)
    ap.add_argument("--tag", default="fleurs")
    args = ap.parse_args()

    audio_dir = Path(args.audio_dir)
    refs = json.loads((audio_dir.parent / "references.json").read_text(encoding="utf-8"))

    t0 = time.perf_counter()
    model = load_model()
    load_s = time.perf_counter() - t0
    print(f"IndicConformer loaded in {load_s:.1f} s", flush=True)

    files = sorted(audio_dir.glob("*.wav"))[: args.limit]
    for decoding in args.decoding:
        hyps, gold, rows = [], [], []
        total_audio = total_time = 0.0
        for i, f in enumerate(files):
            audio = load_audio(f)
            dur = len(audio) / 16000
            wav = torch.from_numpy(audio).unsqueeze(0)
            t = time.perf_counter()
            with torch.inference_mode():
                text = model(wav, "ta", decoding)
            took = time.perf_counter() - t
            ref = refs.get(f"{audio_dir.name}/{f.name}", {}).get("text", "")
            if i > 0:
                total_audio += dur
                total_time += took
            rows.append({"file": f.name, "seconds_audio": round(dur, 1), "seconds_taken": round(took, 2), "hyp": text, "ref": ref})
            if ref:
                hyps.append(normalise(text))
                gold.append(normalise(ref))
            print(f"[{decoding} {i + 1}/{len(files)}] {dur:4.1f}s -> {took:4.2f}s | {text[:80]}", flush=True)
        summary = {
            "model": f"indic-conformer-600m ({decoding})",
            "lang": "ta",
            "clips": len(files),
            "load_seconds": round(load_s, 1),
            "avg_seconds_per_clip": round(total_time / max(1, len(files) - 1), 2),
            "real_time_factor": round(total_time / total_audio, 2) if total_audio else None,
            "WER": round(jiwer.wer(gold, hyps), 3) if gold else None,
            "CER": round(jiwer.cer(gold, hyps), 3) if gold else None,
        }
        print(json.dumps(summary, ensure_ascii=False), flush=True)
        out = Path(f"results/stt_indicconformer_{decoding}_{args.tag}.json")
        out.parent.mkdir(exist_ok=True)
        out.write_text(json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
