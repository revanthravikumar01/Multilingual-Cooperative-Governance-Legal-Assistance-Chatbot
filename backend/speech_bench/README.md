# Speech benchmark (Decision 38)

These scripts compared free speech-to-text (STT) and text-to-speech (TTS) models on the kiosk laptop
(Ryzen 7 170, 16 GB RAM, RTX 3050 Laptop GPU 4 GB, Windows 11, Python 3.14) on 2026-11-26.
They are a record of the test, **not** part of the running backend.

## Results

**Tamil speech → text** (15 FLEURS Tamil clips, average 11 s each; lower error is better)

| Model | Runs on | Time per clip | Character errors | Word errors |
|---|---|---|---|---|
| Whisper Tamil small (`vasista22/whisper-tamil-small`) | CPU | 7.6 s | 2.2% | 7.4% |
| Whisper Tamil small | GPU | 1.8 s | 2.2% | 7.4% |
| Whisper Tamil small, int8 | CPU | 5.9 s | 3.5% | 12.5% |
| **IndicConformer 600M, RNNT** (`ai4bharat/indic-conformer-600m-multilingual`) | CPU | **1.0 s** | 3.0% | 15.7% |
| IndicConformer 600M, CTC | CPU | 0.55 s | 3.8% | 19.9% |

Word errors look worse than character errors for Tamil: one wrong suffix makes the whole word "wrong".

**English speech → text** (15 FLEURS English clips): Whisper small on CPU, 2.1 s per clip, 6.6% word errors.

**Tamil text → speech** (5 test sentences; clarity = character errors when IndicConformer transcribes the voice back)

| Model / setting | Runs on | Time per sentence | Clarity |
|---|---|---|---|
| Meta MMS-TTS Tamil (non-commercial licence) | CPU | ~1 s | 4.5–6.5%, misheard "கூட்டுறவுச் சங்கங்கள்" |
| IndicF5, 32 steps | CPU | 115–160 s | 5.2% (incl. the digits sentence) |
| IndicF5, 32 steps | GPU fp32 | ~16 s | 0.7% |
| **IndicF5, 16 steps, bf16 transformer** | **GPU** | **~4 s** | **1.5%** |
| IndicF5, 8 steps, bf16 transformer | GPU | ~2 s | 6.2% |
| IndicF5, fp16 autocast | GPU | — | noise (unusable) |

Digits are garbled by every voice ("34(2)" is read as "342"), so spoken text must write numbers as words.
Peak GPU memory: IndicF5 2.9 GB, Whisper small 1.1 GB.

Did not run on this laptop: faster-whisper (Smart App Control blocks the unsigned `ctranslate2.dll`)
and Indic Parler-TTS (needs `tokenizers` 0.20.3, which has no Python 3.14 wheel).

## Reproducing

Use a **separate** virtual environment, not `backend/.venv`. The AI4Bharat models are gated: accept their terms on
huggingface.co and log in once with
`python -c "from huggingface_hub import login; login()"` (Smart App Control blocks `hf.exe`).

IndicF5 setup notes for Windows + Python 3.14:
- `pip install --no-deps git+https://github.com/ai4bharat/IndicF5.git` (it pins numpy 1.26, which has no 3.14 wheel),
  then its other dependencies, plus `audioop-lts` and `wandb`.
- `stubs.py` replaces the training-only `datasets` import, because Smart App Control blocks pyarrow's dataset DLL.
- `bench_tts_f5.py` reads WAV with soundfile (torchaudio 2.9+ needs FFmpeg) and loads the model without
  `torch.compile` (no C++ compiler on the laptop).
- GPU PyTorch: `torch 2.14.1+cu130` (no CUDA build of 2.15 for Python 3.14). In a long folder path, pip fails on
  Windows' path limit; install from a short path such as `C:\speech`.

```
python fetch_fleurs.py audio 15                      # 15 Tamil + 15 English clips with transcripts
python bench_stt_ic.py audio/ta                      # IndicConformer
python bench_stt.py vasista22/whisper-tamil-small ta audio/ta --gen-config openai/whisper-small [--device cuda]
python bench_stt.py openai/whisper-small en audio/en
python bench_tts_f5.py tts_f5 --nfe 16 --device cuda --dtype bfloat16
```

`results/` holds the raw output of each run (every transcript and timing).
