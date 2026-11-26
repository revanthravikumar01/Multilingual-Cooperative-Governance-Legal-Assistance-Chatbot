# CIVI speech service (Phase 4, Decision 38)

A small local server that turns speech into text and text into speech, **for free, on the kiosk laptop**.
The main backend (`backend/`) calls it; Flutter and the ESP32 never talk to it directly.

| Job | Engine | Runs on | Speed on the kiosk laptop |
|---|---|---|---|
| Tamil speech → text | AI4Bharat IndicConformer 600M (MIT) | CPU | ~1 s per question |
| English speech → text | OpenAI Whisper small (Apache-2.0) | CPU | ~2 s per question |
| Tamil text → speech | AI4Bharat IndicF5 (MIT) | NVIDIA GPU (bf16, 16 steps) | ~4 s per sentence |
| English text → speech | Windows built-in voice (Microsoft Zira) | CPU | ~1 s |

Benchmarks: `backend/speech_bench/README.md`.

It has **its own Python environment** (`speech_service/.venv`), separate from `backend/.venv`, because it
needs the GPU build of PyTorch and IndicF5's dependencies.

## Requirements

- Windows 11, Python 3.14, an NVIDIA GPU with ≥ 4 GB memory (RTX 3050 tested). Without a GPU, Tamil speech
  takes 1–2 minutes per sentence; use a paid voice (e.g. Sarvam) instead.
- ~9 GB of disk: PyTorch 2 GB (+ unpacked), models ~4.5 GB.
- A Hugging Face account that has accepted the terms of
  [IndicConformer](https://huggingface.co/ai4bharat/indic-conformer-600m-multilingual) and
  [IndicF5](https://huggingface.co/ai4bharat/IndicF5), logged in once on this laptop:

  ```powershell
  backend\.venv\Scripts\python.exe -c "from huggingface_hub import login; login()"
  ```

## Setup (once)

From the repository folder:

```powershell
py speech_service\setup_speech.py
```

It creates the environment, downloads PyTorch and the models (resuming if the internet drops), and checks
the GPU. Run it again if it stops halfway; finished steps are skipped.

## Run

```powershell
speech_service\.venv\Scripts\python.exe -m uvicorn civi_speech.main:app --app-dir speech_service --host 127.0.0.1 --port 8001
```

Models load in the background (about a minute). Check `http://127.0.0.1:8001/health` until every engine
says `ready`. Keep `--host 127.0.0.1`: the service has no login and must only be reachable from this laptop.

## Try it

With the backend also running (port 8000), send a recorded question and hear the answer:

```powershell
cd backend
.\.venv\Scripts\python.exe -m app.scripts.voice_demo C:\path\to\question.wav --language ta
```

## Tamil voice

IndicF5 copies the voice of a short reference recording. By default it uses AI4Bharat's sample voice.
To use a team member's voice **with their consent**, see [voices/README.md](voices/README.md).

## Settings (optional environment variables)

| Variable | Default | Meaning |
|---|---|---|
| `CIVI_TAMIL_STT_DECODING` | `rnnt` | `ctc` is ~2× faster, slightly less accurate |
| `CIVI_TAMIL_TTS_STEPS` | `16` | `32` = clearer Tamil voice, 2× slower; `8` = faster, rougher |
| `CIVI_TAMIL_TTS_DEVICE` | `auto` | `cuda` or `cpu` |
| `CIVI_ENGLISH_VOICE` | `Microsoft Zira Desktop` | or `Microsoft David Desktop` |
| `CIVI_ENGLISH_VOICE_RATE` | `0` | −10 (slow) … 10 (fast) |
| `CIVI_MIN_SPEECH_CONTRAST` | `1.4` | recordings without speech-like loud/quiet contrast count as "nothing said" (speech ≈ 1.8–5, noise ≈ 1.05) |
| `HF_HUB_OFFLINE` | `1` | models load from the local cache without update checks; set `0` to allow downloads |

## Windows notes

- Smart App Control blocks some unsigned files (for example `faster-whisper`), which is why these engines
  were chosen. If a new package fails with "An Application Control policy has blocked this file", that
  package can't be used while Smart App Control is on.
- The PyTorch download is unpacked by the setup script instead of pip, because some of its C++ header files
  have paths longer than Windows allows. Those headers are only needed to compile code, not to run it.

## Tests

```powershell
speech_service\.venv\Scripts\python.exe -m pip install pytest==9.0.1
speech_service\.venv\Scripts\python.exe -m pytest speech_service\tests -q
```

These check the audio logic (silence/noise detection, trimming, sentence splitting) without loading models.
The backend's tests (`backend/tests/test_voice.py`) cover the voice endpoints with a fake speech service.
