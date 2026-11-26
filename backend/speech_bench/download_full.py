"""Download whole model repos with automatic resume. Usage: python download_full.py repo_id [...]"""
import os, sys, time
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "30")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
from huggingface_hub import snapshot_download  # noqa: E402

for repo in sys.argv[1:]:
    for attempt in range(1, 81):
        try:
            path = snapshot_download(repo, ignore_patterns=["*.pyc", "f5_tts/train/*", "f5_tts/eval/*"])
            print(f"Done {repo}: {path}", flush=True)
            break
        except Exception as exc:
            print(f"{repo} attempt {attempt} interrupted ({type(exc).__name__}: {str(exc)[:120]})", flush=True)
            time.sleep(5)
