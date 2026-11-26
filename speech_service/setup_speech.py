"""One-time setup of the CIVI speech service environment (Windows, Python 3.14, NVIDIA GPU).

Run from the repository folder with any Python 3.14:
    py speech_service\\setup_speech.py

It is safe to run again: finished steps are skipped and downloads resume where they stopped.
Steps:
  1. Create speech_service\\.venv (separate from backend\\.venv: different PyTorch build).
  2. Download the GPU build of PyTorch (~2 GB, resumable, checksum-verified) and unpack it.
     pip can't install it here because some of its C++ header files have paths longer than Windows
     allows; those headers are only needed to compile extensions, so they are skipped.
  3. Install the pinned packages (requirements.txt), torchaudio and AI4Bharat's IndicF5 code.
  4. Download the models (~4.5 GB in total; resumable). The AI4Bharat models are gated: accept their
     terms on huggingface.co and log in first with
       backend\\.venv\\Scripts\\python.exe -c "from huggingface_hub import login; login()"
"""

import hashlib
import os
import subprocess
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
VENV = HERE / ".venv"
CACHE = HERE / ".cache"
VENV_PYTHON = VENV / "Scripts" / "python.exe"
SITE_PACKAGES = VENV / "Lib" / "site-packages"

TORCH_VERSION = "2.14.1+cu130"
TORCH_WHEEL = f"torch-{TORCH_VERSION}-cp314-cp314-win_amd64.whl"
TORCH_URL = "https://download.pytorch.org/whl/cu130/torch-2.14.1%2Bcu130-cp314-cp314-win_amd64.whl"
TORCH_SHA256 = "e25757e423be3c107a36d7495fa5aeb021b9ab506457cd7c7e068505f0283ae0"
TORCHAUDIO = "torchaudio==2.11.1"
INDICF5 = "f5_tts @ git+https://github.com/ai4bharat/IndicF5.git@13f7c4d627cc10111aea8fe9c0039462cacacdc7"

MODELS = [
    ("ai4bharat/indic-conformer-600m-multilingual", None),
    ("ai4bharat/IndicF5", ["*.json", "*.txt", "*.safetensors", "prompts/*"]),
    ("openai/whisper-small", ["*.json", "*.txt", "*.safetensors"]),
    ("charactr/vocos-mel-24khz", ["config.yaml", "pytorch_model.bin"]),
]


def step(text: str) -> None:
    print(f"\n=== {text}", flush=True)


def run(*args: str) -> None:
    subprocess.run(list(args), check=True)


def create_venv() -> None:
    step("1. Python environment")
    if VENV_PYTHON.exists():
        print("exists:", VENV)
        return
    base = getattr(sys, "_base_executable", sys.executable)
    run(base, "-m", "venv", str(VENV))


def download_torch() -> Path:
    step("2. GPU PyTorch download (~2 GB, resumes if interrupted)")
    CACHE.mkdir(exist_ok=True)
    target = CACHE / TORCH_WHEEL
    for attempt in range(1, 200):
        have = target.stat().st_size if target.exists() else 0
        request = urllib.request.Request(TORCH_URL, headers={"Range": f"bytes={have}-"} if have else {})
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                if response.status == 416:  # already complete
                    break
                total = have + int(response.headers.get("Content-Length", 0))
                mode = "ab" if response.status == 206 else "wb"
                with open(target, mode) as out:
                    while chunk := response.read(1 << 20):
                        out.write(chunk)
                        print(f"\r  {out.tell() / 1e6:,.0f} / {total / 1e6:,.0f} MB", end="", flush=True)
            print()
            break
        except urllib.error.HTTPError as exc:
            if exc.code == 416:
                break
            print(f"\n  attempt {attempt}: HTTP {exc.code}; retrying in 5 s")
        except OSError as exc:
            print(f"\n  attempt {attempt}: {type(exc).__name__}; resuming in 5 s")
        time.sleep(5)

    print("  checking file...", flush=True)
    digest = hashlib.sha256()
    with open(target, "rb") as f:
        while block := f.read(1 << 22):
            digest.update(block)
    if digest.hexdigest() != TORCH_SHA256:
        target.unlink()
        sys.exit("The PyTorch download was corrupted and has been deleted. Run this script again.")
    return target


def unpack_torch(wheel: Path) -> None:
    if (SITE_PACKAGES / "torch" / "lib").exists() and any(SITE_PACKAGES.glob("torch-*.dist-info")):
        print("  PyTorch already unpacked")
        return
    print("  unpacking (skipping C++ headers)...", flush=True)
    skipped = 0
    with zipfile.ZipFile(wheel) as archive:
        for member in archive.infolist():
            name = member.filename
            if name.startswith(("torch/include/", "torch/share/cmake/")) or "/licenses/" in name:
                skipped += 1
                continue
            try:
                archive.extract(member, SITE_PACKAGES)
            except OSError:  # a path still too long for Windows: not needed at run time
                skipped += 1
    print(f"  done ({skipped} build-only files skipped)")


def install_packages() -> None:
    step("3. Packages")
    pip = [str(VENV_PYTHON), "-m", "pip", "install", "--disable-pip-version-check"]
    run(*pip, "-r", str(HERE / "requirements.txt"))
    # torchaudio and IndicF5 pin old versions of torch/numpy that don't exist for Python 3.14;
    # their code works with the versions above, so they are installed without dependencies.
    run(*pip, "--no-deps", TORCHAUDIO, INDICF5)


def download_models() -> None:
    step("4. Models (~4.5 GB, resumes if interrupted)")
    code = f"""
import os, time
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "30")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
from huggingface_hub import snapshot_download
for repo, patterns in {MODELS!r}:
    for attempt in range(1, 80):
        try:
            print("  ", repo, "->", snapshot_download(repo, allow_patterns=patterns), flush=True)
            break
        except Exception as exc:
            if "401" in str(exc) or "403" in str(exc) or "gated" in str(exc).lower():
                raise SystemExit(f"No access to {{repo}}. Accept its terms on huggingface.co and log in first.")
            print(f"   {{repo}} attempt {{attempt}} interrupted ({{type(exc).__name__}}); resuming", flush=True)
            time.sleep(5)
"""
    run(str(VENV_PYTHON), "-c", code)


def check() -> None:
    step("5. Check")
    run(str(VENV_PYTHON), "-c", (
        "import torch, onnxruntime, transformers;"
        "print('  torch', torch.__version__, '| GPU:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'none');"
        "import f5_tts, vocos; print('  IndicF5 code ok')"
    ))
    print("\nSetup complete. Start the service with:")
    print(r"  speech_service\.venv\Scripts\python.exe -m uvicorn civi_speech.main:app --app-dir speech_service --host 127.0.0.1 --port 8001")


if __name__ == "__main__":
    if sys.version_info[:2] != (3, 14) or os.name != "nt":
        sys.exit("This setup is for Windows with Python 3.14.")
    create_venv()
    unpack_torch(download_torch())
    install_packages()
    download_models()
    check()
